from collections import defaultdict
from decimal import Decimal
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
DENY_INDICATORS = frozenset({"C5", "M6", "U5", "X5", "E5", "Y5", "K5"})
# Indicators that result in denial as packaged (no separate payment)
DENY_PACKAGED_INDICATORS = frozenset({"L1", "NI", "S1", "D1"})
# Indicators returned as unprocessable
UNPROCESSABLE_INDICATORS = frozenset({"D5", "B5"})
# Combined set for quick lookup
NO_PAYMENT_INDICATORS = (
    DENY_INDICATORS | DENY_PACKAGED_INDICATORS | UNPROCESSABLE_INDICATORS
)

# Payment indicators exempt from geographic wage adjustment per CMS §40.2:
#   H2  - Brachytherapy sources
#   J7  - OPPS pass-through devices (contractor-priced)
#   K2  - Separately payable drugs and biologicals (OPPS rate)
#   K7  - Unclassified drugs and biologicals (contractor-priced)
#   F4  - Corneal tissue acquisition / hepatitis B vaccine (reasonable cost)
#   L6  - NTIOL / qualifying non-opioid devices
WAGE_EXEMPT_INDICATORS = frozenset({"H2", "J7", "K2", "K7", "F4", "L6"})

# Modifier constants
MOD_TERMINATED_PRE_ANESTHESIA = "73"  # Terminated before anesthesia (50% pay)
MOD_TERMINATED_POST_ANESTHESIA = "74"  # Terminated after anesthesia (100% pay)
MOD_REDUCED_PROCEDURE = "52"  # Reduced/discontinued procedure (50% pay)
MOD_DEVICE_NO_COST = "FB"  # Device furnished without cost / full credit
MOD_DEVICE_PARTIAL_CREDIT = "FC"  # Device with partial credit (≥50%)


class AscMueLimit(BaseModel):
    code: str = ""
    mue_limit: int = 0
    up_to_limit: bool = False


class AscLineOutput(BaseModel):
    line_number: int = 0
    hcpcs: str = ""
    payment_indicator: str = ""
    payment_rate: float = 0.0
    wage_index: float = 0.0
    adjusted_rate: float = 0.0  # Wage-adjusted rate per unit (before MPR)
    units: int = 1  # Effective units billed
    device_offset_amount: float = 0.0
    device_credit: bool = False
    # Code pair (pass-through device) fields
    code_pair_offset: float = 0.0  # Offset from code pair multiplier
    code_pair_device: str = ""  # Device HCPCS that triggered the code pair offset
    details: str = ""
    status: str = ""  # "payable", "denied", "unprocessable", or "packaged"
    status_reason: str = ""  # Reason for denial/rejection
    subject_to_discount: bool = False
    discount_applied: bool = False  # True if 50% MPR discount was applied
    line_payment: float = 0.0  # Medicare 80% payment for this line
    line_copayment: float = 0.0  # Beneficiary 20% copayment for this line
    line_total: float = 0.0  # Total allowed amount (100% = payment + copayment)


class AscOutput(BaseModel):
    cbsa: str = ""
    wage_index: float = 0.0
    lines: List[AscLineOutput] = Field(default_factory=list)
    total_payment: float = 0.0  # Medicare 80% total
    total_copayment: float = 0.0  # Beneficiary 20% total
    total: float = 0.0  # Total allowed amount (100%)
    error: Optional[ReturnCode] = None
    message: Optional[str] = None

    def get_payment(self) -> float:
        return self.total_payment


