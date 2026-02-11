import os
from datetime import datetime
from logging import Logger, getLogger

import jpype
from pydantic import BaseModel
from sqlalchemy import Engine

from myelin.helpers.utils import (
    ProviderDataError,
    ReturnCode,
    create_supported_years,
    float_or_none,
    handle_java_exceptions,
    py_date_to_java_date,
)
from myelin.input.claim import Claim
from myelin.irfg.irfg_output import IrfgOutput
from myelin.plugins import apply_client_methods, run_client_load_classes
from myelin.pricers.ipsf import IPSFProvider
from myelin.pricers.url_loader import UrlLoader


class IrfOutput(BaseModel):
    claim_id: str = ""
    return_code: ReturnCode | None = None
    calculation_version: str | None = None
    total_payment: float | None = None
    average_length_of_stay: float | None = None
    budget_neutrality_conversion_amt: float | None = None
    relative_weight: float | None = None
    charge_outlier_threshold_amt: float | None = None
    cost_outlier_threshold_id: str | None = None
    facility_costs: float | None = None
    facility_rate_percent: float | None = None
    facility_specific_payment: float | None = None
    facility_specific_rate_pre_blended: float | None = None
    federal_payment_amt: float | None = None
    federal_penalty_amt: float | None = None
    federal_rate_percent: float | None = None
    length_of_stay: int | None = None
    lifetime_reserve_days_used: int | None = None
    low_income_payment: float | None = None
    low_income_payment_penalty_amt: float | None = None
    low_income_payment_percent: float | None = None
    national_labor_percent: float | None = None
    national_nonlabor_percent: float | None = None
    national_threshold_adjustment_amt: float | None = None
    outlier_payment: float | None = None
    outlier_penalty_amt: float | None = None
    outlier_threshold: float | None = None
    price_case_mix_group: str | None = None
    regular_days_used: int | None = None
    rural_adjustment_percent: float | None = None
    standard_payment_amt: float | None = None
    submitted_case_mix_group: str | None = None
    teaching_payment: float | None = None
    teaching_payment_penalty_amt: float | None = None
    total_penalty_amt: float | None = None
    transfer_percent: float | None = None

    def from_java(self, java_obj: jpype.JObject) -> None:
        rtn_code = java_obj.getReturnCodeData()
        if rtn_code is not None:
            self.return_code = ReturnCode()
            self.return_code.from_java(rtn_code)
        self.calculation_version = str(java_obj.getCalculationVersion())
        payment_data = java_obj.getPaymentData()
        if payment_data is not None:
            self.total_payment = float_or_none(payment_data.getTotalPayment())
            self.average_length_of_stay = float(payment_data.getAverageLengthOfStay())
            self.budget_neutrality_conversion_amt = float_or_none(
                payment_data.getBudgetNeutralityConversionAmount()
            )
            self.relative_weight = float_or_none(
                payment_data.getCaseMixGroupRelativeWeight()
            )
            self.charge_outlier_threshold_amt = float_or_none(
                payment_data.getChargeOutlierThresholdAmount()
            )
            self.cost_outlier_threshold_id = str(
                payment_data.getCostOutlierThresholdIdentifier()
            )
            self.facility_costs = float_or_none(payment_data.getFacilityCosts())
            self.facility_rate_percent = float_or_none(
                payment_data.getFacilityRatePercent()
            )
            self.facility_specific_payment = float_or_none(
                payment_data.getFacilitySpecificPayment()
            )
            self.facility_specific_rate_pre_blended = float_or_none(
                payment_data.getFacilitySpecificRatePreBlend()
            )
            self.federal_payment_amt = float_or_none(
                payment_data.getFederalPaymentAmount()
            )
            self.federal_penalty_amt = float_or_none(
                payment_data.getFederalPenaltyAmount()
            )
            self.federal_rate_percent = float_or_none(
                payment_data.getFederalRatePercent()
            )
            self.length_of_stay = payment_data.getLengthOfStay()
            self.lifetime_reserve_days_used = payment_data.getLifetimeReserveDaysUsed()
            self.low_income_payment = float_or_none(payment_data.getLowIncomePayment())
            self.low_income_payment_penalty_amt = float_or_none(
                payment_data.getLowIncomePaymentPenaltyAmount()
            )
            self.low_income_payment_percent = float_or_none(
                payment_data.getLowIncomePaymentPercent()
            )
            self.national_labor_percent = float_or_none(
                payment_data.getNationalLaborPercent()
            )
            self.national_nonlabor_percent = float_or_none(
                payment_data.getNationalNonLaborPercent()
            )
            self.national_threshold_adjustment_amt = float_or_none(
                payment_data.getNationalThresholdAdjustmentAmount()
            )
            self.outlier_payment = float_or_none(payment_data.getOutlierPayment())
            self.outlier_penalty_amt = float_or_none(
                payment_data.getOutlierPenaltyAmount()
            )
            self.outlier_threshold = float_or_none(
                payment_data.getOutlierThresholdAmount()
            )
            self.price_case_mix_group = str(payment_data.getPricedCaseMixGroupCode())
            self.submitted_case_mix_group = str(
                payment_data.getSubmittedCaseMixGroupCode()
            )
            self.regular_days_used = payment_data.getRegularDaysUsed()
            self.rural_adjustment_percent = float_or_none(
                payment_data.getRuralAdjustmentPercent()
            )
            self.standard_payment_amt = float_or_none(payment_data.getStandardPayment())
            self.teaching_payment = float_or_none(payment_data.getTeachingPayment())
            self.teaching_payment_penalty_amt = float_or_none(
                payment_data.getTeachingPaymentPenaltyAmount()
            )
            self.total_penalty_amt = float_or_none(payment_data.getTotalPenaltyAmount())
            self.transfer_percent = float_or_none(payment_data.getTransferPercent())


