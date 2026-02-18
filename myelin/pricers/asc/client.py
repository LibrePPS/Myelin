from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from myelin.input.claim import Claim
from myelin.input.claim import LineItem
from myelin.pricers.asc.data_loader import AscReferenceData, AscRefData, CodePairEntry
from myelin.pricers.opsf import OPSFProvider
from myelin.helpers.utils import ReturnCode


# Payment indicator denial/rejection rules per CMS §60.3
# Indicators that result in denial (no payment)
DENY_INDICATORS = frozenset({"C5", "M6", "U5", "X5", "E5", "Y5"})
# Indicators that result in denial as packaged (no separate payment)
DENY_PACKAGED_INDICATORS = frozenset({"L1", "NI", "S1"})
# Indicators returned as unprocessable
UNPROCESSABLE_INDICATORS = frozenset({"D5", "B5"})
# Combined set for quick lookup
NO_PAYMENT_INDICATORS = (
    DENY_INDICATORS | DENY_PACKAGED_INDICATORS | UNPROCESSABLE_INDICATORS
)

# Modifier constants
MOD_TERMINATED_PRE_ANESTHESIA = "73"  # Terminated before anesthesia (50% pay)
MOD_TERMINATED_POST_ANESTHESIA = "74"  # Terminated after anesthesia (100% pay)
MOD_REDUCED_PROCEDURE = "52"  # Reduced/discontinued procedure (50% pay)
MOD_DEVICE_NO_COST = "FB"  # Device furnished without cost / full credit
MOD_DEVICE_PARTIAL_CREDIT = "FC"  # Device with partial credit (≥50%)


class AscLineOutput(BaseModel):
    line_number: int = 0
    hcpcs: str = ""
    payment_indicator: str = ""
    payment_rate: float = 0.0
    wage_index: float = 0.0
    adjusted_rate: float = 0.0
    device_offset_amount: float = 0.0
    device_credit: bool = False
    # Code pair (pass-through device) fields
    code_pair_offset: float = 0.0  # Offset from code pair multiplier
    code_pair_device: str = ""  # Device HCPCS that triggered the code pair offset
    details: str = ""
    status: str = ""  # "payable", "denied", "unprocessable", or "packaged"
    status_reason: str = ""  # Reason for denial/rejection
    subject_to_discount: bool = False
    discount_applied: bool = False  # True if 50% discount was applied


class AscOutput(BaseModel):
    cbsa: str = ""
    wage_index: float = 0.0
    lines: List[AscLineOutput] = Field(default_factory=list)
    total_payment: float = 0.0
    error: Optional[ReturnCode] = None
    message: Optional[str] = None

    def get_payment(self) -> float:
        return self.total_payment


