from datetime import datetime

import jpype

from myelin.helpers.utils import handle_java_exceptions
from myelin.input.claim import (
    PoaType,
)
from myelin.ioce.ioce_output import IoceOutput
from myelin.plugins import apply_client_methods, run_client_load_classes


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

    def load_classes(self):
        """Load all required Java classes and components"""
        try:
            # Main component classes
            self.ioce_component_class = jpype.JClass("gov.cms.oce.IoceComponent")
            self.ioce_claim_class = jpype.JClass("gov.cms.oce.IoceClaim")

            # External model classes
            self.oce_claim_factory_class = jpype.JClass(
                "gov.cms.oce.model.external.OceClaimFactory"
            )
            self.oce_claim_class = jpype.JClass("gov.cms.oce.model.external.OceClaim")
            self.oce_line_item_class = jpype.JClass(
                "gov.cms.oce.model.external.OceLineItem"
            )
            self.oce_diagnosis_code_class = jpype.JClass(
                "gov.cms.oce.model.external.OceDiagnosisCode"
            )
            self.oce_hcpcs_modifier_class = jpype.JClass(
                "gov.cms.oce.model.external.OceHcpcsModifier"
            )
            self.oce_value_code_class = jpype.JClass(
                "gov.cms.oce.model.external.OceValueCode"
            )
            self.oce_processing_info_class = jpype.JClass(
                "gov.cms.oce.model.external.OceProcessingInformation"
            )

            # Initialize factory and component
            self.factory = self.oce_claim_factory_class.getInstance()
            self.ioce_component = self.ioce_component_class()

        except Exception as e:
            raise RuntimeError(f"Failed to initialize Ioce Java classes: {e}")

    def format_date(self, date_input):
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
        elif isinstance(date_input, datetime):
            return date_input.strftime("%Y%m%d")
        else:
            raise ValueError(f"Unsupported date type: {type(date_input)}")

    def format_age(self, age):
        """Format age as 3-digit string"""
        if age is None:
            return "000"
        return f"{int(age):03d}"

    def format_sex(self, sex):
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

    def create_diagnosis_code(self, dx_code):
        """Create Java OceDiagnosisCode from Python DiagnosisCode"""
        if dx_code is None:
            return None

        # Remove periods from diagnosis codes
        clean_code = dx_code.code.replace(".", "")

        # Convert POA to string
        poa_str = "U"  # Default to "U" (unknown)
        if dx_code.poa == PoaType.Y:
            poa_str = "Y"
        elif dx_code.poa == PoaType.N:
            poa_str = "N"
        elif dx_code.poa == PoaType.W:
            poa_str = "W"
        elif dx_code.poa == PoaType.U:
            poa_str = "U"

        return self.factory.createDiagnosisCode(clean_code, poa_str)

    def create_hcpcs_modifier(self, modifier_str):
        """Create Java OceHcpcsModifier from string"""
        if modifier_str is None or modifier_str == "":
            return None
        return self.factory.createHcpcsModifier(str(modifier_str))

    def create_value_code(self, value_code):
        """Create Java OceValueCode from Python ValueCode"""
        if value_code is None:
            return None

        # Format amount as 9-character string with leading zeros
        amount_str = f"{int(value_code.amount * 100):09d}"  # Convert to cents
        return self.factory.createValueCode(value_code.code, amount_str)

    def create_line_item(self, line_item):
        """Create Java OceLineItem from Python LineItem"""
        if line_item is None:
            return None

        java_line = self.factory.createLineItem()

        # Set basic line item fields
        if line_item.service_date:
            java_line.setServiceDate(self.format_date(line_item.service_date))

        if line_item.revenue_code:
            java_line.setRevenueCode(str(line_item.revenue_code))

        if line_item.hcpcs:
            java_line.setHcpcs(str(line_item.hcpcs))

        # Add HCPCS modifiers
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

        return java_line

    def create_oce_claim(self, claim):
        """Create Java OceClaim from Python Claim"""
        # Create the claim object
        oce_claim = self.factory.createClaim()

        # Set claim identifier
        if claim.claimid:
            oce_claim.setClaimId(str(claim.claimid))
        else:
            oce_claim.setClaimId("DEFAULT_CLAIM_ID")

        # Set patient demographics
        if claim.patient:
            oce_claim.setAge(self.format_age(claim.patient.age))
            oce_claim.setSex(self.format_sex(claim.patient.sex))
        else:
            oce_claim.setAge("065")  # Default age
            oce_claim.setSex("0")  # Unknown sex

        # Set dates
        if claim.from_date:
            oce_claim.setDateStarted(self.format_date(claim.from_date))
        if claim.thru_date:
            oce_claim.setDateEnded(self.format_date(claim.thru_date))
        if hasattr(claim, "receipt_date") and claim.receipt_date:
            oce_claim.setReceiptDate(self.format_date(claim.receipt_date))

        # Set bill type (3-character)
        if claim.bill_type:
            bill_type_str = str(claim.bill_type).ljust(3, "0")[
                :3
            ]  # Pad or truncate to 3 chars
            oce_claim.setBillType(bill_type_str)
        else:
            oce_claim.setBillType("131")  # Default outpatient bill type

        # Set patient discharge status (2-character)
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

        # Set provider identifiers
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

        # Add occurrence codes
        if hasattr(claim, "occurrence_codes") and claim.occurrence_codes:
            for occ_code in claim.occurrence_codes:
                if occ_code and occ_code.code:
                    oce_claim.addOccurrenceCodeInput(str(occ_code.code))

        # Add condition codes
        if hasattr(claim, "cond_codes") and claim.cond_codes:
            for cond_code in claim.cond_codes:
                if cond_code:
                    oce_claim.addConditionCodeInput(str(cond_code))

        # Add value codes
        if hasattr(claim, "value_codes") and claim.value_codes:
            for value_code in claim.value_codes:
                if value_code:
                    java_value_code = self.create_value_code(value_code)
                    if java_value_code:
                        oce_claim.addValueCodeInput(java_value_code)

        # Set principal diagnosis
        if claim.principal_dx:
            java_principal_dx = self.create_diagnosis_code(claim.principal_dx)
            if java_principal_dx:
                oce_claim.setPrincipalDiagnosisCode(java_principal_dx)

        # Add reason for visit diagnosis (typically same as principal for outpatient)
        if claim.principal_dx:
            java_rfv_dx = self.create_diagnosis_code(claim.principal_dx)
            if java_rfv_dx:
                oce_claim.addReasonForVisitDiagnosisCode(java_rfv_dx)

        # Add secondary diagnoses
        if claim.secondary_dxs:
            for secondary_dx in claim.secondary_dxs:
                if secondary_dx:
                    java_secondary_dx = self.create_diagnosis_code(secondary_dx)
                    if java_secondary_dx:
                        oce_claim.addSecondaryDiagnosisCode(java_secondary_dx)

        # Add line items
        if claim.lines:
            for line in claim.lines:
                if line:
                    java_line = self.create_line_item(line)
                    if java_line:
                        oce_claim.addLineItem(java_line)

        return oce_claim

    @handle_java_exceptions
    def process(self, claim, include_descriptions: bool = True):
        """Process a claim through IOCE and return IoceOutput"""
        try:
            # Create Java OceClaim from Python claim
            oce_claim = self.create_oce_claim(claim)

            # Create IoceClaim wrapper
            ioce_claim = self.ioce_claim_class(oce_claim)

            # Process the claim
            self.ioce_component.process(ioce_claim)

            # Get the processed model back
            processed_model = ioce_claim.getModel()

            # Extract output
            Ioce_output = IoceOutput()
            Ioce_output.from_java(processed_model)

            # Append descriptions
            if include_descriptions:
                Ioce_output = self.append_descriptions(Ioce_output)

            return Ioce_output

        except Exception as e:
            raise RuntimeError(f"Error processing Ioce claim {claim.claimid}: {e}")

    def _enrich_disposition_and_edits(
        self,
        result,
        disposition_type_id: str,
        disposition_attr: str,
        edit_list_attr: str,
        internal_version: int,
    ):
        """
        Generic function to enrich disposition and edit descriptions.

        Args:
            result: The result object to enrich
            disposition_type_id: The disposition type ID (e.g., "1", "2", "3", etc.)
            disposition_attr: The disposition attribute name (e.g., "claim_disposition")
            edit_list_attr: The edit list attribute name (e.g., "claim_rejection_edit_list")
            internal_version: The internal version for lookups
        """
        disposition_value = getattr(result, disposition_attr, None)
        if disposition_value:
            # Get disposition description
            disp_desc = self.ioce_component.getClaimDispositionDescription(
                disposition_type_id, internal_version
            )
            setattr(
                result,
                f"{disposition_attr}_description",
                str(disp_desc) if disp_desc else "",
            )

            # Get disposition value description
            disp_value_desc = self.ioce_component.getClaimDispositionValueDescription(
                disposition_type_id, disposition_value, internal_version
            )
            setattr(
                result,
                f"{disposition_attr}_value_description",
                str(disp_value_desc) if disp_value_desc else "",
            )

            # Enrich edit descriptions
            edit_list = getattr(result, edit_list_attr, [])
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
            if result.processing_information.return_code.code is not None:
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
