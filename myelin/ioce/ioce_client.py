from datetime import datetime
import jpype  # pyright: ignore[reportMissingTypeStubs]

from myelin.helpers.utils import handle_java_exceptions
from myelin.input.claim import (
    Claim,
    DiagnosisCode,
    LineItem,
    PoaType,
    ValueCode,
)
from myelin.ioce.ioce_output import IoceOutput, IoceOutputEdit
from myelin.plugins import apply_client_methods, run_client_load_classes

# Provides stubs during TYPE_CHECKING and protocol classes at runtime
from myelin.ioce.ioce_types import (
    OceClaim,
    OceLineItem,
    OceDiagnosisCode,
    OceHcpcsModifier,
    OceValueCode,
    OceProcessingInformation,
    OceClaimFactory,
    IoceComponent,
    IoceClaim,
)


class IoceClient:
    """Client for processing claims through the IOCE (Integrated Outpatient Code Editor) software"""

    def __init__(self):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using IoceClient."
            )
        self.load_classes()
        try:
            run_client_load_classes(self)
        except Exception:
            pass
        try:
            apply_client_methods(self)
        except Exception:
            pass

    def load_classes(self) -> None:
        """Load all required Java classes and components"""
        try:
            self.ioce_component_class: type[IoceComponent] = jpype.JClass(
                "gov.cms.oce.IoceComponent"
            )  # pyright: ignore[reportAttributeAccessIssue]
            self.ioce_claim_class: type[IoceClaim] = jpype.JClass(
                "gov.cms.oce.IoceClaim"
            )  # pyright: ignore[reportAttributeAccessIssue]
            self.oce_claim_factory_class: type[OceClaimFactory] = jpype.JClass(
                "gov.cms.oce.model.external.OceClaimFactory"
            )  # pyright: ignore[reportAttributeAccessIssue]
            self.oce_claim_class: type[OceClaim] = jpype.JClass(
                "gov.cms.oce.model.external.OceClaim"
            )  # pyright: ignore[reportAttributeAccessIssue]
            self.oce_line_item_class: type[OceLineItem] = jpype.JClass(
                "gov.cms.oce.model.external.OceLineItem"
            )  # pyright: ignore[reportAttributeAccessIssue]
            self.oce_diagnosis_code_class: type[OceDiagnosisCode] = jpype.JClass(
                "gov.cms.oce.model.external.OceDiagnosisCode"
            )  # pyright: ignore[reportAttributeAccessIssue]
            self.oce_hcpcs_modifier_class: type[OceHcpcsModifier] = jpype.JClass(
                "gov.cms.oce.model.external.OceHcpcsModifier"
            )  # pyright: ignore[reportAttributeAccessIssue]
            self.oce_value_code_class: type[OceValueCode] = jpype.JClass(
                "gov.cms.oce.model.external.OceValueCode"
            )  # pyright: ignore[reportAttributeAccessIssue]
            self.oce_processing_info_class: type[OceProcessingInformation] = (
                jpype.JClass("gov.cms.oce.model.external.OceProcessingInformation")
            )  # pyright: ignore[reportAttributeAccessIssue]

            self.factory: OceClaimFactory = self.oce_claim_factory_class.getInstance()
            self.ioce_component: IoceComponent = self.ioce_component_class()

        except Exception as e:
            raise RuntimeError(f"Failed to initialize Ioce Java classes: {e}")

    def format_date(self, date_input: datetime | str | None) -> str:
        """Convert date to YYYYMMDD format required by IOCE"""
        if date_input is None:
            return ""

        if isinstance(date_input, str):
            # Assume input is in YYYY-MM-DD format
            try:
                date_obj = datetime.strptime(date_input, "%Y-%m-%d")
                return date_obj.strftime("%Y%m%d")
            except ValueError:
                # Try to parse as YYYYMMDD already
                if len(date_input) == 8 and date_input.isdigit():
                    return date_input
                raise ValueError(f"Invalid date format: {date_input}")
        else:
            return date_input.strftime("%Y%m%d")

    def format_age(self, age: int | None) -> str:
        """Format age as 3-digit string"""
        if age is None:
            return "000"
        return f"{int(age):03d}"

    def format_sex(self, sex: str | None) -> str:
        """Format sex as required by IOCE (0=unknown, 1=male, 2=female)"""
        if sex is None:
            return "0"
        sex_str = str(sex).upper()
        if sex_str.startswith("M"):
            return "1"
        elif sex_str.startswith("F"):
            return "2"
        else:
            return "0"

    def create_diagnosis_code(
        self, dx_code: DiagnosisCode | None
    ) -> OceDiagnosisCode | None:
        """Create Java OceDiagnosisCode from Python DiagnosisCode"""
        if not dx_code or not dx_code.code:
            return None

        clean_code = dx_code.code.replace(".", "")
        poa_str = "U"
        if dx_code.poa == PoaType.Y:
            poa_str = "Y"
        elif dx_code.poa == PoaType.N:
            poa_str = "N"
        elif dx_code.poa == PoaType.W:
            poa_str = "W"
        elif dx_code.poa == PoaType.U:
            poa_str = "U"

        return self.factory.createDiagnosisCode(clean_code, poa_str)

    def create_hcpcs_modifier(
        self, modifier_str: str | None
    ) -> OceHcpcsModifier | None:
        """Create Java OceHcpcsModifier from string"""
        if modifier_str is None or modifier_str == "":
            return None
        return self.factory.createHcpcsModifier(str(modifier_str))

    def create_value_code(self, value_code: ValueCode) -> OceValueCode:
        """Create Java OceValueCode from Python ValueCode"""
        # Format amount as 9-character string with leading zeros
        amount_str = f"{int(value_code.amount * 100):09d}"  # Convert to cents
        return self.factory.createValueCode(value_code.code, amount_str)

    def create_line_item(self, line_item: LineItem) -> OceLineItem:
        """Create Java OceLineItem from Python LineItem"""

        java_line = self.factory.createLineItem()

        if line_item.service_date:
            java_line.setServiceDate(self.format_date(line_item.service_date))

        if line_item.revenue_code:
            java_line.setRevenueCode(str(line_item.revenue_code))

        if line_item.hcpcs:
            java_line.setHcpcs(str(line_item.hcpcs))

        if line_item.modifiers:
            for modifier in line_item.modifiers:
                if modifier:
                    java_line.addHcpcsModifierInput(str(modifier))

        # Set units (9-digit string)
        if line_item.units:
            java_line.setUnitsInput(f"{int(line_item.units):09d}")

        # Set charge (10-digit string with 2 decimal places)
        if line_item.charges > 0:
            charge_str = f"{line_item.charges:.2f}"
            java_line.setCharge(charge_str)

        # Set action flag (optional, payer-only field)
        # Default to "0" if not specified
        java_line.setActionFlagInput("0")

        if line_item.override is not None:
            override_set = False
            if line_item.override.apc != "":
                java_line.setContractorApc(line_item.override.apc)
                override_set = True
            if line_item.override.status_indicator != "":
                java_line.setContractorStatusIndicator(
                    line_item.override.status_indicator
                )
                override_set = True
            if line_item.override.payment_indicator != "":
                java_line.setContractorPaymentIndicator(
                    line_item.override.payment_indicator
                )
                override_set = True
            if line_item.override.discounting_formula != "":
                if str(line_item.override.discounting_formula).isnumeric():
                    java_line.setContractorDiscountingFormula(
                        line_item.override.discounting_formula
                    )
                else:
                    raise ValueError(
                        f"Discounting formula must be a numeric value: {line_item.override.discounting_formula} for code {line_item.hcpcs}"
                    )
                override_set = True
            if line_item.override.rejection_denial_flag != "":
                java_line.setContractorRejectionDenialFlag(
                    line_item.override.rejection_denial_flag
                )
                override_set = True
            if line_item.override.packaging_flag != "":
                java_line.setContractorPackagingFlag(line_item.override.packaging_flag)
                override_set = True
            if line_item.override.payment_adjustment_flag_01 != "":
                java_line.setContractorPaymentAdjustmentFlag01(
                    line_item.override.payment_adjustment_flag_01
                )
                override_set = True
            if line_item.override.payment_method_flag != "":
                java_line.setContractorPaymentMethodFlag(
                    line_item.override.payment_method_flag
                )
                override_set = True
            if line_item.override.payment_adjustment_flag_02 != "":
                java_line.setContractorPaymentAdjustmentFlag02(
                    line_item.override.payment_adjustment_flag_02
                )
                override_set = True

            """
            The IOCE has logic to ignore overrides if the edit bypass list is empty or does not contain
            a valid edit value. We can "trick" the system to applying the overrides by adding the 
            "invalid" edit value of "-1" to edit bypass list.
            """

            if len(line_item.override.edit_bypass_list) > 0:
                for bypass in line_item.override.edit_bypass_list:
                    java_line.addContractorEditBypass(bypass)
            elif override_set:
                java_line.addContractorEditBypass("-1")
        return java_line

    def create_oce_claim(self, claim: Claim) -> OceClaim:
        """Create Java OceClaim from Python Claim"""
        oce_claim = self.factory.createClaim()

        if claim.claimid:
            oce_claim.setClaimId(str(claim.claimid))
        else:
            oce_claim.setClaimId("DEFAULT_CLAIM_ID")

        if claim.patient:
            oce_claim.setAge(self.format_age(claim.patient.age))
            oce_claim.setSex(self.format_sex(claim.patient.sex))
        else:
            oce_claim.setAge("065")  # Default age
            oce_claim.setSex("0")  # Unknown sex

        if claim.from_date:
            oce_claim.setDateStarted(self.format_date(claim.from_date))
        if claim.thru_date:
            oce_claim.setDateEnded(self.format_date(claim.thru_date))
        if hasattr(claim, "receipt_date") and claim.receipt_date:
            oce_claim.setReceiptDate(self.format_date(claim.receipt_date))

        if claim.bill_type:
            bill_type_str = str(claim.bill_type).ljust(3, "0")[
                :3
            ]  # Pad or truncate to 3 chars
            oce_claim.setBillType(bill_type_str)
        else:
            oce_claim.setBillType("131")  # Default outpatient bill type

        if claim.patient_status:
            status_str = str(claim.patient_status).zfill(2)[
                :2
            ]  # Pad with zeros or truncate
            oce_claim.setPatientStatus(status_str)
        else:
            oce_claim.setPatientStatus("01")  # Default

        # Set Ioce flag (1=Opps, 2=Non-Opps)
        # For Opps processing, we default to "1"
        if claim.opps_flag:
            oce_claim.setOppsFlag(str(claim.opps_flag))
        else:
            oce_claim.setOppsFlag("1")  # Default to Opps

        if claim.billing_provider and claim.billing_provider.npi:
            npi_str = str(claim.billing_provider.npi)[:13]  # Truncate to 13 chars
            oce_claim.setNationalProviderId(npi_str)

        # Set CMS certification number (6-character)
        # This might come from provider other_id or additional_data
        if claim.billing_provider and claim.billing_provider.other_id:
            cert_num = str(claim.billing_provider.other_id)[:6]
            oce_claim.setCmsCertificationNumber(cert_num)
        else:
            oce_claim.setCmsCertificationNumber("123456")  # Default

        if hasattr(claim, "occurrence_codes") and claim.occurrence_codes:
            for occ_code in claim.occurrence_codes:
                if occ_code and occ_code.code:
                    oce_claim.addOccurrenceCodeInput(str(occ_code.code))

        if hasattr(claim, "cond_codes") and claim.cond_codes:
            for cond_code in claim.cond_codes:
                if cond_code:
                    oce_claim.addConditionCodeInput(str(cond_code))

        if hasattr(claim, "value_codes") and claim.value_codes:
            for value_code in claim.value_codes:
                if value_code:
                    java_value_code = self.create_value_code(value_code)
                    if java_value_code:
                        oce_claim.addValueCodeInput(java_value_code)

        if claim.principal_dx:
            java_principal_dx = self.create_diagnosis_code(claim.principal_dx)
            if java_principal_dx:
                oce_claim.setPrincipalDiagnosisCode(java_principal_dx)

        # Add reason for visit diagnosis (typically same as principal for outpatient)
        if claim.principal_dx:
            java_rfv_dx = self.create_diagnosis_code(claim.principal_dx)
            if java_rfv_dx:
                oce_claim.addReasonForVisitDiagnosisCode(java_rfv_dx)

        if claim.secondary_dxs:
            for secondary_dx in claim.secondary_dxs:
                if secondary_dx:
                    java_secondary_dx = self.create_diagnosis_code(secondary_dx)
                    if java_secondary_dx:
                        oce_claim.addSecondaryDiagnosisCode(java_secondary_dx)

        if claim.lines:
            for line in claim.lines:
                if line:
                    java_line = self.create_line_item(line)
                    if java_line:
                        oce_claim.addLineItem(java_line)

        return oce_claim

    @handle_java_exceptions
    def process(self, claim: Claim, include_descriptions: bool = True) -> IoceOutput:
        """Process a claim through IOCE and return IoceOutput"""
        try:
            oce_claim = self.create_oce_claim(claim)

            ioce_claim = self.ioce_claim_class(oce_claim)

            self.ioce_component.process(ioce_claim)

            processed_model = ioce_claim.getModel()

            Ioce_output = IoceOutput()
            _ = Ioce_output.from_java(processed_model)

            if include_descriptions:
                Ioce_output = self.append_descriptions(Ioce_output)

            return Ioce_output

        except Exception as e:
            raise RuntimeError(f"Error processing Ioce claim {claim.claimid}: {e}")

    def _enrich_disposition_and_edits(
        self,
        result: IoceOutput,
        disposition_type_id: str,
        disposition_attr: str,
        edit_list_attr: str,
        internal_version: int,
    ) -> None:
        """
        Generic function to enrich disposition and edit descriptions.

        Args:
            result: The result object to enrich
            disposition_type_id: The disposition type ID (e.g., "1", "2", "3", etc.)
            disposition_attr: The disposition attribute name (e.g., "claim_disposition")
            edit_list_attr: The edit list attribute name (e.g., "claim_rejection_edit_list")
            internal_version: The internal version for lookups
        """
        disposition_value: str | None = getattr(result, disposition_attr, None)
        if disposition_value:
            if disposition_value in ("", "0"):
                return
            disp_desc = self.ioce_component.getClaimDispositionDescription(
                disposition_type_id, internal_version
            )
            setattr(
                result,
                f"{disposition_attr}_description",
                str(disp_desc) if disp_desc else "",
            )

            disp_value_desc = self.ioce_component.getClaimDispositionValueDescription(
                disposition_type_id, disposition_value, internal_version
            )
            setattr(
                result,
                f"{disposition_attr}_value_description",
                str(disp_value_desc) if disp_value_desc else "",
            )

            # Enrich edit descriptions
            edit_list: list[IoceOutputEdit] = getattr(result, edit_list_attr, [])
            for edit in edit_list:
                edit_desc = self.ioce_component.getEditDescription(
                    str(int(edit.edit)), internal_version
                )
                edit.description = str(edit_desc) if edit_desc else ""

    # TODO: More descriptions available in the IOCE component
    def append_descriptions(self, result: IoceOutput) -> IoceOutput:
        """
        Get human-readable descriptions for codes and values in the result.
        This uses the IOCE component's description methods.
        """

        try:
            internal_version = result.processing_information.internal_version

            # Get return code description
            if result.processing_information.return_code.code:
                return_code_desc = self.ioce_component.getLatestErrorDescription(
                    str(result.processing_information.return_code.code)
                )
                result.processing_information.return_code.description = (
                    str(return_code_desc) if return_code_desc else ""
                )

            # Get claim processed flag description
            if result.claim_processed_flag:
                claim_flag_desc = self.ioce_component.getClaimProcessedFlagDescription(
                    result.claim_processed_flag, internal_version
                )
                result.claim_processed_flag_description = (
                    str(claim_flag_desc) if claim_flag_desc else ""
                )

            # Enrich disposition and edit descriptions
            disposition_configs = [
                ("1", "claim_disposition", "claim_rejection_edit_list"),
                ("2", "claim_rejection_disposition", "claim_rejection_edit_list"),
                ("3", "claim_denial_disposition", "claim_denial_edit_list"),
                (
                    "4",
                    "claim_return_to_provider_disposition",
                    "claim_return_to_provider_edit_list",
                ),
                ("5", "claim_suspension_disposition", "claim_suspension_edit_list"),
                ("6", "line_rejection_disposition", "line_rejection_edit_list"),
                ("7", "line_denial_disposition", "line_denial_edit_list"),
            ]

            for (
                disposition_type_id,
                disposition_attr,
                edit_list_attr,
            ) in disposition_configs:
                self._enrich_disposition_and_edits(
                    result,
                    disposition_type_id,
                    disposition_attr,
                    edit_list_attr,
                    internal_version,
                )

            for item in result.reason_for_visit_diagnosis_code_list:
                if item.diagnosis:
                    diagnosis_desc = self.ioce_component.getDiagnosisDescription(
                        item.diagnosis, internal_version
                    )
                    item.description = str(diagnosis_desc) if diagnosis_desc else ""

                if item.edit_list:
                    for edit in item.edit_list:
                        edit_desc = self.ioce_component.getEditDescription(
                            str(int(edit.edit)), internal_version
                        )
                        edit.description = str(edit_desc) if edit_desc else ""

            # Get line item descriptions
            for i, line in enumerate(result.line_item_list):
                if line.hcpcs:
                    hcpcs_desc = self.ioce_component.getHcpcsDescription(
                        line.hcpcs, internal_version
                    )
                    line.hcpcs_description = str(hcpcs_desc) if hcpcs_desc else ""

                if line.hcpcs_apc:
                    apc_desc = self.ioce_component.getApcDescription(
                        line.hcpcs_apc, internal_version
                    )
                    line.hcpcs_apc_description = str(apc_desc) if apc_desc else ""

                if line.payment_apc:
                    payment_apc_desc = self.ioce_component.getApcDescription(
                        line.payment_apc, internal_version
                    )
                    line.payment_apc_description = (
                        str(payment_apc_desc) if payment_apc_desc else ""
                    )

                if line.status_indicator:
                    status_desc = self.ioce_component.getStatusIndicatorDescription(
                        line.status_indicator, internal_version
                    )
                    line.status_indicator_description = (
                        str(status_desc) if status_desc else ""
                    )

                if line.hcpcs_edit_list:
                    for item in line.hcpcs_edit_list:
                        edit_desc = self.ioce_component.getEditDescription(
                            str(int(item.edit)), internal_version
                        )
                        item.description = str(edit_desc) if edit_desc else ""

                if line.revenue_edit_list:
                    for item in line.revenue_edit_list:
                        edit_desc = self.ioce_component.getEditDescription(
                            str(int(item.edit)), internal_version
                        )
                        item.description = str(edit_desc) if edit_desc else ""

                if line.service_date_edit_list:
                    for item in line.service_date_edit_list:
                        edit_desc = self.ioce_component.getEditDescription(
                            str(int(item.edit)), internal_version
                        )
                        item.description = str(edit_desc) if edit_desc else ""

                if line.hcpcs_modifier_input_list:
                    for item in line.hcpcs_modifier_input_list:
                        if item.edit_list:
                            for edit in item.edit_list:
                                edit_desc = self.ioce_component.getEditDescription(
                                    str(int(edit.edit)), internal_version
                                )
                                edit.description = str(edit_desc) if edit_desc else ""

                if line.hcpcs_modifier_output_list:
                    for item in line.hcpcs_modifier_output_list:
                        if item.edit_list:
                            for edit in item.edit_list:
                                edit_desc = self.ioce_component.getEditDescription(
                                    str(int(edit.edit)), internal_version
                                )
                                edit.description = str(edit_desc) if edit_desc else ""

                if line.packaging_flag:
                    flag_desc = self.ioce_component.getPackagingFlagDescription(
                        line.packaging_flag.flag, internal_version
                    )
                    line.packaging_flag.description = (
                        str(flag_desc) if flag_desc else ""
                    )

                if line.payment_adjustment_flag01:
                    flag_desc = self.ioce_component.getPaymentAdjustmentFlagDescription(
                        line.payment_adjustment_flag01.flag, internal_version
                    )
                    line.payment_adjustment_flag01.description = (
                        str(flag_desc) if flag_desc else ""
                    )

                if line.payment_adjustment_flag02:
                    flag_desc = self.ioce_component.getPaymentAdjustmentFlagDescription(
                        line.payment_adjustment_flag02.flag, internal_version
                    )
                    line.payment_adjustment_flag02.description = (
                        str(flag_desc) if flag_desc else ""
                    )

            # Get diagnosis descriptions
            if result.principal_diagnosis_code.diagnosis:
                principal_desc = self.ioce_component.getDiagnosisDescription(
                    result.principal_diagnosis_code.diagnosis, internal_version
                )
                result.principal_diagnosis_code.description = (
                    str(principal_desc) if principal_desc else ""
                )

                for item in result.principal_diagnosis_code.edit_list:
                    edit_desc = self.ioce_component.getEditDescription(
                        str(int(item.edit)), internal_version
                    )
                    item.description = str(edit_desc) if edit_desc else ""

            if result.secondary_diagnosis_code_list:
                for item in result.secondary_diagnosis_code_list:
                    if item.diagnosis:
                        diagnosis_desc = self.ioce_component.getDiagnosisDescription(
                            item.diagnosis, internal_version
                        )
                        item.description = str(diagnosis_desc) if diagnosis_desc else ""

                    if item.edit_list:
                        for edit in item.edit_list:
                            edit_desc = self.ioce_component.getEditDescription(
                                str(int(edit.edit)), internal_version
                            )
                            edit.description = str(edit_desc) if edit_desc else ""

        except Exception as e:
            print(f"Warning: Could not retrieve some descriptions: {e}")

        return result
