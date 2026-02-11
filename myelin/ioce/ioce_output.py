from datetime import datetime

from pydantic import BaseModel, Field
from typing_extensions import override

# Provides stubs during TYPE_CHECKING and protocol classes at runtime
from myelin.ioce.ioce_types import (
    OceClaim,
    OceLineItem,
    OceDiagnosisCode,
    OceHcpcsModifier,
    OceValueCode,
    OceProcessingInformation,
)
from myelin.helpers.utils import JavaRuntimeError


class IoceReturnCode(BaseModel):
    """Return code information"""

    code: int = 0
    description: str = ""


class IoceOutputEdit(BaseModel):
    """Output for edits"""

    edit: str = ""
    description: str = ""


class IoceOutputFlag(BaseModel):
    """Output for flags"""

    flag: str = ""
    description: str = ""


def datestr_to_datetime(date_str: str) -> datetime:
    """Convert a date string to a datetime object."""
    try:
        return datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise JavaRuntimeError(
                code="JERR_INVALID_DATE",
                description="Invalid date format",
                explanation=f"Invalid date format: {date_str}",
            )


def java_string_to_int(java_string: str) -> int | None:
    """Convert a Java-style string to an integer."""
    try:
        return int(java_string)
    except (ValueError, TypeError):
        return None


def java_string_to_float(java_string: str) -> float | None:
    """Convert a Java-style string to a float."""
    try:
        return float(java_string)
    except (ValueError, TypeError):
        return None


class IoceProcessingInformation(BaseModel):
    """Processing information from IOCE output"""

    claim_id: str = ""
    return_code: IoceReturnCode = Field(default_factory=IoceReturnCode)
    lines_processed: int = 0
    internal_version: int = 0
    version: str = ""
    time_started: int = 0
    time_ended: int = 0
    debug_flag: str = ""
    comment_data: str = ""

    def from_java(
        self, java_obj: OceProcessingInformation | None
    ) -> "IoceProcessingInformation":
        if not java_obj:
            return self

        self.claim_id = str(java_obj.getClaimId()) if java_obj.getClaimId() else ""
        self.return_code.code = (
            java_obj.getReturnCode() if java_obj.getReturnCode() else 0
        )
        self.lines_processed = (
            java_obj.getLinesProcessed() if java_obj.getLinesProcessed() else 0
        )
        self.internal_version = (
            java_obj.getInternalVersion()
            if hasattr(java_obj, "getInternalVersion")
            else 0
        )
        self.version = str(java_obj.getVersion()) if java_obj.getVersion() else ""
        self.time_started = (
            java_obj.getTimeStarted() if java_obj.getTimeStarted() else 0
        )
        self.time_ended = java_obj.getTimeEnded() if java_obj.getTimeEnded() else 0
        self.debug_flag = (
            str(java_obj.getDebugFlag()) if java_obj.getDebugFlag() else ""
        )
        self.comment_data = (
            str(java_obj.getCommentData()) if java_obj.getCommentData() else ""
        )
        return self


class IoceOutputDiagnosisCode(BaseModel):
    """Output for diagnosis codes with associated edits"""

    diagnosis: str = ""
    description: str = ""
    present_on_admission: str = ""
    edit_list: list[IoceOutputEdit] = Field(default_factory=list)

    def from_java(self, java_obj: OceDiagnosisCode | None) -> "IoceOutputDiagnosisCode":
        if not java_obj:
            return self

        self.diagnosis = str(java_obj.getDiagnosis()) if java_obj.getDiagnosis() else ""
        self.present_on_admission = (
            str(java_obj.getPresentOnAdmission())
            if java_obj.getPresentOnAdmission()
            else ""
        )

        self.edit_list = []
        if hasattr(java_obj, "getEditList") and java_obj.getEditList():
            for edit in java_obj.getEditList():
                self.edit_list.append(IoceOutputEdit(edit=str(edit)))

        return self