class AscClient:
    def __init__(self, data_dir: str, logger=None, preload_data: bool = False):
        self.data_loader = AscReferenceData(data_dir)
        self.logger = logger
        if preload_data:
            self.data_loader.preload_all_data()

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

    def _mue_check(
        self,
        claim: Claim,
        calculated_lines: List[AscLineOutput],
        mues: dict[str, AscMueLimit] | None = None,
    ) -> None:
        """
        Apply Medically Unlikely Edit (MUE) limits to calculated output lines.

        MUEs cap the number of units that can be billed for a given HCPCS code
        on a single claim date. Two enforcement modes exist:

        - up_to_limit=False (line edit): If total billed units for a HCPCS
          exceed the MUE limit, ALL lines for that code are denied. The
          adjudicator cannot split the claim; the entire service is rejected.

        - up_to_limit=True (date-of-service edit): Units up to the MUE limit
          are payable; excess units are denied. Lines are filled greedily in
          claim order — each line's units are consumed until the allowed
          budget is exhausted, then remaining lines are zeroed out.

        Only lines with status="payable" are considered; denied/packaged lines
        are left untouched.

        Args:
            claim: The original claim (used to read billed units per line).
            calculated_lines: The list of AscLineOutput objects to mutate in place.
            mues: Optional dict mapping HCPCS code → AscMueLimit. If None or
                  empty, this method is a no-op.
        """
        if not mues:
            return

        # Build a map from line_number → original claim line for unit lookup.
        line_map: Dict[int, LineItem] = {
            idx + 1: line for idx, line in enumerate(claim.lines)
        }

        # Group payable output lines by (HCPCS, service_date).
        # MUE limits are applied per code per date of service — lines for the
        # same HCPCS on different dates are evaluated independently.
        hcpcs_to_lines: Dict[Tuple[str, object], List[AscLineOutput]] = defaultdict(list)
        for out_line in calculated_lines:
            if out_line.status == "payable" and out_line.hcpcs in mues:
                svc_date = line_map[out_line.line_number].service_date
                hcpcs_to_lines[(out_line.hcpcs, svc_date)].append(out_line)

        for (hcpcs, _svc_date), lines_for_code in hcpcs_to_lines.items():
            mue = mues[hcpcs]
            # Sum billed units across all payable lines for this HCPCS.
            total_units = sum(
                max(1, int(line_map[g.line_number].units or 1)) for g in lines_for_code
            )

            if total_units <= mue.mue_limit:
                # Within limit — nothing to do.
                continue

            if not mue.up_to_limit:
                # Line edit: deny ALL lines for this HCPCS.
                for g in lines_for_code:
                    g.status = "denied"
                    g.status_reason = (
                        f"MUE exceeded: {total_units} units billed, "
                        f"limit is {mue.mue_limit} (all units denied)"
                    )
                    g.adjusted_rate = 0.0
                    g.units = 0
                    g.line_payment = 0.0
                    g.line_copayment = 0.0
                    g.line_total = 0.0
            else:
                # Date-of-service edit: allow up to the limit, deny the rest.
                remaining_allowed = mue.mue_limit
                for g in lines_for_code:
                    billed = max(1, int(line_map[g.line_number].units or 1))
                    if remaining_allowed <= 0:
                        # Budget exhausted — deny this line entirely.
                        g.status = "denied"
                        g.status_reason = (
                            f"MUE exceeded: {total_units} units billed, "
                            f"limit is {mue.mue_limit} (excess denied)"
                        )
                        g.adjusted_rate = 0.0
                        g.units = 0
                        g.line_payment = 0.0
                        g.line_copayment = 0.0
                        g.line_total = 0.0
                    elif billed > remaining_allowed:
                        # Partial: cap this line's units at the remaining budget.
                        g.units = remaining_allowed
                        g.status_reason = (
                            f"MUE partial: {billed} units billed, "
                            f"{remaining_allowed} allowed (limit {mue.mue_limit})"
                        )
                        remaining_allowed = 0
                        # adjusted_rate is per-unit; line_payment/copayment/total
                        # will be recalculated during final summation, so we only
                        # update the unit count here.
                    else:
                        # This line fits entirely within the remaining budget.
                        remaining_allowed -= billed

    def process(
        self,
        claim: Claim,
        opsf_provider: Optional[OPSFProvider] = None,
        mues: dict[str, AscMueLimit] | None = None,
        **kwargs,
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

        # 5. MUE Check: enforce Medically Unlikely Edit limits.
        # We run before ancillary check so that if a surgical procedure is denied due to MUE, 
        # the ancillary services are also denied.
        self._mue_check(claim, calculated_lines, mues)

        # 5b. CMS §60.2: Ancillary services require a related surgical procedure on the same claim.
        # Addendum AA = surgical procedures; Addendum BB = covered ancillary services.
        # If no payable AA line exists, all payable BB lines are returned as unprocessable.
        rates_lookup = ref_data.get("rates", {})
        has_payable_surgical = any(
            g.status == "payable"
            and rates_lookup.get(g.hcpcs, {}).get("addendum", "AA") == "AA"
            for g in calculated_lines
        )
        if not has_payable_surgical:
            for g in calculated_lines:
                if (
                    rates_lookup.get(g.hcpcs, {}).get("addendum") == "BB"
                    and g.status == "payable"
                ):
                    g.status = "unprocessable"
                    g.status_reason = (
                        "No related surgical procedure on claim (CMS §60.2)"
                    )
                    g.adjusted_rate = 0.0

        # 6. Final Summation
        # Calculate total payment applying discount logic to units > 1
        total = 0.0

        # Per CMS §40.5: "In determining the ranking of procedures for application of
        # the multiple procedure reduction, contractors shall use the lower of the
        # billed charge or the ASC payment amount."
        # Per CMS §40: "Medicare contractors calculate payment for each separately
        # payable procedure and service based on the lower of 80 percent of actual
        # charges or the ASC payment rate." (charge comparison at line-item level)

        line_map = {idx: line for idx, line in enumerate(claim.lines)}

        # Helper: effective rate is the lower of adjusted_rate vs billed charges (per unit).
        # Uses Decimal arithmetic to avoid floating-point drift.
        # NOTE: unit_count comes from line_out.units, which may have been capped by
        # _mue_check. Fall back to the claim line's billed units if line_out.units
        # is 0 (fully denied lines are excluded from the discount pools below).
        def _effective_rate(line_out: AscLineOutput) -> Decimal:
            line_item = line_map[line_out.line_number - 1]
            charges = (
                Decimal(str(line_item.charges))
                if line_item.charges and line_item.charges > 0
                else None
            )
            unit_count = line_out.units if line_out.units > 0 else (
                max(1, int(line_item.units))
                if line_item.units and line_item.units >= 1
                else 1
            )
            rate = Decimal(str(line_out.adjusted_rate))
            if charges is not None:
                charge_per_unit = charges / Decimal(unit_count)
                return min(rate, charge_per_unit)
            return rate

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
        _HALF = Decimal("0.5")
        _COPAY_RATE = Decimal("0.20")
        _PAYMENT_RATE = Decimal("1") - _COPAY_RATE
        _CENTS = Decimal("0.01")  # quantize target: round to 2 decimal places
        total = Decimal("0")

        for mpr_idx, mpr_line in enumerate(discount_lines):
            # Use line_out.units — may have been capped by _mue_check.
            # Fall back to the billed units on the claim if not yet set.
            units = mpr_line.units if mpr_line.units > 0 else max(
                1, int(line_map[mpr_line.line_number - 1].units or 1)
            )
            eff_rate = _effective_rate(mpr_line)

            if mpr_idx == 0:
                payment = eff_rate
                if units > 1:
                    payment += eff_rate * _HALF * Decimal(units - 1)
                mpr_line.discount_applied = False
            else:
                payment = eff_rate * _HALF * Decimal(units)
                mpr_line.discount_applied = True

            # Round to cents before accumulating so sum(line_payment) == total_payment
            payment = payment.quantize(_CENTS)
            mpr_line.units = units
            mpr_line.line_payment = float((payment * _PAYMENT_RATE).quantize(_CENTS))
            mpr_line.line_copayment = float((payment * _COPAY_RATE).quantize(_CENTS))
            mpr_line.line_total = float(payment)
            total += payment

        # Add non-discountable lines (also subject to lower-of-charge rule)
        for nd_line in no_discount_lines:
            # Skip lines that are not payable (denied, packaged, unprocessable).
            # Their payment fields were already zeroed during line processing or
            # by _mue_check; overwriting units here would undo that.
            if nd_line.status != "payable":
                continue
            # Use line_out.units — may have been capped by _mue_check.
            units = nd_line.units if nd_line.units > 0 else max(
                1, int(line_map[nd_line.line_number - 1].units or 1)
            )
            eff_rate = _effective_rate(nd_line)
            payment = (eff_rate * Decimal(units)).quantize(_CENTS)
            nd_line.units = units
            nd_line.line_payment = float((payment * _PAYMENT_RATE).quantize(_CENTS))
            nd_line.line_copayment = float((payment * _COPAY_RATE).quantize(_CENTS))
            nd_line.line_total = float(payment)
            total += payment

        output.lines = sorted(
            discount_lines + no_discount_lines, key=lambda x: x.line_number
        )
        output.total_payment = float((total * _PAYMENT_RATE).quantize(_CENTS))
        output.total_copayment = float((total * _COPAY_RATE).quantize(_CENTS))
        output.total = float(total)

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
        line_out = AscLineOutput(line_number=idx + 1, hcpcs=line.hcpcs, units=line.units)

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

        # --- Modifier flags (needed before wage adjustment) ---
        modifiers = line.modifiers or []
        is_terminated_pre = MOD_TERMINATED_PRE_ANESTHESIA in modifiers
        is_terminated_post = MOD_TERMINATED_POST_ANESTHESIA in modifiers
        is_reduced = MOD_REDUCED_PROCEDURE in modifiers
        has_fb = MOD_DEVICE_NO_COST in modifiers
        has_fc = MOD_DEVICE_PARTIAL_CREDIT in modifiers

        # --- Device Offset: subtract from base rate BEFORE wage adjustment (CMS §40.8) ---
        # Removing the device portion from the base rate ensures we never wage-index
        # a zero-cost device component (avoids over/under-payment in high/low wage areas).
        device_credit = False
        offset_amount = 0.0
        reduced_base_rate = base_rate

        if is_terminated_pre:
            # §40.10: For device-intensive procedures terminated pre-anesthesia,
            # remove the full device offset from the base rate before the 50% cut.
            dev_offset_val = ref_data["device_offsets"].get(line.hcpcs, 0.0)
            if dev_offset_val > 0:
                reduced_base_rate = max(0.0, base_rate - dev_offset_val)
                offset_amount = dev_offset_val
                line_out.details += (
                    f" (Mod 73: Device Offset {dev_offset_val:.2f} Removed from Base)"
                )
            if has_fb or has_fc:
                line_out.details += " (Mod 73 present, FB/FC Ignored)"

        elif has_fb or has_fc:
            # §40.8: FB = full credit (100% offset), FC = partial credit (50% offset)
            dev_offset = ref_data["device_offsets"].get(line.hcpcs)
            if dev_offset:
                device_credit = True
                if has_fb:
                    offset_amount = dev_offset
                    line_out.details += (
                        f" (Mod FB: Full Device Offset -{offset_amount:.2f})"
                    )
                else:  # has_fc
                    offset_amount = dev_offset * 0.50
                    line_out.details += (
                        f" (Mod FC: Partial Device Offset -{offset_amount:.2f})"
                    )
                reduced_base_rate = max(0.0, base_rate - offset_amount)

        # --- Geographic Adjustment (CMS §40.2) ---
        # Certain payment indicators are exempt from wage adjustment and paid at the flat rate.
        _D = Decimal  # shorthand for readability
        d_reduced_base = _D(str(reduced_base_rate))
        d_wage = _D(str(wage_index))

        if payment_ind in WAGE_EXEMPT_INDICATORS:
            adjusted_rate = d_reduced_base
            line_out.details += f" (No Wage Adj: Indicator {payment_ind})"
        else:
            # Apply 50/50 split to the REDUCED base rate so the device portion is not wage-indexed.
            half = _D("0.5")
            labor_portion = d_reduced_base * half
            non_labor_portion = d_reduced_base * half
            adjusted_rate = (labor_portion * d_wage) + non_labor_portion

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
                    d_mult = Decimal(str(multiplier))
                    offset = adjusted_rate * d_mult
                    adjusted_rate = max(Decimal("0"), adjusted_rate - offset)
                    line_out.code_pair_offset = float(offset)
                    line_out.code_pair_device = matched_device
                    line_out.details += (
                        f" (CodePair:{matched_device} -{float(offset):.2f})"
                    )
                    device_available_units[device_code] -= 1
                    break

        # --- Modifier Payment Reductions (CMS §40.4, §40.10) ---
        # Device offset already applied to base rate above; only percentage cuts remain.
        if is_terminated_pre:
            adjusted_rate = adjusted_rate * Decimal("0.5")
            line_out.subject_to_discount = False
            line_out.details += " (Mod 73: 50% Reduct)"
            # Lower-of: cap at submitted charges (CMS §40)
            if line.charges and line.charges > 0:
                charge_limit = Decimal(str(line.charges))
                if charge_limit < adjusted_rate:
                    adjusted_rate = charge_limit
                    line_out.details += (
                        f" (Lower-of: Charges {float(charge_limit):.2f})"
                    )
            line_out.adjusted_rate = float(adjusted_rate)
            line_out.device_credit = False
            line_out.device_offset_amount = offset_amount
            return line_out

        if is_reduced:
            adjusted_rate = adjusted_rate * Decimal("0.5")
            line_out.subject_to_discount = False
            line_out.details += " (Mod 52: 50% Reduct)"
        elif is_terminated_post:
            line_out.details += " (Mod 74: Full Pay)"

        # --- Lower-of: submitted charges vs adjusted rate (CMS §40) ---
        if line.charges and line.charges > 0:
            charge_limit = Decimal(str(line.charges))
            if charge_limit < adjusted_rate:
                adjusted_rate = charge_limit
                line_out.details += f" (Lower-of: Charges {float(charge_limit):.2f})"

        line_out.adjusted_rate = float(adjusted_rate)
        line_out.device_credit = device_credit
        line_out.device_offset_amount = offset_amount
        return line_out
