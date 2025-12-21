import os
from datetime import datetime
from logging import Logger, getLogger

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
from myelin.hhag import HhagOutput
from myelin.input import Claim
from myelin.plugins import apply_client_methods, run_client_load_classes
from myelin.pricers.ipsf import IPSFProvider
from myelin.pricers.url_loader import UrlLoader


class RevCodeData:
    def __init__(self):
        self.code: str | None = None
        self.earliest_date: datetime | None = None
        self.count: int | None = None
        self.total_units: float | None = None


def get_rev_code_data(claim: Claim) -> dict[str, RevCodeData]:
    rev_code_data = dict()
    for line in claim.lines:
        rev_code = line.revenue_code.strip()
        if rev_code in ("", "0000", "0023"):
            continue
        if rev_code in rev_code_data:
            data = rev_code_data[rev_code]
            if line.service_date:
                if data.earliest_date is None or line.service_date < data.earliest_date:
                    data.earliest_date = line.service_date
            data.count += 1
            data.total_units += line.units if line.units else 0.0
        else:
            data = RevCodeData()
            data.code = rev_code
            if line.service_date:
                data.earliest_date = line.service_date
            data.count = 1
            data.total_units = line.units if line.units else 0.0
            rev_code_data[rev_code] = data
    return rev_code_data


class RevenuePaymentData(BaseModel):
    revenue_code: str | None = None
    addon_visit_amount: float | None = None
    cost: float | None = None
    dollar_rate: float | None = None

    def from_java(self, java_object) -> None:
        self.revenue_code = str(java_object.getRevenueCode())
        self.addon_visit_amount = float_or_none(java_object.getAddOnVisitAmount())
        self.cost = float_or_none(java_object.getCost())
        self.dollar_rate = float_or_none(java_object.getDollarRate())


class HhaOutput(BaseModel):
    claim_id: str = ""
    return_code: ReturnCode | None = None
    hhrg_weight: float | None = None
    hhrg_payment: float | None = None
    late_submission_penalty: float | None = None
    outlier_payment: float | None = None
    standardized_payment: float | None = None
    total_covered_visits: int | None = None
    vbp_amount: float | None = None
    hhrg_code: str | None = None
    total_payment: float | None = None
    revenue_payments: list[RevenuePaymentData] | None = None

    def from_java(self, java_object) -> None:
        payment_data = java_object.getPaymentData()
        return_code = java_object.getReturnCodeData()
        if return_code:
            self.return_code = ReturnCode()
            self.return_code.from_java(return_code)
        if payment_data:
            self.hhrg_weight = float_or_none(payment_data.getHhrgWeight())
            self.hhrg_payment = float_or_none(payment_data.getHhrgPayment())
            self.late_submission_penalty = float_or_none(
                payment_data.getLateSubmissionPenaltyAmount()
            )
            self.outlier_payment = float_or_none(payment_data.getOutlierPayment())
            self.standardized_payment = float_or_none(
                payment_data.getStandardizedPayment()
            )
            self.total_covered_visits = payment_data.getTotalQuantityOfCoveredVisits()
            self.vbp_amount = float_or_none(
                payment_data.getValueBasedPurchasingAdjustmentAmount()
            )
            self.total_payment = float_or_none(payment_data.getTotalPayment())
            self.revenue_payments = []
            java_revs = payment_data.getRevenuePayments()
            if java_revs:
                for rev in java_revs:
                    rev_data = RevenuePaymentData()
                    rev_data.from_java(rev)
                    self.revenue_payments.append(rev_data)


