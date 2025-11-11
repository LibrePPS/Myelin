import os
from datetime import datetime
from logging import Logger, getLogger
from threading import current_thread
from typing import Optional

import jpype
from pydantic import BaseModel
from sqlalchemy import Engine

from myelin.helpers.utils import (
    ReturnCode,
    create_supported_years,
    float_or_none,
    handle_java_exceptions,
    py_date_to_java_date,
)
from myelin.input.claim import Claim
from myelin.msdrg.msdrg_output import MsdrgOutput
from myelin.plugins import apply_client_methods, run_client_load_classes
from myelin.pricers.ipsf import IPSFProvider
from myelin.pricers.url_loader import UrlLoader

ECTCodes = {
    "GZB0ZZZ": {"start_date": datetime(2015, 10, 1), "end_date": datetime(2100, 1, 1)},
    "GZB1ZZZ": {"start_date": datetime(2015, 10, 1), "end_date": datetime(2100, 1, 1)},
    "GZB2ZZZ": {"start_date": datetime(2015, 10, 1), "end_date": datetime(2100, 1, 1)},
    "GZB3ZZZ": {"start_date": datetime(2015, 10, 1), "end_date": datetime(2100, 1, 1)},
    "GZB4ZZZ": {"start_date": datetime(2015, 10, 1), "end_date": datetime(2100, 1, 1)},
}


class IpfAdditionalVariables(BaseModel):
    adjusted_per_diem_amount: Optional[float] = None
    base_labor_amount: Optional[float] = None
    base_non_labor_amount: Optional[float] = None
    budget_rate_amount: Optional[float] = None
    electro_convulsive_therapy_payment: Optional[float] = None
    factor_payment: Optional[float] = None
    outlier_adjusted_cost: Optional[float] = None
    federal_payment: Optional[float] = None
    outlier_base_labor_amount: Optional[float] = None
    outlier_base_non_labor_amount: Optional[float] = None
    outlier_cost: Optional[float] = None
    outlier_payment: Optional[float] = None
    outlier_per_diem_amount: Optional[float] = None
    outlier_threshold_adjusted_amount: Optional[float] = None
    outlier_threshold_amount: Optional[float] = None
    stop_loss_amount: Optional[float] = None
    teaching_payment: Optional[float] = None
    wage_adjusted_amount: Optional[float] = None

    def from_java(self, java_obj):
        if java_obj is None:
            return
        self.adjusted_per_diem_amount = float_or_none(
            java_obj.getAdjustedPerDiemAmount()
        )
        self.base_labor_amount = float_or_none(java_obj.getBaseLaborAmount())
        self.base_non_labor_amount = float_or_none(java_obj.getBaseNonLaborAmount())
        self.budget_rate_amount = float_or_none(java_obj.getBudgetRateAmount())
        self.electro_convulsive_therapy_payment = float_or_none(
            java_obj.getElectroConvulsiveTherapyPayment()
        )
        self.factor_payment = float_or_none(java_obj.getFactorPayment())
        self.outlier_adjusted_cost = float_or_none(java_obj.getOutlierAdjustedCost())
        self.federal_payment = float_or_none(java_obj.getFederalPayment())
        self.outlier_base_labor_amount = float_or_none(
            java_obj.getOutlierBaseLaborAmount()
        )
        self.outlier_base_non_labor_amount = float_or_none(
            java_obj.getOutlierBaseNonLaborAmount()
        )
        self.outlier_cost = float_or_none(java_obj.getOutlierCost())
        self.outlier_payment = float_or_none(java_obj.getOutlierPayment())
        self.outlier_per_diem_amount = float_or_none(java_obj.getOutlierPerDiemAmount())
        self.outlier_threshold_adjusted_amount = float_or_none(
            java_obj.getOutlierThresholdAdjustedAmount()
        )
        self.outlier_threshold_amount = float_or_none(
            java_obj.getOutlierThresholdAmount()
        )
        self.stop_loss_amount = float_or_none(java_obj.getStopLossAmount())
        self.teaching_payment = float_or_none(java_obj.getTeachingPayment())
        self.wage_adjusted_amount = float_or_none(java_obj.getWageAdjustedAmount())


