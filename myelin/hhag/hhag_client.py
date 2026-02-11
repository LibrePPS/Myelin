import jpype

from myelin.helpers.utils import handle_java_exceptions, JavaRuntimeError
from myelin.hhag.hhag_output import HhagOutput
from myelin.input.claim import Claim


class HhagClient:
    def __init__(self):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using HhagClient."
            )
        self.load_classes()
        self.load_hhag_grouper()

    def load_classes(self):
        self.hhag_claim_class: jpype.JClass = jpype.JClass(
            "gov.cms.hh.data.exchange.ClaimContainer"
        )
        self.hhag_dx_class: jpype.JClass = jpype.JClass(
            "gov.cms.hh.data.exchange.DxContainer"
        )
        self.hhag_grouper_class: jpype.JClass = jpype.JClass(
            "gov.cms.hh.grouper.GrouperFactory"
        )
        self.hhag_edit_collection_class: jpype.JClass = jpype.JClass(
            "gov.cms.hh.logic.validation.EditCollection"
        )
        self.hhag_edit_class: jpype.JClass = jpype.JClass(
            "gov.cms.hh.logic.validation.Edit"
        )
        self.hhag_edit_type_enum: jpype.JClass = jpype.JClass(
            "gov.cms.hh.data.meta.enumer.EditType_EN"
        )
        self.hhag_edit_severity_enum: jpype.JClass = jpype.JClass(
            "java.util.logging.Level"
        )
        self.hhag_edit_id_enum: jpype.JClass = jpype.JClass(
            "gov.cms.hh.data.meta.enumer.EditId_EN"
        )

    def load_hhag_grouper(self) -> None:
        self.hhag_grouper_obj: jpype.JObject = self.hhag_grouper_class(True)

    def create_input_claim(self, claim: Claim) -> jpype.JObject:
        claim_obj = self.hhag_claim_class()
        claim_obj.setClaimId(claim.claimid)

        if claim.from_date is not None:
            if claim.admit_date is not None:
                if claim.admit_date == claim.from_date:
                    claim_obj.setPeriodTiming("1")
                else:
                    claim_obj.setPeriodTiming("2")
            else:
                claim_obj.setPeriodTiming("2")
            claim_obj.setFromDate(claim.from_date.strftime("%Y%m%d"))
        else:
            raise JavaRuntimeError(
                code="JERR_INVALID_DATE",
                description="Invalid date format",
                explanation="Claim 'from_date' is required.",
            )

        if claim.thru_date is not None:
            claim_obj.setThroughDate(claim.thru_date.strftime("%Y%m%d"))
        else:
            raise JavaRuntimeError(
                code="JERR_INVALID_DATE",
                description="Invalid date format",
                explanation="Claim 'thru_date' is required.",
            )

        for code in claim.occurrence_codes:
            if code.code == "61":
                claim_obj.setReferralSource("61")
            elif code.code == "62":
                claim_obj.setReferralSource("62")

        if claim.principal_dx is not None:
            claim_obj.setPdx(claim.principal_dx.code, claim.principal_dx.poa.name)

        for dx in claim.secondary_dxs:
            claim_obj.addSdx(dx.code, dx.poa.name)

        if claim.oasis_assessment is not None:
            claim_obj.setHospRiskHistoryFalls(str(claim.oasis_assessment.fall_risk))
            claim_obj.setHospRiskWeightLoss(str(claim.oasis_assessment.weight_loss))
            claim_obj.setHospRiskMultiHospital(
                str(claim.oasis_assessment.multiple_hospital_stays)
            )
            claim_obj.setHospRiskMultiEdVisit(
                str(claim.oasis_assessment.multiple_ed_visits)
            )
            claim_obj.setHospRiskMentalBehavDecl(
                str(claim.oasis_assessment.mental_behavior_risk)
            )
            claim_obj.setHospRiskCompliance(str(claim.oasis_assessment.compliance_risk))
            claim_obj.setHospRiskFiveMoreMeds(
                str(claim.oasis_assessment.five_or_more_meds)
            )
            claim_obj.setHospRiskExhaustion(str(claim.oasis_assessment.exhaustion))
            claim_obj.setHospRiskOtherRisk(str(claim.oasis_assessment.other_risk))
            claim_obj.setHospRiskNoneAbove(str(claim.oasis_assessment.none_of_above))
            claim_obj.setGrooming(claim.oasis_assessment.grooming)
            claim_obj.setDressUpper(claim.oasis_assessment.dress_upper)
            claim_obj.setDressLower(claim.oasis_assessment.dress_lower)
            claim_obj.setBathing(claim.oasis_assessment.bathing)
            claim_obj.setToileting(claim.oasis_assessment.toileting)
            claim_obj.setTransferring(claim.oasis_assessment.transferring)
            claim_obj.setAmbulation(claim.oasis_assessment.ambulation)
        return claim_obj

    def set_oasis_defaults(self, claim_obj: jpype.JObject) -> None:
        claim_obj.setHospRiskHistoryFalls("0")
        claim_obj.setHospRiskWeightLoss("0")
        claim_obj.setHospRiskMultiHospital("0")
        claim_obj.setHospRiskMultiEdVisit("0")
        claim_obj.setHospRiskMentalBehavDecl("0")
        claim_obj.setHospRiskCompliance("0")
        claim_obj.setHospRiskFiveMoreMeds("0")
        claim_obj.setHospRiskExhaustion("0")
        claim_obj.setHospRiskOtherRisk("0")
        claim_obj.setHospRiskNoneAbove("1")
        claim_obj.setGrooming("00")
        claim_obj.setDressUpper("00")
        claim_obj.setDressLower("00")
        claim_obj.setBathing("00")
        claim_obj.setToileting("00")
        claim_obj.setTransferring("00")
        claim_obj.setAmbulation("00")

    @handle_java_exceptions
    def process(self, claim: Claim) -> HhagOutput:
        """
        Process the claim through the HHAG system.
        Remember that the HHA Grouper requires OASIS assesment data to be entered..
        """
        claim_obj = self.create_input_claim(claim)
        self.hhag_grouper_obj.group(claim_obj)
        hhag_output = HhagOutput()
        hhag_output.from_java(claim_obj)
        return hhag_output
