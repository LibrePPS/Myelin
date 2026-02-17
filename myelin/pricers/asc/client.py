from typing import List, Optional

from pydantic import BaseModel, Field

from myelin.input.claim import Claim
from myelin.pricers.asc.data_loader import AscReferenceData
from myelin.pricers.opsf import OPSFProvider
from myelin.helpers.utils import ReturnCode


class AscLineOutput(BaseModel):
    line_number: int = 0
    hcpcs: str = ""
    payment_indicator: str = ""
    payment_rate: float = 0.0
    wage_index: float = 0.0
    adjusted_rate: float = 0.0
    device_offset_amount: float = 0.0
    device_credit: bool = False
    details: str = ""
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
        provider_geo = opsf_provider.cbsa_actual_geographic_location if opsf_provider else None

        cbsa = (
            claim.additional_data.get("cbsa", None) # if CBSA explicitly provided use it
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

        # We need to track lines that are subject to discounting for the sorting step
        discountable_lines = []

        line_map = {idx: line for idx, line in enumerate(claim.lines)}

        for idx, line in enumerate(claim.lines):
            line_out = AscLineOutput(line_number=idx + 1, hcpcs=line.hcpcs)

            # Lookup Rate
            info = ref_data["rates"].get(line.hcpcs)
            if not info:
                line_out.details = "Code not found in ASC Fee Schedule"
                calculated_lines.append(line_out)
                continue

            base_rate = info["rate"]
            payment_ind = info["indicator"]
            line_out.payment_indicator = payment_ind
            line_out.payment_rate = base_rate
            line_out.wage_index = wage_index
            line_out.subject_to_discount = info["subject_to_discount"]

            # Packaged services (N1, etc) - usually rate is 0 in file, but logic might say "Packaged"
            if base_rate == 0:
                line_out.details = "Packaged or No Payment"
                calculated_lines.append(line_out)
                continue

            # Geographic Adjustment
            # Formula: (Rate * 0.50 * WI) + (Rate * 0.50)
            # 50% Labor Share hardcoded for ASC
            labor_portion = base_rate * 0.50
            non_labor_portion = base_rate * 0.50

            adjusted_rate = (labor_portion * wage_index) + non_labor_portion

            # Device Intensive Logic
            # If modifier FB or FC is present AND code is device intensive (has offset)
            # Then we reduce payment by the offset amount.
            # NOTE: FB = Full credit, FC = Partial credit.
            modifiers = line.modifiers or []
            # Check for Terminated/Reduced Modifiers
            is_terminated_pre = "73" in modifiers
            is_reduced = "52" in modifiers
            is_terminated_post = "74" in modifiers

            device_credit = False
            offset_amount = 0.0

            if "FB" in modifiers or "FC" in modifiers:
                # Check if device intensive (present in FF)
                dev_offset = ref_data["device_offsets"].get(line.hcpcs)
                if dev_offset:
                    device_credit = True
                    offset_amount = dev_offset
                    # Ensure we don't reduce below 0 (unlikely but safe)
                    adjusted_rate = max(0.0, adjusted_rate - offset_amount)

            # Modifier 73 Specific Logic: Remove device offset (if device intensive) then cut in half.
            # 40.10: For Modifier 73, remove the device portion *before* the 50% reduction.
            dev_offset_val = ref_data["device_offsets"].get(line.hcpcs, 0.0)

            if is_terminated_pre:
                if dev_offset_val > 0:
                     # Remove device offset if not already removed by FB/FC (unlikely to have both?)
                     if not device_credit:
                         adjusted_rate = max(0.0, adjusted_rate - dev_offset_val)
                
                # Apply 50% reduction
                adjusted_rate = adjusted_rate * 0.50
                # Mark as not subject to further MPR
                line_out.subject_to_discount = False
                line_out.details += " (Mod 73: 50% Reduct)"

            elif is_reduced:
                # Modifier 52: 50% reduction.
                adjusted_rate = adjusted_rate * 0.50
                # Exempt from MPR
                line_out.subject_to_discount = False
                line_out.details += " (Mod 52: 50% Reduct)"
            
            elif is_terminated_post:
                # Modifier 74: 100% payment (already calculated).
                # Subject to MPR (so leave subject_to_discount as is).
                line_out.details += " (Mod 74: Full Pay)"

            line_out.adjusted_rate = adjusted_rate
            line_out.device_credit = device_credit
            line_out.device_offset_amount = offset_amount

            # Add to list
            calculated_lines.append(line_out)
            if line_out.subject_to_discount and line_out.adjusted_rate > 0:
                discountable_lines.append(line_out)

        # 5. Multiple Procedure Discounting
        # "Rank procedures by adjusted payment rate ... highest pays 100%, subsequent pay 50%"
        # Only applies to codes with "Subject to Multiple Procedure Discounting" indicator (Y)

        discountable_lines.sort(key=lambda x: x.adjusted_rate, reverse=True)

        # First one gets full payment
        if discountable_lines:
            discountable_lines[0].discount_applied = False
            # The rest get 50%
            for line in discountable_lines[1:]:
                line.discount_applied = True
                line.adjusted_rate = line.adjusted_rate * 0.50

        # 6. Final Summation
        # Calculate total payment applying discount logic to units > 1
        total = 0.0

        # Sort ALL lines by adjusted rate first to identify the primary procedure
        # Only lines subject to discount participate in strictly "primary vs secondary" ranking logic for the *first* unit.
        # Lines NOT subject to discount are just paid at 100% of their rate (or packaged).

        # Re-calc discounting properly:
        # 1. Separate lines into "Subject to Discount" and "Not Subject"
        discount_lines = [
            g for g in calculated_lines if g.subject_to_discount and g.adjusted_rate > 0
        ]
        no_discount_lines = [
            g
            for g in calculated_lines
            if not g.subject_to_discount or g.adjusted_rate <= 0
        ]

        # 2. Sort discountable lines by adjusted rate descending
        discount_lines.sort(key=lambda x: x.adjusted_rate, reverse=True)

        # 3. Apply discount
        # First unit of first procedure = 100%
        # All subsequent units of first procedure = 50%
        # All units of all subsequent discountable procedures = 50%

        for idx, line in enumerate(discount_lines):
            units = line_map[line.line_number - 1].units
            if units < 1:
                units = 1

            if idx == 0:
                # Highest valued procedure
                # First unit pays 100%
                payment = line.adjusted_rate

                # Remaining units pay 50%
                if units > 1:
                    payment += line.adjusted_rate * 0.50 * (units - 1)

                line.discount_applied = (
                    False  # Partially true if units > 1, but "Line 1" is primary
                )
            else:
                # Subsequent procedures
                # All units pay 50%
                payment = (line.adjusted_rate * 0.50) * units
                line.discount_applied = True

            total += payment

        # 4. Add non-discountable lines
        for line in no_discount_lines:
            units = line_map[line.line_number - 1].units
            if units < 1:
                units = 1
            total += line.adjusted_rate * units

        output.lines = sorted(
            discount_lines + no_discount_lines, key=lambda x: x.line_number
        )
        output.total_payment = total

        return output