class IpfOutput(BaseModel):
    claim_id: str = ""
    calculation_version: Optional[str] = None
    return_code: Optional[ReturnCode] = None
    total_payment: Optional[float] = None
    final_cbsa: Optional[str] = None
    wage_index: Optional[float] = None
    age_adjustment_percent: Optional[float] = None
    comorbidity_factor: Optional[float] = None
    cost_of_living_adjustment_percent: Optional[float] = None
    cost_to_charge_ratio: Optional[float] = None
    drg_factor: Optional[float] = None
    emergency_adjustment_percent: Optional[float] = None
    national_labor_percent: Optional[float] = None
    national_non_labor_percent: Optional[float] = None
    rural_adjustment_percent: Optional[float] = None
    teach_adjustment_percent: Optional[float] = None
    additional_variables: Optional[IpfAdditionalVariables] = None

    def from_java(self, java_obj):
        self.return_code = ReturnCode()
        self.return_code.from_java(java_obj.getReturnCodeData())
        self.calculation_version = str(java_obj.getCalculationVersion())

        payment_data = java_obj.getPaymentData()
        if payment_data is not None:
            self.total_payment = float_or_none(payment_data.getTotalPayment())
            self.final_cbsa = str(payment_data.getFinalCbsa())
            self.wage_index = float_or_none(payment_data.getFinalWageIndex())
            self.age_adjustment_percent = float_or_none(
                payment_data.getAgeAdjustmentPercent()
            )
            self.comorbidity_factor = float_or_none(payment_data.getComorbidityFactor())
            self.cost_of_living_adjustment_percent = float_or_none(
                payment_data.getCostOfLivingAdjustmentPercent()
            )
            self.cost_to_charge_ratio = float_or_none(
                payment_data.getCostToChargeRatio()
            )
            self.drg_factor = float_or_none(
                payment_data.getDiagnosisRelatedGroupFactor()
            )
            self.emergency_adjustment_percent = float_or_none(
                payment_data.getEmergencyAdjustmentPercent()
            )
            self.national_labor_percent = float_or_none(
                payment_data.getNationalLaborSharePercent()
            )
            self.national_non_labor_percent = float_or_none(
                payment_data.getNationalNonLaborSharePercent()
            )
            self.rural_adjustment_percent = float_or_none(
                payment_data.getRuralAdjustmentPercent()
            )
            self.teach_adjustment_percent = float_or_none(
                payment_data.getTeachingAdjustmentPercent()
            )
            additional_vars = payment_data.getAdditionalVariables()
            if additional_vars is not None:
                self.additional_variables = IpfAdditionalVariables()
                self.additional_variables.from_java(additional_vars)


