from datetime import datetime

import jpype

from myelin.helpers.utils import handle_java_exceptions
from myelin.input.claim import Claim
from myelin.plugins import apply_client_methods, run_client_load_classes

from .mce_output import MceOutput


class MceClient:
    def __init__(self):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using MceClient."
            )
        self.load_enums()
        self.load_classes()
        try:
            run_client_load_classes(self)
        except Exception:
            pass
        try:
            apply_client_methods(self)
        except Exception:
            pass

    def load_enums(self) -> None:
        self.icd_vers = jpype.JClass("gov.cms.editor.mce.component.edit.Const")
        self.edit_enum = jpype.JClass("gov.cms.editor.mce.model.enums.Edit")
        self.edit_type_enum = jpype.JClass("gov.cms.editor.mce.model.enums.EditType")

    def load_classes(self) -> None:
        self.mce_record = jpype.JClass("gov.cms.editor.mce.transfer.MceRecord")
        self.mce_output = jpype.JClass("gov.cms.editor.mce.transfer.MceOutput")
        self.mce_dx_class = jpype.JClass("gov.cms.editor.mce.model.MceDiagnosisCode")
        self.mce_pr_class = jpype.JClass("gov.cms.editor.mce.model.MceProcedureCode")
        self.java_list = jpype.JClass("java.util.List")
        self.mce_component_class = jpype.JClass("gov.cms.editor.mce.MceComponent")
        self.mce_component = self.mce_component_class()
        self.java_int = jpype.JClass("java.lang.Integer")

    def calculate_los(self, claim: Claim) -> int:
        if isinstance(claim.from_date, str):
            from_date = datetime.strptime(claim.from_date, "%Y-%m-%d")
        elif isinstance(claim.from_date, datetime):
            from_date = claim.from_date
        else:
            raise ValueError("from_date must be a string or datetime object")
        if isinstance(claim.thru_date, str):
            thru_date = datetime.strptime(claim.thru_date, "%Y-%m-%d")
        elif isinstance(claim.thru_date, datetime):
            thru_date = claim.thru_date
        else:
            raise ValueError("thru_date must be a string or datetime object")
        return (thru_date - from_date).days + 1 if thru_date >= from_date else 1

    def create_input(self, claim: Claim) -> jpype.JObject | None:
        if claim.patient_status is None or not claim.patient_status.isnumeric():
            raise ValueError(
                "Invalid Patient Discharge Status given for MCE processing."
            )

        mce_record = self.mce_record.builder()
        mce_record.withIcdVersion(self.icd_vers.ICD_10)
        if str(claim.patient_status).isnumeric():
            mce_record.withDischargeStatus(self.java_int(int(claim.patient_status)))
        if claim.patient is not None:
            mce_record.withAgeYears(
                self.java_int(claim.patient.age)
                if claim.patient.age is not None
                else self.java_int(0)
            )
            if str(claim.patient.sex).upper().startswith("M"):
                mce_record.withSex(self.java_int(1))
            else:
                mce_record.withSex(self.java_int(2))
        if claim.los > 0:
            mce_record.withLengthOfStay(self.java_int(claim.los))
        else:
            mce_record.withLengthOfStay(self.java_int(self.calculate_los(claim)))

        if claim.admit_dx:
            mce_record.withAdmitDiagnosis(
                self.mce_dx_class(claim.admit_dx.code.replace(".", ""))
            )

        if isinstance(claim.thru_date, str):
            discharge_date = datetime.strptime(claim.thru_date, "%Y-%m-%d").strftime(
                "%Y%m%d"
            )
            mce_record.withDischargeDate(discharge_date)
        elif isinstance(claim.thru_date, datetime):
            discharge_date = claim.thru_date.strftime("%Y%m%d")
            mce_record.withDischargeDate(discharge_date)
        else:
            raise ValueError("thru_date must be a string or datetime object")
        mce_record = mce_record.build()
        if claim.principal_dx:
            mce_record.addCode(
                self.mce_dx_class(claim.principal_dx.code.replace(".", ""))
            )
        for dx in claim.secondary_dxs:
            mce_record.addCode(self.mce_dx_class(dx.code.replace(".", "")))
        for pr in claim.inpatient_pxs:
            mce_record.addCode(self.mce_pr_class(pr.code.replace(".", "")))
        return mce_record

    @handle_java_exceptions
    def process(self, claim: Claim) -> MceOutput:
        mce_input = self.create_input(claim)
        if not mce_input:
            raise RuntimeError("Failed to create MCE input")
        self.mce_component.process(mce_input)
        java_output = mce_input.getMceOutput()
        mce_output = MceOutput()
        mce_output.from_java(java_output, mce_input)
        return mce_output
