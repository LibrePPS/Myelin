from datetime import datetime

import jpype

from myelin.helpers.utils import (
    handle_java_exceptions,
    py_date_to_java_date,
    JavaRuntimeError,
)
from myelin.input import IrfPai
from myelin.input.claim import (
    Claim,
)
from myelin.plugins import apply_client_methods, run_client_load_classes

from .irfg_output import IrfgOutput

ASSESSMENT_TAGS: dict[str, str] = {
    "eating_self_admsn_cd": "GG0130A1",
    "oral_hygne_admsn_cd": "GG0130B1",
    "toileting_hygne_admsn_cd": "GG0130C1",
    "bathing_hygne_admsn_cd": "GG0130E1",
    "upper_body_dressing_cd": "GG0130F1",
    "lower_body_dressing_cd": "GG0130G1",
    "footwear_dressing_cd": "GG0130H1",
    "sit_to_lying_cd": "GG0170B1",
    "lying_to_sit_cd": "GG0170C1",
    "sit_to_stand_cd": "GG0170D1",
    "chair_bed_transfer_cd": "GG0170E1",
    "toilet_transfer_cd": "GG0170F1",
    "walk_10_feet_cd": "GG0170G1",
    "walk_50_feet_cd": "GG0170H1",
    "walk_150_feet_cd": "GG0170I1",
    "step_1_cd": "GG0170M1",
    "urinary_continence_cd": "H0350",
    "bowel_continence_cd": "H0400",
}


class IrfgClient:
    def __init__(self):
        """
        DrgClient class is responsible for interacting with the CMS Java based DRG system.
        The Client will load the necessary Java classes and convert from Python objects to Java objects.
        """
        if not jpype.isJVMStarted():
            raise RuntimeError("JVM is not started")
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
        """
        Load the necessary Java classes for the DRG client.
        """
        self.cmg_grouper_class = jpype.JClass("gov.cms.grouper.irf.app.Cmg")
        self.irf_claim_class = jpype.JClass("gov.cms.grouper.irf.transfer.IrfClaim")
        self.assessment_class = jpype.JClass("gov.cms.grouper.irf.transfer.Assessment")
        self.java_integer_class = jpype.JClass("java.lang.Integer")
        self.java_big_decimal_class = jpype.JClass("java.math.BigDecimal")
        self.java_string_class = jpype.JClass("java.lang.String")
        self.array_list_class = jpype.JClass("java.util.ArrayList")
        self.java_date_class = jpype.JClass("java.time.LocalDate")
        self.java_data_formatter = jpype.JClass("java.time.format.DateTimeFormatter")
        self.pai_class = jpype.JClass("gov.cms.grouper.irf.model.Pai")
        self.dx_code_class = jpype.JClass(
            "com.mmm.his.cer.foundation.model.DiagnosisCode"
        )

    def py_date_to_java_date(self, py_date: datetime | None) -> jpype.JObject | None:
        """
        Convert a Python date object to a Java LocalDate object.
        """
        if py_date is None:
            return None
        return py_date_to_java_date(self, py_date)

    def create_assessments(self, pai: IrfPai) -> jpype.JObject | None:
        """
        Create a list of Assessment Java objects from the given IrfPai object.

        Java constructor:
            public Assessment(String name, String item, String value)
        The item parameter is what matters, it's tied to the form location on IRF-PAI data spec.
        The name parameter doesn't seem to be used within the CMG Grouper but we provide for completeness.
        """
        assessment_list = self.array_list_class()
        for tag, code in ASSESSMENT_TAGS.items():
            value = getattr(pai, tag, None)
            if value is not None:
                assessment = self.assessment_class(code, code, value)
                assessment_list.add(assessment)
        return assessment_list

    def create_claim_input(self, claim: Claim) -> jpype.JObject | None:
        """
        Create a new IrfClaim Java object.
        """
        if not claim.irf_pai:
            raise JavaRuntimeError(
                code="JERR_INVALID_DATE",
                description="Invalid date format",
                explanation="IRF-PAI assessment data is required for IRF claims",
            )
        claim_obj = self.irf_claim_class()
        claim_obj.setAssessmentSystem(claim.irf_pai.assessment_system)
        claim_obj.setTransactionType(claim.irf_pai.transaction_type)
        if not claim.patient:
            raise JavaRuntimeError(
                code="JERR_INVALID_DATE",
                description="Invalid date format",
                explanation="Patient information is required for IRF claims",
            )
        claim_obj.setBirthDate(self.py_date_to_java_date(claim.patient.date_of_birth))
        claim_obj.setAdmissionDate(self.py_date_to_java_date(claim.admit_date))
        claim_obj.setImpairmentGroup(claim.irf_pai.impairment_admit_group_code)
        claim_obj.setDischargeDate(self.py_date_to_java_date(claim.thru_date))
        dx_idx = 0
        # Do not strip decimal points out of Dx Codes, CMS's CMG Grouper validates the pattern of ICD-10 codes
        if claim.principal_dx:
            claim_obj.addCode(self.dx_code_class(claim.principal_dx.code.ljust(8, "^")))
            dx_idx += 1
        while dx_idx < len(claim.secondary_dxs) and dx_idx < 25:
            if claim.secondary_dxs[dx_idx]:
                claim_obj.addCode(
                    self.dx_code_class(claim.secondary_dxs[dx_idx].code.ljust(8, "^"))
                )
            dx_idx += 1
        assessments = self.create_assessments(claim.irf_pai)
        if assessments:
            claim_obj.setAssessments(assessments)
        return claim_obj

    @handle_java_exceptions
    def process(self, claim: Claim) -> IrfgOutput:
        """
        Process the given claim and return the DRG output.
        """
        if not claim:
            raise JavaRuntimeError(
                code="JERR_INVALID_DATE",
                description="Invalid date format",
                explanation="Claim cannot be None",
            )
        claim_input = self.create_claim_input(claim)
        if not claim_input:
            raise JavaRuntimeError(
                code="JERR_INVALID_DATE",
                description="Invalid date format",
                explanation="Failed to create claim input for IRF Grouper",
            )
        grouper = self.cmg_grouper_class()
        try:
            grouper.process(claim_input)
        except jpype.JException as ex:
            raise JavaRuntimeError(
                code="JERR_INVALID_DATE",
                description="Invalid date format",
                explanation=f"Java exception during IRF Grouper processing: {str(ex)}",
            )
        output = IrfgOutput()
        output.claim_id = claim.claimid
        output.from_java(claim_input)
        return output
