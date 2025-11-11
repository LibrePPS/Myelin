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


class LtchOutput(BaseModel):
    claim_id: str = ""
    calculation_version: Optional[str] = None
    return_code: Optional[ReturnCode] = None
    total_payment: Optional[float] = None
    final_cbsa: Optional[str] = None
    adjusted_payment: Optional[float] = None
    average_length_of_stay: Optional[float] = None
    blend_year: Optional[int] = None
    budget_neutrality_rate: Optional[float] = None
    change_of_therapy_indicator: Optional[str] = None
    charge_threshold_amount: Optional[float] = None
    cost_of_living_adjustment_percent: Optional[float] = None
    discharge_payment_percent_amount: Optional[float] = None
    drg_relative_weight: Optional[float] = None
    facility_costs: Optional[float] = None
    facility_specific_rate: Optional[float] = None
    federal_payment: Optional[float] = None
    federal_rate_percent: Optional[float] = None
    inpatient_threshold: Optional[float] = None
    length_of_stay: Optional[int] = None
    lifetime_reserve_days_used: Optional[int] = None
    national_labor_percent: Optional[float] = None
    national_non_labor_percent: Optional[float] = None
    outlier_payment: Optional[float] = None
    outlier_threshold_amount: Optional[float] = None
    regular_days_used: Optional[int] = None
    site_neutral_cost_payment: Optional[float] = None
    site_neutral_ipps_payment: Optional[float] = None
    standard_full_payment: Optional[float] = None
    standard_short_stay_outlier_payment: Optional[float] = None
    submitted_diagnosis_related_group: Optional[str] = None

    def from_java(self, java_obj):
        self.return_code = ReturnCode()
        self.return_code.from_java(java_obj.getReturnCodeData())
        self.calculation_version = str(java_obj.getCalculationVersion())

        payment_data = java_obj.getPaymentData()
        if payment_data is not None:
            self.total_payment = float_or_none(payment_data.getTotalPayment())
            self.final_cbsa = str(payment_data.getFinalCbsa())
            self.adjusted_payment = float_or_none(payment_data.getAdjustedPayment())
            self.average_length_of_stay = float_or_none(
                payment_data.getAverageLengthOfStay()
            )
            self.blend_year = payment_data.getBlendYear()
            self.budget_neutrality_rate = float_or_none(
                payment_data.getBudgetNeutralityRate()
            )
            self.change_of_therapy_indicator = str(
                payment_data.getChangeOfTherapyIndicator()
            )
            self.charge_threshold_amount = float_or_none(
                payment_data.getChargeThresholdAmount()
            )
            self.cost_of_living_adjustment_percent = float_or_none(
                payment_data.getCostOfLivingAdjustmentPercent()
            )
            self.discharge_payment_percent_amount = float_or_none(
                payment_data.getDischargePaymentPercentAmount()
            )
            self.drg_relative_weight = float_or_none(
                payment_data.getDrgRelativeWeight()
            )
            self.facility_costs = float_or_none(payment_data.getFacilityCosts())
            self.facility_specific_rate = float_or_none(
                payment_data.getFacilitySpecificRate()
            )
            self.federal_payment = float_or_none(payment_data.getFederalPayment())
            self.federal_rate_percent = float_or_none(
                payment_data.getFederalRatePercent()
            )
            self.inpatient_threshold = float_or_none(
                payment_data.getInpatientThreshold()
            )
            self.length_of_stay = payment_data.getLengthOfStay()
            self.lifetime_reserve_days_used = payment_data.getLifetimeReserveDaysUsed()
            self.national_labor_percent = float_or_none(
                payment_data.getNationalLaborPercent()
            )
            self.national_non_labor_percent = float_or_none(
                payment_data.getNationalNonLaborPercent()
            )
            self.outlier_payment = float_or_none(payment_data.getOutlierPayment())
            self.outlier_threshold_amount = float_or_none(
                payment_data.getOutlierThresholdAmount()
            )
            self.regular_days_used = payment_data.getRegularDaysUsed()
            self.site_neutral_cost_payment = float_or_none(
                payment_data.getSiteNeutralCostPayment()
            )
            self.site_neutral_ipps_payment = float_or_none(
                payment_data.getSiteNeutralIppsPayment()
            )
            self.standard_full_payment = float_or_none(
                payment_data.getStandardFullPayment()
            )
            self.standard_short_stay_outlier_payment = float_or_none(
                payment_data.getStandardShortStayOutlierPayment()
            )
            self.submitted_diagnosis_related_group = str(
                payment_data.getSubmittedDiagnosisRelatedGroup()
            )