class IrfClient:
    def __init__(
        self,
        jar_path: str | None = None,
        db: Engine | None = None,
        logger: Logger | None = None,
    ):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before creating a IrfClient instance."
            )
        if jar_path is None or not os.path.exists(jar_path):
            raise ValueError(f"Invalid jar_path: {jar_path}")
        self.url_loader = UrlLoader()
        # This loads the jar file into our URL class loader
        self.url_loader.load_urls([f"file://{jar_path}"])
        self.db = db
        if logger is not None:
            self.logger = logger
        else:
            self.logger = getLogger("IrfClient")
        self.load_classes()
        # Allow plugins to load extra/override Java classes before pricer setup
        try:
            run_client_load_classes(self)
        except Exception:
            # Plugins are optional; ignore failures here to avoid breaking core use
            pass
        self.pricer_setup()
        # Bind plugin-provided methods to this client instance
        try:
            apply_client_methods(self)
        except Exception:
            pass

    def load_classes(self) -> None:
        self.irf_pricer_config_class = jpype.JClass(
            "gov.cms.fiss.pricers.irf.IrfPricerConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.irf_pricer_dispatch_class = jpype.JClass(
            "gov.cms.fiss.pricers.irf.core.IrfPricerDispatch",
            loader=self.url_loader.class_loader,
        )
        self.irf_pricer_request_class = jpype.JClass(
            "gov.cms.fiss.pricers.irf.api.v2.IrfClaimPricingRequest",
            loader=self.url_loader.class_loader,
        )
        self.irf_pricer_response_class = jpype.JClass(
            "gov.cms.fiss.pricers.irf.api.v2.IrfClaimPricingResponse",
            loader=self.url_loader.class_loader,
        )
        self.irf_pricer_payment_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.irf.api.v2.IrfPaymentData",
            loader=self.url_loader.class_loader,
        )
        self.irf_pricer_provider_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.irf.api.v2.IrfInpatientProviderData",
            loader=self.url_loader.class_loader,
        )
        self.irf_pricer_claim_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.irf.api.v2.IrfClaimData",
            loader=self.url_loader.class_loader,
        )
        self.irf_csv_ingest_class = jpype.JClass(
            "gov.cms.fiss.pricers.common.csv.CsvIngestionConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.irf_data_table_class = jpype.JClass(
            "gov.cms.fiss.pricers.irf.core.tables.DataTables",
            loader=self.url_loader.class_loader,
        )
        self.array_list_class = jpype.JClass(
            "java.util.ArrayList", loader=self.url_loader.class_loader
        )
        self.java_integer_class = jpype.JClass(
            "java.lang.Integer", loader=self.url_loader.class_loader
        )
        self.java_big_decimal_class = jpype.JClass(
            "java.math.BigDecimal", loader=self.url_loader.class_loader
        )
        self.java_date_class = jpype.JClass(
            "java.time.LocalDate", loader=self.url_loader.class_loader
        )
        self.java_data_formatter = jpype.JClass(
            "java.time.format.DateTimeFormatter", loader=self.url_loader.class_loader
        )

    def create_dispatch(self) -> jpype.JObject:
        return self.irf_pricer_dispatch_class(self.irf_config_obj)

    def py_date_to_java_date(
        self, py_date: datetime | str | int | None
    ) -> jpype.JObject:
        return py_date_to_java_date(self, py_date)

    def pricer_setup(self):
        self.irf_config_obj = self.irf_pricer_config_class()
        self.csv_ingest_obj = self.irf_csv_ingest_class()
        self.irf_config_obj.setCsvIngestionConfiguration(self.csv_ingest_obj)
        supported_years = create_supported_years(pps="IRF")
        self.irf_config_obj.setSupportedYears(supported_years)
        self.irf_data_table_class.loadDataTables(self.irf_config_obj)
        self.dispatch_obj = self.create_dispatch()
        if self.dispatch_obj is None:
            raise RuntimeError(
                "Failed to create IrfPricerDispatch object. Check your JAR file and classpath."
            )

    def create_input_claim(
        self, claim: Claim, irfg: IrfgOutput | None = None, **kwargs: object
    ) -> tuple[jpype.JObject, IPSFProvider]:
        if self.db is None:
            raise ValueError("Database connection is required for IrfClient.")
        claim_obj = self.irf_pricer_claim_data_class()
        provider_data = self.irf_pricer_provider_data_class()
        pricing_request = self.irf_pricer_request_class()

        cmg_code = None
        if irfg is None:
            for line in claim.lines:
                if line.revenue_code == "0024":
                    if line.hcpcs.strip() != "":
                        cmg_code = line.hcpcs.strip()
                    else:
                        raise ValueError("CMG code is required for IRF claims.")
            if cmg_code is None:
                raise ValueError("CMG code is required for IRF claims.")
        else:
            if irfg.cmg_group is None:
                raise ValueError("CMG code is required for IRF claims.")
            cmg_code = irfg.cmg_group
        if cmg_code is None:
            raise ValueError("CMG code is required for IRF claims.")
        claim_obj.setCaseMixGroup(cmg_code)
        claim_obj.setCoveredCharges(self.java_big_decimal_class(claim.total_charges))
        claim_obj.setCoveredDays(claim.los - claim.non_covered_days)
        claim_obj.setDischargeDate(self.py_date_to_java_date(claim.thru_date))
        claim_obj.setLengthOfStay(claim.los)
        claim_obj.setPatientStatus(claim.patient_status)
        found_66 = False
        for cond in claim.cond_codes:
            if cond == "66":
                claim_obj.setOutlierSpecialPaymentIndicator("1")
                found_66 = True
        if not found_66:
            claim_obj.setOutlierSpecialPaymentIndicator("0")
        if "irf" in claim.additional_data:
            if "lifetime_reserve_days" in claim.additional_data["irf"]:
                claim_obj.setLifetimeReserveDays(
                    claim.additional_data["irf"]["lifetime_reserve_days"]
                )
        ipsf_provider = IPSFProvider()
        ipsf_provider.from_claim(claim, self.db, **kwargs)
        claim_obj.setProviderCcn(ipsf_provider.provider_ccn)
        pricing_request.setClaimData(claim_obj)
        ipsf_provider.set_java_values(provider_data, self)
        pricing_request.setProviderData(provider_data)
        return pricing_request, ipsf_provider

    def process_claim(
        self, claim: Claim, pricing_request: jpype.JObject
    ) -> jpype.JObject:
        if hasattr(self.dispatch_obj, "process"):
            return self.dispatch_obj.process(pricing_request)
        raise ValueError("Dispatch object does not have a process method.")

    @handle_java_exceptions
    def process(
        self, claim: Claim, irfg: IrfgOutput | None = None, **kwargs: object
    ) -> tuple[IrfOutput, IPSFProvider]:
        """
        Process the claim and return the IRF pricing response.

        :param claim: Claim object to process.
        :return: IrfOutput object.
        """
        if not isinstance(claim, Claim):
            raise ValueError("claim must be an instance of Claim")
        try:
            pricing_request, ipsf_provider = self.create_input_claim(
                claim, irfg, **kwargs
            )
        except ProviderDataError as e:
            self.logger.warning(
                f"Provider data error for claim {claim.claimid}: {e.description} — {e.explanation}"
            )
            irf_output = IrfOutput()
            irf_output.claim_id = claim.claimid
            irf_output.return_code = e.to_return_code()
            return irf_output, IPSFProvider()
        pricing_response = self.process_claim(claim, pricing_request)
        irf_output = IrfOutput()
        irf_output.claim_id = claim.claimid
        irf_output.from_java(pricing_response)
        return irf_output, ipsf_provider