class IpfClient:
    def __init__(
        self,
        jar_path=None,
        db: Optional[Engine] = None,
        logger: Optional[Logger] = None,
    ):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using IpfClient."
            )
        # We need to use the URL class loader from Java to prevent classpath issues with other CMS pricers
        if jar_path is None:
            raise ValueError("jar_path must be provided to IpfClient")
        if not os.path.exists(jar_path):
            raise ValueError(f"jar_path does not exist: {jar_path}")
        self.url_loader = UrlLoader()
        # This loads the jar file into our URL class loader
        self.url_loader.load_urls([f"file://{jar_path}"])
        self.db = db
        if logger is not None:
            self.logger = logger
        else:
            self.logger = getLogger("IpfClient")
        self.load_classes()
        try:
            run_client_load_classes(self)
        except Exception:
            pass
        self.pricer_setup()
        try:
            apply_client_methods(self)
        except Exception:
            pass

    def load_classes(self):
        self.ipf_csv_ingest_class = jpype.JClass(
            "gov.cms.fiss.pricers.common.csv.CsvIngestionConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.ipf_claim_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.ipf.api.v2.IpfClaimData",
            loader=self.url_loader.class_loader,
        )
        self.ipf_price_request = jpype.JClass(
            "gov.cms.fiss.pricers.ipf.api.v2.IpfClaimPricingRequest",
            loader=self.url_loader.class_loader,
        )
        self.ipf_price_response = jpype.JClass(
            "gov.cms.fiss.pricers.ipf.api.v2.IpfClaimPricingResponse",
            loader=self.url_loader.class_loader,
        )
        self.ipf_payment_data = jpype.JClass(
            "gov.cms.fiss.pricers.ipf.api.v2.IpfPaymentData",
            loader=self.url_loader.class_loader,
        )
        self.ipf_price_config = jpype.JClass(
            "gov.cms.fiss.pricers.ipf.IpfPricerConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.ipf_dispatch = jpype.JClass(
            "gov.cms.fiss.pricers.ipf.core.IpfPricerDispatch",
            loader=self.url_loader.class_loader,
        )
        self.inpatient_prov_data = jpype.JClass(
            "gov.cms.fiss.pricers.ipf.api.v2.IpfInpatientProviderData",
            loader=self.url_loader.class_loader,
        )
        self.rtn_code_data = jpype.JClass(
            "gov.cms.fiss.pricers.common.api.ReturnCodeData",
            loader=self.url_loader.class_loader,
        )
        self.ipf_data_tables_class = jpype.JClass(
            "gov.cms.fiss.pricers.ipf.core.tables.DataTables",
            loader=self.url_loader.class_loader,
        )
        self.array_list_class = jpype.JClass(
            "java.util.ArrayList", loader=self.url_loader.class_loader
        )
        self.java_integer_class = jpype.JClass(
            "java.lang.Integer", loader=self.url_loader.class_loader
        )
        self.java_date_class = jpype.JClass(
            "java.time.LocalDate", loader=self.url_loader.class_loader
        )
        self.java_data_formatter = jpype.JClass(
            "java.time.format.DateTimeFormatter", loader=self.url_loader.class_loader
        )
        self.java_big_decimal_class = jpype.JClass(
            "java.math.BigDecimal", loader=self.url_loader.class_loader
        )
        self.java_string_class = jpype.JClass(
            "java.lang.String", loader=self.url_loader.class_loader
        )

    def pricer_setup(self):
        self.ipf_config_obj = self.ipf_price_config()
        self.csv_ingest_obj = self.ipf_csv_ingest_class()
        self.ipf_config_obj.setCsvIngestionConfiguration(self.csv_ingest_obj)

        # Get today's year
        supported_years = create_supported_years("IPF")
        self.ipf_config_obj.setSupportedYears(supported_years)
        self.ipf_data_tables_class.loadDataTables(self.ipf_config_obj)
        self.dispatch_obj = self.ipf_dispatch(self.ipf_config_obj)
        if self.dispatch_obj is None:
            raise RuntimeError(
                "Failed to create IpfPricerDispatch object. Check your JAR file and classpath."
            )

    def py_date_to_java_date(self, py_date):
        return py_date_to_java_date(self, py_date)

    def hasOutlierOccurrence(self, claim: Claim) -> bool:
        if len(claim.occurrence_codes) == 0:
            return False
        for code in claim.occurrence_codes:
            if code.code in ("31", "A3", "B3", "C3"):
                return True
        return False

    def ectUnits(self, claim: Claim) -> int:
        """
        Calculate the number of ECT units based on the inpatient procedure codes.
        """
        ect_units = 0
        for px in claim.inpatient_pxs:
            if px.code in ECTCodes:
                if px.date:
                    if isinstance(px.date, datetime):
                        px_date = px.date
                    else:
                        try:
                            px_date = datetime.strptime(px.date, "%Y-%m-%d")
                        except ValueError:
                            raise ValueError(
                                f"Invalid date format for procedure code {px.code}: {px.date}"
                            )
                    if (
                        ECTCodes[px.code]["start_date"]
                        <= px_date
                        <= ECTCodes[px.code]["end_date"]
                    ):
                        ect_units += 1
                elif claim.from_date:
                    if isinstance(claim.from_date, datetime):
                        from_date = claim.from_date
                    else:
                        try:
                            from_date = datetime.strptime(claim.from_date, "%Y-%m-%d")
                        except ValueError:
                            raise ValueError(
                                f"Invalid from_date format: {claim.from_date}"
                            )
                    if (
                        ECTCodes[px.code]["start_date"]
                        <= from_date
                        <= ECTCodes[px.code]["end_date"]
                    ):
                        ect_units += 1
        return ect_units

    def create_input_claim(
        self, claim: Claim, drg_output: Optional[MsdrgOutput] = None, **kwargs
    ) -> jpype.JObject:
        if self.db is None:
            raise ValueError("Database connection is required for IpfClient.")
        claim_object = self.ipf_claim_data_class()
        pricing_request = self.ipf_price_request()
        ipsf_provider = IPSFProvider()
        provider_object = self.inpatient_prov_data()
        claim_object.setCoveredCharges(self.java_big_decimal_class(claim.total_charges))
        if claim.los < claim.non_covered_days:
            raise ValueError("LOS cannot be less than non-covered days")
        if claim.thru_date is not None:
            claim_object.setDischargeDate(self.py_date_to_java_date(claim.thru_date))
        else:
            raise ValueError("Thru date is required.")
        claim_object.setLengthOfStay(self.java_integer_class(claim.los))
        claim_object.setPatientStatus(claim.patient_status)
        claim_object.setSourceOfAdmission(claim.admission_source)
        ect_units = self.ectUnits(claim)
        if ect_units > 0:
            claim_object.setServiceUnits(ect_units)
        if claim.patient is not None:
            claim_object.setPatientAge(self.java_integer_class(claim.patient.age))
        if self.hasOutlierOccurrence(claim):
            claim_object.setOutlierSpecialPaymentIndicator("Y")

        if drg_output is not None:
            claim_object.setDiagnosisRelatedGroup(str(drg_output.final_drg_value))
            claim_object.setDiagnosisRelatedGroupSeverity(
                str(drg_output.final_severity)
            )
        else:
            # @TODO need to add the ability to pass a DRG without a MsdrgOutput object
            raise ValueError("DRG output is required for IPF pricing.")

        java_dxs = self.array_list_class()
        # @TODO need to verify if we need to strip out decimal points from diagnosis codes
        if claim.principal_dx is not None:
            java_dxs.add(self.java_string_class(claim.principal_dx.code))
        if claim.admit_dx is not None:
            java_dxs.add(self.java_string_class(claim.admit_dx.code))
        for dx in claim.secondary_dxs:
            if dx.code:
                java_dxs.add(self.java_string_class(dx.code))
        claim_object.setDiagnosisCodes(java_dxs)
        java_pxs = self.array_list_class()
        for px in claim.inpatient_pxs:
            if px.code:
                java_pxs.add(self.java_string_class(px.code))
        claim_object.setProcedureCodes(java_pxs)

        if claim.billing_provider is not None:
            if isinstance(claim.thru_date, datetime):
                date_int = int(claim.thru_date.strftime("%Y%m%d"))
            else:
                date_int = int(claim.thru_date.replace("-", ""))
            ipsf_provider = IPSFProvider()
            ipsf_provider.from_sqlite(
                self.db, claim.billing_provider, date_int, **kwargs
            )
            claim_object.setProviderCcn(ipsf_provider.provider_ccn)
        elif claim.servicing_provider is not None:
            if isinstance(claim.thru_date, datetime):
                date_int = int(claim.thru_date.strftime("%Y%m%d"))
            else:
                date_int = int(claim.thru_date.replace("-", ""))
            ipsf_provider = IPSFProvider()
            ipsf_provider.from_sqlite(
                self.db, claim.servicing_provider, date_int, **kwargs
            )
            claim_object.setProviderCcn(ipsf_provider.provider_ccn)
        else:
            raise ValueError(
                "Either billing or servicing provider must be provided for IPPS pricing."
            )
        ipsf_provider.set_java_values(provider_object, self)
        pricing_request.setClaimData(claim_object)
        pricing_request.setProviderData(provider_object)
        return pricing_request

    def process_claim(
        self, claim: Claim, pricing_request: jpype.JObject
    ) -> jpype.JObject:
        if hasattr(self.dispatch_obj, "process"):
            return self.dispatch_obj.process(pricing_request)
        raise ValueError("Dispatch object does not have a process method.")

    @handle_java_exceptions
    def process(
        self, claim: Claim, drg_output: Optional[MsdrgOutput] = None, **kwargs
    ) -> IpfOutput:
        """
        Processes the python claim object through the CMS IPF Java Pricer.
        """
        self.logger.debug(
            f"IpfClient processing claim on thread {current_thread().ident}"
        )
        pricing_request = self.create_input_claim(claim, drg_output, **kwargs)
        pricing_response = self.process_claim(claim, pricing_request, **kwargs)
        ipf_output = IpfOutput()
        ipf_output.claim_id = claim.claimid
        ipf_output.from_java(pricing_response)
        return ipf_output