class IoceOutputHcpcsModifier(BaseModel):
    """Output for HCPCS modifiers with associated edits"""

    hcpcs_modifier: str = ""
    edit_list: list[IoceOutputEdit] = Field(default_factory=list)

    def from_java(self, java_obj: OceHcpcsModifier | None) -> "IoceOutputHcpcsModifier":
        if not java_obj:
            return self

        self.hcpcs_modifier = (
            str(java_obj.getHcpcsModifier()) if java_obj.getHcpcsModifier() else ""
        )

        self.edit_list = []
        if hasattr(java_obj, "getEditList") and java_obj.getEditList():
            for edit in java_obj.getEditList():
                self.edit_list.append(IoceOutputEdit(edit=str(edit)))
        return self


class IoceOutputValueCode(BaseModel):
    """Output for value codes"""

    code: str = ""
    value: str = ""

    def from_java(self, java_obj: OceValueCode | None) -> "IoceOutputValueCode":
        if not java_obj:
            return self

        self.code = str(java_obj.getCode()) if java_obj.getCode() else ""
        self.value = str(java_obj.getValue()) if java_obj.getValue() else ""
        return self


class IoceOutputLineItem(BaseModel):
    """Output for line items with all OPPS processing results"""

    service_date: datetime | None = None
    revenue_code: str = ""
    hcpcs: str = ""
    hcpcs_description: str = ""
    units_input: int | None = None
    charge: float | None = None
    action_flag_input: str = ""

    action_flag_output: str = ""
    rejection_denial_flag: str = ""
    payment_method_flag: str = ""
    hcpcs_apc: str = ""
    hcpcs_apc_description: str = ""
    payment_apc: str = ""
    payment_apc_description: str = ""
    units_output: int | None = None
    status_indicator: str = ""
    status_indicator_description: str = ""
    payment_indicator: str = ""
    packaging_flag: IoceOutputFlag = Field(default_factory=IoceOutputFlag)
    payment_adjustment_flag01: IoceOutputFlag = Field(default_factory=IoceOutputFlag)
    payment_adjustment_flag02: IoceOutputFlag = Field(default_factory=IoceOutputFlag)
    discounting_formula: int | None = None
    composite_adjustment_flag: str = ""

    hcpcs_modifier_input_list: list[IoceOutputHcpcsModifier] = Field(
        default_factory=list
    )
    hcpcs_modifier_output_list: list[IoceOutputHcpcsModifier] = Field(
        default_factory=list
    )

    hcpcs_edit_list: list[IoceOutputEdit] = Field(default_factory=list)
    revenue_edit_list: list[IoceOutputEdit] = Field(default_factory=list)
    service_date_edit_list: list[IoceOutputEdit] = Field(default_factory=list)

    def from_java(self, java_obj: OceLineItem | None) -> "IoceOutputLineItem":
        if not java_obj:
            return self

        self.service_date = (
            datestr_to_datetime(str(java_obj.getServiceDate()))
            if java_obj.getServiceDate()
            else None
        )
        self.revenue_code = (
            str(java_obj.getRevenueCode()) if java_obj.getRevenueCode() else ""
        )
        self.hcpcs = str(java_obj.getHcpcs()) if java_obj.getHcpcs() else ""
        self.units_input = java_string_to_int(
            str(java_obj.getUnitsInput()) if java_obj.getUnitsInput() else ""
        )
        self.charge = java_string_to_float(
            str(java_obj.getCharge()) if java_obj.getCharge() else ""
        )
        self.action_flag_input = (
            str(java_obj.getActionFlagInput()) if java_obj.getActionFlagInput() else ""
        )

        self.action_flag_output = (
            str(java_obj.getActionFlagOutput())
            if java_obj.getActionFlagOutput()
            else ""
        )
        self.rejection_denial_flag = (
            str(java_obj.getRejectionDenialFlag())
            if java_obj.getRejectionDenialFlag()
            else ""
        )
        self.payment_method_flag = (
            str(java_obj.getPaymentMethodFlag())
            if java_obj.getPaymentMethodFlag()
            else ""
        )
        self.hcpcs_apc = str(java_obj.getHcpcsApc()) if java_obj.getHcpcsApc() else ""
        self.payment_apc = (
            str(java_obj.getPaymentApc()) if java_obj.getPaymentApc() else ""
        )
        self.units_output = java_string_to_int(
            str(java_obj.getUnitsOutput()) if java_obj.getUnitsOutput() else ""
        )
        self.status_indicator = (
            str(java_obj.getStatusIndicator()) if java_obj.getStatusIndicator() else ""
        )
        self.payment_indicator = (
            str(java_obj.getPaymentIndicator())
            if java_obj.getPaymentIndicator()
            else ""
        )
        self.discounting_formula = java_string_to_int(
            str(java_obj.getDiscountingFormula())
            if java_obj.getDiscountingFormula()
            else ""
        )
        self.composite_adjustment_flag = (
            str(java_obj.getCompositeAdjustmentFlag())
            if java_obj.getCompositeAdjustmentFlag()
            else ""
        )

        self.hcpcs_modifier_input_list = []
        if (
            hasattr(java_obj, "getHcpcsModifierInputList")
            and java_obj.getHcpcsModifierInputList()
        ):
            for modifier in java_obj.getHcpcsModifierInputList():
                self.hcpcs_modifier_input_list.append(
                    IoceOutputHcpcsModifier().from_java(modifier)
                )

        self.hcpcs_modifier_output_list = []
        if (
            hasattr(java_obj, "getHcpcsModifierOutputList")
            and java_obj.getHcpcsModifierOutputList()
        ):
            for modifier in java_obj.getHcpcsModifierOutputList():
                self.hcpcs_modifier_output_list.append(
                    IoceOutputHcpcsModifier().from_java(modifier)
                )

        self.hcpcs_edit_list = []
        if hasattr(java_obj, "getHcpcsEditList") and java_obj.getHcpcsEditList():
            for edit in java_obj.getHcpcsEditList():
                self.hcpcs_edit_list.append(IoceOutputEdit(edit=str(edit)))

        self.revenue_edit_list = []
        if hasattr(java_obj, "getRevenueEditList") and java_obj.getRevenueEditList():
            for edit in java_obj.getRevenueEditList():
                self.revenue_edit_list.append(IoceOutputEdit(edit=str(edit)))

        self.service_date_edit_list = []
        if (
            hasattr(java_obj, "getServiceDateEditList")
            and java_obj.getServiceDateEditList()
        ):
            for edit in java_obj.getServiceDateEditList():
                self.service_date_edit_list.append(IoceOutputEdit(edit=str(edit)))

        if hasattr(java_obj, "getPackagingFlag") and java_obj.getPackagingFlag():
            self.packaging_flag.flag = (
                str(java_obj.getPackagingFlag()) if java_obj.getPackagingFlag() else ""
            )

        if (
            hasattr(java_obj, "getPaymentAdjustmentFlag01")
            and java_obj.getPaymentAdjustmentFlag01()
        ):
            self.payment_adjustment_flag01.flag = (
                str(java_obj.getPaymentAdjustmentFlag01())
                if java_obj.getPaymentAdjustmentFlag01()
                else ""
            )

        if (
            hasattr(java_obj, "getPaymentAdjustmentFlag02")
            and java_obj.getPaymentAdjustmentFlag02()
        ):
            self.payment_adjustment_flag02.flag = (
                str(java_obj.getPaymentAdjustmentFlag02())
                if java_obj.getPaymentAdjustmentFlag02()
                else ""
            )

        return self