class AscClient:
    def __init__(self, data_dir: str, logger=None):
        self.data_loader = AscReferenceData(data_dir)
        self.logger = logger

    def _get_code_pair_offset(
        self,
        procedure_hcpcs: str,
        device_hcpcs: str,
        code_pairs: Dict[Tuple[str, str], List[CodePairEntry]],
        claim_date: datetime,
    ) -> Tuple[float, str]:
        """
        Look up the code pair offset for a procedure/device combination.

        Per CMS 40.7: When a pass-through device is billed with a procedure,
        the device offset is calculated using the procedure percent multiplier.

        Args:
            procedure_hcpcs: The procedure HCPCS code
            device_hcpcs: The device HCPCS code from the claim
            code_pairs: The code pair reference data
            claim_date: The claim thru date for date range validation

        Returns:
            Tuple of (offset_amount, device_hcpcs) - returns (0.0, "") if no match
        """
        key = (device_hcpcs, procedure_hcpcs)
        entries = code_pairs.get(key, [])

        if not entries:
            return 0.0, ""

        # Find the entry that is valid for the claim date
        for entry in entries:
            effective = entry.get("effective_date", "")
            end = entry.get("end_date", "")

            # Parse dates if available
            try:
                eff_date = datetime.strptime(effective, "%Y%m%d") if effective else None
                end_date = datetime.strptime(end, "%Y%m%d") if end else None

                # Check if claim date falls within the effective date range
                if eff_date and end_date:
                    if not (eff_date <= claim_date <= end_date):
                        continue
                elif eff_date and claim_date < eff_date:
                    continue
                elif end_date and claim_date > end_date:
                    continue
            except ValueError:
                # If date parsing fails, skip this entry
                continue

            # Get the percent multiplier
            multiplier = entry.get("percent_multiplier", 0.0)

            # The offset is the multiplier applied to the device payment
            # This is typically used to reduce the procedure payment when a device is included
            return multiplier, device_hcpcs

        # No valid entry found for this date
        return 0.0, ""

    def _find_code_pair_devices(
        self,
        claim_lines: List[LineItem],
    ) -> Dict[str, List[Tuple[int, LineItem]]]:
        """
        Find all device codes on the claim that are in the code pair file.

        Returns a dict mapping device_hcpcs to list of (line_index, line_item) tuples.
        Only devices that exist in the code_pairs reference data are returned.
        """
        device_lines: Dict[str, List[Tuple[int, LineItem]]] = {}

        for idx, line in enumerate(claim_lines):
            hcpcs = line.hcpcs.upper().strip() if line.hcpcs else ""
            if hcpcs.startswith("C"):  # Device codes typically start with C
                if hcpcs not in device_lines:
                    device_lines[hcpcs] = []
                device_lines[hcpcs].append((idx, line))

        return device_lines

    def process(
        self, claim: Claim, opsf_provider: Optional[OPSFProvider] = None, **kwargs
    ) -> AscOutput:
        output = AscOutput()
        # 1. Validation
        # Adjusted logic: We need either OPSF Provider OR a direct CBSA in additional_data.
        # Fail if BOTH are missing.
        has_provider = opsf_provider is not None
        has_cbsa_override = "cbsa" in claim.additional_data

        if not has_provider and not has_cbsa_override:
            output.error = ReturnCode(
                code="ASC01",
                description="Missing OPSF Provider or CBSA",
                explanation="ASC pricing requires OPSF provider data for Wage Index lookup.",
            )
            return output

        # Basic eligibility checks (Bill Type 83 for ASC etc - usually done before calling, but good to check)
        # Assuming caller filters.

        # 2. Get Reference Data
        if claim.thru_date is None:
            output.error = ReturnCode(
                code="ASC03",
                description="Missing Thru Date",
                explanation="ASC pricing requires thru date for reference data lookup.",
            )
            return output
        try:
            ref_data = self.data_loader.get_data(claim.thru_date)
        except FileNotFoundError:
            output.error = ReturnCode(
                code="ASC02",
                description="Data Not Found",
                explanation=f"No ASC reference data found for date {claim.thru_date}",
            )
            return output
        except Exception as e:
            if self.logger:
                self.logger.error(f"ASC Data Load Error: {e}")
            output.error = ReturnCode(
                code="ASC99", description="System Error", explanation=str(e)
            )
            return output

        # 3. Determine Wage Index
        # Safe access to provider fields
        provider_wi = opsf_provider.cbsa_wage_index_location if opsf_provider else None
        provider_geo = (
            opsf_provider.cbsa_actual_geographic_location if opsf_provider else None
        )

        cbsa = (
            claim.additional_data.get(
                "cbsa", None
            )  # if CBSA explicitly provided use it
            or provider_wi
            or provider_geo
            or "0"
        )
        wage_index = ref_data["wage_indices"].get(cbsa, None)
        if wage_index is None:
            output.message = f"Wage Index not found for CBSA {cbsa}, it will default to 1.0. Please pass a valid CBSA in additional_data object and reprocess if desired."
            wage_index = 1.0

        output.cbsa = cbsa
        output.wage_index = wage_index

        # 4. Line Item Calculation
        calculated_lines: List[AscLineOutput] = []

        # 4b. Identify code pair devices on the claim
        # Per CMS 40.7: When a pass-through device is billed with a procedure,
        # the procedure payment is reduced by the device's percent multiplier.
        # Only apply to the FIRST matching device/procedure pair per claim.
        code_pairs = ref_data.get("code_pairs", {})

        # Find all device codes on the claim that are in the code_pairs reference.
        # Per CMS §40.7: "If there is more than 1 unit of a pass-through device on
        # the claim, the contractor should take an offset for each code pair. No code
        # pair should be offset more than once and the number of code pairs receiving
        # an offset should be no more than the units of a pass-through device."
        # Track available units per device HCPCS (sum across lines for same device).
        device_available_units: Dict[str, int] = {}
        for line in claim.lines:
            hcpcs = line.hcpcs.upper().strip() if line.hcpcs else ""
            if hcpcs.startswith("C"):
                # Check if this device exists in any code pair key
                if any(k[0] == hcpcs for k in code_pairs.keys()):
                    line_units = max(1, int(line.units)) if line.units >= 1 else 1
                    device_available_units[hcpcs] = (
                        device_available_units.get(hcpcs, 0) + line_units
                    )

        for idx, line in enumerate(claim.lines):
            line_out = self._process_line(
                line,
                idx,
                ref_data,
                wage_index,
                code_pairs,
                device_available_units,
                claim.thru_date,
            )
            calculated_lines.append(line_out)

        # 5. Final Summation
        # Calculate total payment applying discount logic to units > 1
        total = 0.0

        # Per CMS §40.5: "In determining the ranking of procedures for application of
        # the multiple procedure reduction, contractors shall use the lower of the
        # billed charge or the ASC payment amount."
        # Per CMS §40: "Medicare contractors calculate payment for each separately
        # payable procedure and service based on the lower of 80 percent of actual
        # charges or the ASC payment rate." (charge comparison at line-item level)

        line_map = {idx: line for idx, line in enumerate(claim.lines)}

        # Helper: effective rate is the lower of adjusted_rate vs billed charges (per unit)
        def _effective_rate(line_out: AscLineOutput) -> float:
            line_item = line_map[line_out.line_number - 1]
            charges = line_item.charges if line_item.charges > 0 else float("inf")
            unit_count = line_item.units if line_item.units >= 1 else 1
            charge_per_unit = charges / unit_count
            return min(line_out.adjusted_rate, charge_per_unit)

        # Separate lines into "Subject to Discount" and "Not Subject"
        discount_lines = [
            g for g in calculated_lines if g.subject_to_discount and g.adjusted_rate > 0
        ]
        no_discount_lines = [
            g
            for g in calculated_lines
            if not g.subject_to_discount or g.adjusted_rate <= 0
        ]

        # Sort discountable lines by effective rate descending (lower of charge vs rate)
        discount_lines.sort(key=lambda x: _effective_rate(x), reverse=True)

        # Apply discount: first unit of first procedure = 100%, all others = 50%
        for mpr_idx, mpr_line in enumerate(discount_lines):
            units = line_map[mpr_line.line_number - 1].units
            if units < 1:
                units = 1
            eff_rate = _effective_rate(mpr_line)

            if mpr_idx == 0:
                payment = eff_rate
                if units > 1:
                    payment += eff_rate * 0.50 * (units - 1)
                mpr_line.discount_applied = False
            else:
                payment = (eff_rate * 0.50) * units
                mpr_line.discount_applied = True

            total += payment

        # Add non-discountable lines (also subject to lower-of-charge rule)
        for nd_line in no_discount_lines:
            units = line_map[nd_line.line_number - 1].units
            if units < 1:
                units = 1
            eff_rate = _effective_rate(nd_line)
            total += eff_rate * units

        output.lines = sorted(
            discount_lines + no_discount_lines, key=lambda x: x.line_number
        )
        output.total_payment = total

        return output

    def _process_line(
        self,
        line: LineItem,
        idx: int,
        ref_data: AscRefData,
        wage_index: float,
        code_pairs: Dict[Tuple[str, str], List[CodePairEntry]],
        device_available_units: Dict[str, int],
        claim_date: datetime,
    ) -> AscLineOutput:
        """
        Process a single claim line and return its pricing output.

        Handles rate lookup, payment indicator denials (CMS §60.3),
        geographic wage adjustment (CMS §40.2), code pair offsets for
        pass-through devices (CMS §40.7), and modifier logic for
        terminated/reduced procedures and device credits (CMS §40.4, §40.8, §40.10).

        Args:
            line: The claim line item to process.
            idx: Zero-based index of the line on the claim.
            ref_data: Loaded reference data (rates, device_offsets, wage_indices, code_pairs).
            wage_index: The wage index value for this claim's CBSA.
            code_pairs: Code pair lookup dict from ref_data.
            device_available_units: Mutable dict tracking remaining device units
                                    available for code pair offsets.
            claim_date: The claim's thru_date for date-range validation.

        Returns:
            A fully populated AscLineOutput for this line.
        """
        line_out = AscLineOutput(line_number=idx + 1, hcpcs=line.hcpcs)

        # --- Rate Lookup ---
        info = ref_data["rates"].get(line.hcpcs)
        if not info:
            line_out.details = "Code not found in ASC Fee Schedule"
            return line_out

        base_rate = info["rate"]
        payment_ind = info["indicator"]
        line_out.payment_indicator = payment_ind
        line_out.payment_rate = base_rate
        line_out.wage_index = wage_index
        line_out.subject_to_discount = info["subject_to_discount"]

        # --- Payment Indicator Denials (CMS §60.3) ---
        if payment_ind in DENY_INDICATORS:
            line_out.status = "denied"
            line_out.status_reason = f"Indicator {payment_ind}: denied per CMS §60.3"
            line_out.details = f"Denied (Indicator {payment_ind})"
            line_out.adjusted_rate = 0.0
            return line_out

        if payment_ind in DENY_PACKAGED_INDICATORS:
            line_out.status = "packaged"
            line_out.status_reason = (
                f"Indicator {payment_ind}: packaged, no separate payment per CMS §60.3"
            )
            line_out.details = f"Packaged/No Separate Payment (Indicator {payment_ind})"
            line_out.adjusted_rate = 0.0
            return line_out

        if payment_ind in UNPROCESSABLE_INDICATORS:
            line_out.status = "unprocessable"
            line_out.status_reason = (
                f"Indicator {payment_ind}: unprocessable per CMS §60.3"
            )
            line_out.details = f"Unprocessable (Indicator {payment_ind})"
            line_out.adjusted_rate = 0.0
            return line_out

        if base_rate == 0:
            line_out.status = "packaged"
            line_out.details = "Packaged or No Payment"
            return line_out

        line_out.status = "payable"

        # --- Geographic Adjustment (CMS §40.2) ---
        # Formula: (Rate * 0.50 * WI) + (Rate * 0.50)
        # 50% Labor Share hardcoded for ASC
        labor_portion = base_rate * 0.50
        non_labor_portion = base_rate * 0.50
        adjusted_rate = (labor_portion * wage_index) + non_labor_portion

        # --- Code Pair / Pass-Through Device Logic (CMS §40.7) ---
        line_hcpcs = line.hcpcs.upper().strip() if line.hcpcs else ""
        is_device_line = line_hcpcs.startswith("C")

        if not is_device_line and device_available_units and code_pairs:
            for device_code in list(device_available_units.keys()):
                if device_available_units[device_code] <= 0:
                    continue
                multiplier, matched_device = self._get_code_pair_offset(
                    line.hcpcs, device_code, code_pairs, claim_date
                )
                if multiplier > 0:
                    offset = adjusted_rate * multiplier
                    adjusted_rate = max(0.0, adjusted_rate - offset)
                    line_out.code_pair_offset = offset
                    line_out.code_pair_device = matched_device
                    line_out.details += f" (CodePair:{matched_device} -{offset:.2f})"
                    device_available_units[device_code] -= 1
                    break

        # --- Modifier Handling (CMS §40.4, §40.8, §40.10) ---
        modifiers = line.modifiers or []
        is_terminated_pre = MOD_TERMINATED_PRE_ANESTHESIA in modifiers
        is_reduced = MOD_REDUCED_PROCEDURE in modifiers
        is_terminated_post = MOD_TERMINATED_POST_ANESTHESIA in modifiers
        has_fb = MOD_DEVICE_NO_COST in modifiers
        has_fc = MOD_DEVICE_PARTIAL_CREDIT in modifiers

        device_credit = False
        offset_amount = 0.0

        # Modifier 73 takes precedence over FB/FC per CMS §40.10
        if is_terminated_pre:
            dev_offset_val = ref_data["device_offsets"].get(line.hcpcs, 0.0)
            if dev_offset_val > 0:
                adjusted_rate = max(0.0, adjusted_rate - dev_offset_val)
                line_out.details += f" (Mod 73: Device Offset {dev_offset_val} Removed)"
            adjusted_rate = adjusted_rate * 0.50
            line_out.subject_to_discount = False
            line_out.details += " (Mod 73: 50% Reduct)"
            if has_fb or has_fc:
                line_out.details += " (Mod 73 present, FB/FC Ignored)"
            line_out.adjusted_rate = adjusted_rate
            line_out.device_credit = False
            line_out.device_offset_amount = 0.0
            return line_out

        # FB/FC only processed if Modifier 73 is NOT present
        # Per CMS §40.8:
        #   FB = device furnished at no cost OR full credit received → remove 100% of offset
        #   FC = partial credit ≥50% of device cost received       → remove 50% of offset
        if has_fb or has_fc:
            dev_offset = ref_data["device_offsets"].get(line.hcpcs)
            if dev_offset:
                device_credit = True
                if has_fb:
                    offset_amount = dev_offset  # 100% reduction
                    line_out.details += f" (Mod FB: Full Device Offset -{offset_amount:.2f})"
                else:  # has_fc
                    offset_amount = dev_offset * 0.50  # 50% reduction
                    line_out.details += f" (Mod FC: Partial Device Offset -{offset_amount:.2f})"
                adjusted_rate = max(0.0, adjusted_rate - offset_amount)

        if is_reduced:
            adjusted_rate = adjusted_rate * 0.50
            line_out.subject_to_discount = False
            line_out.details += " (Mod 52: 50% Reduct)"
        elif is_terminated_post:
            line_out.details += " (Mod 74: Full Pay)"

        line_out.adjusted_rate = adjusted_rate
        line_out.device_credit = device_credit
        line_out.device_offset_amount = offset_amount
        return line_out