class HhaClient:
    def __init__(
        self,
        jar_path: str | None = None,
        db: Engine | None = None,
        logger: Logger | None = None,
    ):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using HhaClient."
            )
        # We need to use the URL class loader from Java to prevent classpath issues with other CMS pricers
        if jar_path is None:
            raise ValueError("jar_path must be provided to HhaClient")
        if not os.path.exists(jar_path):
            raise ValueError(f"jar_path does not exist: {jar_path}")
        self.url_loader = UrlLoader()
        # This loads the jar file into our URL class loader
        self.url_loader.load_urls([f"file://{jar_path}"])
        self.db = db
        if logger is not None:
            self.logger = logger
        else:
            self.logger = getLogger("HhaClient")
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

    def load_classes(self) -> None:
        self.hha_pricer_config_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.HhaPricerConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.hha_pricer_dispatch_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.core.HhaPricerDispatch",
            loader=self.url_loader.class_loader,
        )
        self.hha_pricer_request_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.api.v2.HhaClaimPricingRequest",
            loader=self.url_loader.class_loader,
        )
        self.hha_pricer_response_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.api.v2.HhaClaimPricingResponse",
            loader=self.url_loader.class_loader,
        )
        self.hha_pricer_payment_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.api.v2.HhaPaymentData",
            loader=self.url_loader.class_loader,
        )
        self.hha_pricer_provider_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.api.v2.HhaInpatientProviderData",
            loader=self.url_loader.class_loader,
        )
        self.hha_pricer_claim_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.api.v2.HhaClaimData",
            loader=self.url_loader.class_loader,
        )
        self.hha_csv_ingest_class = jpype.JClass(
            "gov.cms.fiss.pricers.common.csv.CsvIngestionConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.hha_data_table_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.core.tables.DataTables",
            loader=self.url_loader.class_loader,
        )
        self.rtn_code_data = jpype.JClass(
            "gov.cms.fiss.pricers.common.api.ReturnCodeData",
            loader=self.url_loader.class_loader,
        )
        self.hha_pricer_revenue_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.api.v2.RevenueLineData",
            loader=self.url_loader.class_loader,
        )
        self.hha_pricer_revenue_payment_class = jpype.JClass(
            "gov.cms.fiss.pricers.hha.api.v2.RevenuePaymentData",
            loader=self.url_loader.class_loader,
        )
        self.java_integer_class = jpype.JClass(
            "java.lang.Integer", loader=self.url_loader.class_loader
        )
        self.java_big_decimal_class = jpype.JClass(
            "java.math.BigDecimal", loader=self.url_loader.class_loader
        )
        self.java_string_class = jpype.JClass(
            "java.lang.String", loader=self.url_loader.class_loader
        )
        self.array_list_class = jpype.JClass(
            "java.util.ArrayList", loader=self.url_loader.class_loader
        )
        self.java_date_class = jpype.JClass(
            "java.time.LocalDate", loader=self.url_loader.class_loader
        )
        self.java_data_formatter = jpype.JClass(
            "java.time.format.DateTimeFormatter", loader=self.url_loader.class_loader
        )

    def pricer_setup(self) -> None:
        self.hha_config_obj = self.hha_pricer_config_class()
        self.csv_ingest_obj = self.hha_csv_ingest_class()
        self.hha_config_obj.setCsvIngestionConfiguration(self.csv_ingest_obj)

        # Get today's year
        supported_years = create_supported_years("HHA")
        self.hha_config_obj.setSupportedYears(supported_years)
        self.hha_data_table_class.loadDataTables(self.hha_config_obj)
        self.dispatch_obj = self.hha_pricer_dispatch_class(self.hha_config_obj)
        if self.dispatch_obj is None:
            raise RuntimeError(
                "Failed to create HhaPricerDispatch object. Check your JAR file and classpath."
            )

    def py_date_to_java_date(
        self, py_date: datetime | str | int | None
    ) -> jpype.JObject:
        return py_date_to_java_date(self, py_date)

    def calculate_hhrg_days(self, claim: Claim) -> int:
        earliest_date = None
        latest_date = None
        for line in claim.lines:
            if line.revenue_code == "0023":
                if line.service_date:
                    if earliest_date is None or line.service_date < earliest_date:
                        earliest_date = line.service_date
                    if latest_date is None or line.service_date > latest_date:
                        latest_date = line.service_date
        if earliest_date and latest_date:
            return (latest_date - earliest_date).days + 1
        return 0

    def create_input_claim(
        self, claim: Claim, hhag_output: HhagOutput | None = None, **kwargs: object
    ) -> tuple[jpype.JObject, IPSFProvider]:
        if self.db is None:
            raise ValueError("Database engine is not set for HhaClient")
        claim_object = self.hha_pricer_claim_data_class()
        pricing_request = self.hha_pricer_request_class()
        provider_data = self.hha_pricer_provider_data_class()
        if claim.admit_date:
            claim_object.setAdmissionDate(self.py_date_to_java_date(claim.admit_date))
        elif claim.from_date:
            claim_object.setAdmissionDate(self.py_date_to_java_date(claim.from_date))
        claim_object.setServiceFromDate(self.py_date_to_java_date(claim.from_date))
        if claim.thru_date:
            claim_object.setServiceThroughDate(
                self.py_date_to_java_date(claim.thru_date)
            )
        if claim.receipt_date:
            claim_object.setNoticeReceiptDate(
                self.py_date_to_java_date(claim.receipt_date)
            )
        else:
            claim_object.setNoticeReceiptDate(
                self.py_date_to_java_date(datetime(1800, 1, 1))
            )
        claim_object.setHhrgNumberOfDays(
            self.java_integer_class(self.calculate_hhrg_days(claim))
        )
        claim_object.setTypeOfBill(claim.bill_type)
        found_47 = False
        for code in claim.cond_codes:
            if code == "47":
                claim_object.setLupaSourceAdmissionIndicator("B")
                found_47 = True
        if not found_47:
            claim_object.setLupaSourceAdmissionIndicator("1")
        if claim.patient_status == "06":
            claim_object.setPartialEpisodePaymentIndicator("1")
        else:
            claim_object.setPartialEpisodePaymentIndicator("0")

        hipps_set = False
        if hhag_output is not None:
            claim_object.setHhrgInputCode(hhag_output.hipps_code)
            hipps_set = True
        else:
            # Need to find Hipps code on rev_code 0023 line
            for line in claim.lines:
                if line.revenue_code == "0023" and line.hcpcs is not None:
                    claim_object.setHhrgInputCode(line.hcpcs)
                    hipps_set = True
        if not hipps_set:
            raise ValueError("Hipps code not found")
        rev_data = get_rev_code_data(claim)
        if rev_data is None:
            raise RuntimeError("No revenue code data found in claim")
        rev_list = self.array_list_class()
        for rev_code, data in rev_data.items():
            java_rev = self.hha_pricer_revenue_data_class()
            java_rev.setEarliestLineItemDate(
                self.py_date_to_java_date(data.earliest_date)
            )
            java_rev.setRevenueCode(data.code)
            java_rev.setQuantityOfCoveredVisits(data.count)
            if data.total_units:
                java_rev.setQuantityOfOutlierUnits(int(data.total_units))
            rev_list.add(java_rev)
        claim_object.setRevenueLines(rev_list)

        if "hha" in claim.additional_data and isinstance(
            claim.additional_data["hha"], dict
        ):
            hha_data = claim.additional_data["hha"]
            claim_object.setAdjustmentIndicator(
                hha_data.get("adjustment_indicator", "0")
            )
            claim_object.setInitialPaymentQualityReportingProgramIndicator(
                hha_data.get("initial_payment_quality_reporting_program_indicator", "0")
            )
            claim_object.setLateFilingPenaltyWaiverIndicator(
                hha_data.get("late_filing_penalty_waiver_indicator", "0")
            )
            claim_object.setPriorPaymentTotal(
                self.java_big_decimal_class(hha_data.get("prior_payment_total", 0))
            )
            claim_object.setPriorOutlierTotal(
                self.java_big_decimal_class(hha_data.get("prior_outlier_total", 0))
            )
        else:
            claim_object.setAdjustmentIndicator("0")
            claim_object.setInitialPaymentQualityReportingProgramIndicator("0")
            claim_object.setLateFilingPenaltyWaiverIndicator("0")
            claim_object.setPriorPaymentTotal(self.java_big_decimal_class(0))
            claim_object.setPriorOutlierTotal(self.java_big_decimal_class(0))

        ipsf_provider = IPSFProvider()
        ipsf_provider.from_claim(claim, self.db, **kwargs)
        claim_object.setProviderCcn(ipsf_provider.provider_ccn)
        pricing_request.setClaimData(claim_object)
        # HHA Uses the special provider update factor as vbp adjustment
        if (
            ipsf_provider.special_provider_update_factor is not None
            and ipsf_provider.special_provider_update_factor > 0
            and ipsf_provider.vbp_adjustment == 0
        ):
            ipsf_provider.vbp_adjustment = ipsf_provider.special_provider_update_factor
        ipsf_provider.set_java_values(provider_data, self)
        if claim.patient:
            if claim.patient.address:
                if claim.patient.address.zip:
                    provider_data.setCountyCode(claim.patient.address.zip[:5])
                    provider_data.setCbsaActualGeographicLocation(
                        claim.patient.address.zip[:5]
                    )
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
        self, claim: Claim, hhag_output: HhagOutput | None = None, **kwargs: object
    ) -> tuple[HhaOutput, IPSFProvider]:
        """
        Process the claim and return the SNF pricing response.

        :param claim: Claim object to process.
        :return: SnfOutput object.
        """
        if not isinstance(claim, Claim):
            raise ValueError("claim must be an instance of Claim")
        pricing_request, ipsf_provider = self.create_input_claim(
            claim, hhag_output, **kwargs
        )
        pricing_response = self.process_claim(claim, pricing_request)
        hha_output = HhaOutput()
        hha_output.claim_id = claim.claimid
        hha_output.from_java(pricing_response)
        hha_output.hhrg_code = str(pricing_request.getClaimData().getHhrgInputCode())
        return hha_output, ipsf_provider