class LtchClient:
    def __init__(
        self,
        jar_path=None,
        db: Optional[Engine] = None,
        logger: Optional[Logger] = None,
    ):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using LtcClient."
            )
        if db is None:
            raise ValueError("Database connection is required for LtchClient.")
        # We need to use the URL class loader from Java to prevent classpath issues with other CMS pricers
        if jar_path is None:
            raise ValueError("jar_path must be provided to Ltchlient")
        if not os.path.exists(jar_path):
            raise ValueError(f"jar_path does not exist: {jar_path}")
        self.url_loader = UrlLoader()
        # This loads the jar file into our URL class loader
        self.url_loader.load_urls([f"file://{jar_path}"])
        self.db = db
        if logger is not None:
            self.logger = logger
        else:
            self.logger = getLogger("LtchClient")
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
        self.ltc_csv_ingest_class = jpype.JClass(
            "gov.cms.fiss.pricers.common.csv.CsvIngestionConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.ltc_claim_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.ltch.api.v2.LtchClaimData",
            loader=self.url_loader.class_loader,
        )
        self.ltc_price_request = jpype.JClass(
            "gov.cms.fiss.pricers.ltch.api.v2.LtchClaimPricingRequest",
            loader=self.url_loader.class_loader,
        )
        self.ltc_price_response = jpype.JClass(
            "gov.cms.fiss.pricers.ltch.api.v2.LtchClaimPricingResponse",
            loader=self.url_loader.class_loader,
        )
        self.ltc_payment_data = jpype.JClass(
            "gov.cms.fiss.pricers.ltch.api.v2.LtchPaymentData",
            loader=self.url_loader.class_loader,
        )
        self.ltc_price_config = jpype.JClass(
            "gov.cms.fiss.pricers.ltch.LtchPricerConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.ltc_dispatch = jpype.JClass(
            "gov.cms.fiss.pricers.ltch.core.LtchPricerDispatch",
            loader=self.url_loader.class_loader,
        )
        self.inpatient_prov_data = jpype.JClass(
            "gov.cms.fiss.pricers.ltch.api.v2.LtchInpatientProviderData",
            loader=self.url_loader.class_loader,
        )
        self.rtn_code_data = jpype.JClass(
            "gov.cms.fiss.pricers.common.api.ReturnCodeData",
            loader=self.url_loader.class_loader,
        )
        self.ltc_data_tables_class = jpype.JClass(
            "gov.cms.fiss.pricers.ltch.core.tables.DataTables",
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
        self.ltc_config_obj = self.ltc_price_config()
        self.csv_ingest_obj = self.ltc_csv_ingest_class()
        self.ltc_config_obj.setCsvIngestionConfiguration(self.csv_ingest_obj)

        # Get today's year
        supported_years = create_supported_years("LTC")
        self.ltc_config_obj.setSupportedYears(supported_years)
        self.ltc_data_tables_class.loadDataTables(self.ltc_config_obj)
        self.dispatch_obj = self.ltc_dispatch(self.ltc_config_obj)
        if self.dispatch_obj is None:
            raise RuntimeError(
                "Failed to create LtcPricerDispatch object. Check your JAR file and classpath."
            )

    def py_date_to_java_date(self, py_date):
        return py_date_to_java_date(self, py_date)

    def create_input_claim(
        self, claim: Claim, drg_output: Optional[MsdrgOutput] = None, **kwargs
    ) -> jpype.JObject:
        if self.db is None:
            raise ValueError("Database connection is required for LtchClient.")
        claim_object = self.ltc_claim_data_class()
        pricing_request = self.ltc_price_request()
        ipsf_provider = IPSFProvider()
        provider_object = self.inpatient_prov_data()
        claim_object.setCoveredCharges(self.java_big_decimal_class(claim.total_charges))
        if claim.los < claim.non_covered_days:
            raise ValueError("LOS cannot be less than non-covered days")
        if claim.thru_date is not None:
            claim_object.setDischargeDate(self.py_date_to_java_date(claim.thru_date))
        else:
            raise ValueError("Thru date is required.")
        claim_object.setCoveredDays(
            self.java_integer_class(claim.los - claim.non_covered_days)
        )
        claim_object.setLengthOfStay(self.java_integer_class(claim.los))
        claim_object.setPatientStatus(claim.patient_status)
        claim_object.setOutlierSpecialPaymentIndicator("0")
        # @TODO provide a way to set the lifetime reserve days
        claim_object.setLifetimeReserveDays(self.java_integer_class(0))
        claim_object.setReviewCode("00")
        if drg_output is not None:
            claim_object.setDiagnosisRelatedGroup(str(drg_output.final_drg_value))
            claim_object.setDiagnosisRelatedGroupSeverity(
                str(drg_output.final_severity)
            )
        else:
            # @TODO need to add the ability to pass a DRG without a MsdrgOutput object
            raise ValueError("DRG output is required for LTC pricing.")

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
            if ipsf_provider.provider_type not in ("02", "2", "52"):
                raise ValueError(
                    f"Billed provider has a Provider Type of {ipsf_provider.provider_type} which is not valid for LTCH Pricer"
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
    ) -> LtchOutput:
        """
        Processes the python claim object through the CMS LTCH Java Pricer.
        """
        self.logger.debug(
            f"LtchClient processing claim on thread {current_thread().ident}"
        )
        pricing_request = self.create_input_claim(claim, drg_output, **kwargs)
        pricing_response = self.process_claim(claim, pricing_request, **kwargs)
        ltch_output = LtchOutput()
        ltch_output.claim_id = claim.claimid
        ltch_output.from_java(pricing_response)
        return ltch_output