class IoceOutput(BaseModel):
    """Main OPPS output class containing all processing results"""

    processing_information: IoceProcessingInformation = Field(
        default_factory=IoceProcessingInformation
    )

    version: str = ""
    claim_processed_flag: str = ""
    claim_processed_flag_description: str = ""
    apc_return_buffer_flag: str = ""
    nopps_bill_flag: str = ""

    claim_disposition: str = ""
    claim_disposition_description: str = ""
    claim_disposition_value_description: str = ""
    claim_rejection_disposition: str = ""
    claim_rejection_disposition_description: str = ""
    claim_rejection_disposition_value_description: str = ""
    claim_rejection_edit_list: list[IoceOutputEdit] = Field(default_factory=list)

    claim_denial_disposition: str = ""
    claim_denial_disposition_description: str = ""
    claim_denial_disposition_value_description: str = ""
    claim_denial_edit_list: list[IoceOutputEdit] = Field(default_factory=list)

    claim_return_to_provider_disposition: str = ""
    claim_return_to_provider_disposition_description: str = ""
    claim_return_to_provider_disposition_value_description: str = ""
    claim_return_to_provider_edit_list: list[IoceOutputEdit] = Field(
        default_factory=list
    )

    claim_suspension_disposition: str = ""
    claim_suspension_disposition_description: str = ""
    claim_suspension_disposition_value_description: str = ""
    claim_suspension_edit_list: list[IoceOutputEdit] = Field(default_factory=list)

    line_rejection_disposition: str = ""
    line_rejection_disposition_description: str = ""
    line_rejection_disposition_value_description: str = ""
    line_rejection_edit_list: list[IoceOutputEdit] = Field(default_factory=list)

    line_denial_disposition: str = ""
    line_denial_disposition_description: str = ""
    line_denial_disposition_value_description: str = ""
    line_denial_edit_list: list[IoceOutputEdit] = Field(default_factory=list)

    condition_code_output_list: list[str] = Field(default_factory=list)
    value_code_output_list: list[IoceOutputValueCode] = Field(default_factory=list)

    principal_diagnosis_code: IoceOutputDiagnosisCode = Field(
        default_factory=IoceOutputDiagnosisCode
    )
    reason_for_visit_diagnosis_code_list: list[IoceOutputDiagnosisCode] = Field(
        default_factory=list
    )
    secondary_diagnosis_code_list: list[IoceOutputDiagnosisCode] = Field(
        default_factory=list
    )

    line_item_list: list[IoceOutputLineItem] = Field(default_factory=list)

    def from_java(self, java_claim: OceClaim | None) -> "IoceOutput":
        """Extract all output data from the processed Java OceClaim object"""
        if not java_claim:
            return self

        try:
            if (
                hasattr(java_claim, "getProcessingInformation")
                and java_claim.getProcessingInformation()
            ):
                _ = self.processing_information.from_java(
                    java_claim.getProcessingInformation()
                )

            self.version = (
                str(java_claim.getVersion()) if java_claim.getVersion() else ""
            )
            self.claim_processed_flag = (
                str(java_claim.getClaimProcessedFlag())
                if java_claim.getClaimProcessedFlag()
                else ""
            )
            self.apc_return_buffer_flag = (
                str(java_claim.getApcReturnBufferFlag())
                if java_claim.getApcReturnBufferFlag()
                else ""
            )
            self.nopps_bill_flag = (
                str(java_claim.getNoppsBillFlag())
                if java_claim.getNoppsBillFlag()
                else ""
            )

            self.claim_disposition = (
                str(java_claim.getClaimDisposition())
                if java_claim.getClaimDisposition()
                else ""
            )
            self.claim_rejection_disposition = (
                str(java_claim.getClaimRejectionDisposition())
                if java_claim.getClaimRejectionDisposition()
                else ""
            )
            self.claim_denial_disposition = (
                str(java_claim.getClaimDenialDisposition())
                if java_claim.getClaimDenialDisposition()
                else ""
            )
            self.claim_return_to_provider_disposition = (
                str(java_claim.getClaimReturnToProviderDisposition())
                if java_claim.getClaimReturnToProviderDisposition()
                else ""
            )
            self.claim_suspension_disposition = (
                str(java_claim.getClaimSuspensionDisposition())
                if java_claim.getClaimSuspensionDisposition()
                else ""
            )
            self.line_rejection_disposition = (
                str(java_claim.getLineRejectionDisposition())
                if java_claim.getLineRejectionDisposition()
                else ""
            )
            self.line_denial_disposition = (
                str(java_claim.getLineDenialDisposition())
                if java_claim.getLineDenialDisposition()
                else ""
            )

            self.claim_rejection_edit_list = []
            if (
                hasattr(java_claim, "getClaimRejectionEditList")
                and java_claim.getClaimRejectionEditList()
            ):
                for edit in java_claim.getClaimRejectionEditList():
                    self.claim_rejection_edit_list.append(
                        IoceOutputEdit(edit=str(edit))
                    )

            self.claim_denial_edit_list = []
            if (
                hasattr(java_claim, "getClaimDenialEditList")
                and java_claim.getClaimDenialEditList()
            ):
                for edit in java_claim.getClaimDenialEditList():
                    self.claim_denial_edit_list.append(IoceOutputEdit(edit=str(edit)))

            self.claim_return_to_provider_edit_list = []
            if (
                hasattr(java_claim, "getClaimReturnToProviderEditList")
                and java_claim.getClaimReturnToProviderEditList()
            ):
                for edit in java_claim.getClaimReturnToProviderEditList():
                    self.claim_return_to_provider_edit_list.append(
                        IoceOutputEdit(edit=str(edit))
                    )

            self.claim_suspension_edit_list = []
            if (
                hasattr(java_claim, "getClaimSuspensionEditList")
                and java_claim.getClaimSuspensionEditList()
            ):
                for edit in java_claim.getClaimSuspensionEditList():
                    self.claim_suspension_edit_list.append(
                        IoceOutputEdit(edit=str(edit))
                    )

            self.line_rejection_edit_list = []
            if (
                hasattr(java_claim, "getLineRejectionEditList")
                and java_claim.getLineRejectionEditList()
            ):
                for edit in java_claim.getLineRejectionEditList():
                    self.line_rejection_edit_list.append(IoceOutputEdit(edit=str(edit)))

            self.line_denial_edit_list = []
            if (
                hasattr(java_claim, "getLineDenialEditList")
                and java_claim.getLineDenialEditList()
            ):
                for edit in java_claim.getLineDenialEditList():
                    self.line_denial_edit_list.append(IoceOutputEdit(edit=str(edit)))

            self.condition_code_output_list = []
            if (
                hasattr(java_claim, "getConditionCodeOutputList")
                and java_claim.getConditionCodeOutputList()
            ):
                for code in java_claim.getConditionCodeOutputList():
                    self.condition_code_output_list.append(str(code))

            self.value_code_output_list = []
            if (
                hasattr(java_claim, "getValueCodeOutputList")
                and java_claim.getValueCodeOutputList()
            ):
                for value_code in java_claim.getValueCodeOutputList():
                    val_code = IoceOutputValueCode().from_java(value_code)
                    if val_code.code != "" or val_code.value != "":
                        self.value_code_output_list.append(val_code)

            if (
                hasattr(java_claim, "getPrincipalDiagnosisCode")
                and java_claim.getPrincipalDiagnosisCode()
            ):
                _ = self.principal_diagnosis_code.from_java(
                    java_claim.getPrincipalDiagnosisCode()
                )

            self.reason_for_visit_diagnosis_code_list = []
            if (
                hasattr(java_claim, "getReasonForVisitDiagnosisCodeList")
                and java_claim.getReasonForVisitDiagnosisCodeList()
            ):
                for dx in java_claim.getReasonForVisitDiagnosisCodeList():
                    self.reason_for_visit_diagnosis_code_list.append(
                        IoceOutputDiagnosisCode().from_java(dx)
                    )

            self.secondary_diagnosis_code_list = []
            if (
                hasattr(java_claim, "getSecondaryDiagnosisCodeList")
                and java_claim.getSecondaryDiagnosisCodeList()
            ):
                for dx in java_claim.getSecondaryDiagnosisCodeList():
                    self.secondary_diagnosis_code_list.append(
                        IoceOutputDiagnosisCode().from_java(dx)
                    )

            self.line_item_list = []
            if hasattr(java_claim, "getLineItemList") and java_claim.getLineItemList():
                for line in java_claim.getLineItemList():
                    self.line_item_list.append(IoceOutputLineItem().from_java(line))

        except Exception as e:
            print(f"Warning: Could not extract some OPPS output fields: {e}")

        return self

    @override
    def __str__(self):
        return f"IoceOutput(return_code={self.processing_information.return_code}, lines_processed={self.processing_information.lines_processed})"

    @override
    def __repr__(self):
        return self.__str__()
