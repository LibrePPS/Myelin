import os
from datetime import datetime, timedelta
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
from myelin.input.claim import Claim
from myelin.plugins import apply_client_methods, run_client_load_classes
from myelin.pricers.url_loader import UrlLoader

CARE_REV_CODES = {
    "0651": 0,  # Routine Home Care
    "0652": 1,  # Continuous Home Care
    "0655": 2,  # Inpatient Respite Care
    "0656": 3,  # General Inpatient Care
}
EXPIRED_DISCHARGE_STATUS_CODES = ["40", "41", "42"]


class BillingGroupOutput(BaseModel):
    hcpcs_code: str | None = None
    revenue_code: str | None = None
    payment_amount: float | None = None

    def from_java(self, java_obj: jpype.JClass):
        self.hcpcs_code = str(java_obj.getHcpcsCode())
        self.revenue_code = str(java_obj.getRevenueCode())
        self.payment_amount = float_or_none(java_obj.getAmount())
        return


class EolaOutput(BaseModel):
    index: int | None = None
    payment_amount: float | None = None

    def from_java(self, java_obj: jpype.JClass):
        self.index = java_obj.getIndex()
        self.payment_amount = float_or_none(java_obj.getPayment())
        return


class HospiceOutput(BaseModel):
    claim_id: str = ""
    calculation_version: str | None = None
    return_code: ReturnCode | None = None
    high_routine_home_care_days: int | None = None
    low_routine_home_care_days: int | None = None
    patient_wage_index: float | None = None
    provider_wage_index: float | None = None
    billing_group_payments: list[BillingGroupOutput] | None = None
    eola_payments: list[EolaOutput] | None = None
    total_payment: float | None = None

    def from_java(self, java_obj: jpype.JClass):
        self.calculation_version = str(java_obj.getCalculationVersion())
        self.return_code = ReturnCode()
        self.return_code.from_java(java_obj.getReturnCodeData())
        payment_data = java_obj.getPaymentData()
        self.total_payment = float_or_none(payment_data.getTotalPayment())
        self.high_routine_home_care_days = payment_data.getHighRoutineHomeCareDays()
        self.low_routine_home_care_days = payment_data.getLowRoutineHomeCareDays()
        self.patient_wage_index = float_or_none(payment_data.getPatientWageIndex())
        self.provider_wage_index = float_or_none(payment_data.getProviderWageIndex())
        self.billing_group_payments = []
        bill_payments = payment_data.getBillPayments()
        if bill_payments is not None:
            for bill_payment in bill_payments:
                billing_group_output = BillingGroupOutput()
                billing_group_output.from_java(bill_payment)
                self.billing_group_payments.append(billing_group_output)
        eola_payments = payment_data.getEndOfLifeAddOnDaysPayments()
        self.eola_payments = []
        if eola_payments is not None:
            for eola in eola_payments:
                eola_output = EolaOutput()
                eola_output.from_java(eola)
                self.eola_payments.append(eola_output)
        return


class BillingGroup:
    def __init__(
        self, service_date: datetime, hcpcs_code: str, revenue_code: str, units: float
    ):
        self.service_date = service_date
        self.hcpcs_code = hcpcs_code
        self.revenue_code = revenue_code
        self.units = units

    def verify_units(self, covered_days: int):
        if self.revenue_code == "0652":
            # 0652 is reported in 15 minute increments
            # Calculate the number of days from the units
            days = self.units // 96  # 96 15-minute increments in a day
            if days > covered_days:
                raise ValueError("More units than covered days")
            return
        # All other revenue codes are reported in whole days
        if self.units > covered_days:
            raise ValueError("More units than covered days")


class BillingGroups:
    def __init__(self, allocator):
        self.groups = {}
        self.covered_days = 0
        self.allocator = allocator

    def build_billing_groups(self, claim):
        # Create non-covered ranges
        non_covered_ranges = NonCoveredRanges()
        non_covered_ranges.create_ranges(claim)
        self.covered_days = claim.los
        for start_date, end_date in non_covered_ranges.ranges:
            days = (end_date - start_date).days + 1
            if days <= self.covered_days:
                self.covered_days -= days
        for line in claim.lines:
            if line.revenue_code not in CARE_REV_CODES:
                # Not a care revenue code, skip this line
                continue
            if line.revenue_code in self.groups:
                if line.service_date:
                    if non_covered_ranges.is_non_covered(line.service_date):
                        continue
                else:
                    # No service date, skip this line
                    continue
                self.groups[line.revenue_code].units += line.units
            else:
                if line.service_date:
                    if non_covered_ranges.is_non_covered(line.service_date):
                        continue
                else:
                    # No service date, skip this line
                    continue
                group = BillingGroup(
                    service_date=line.service_date,
                    hcpcs_code=line.hcpcs,
                    revenue_code=line.revenue_code,
                    units=line.units,
                )
                self.groups[line.revenue_code] = group
        # Verify the units for each group
        for revenue_code, group in self.groups.items():
            try:
                group.verify_units(self.covered_days)
            except ValueError as e:
                raise ValueError(
                    f"Invalid billing for revenue code {revenue_code} as units {group.units} exceed covered days {self.covered_days}"
                ) from e


class NonCoveredRanges:
    def __init__(self):
        self.ranges = []

    def create_ranges(self, claim: Claim):
        for span_code in claim.span_codes:
            if span_code.code == "77":
                if span_code.start_date and span_code.end_date:
                    self.ranges.append((span_code.start_date, span_code.end_date))

    def is_non_covered(self, date):
        return any(start <= date <= end for start, end in self.ranges)

    def deinit(self):
        self.ranges.clear()


class RoutineCareRanges:
    def __init__(self, allocator):
        self.ranges = []
        self.allocator = allocator

    def create_ranges(self, claim: Claim):
        for line in claim.lines:
            if line.revenue_code == "0651":
                if line.service_date:
                    thru_date = line.service_date + timedelta(days=line.units)
                    self.ranges.append((line.service_date, thru_date))

    def in_any_range(self, date):
        return any(start <= date <= end for start, end in self.ranges)

    def deinit(self):
        self.ranges.clear()


class HospiceClient:
    def __init__(
        self,
        jar_path: str | None = None,
        db: Engine | None = None,
        logger: Logger | None = None,
    ):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using HospiceClient."
            )
        # We need to use the URL class loader from Java to prevent classpath issues with other CMS pricers
        if jar_path is None:
            raise ValueError("jar_path must be provided to HospiceClient")
        if not os.path.exists(jar_path):
            raise ValueError(f"jar_path does not exist: {jar_path}")
        self.url_loader = UrlLoader()
        # This loads the jar file into our URL class loader
        self.url_loader.load_urls([f"file://{jar_path}"])
        self.db = db
        if logger is not None:
            self.logger = logger
        else:
            self.logger = getLogger("HospiceClient")
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
        self.hospice_pricer_config_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.HospicePricerConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.hospice_pricer_dispatch_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.core.HospicePricerDispatch",
            loader=self.url_loader.class_loader,
        )
        self.hospice_pricer_request_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.api.v2.HospiceClaimPricingRequest",
            loader=self.url_loader.class_loader,
        )
        self.hospice_pricer_response_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.api.v2.HospiceClaimPricingResponse",
            loader=self.url_loader.class_loader,
        )
        self.hospice_pricer_payment_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.api.v2.HospicePaymentData",
            loader=self.url_loader.class_loader,
        )
        self.hospice_pricer_claim_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.api.v2.HospiceClaimData",
            loader=self.url_loader.class_loader,
        )
        self.hospice_csv_ingest_class = jpype.JClass(
            "gov.cms.fiss.pricers.common.csv.CsvIngestionConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.hospice_data_table_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.core.tables.DataTables",
            loader=self.url_loader.class_loader,
        )
        self.rtn_code_data = jpype.JClass(
            "gov.cms.fiss.pricers.common.api.ReturnCodeData",
            loader=self.url_loader.class_loader,
        )
        self.hospice_billing_group_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.api.v2.BillingGroupData",
            loader=self.url_loader.class_loader,
        )
        self.hospice_billing_payment_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.api.v2.BillPaymentData",
            loader=self.url_loader.class_loader,
        )
        self.hospice_eol_addon_payment_class = jpype.JClass(
            "gov.cms.fiss.pricers.hospice.api.v2.EndOfLifeAddOnDaysPaymentData",
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
        self.hospice_config_obj = self.hospice_pricer_config_class()
        self.csv_ingest_obj = self.hospice_csv_ingest_class()
        self.hospice_config_obj.setCsvIngestionConfiguration(self.csv_ingest_obj)

        # Get today's year
        supported_years = create_supported_years("HOSPICE")
        self.hospice_config_obj.setSupportedYears(supported_years)
        self.hospice_data_table_class.loadDataTables(self.hospice_config_obj)
        self.dispatch_obj = self.hospice_pricer_dispatch_class(self.hospice_config_obj)
        if self.dispatch_obj is None:
            raise RuntimeError(
                "Failed to create HospicePricerDispatch object. Check your JAR file and classpath."
            )

    def py_date_to_java_date(
        self, py_date: datetime | str | int | None
    ) -> jpype.JObject:
        return py_date_to_java_date(self, py_date)

    def get_patient_cbsa(self, claim: Claim) -> None | str:
        for val_code in claim.value_codes:
            if val_code.code == "61":
                # Convert the float val amount to an integer and return it as a string
                return str(int(val_code.amount))
        return None

    def determine_date_of_death(self, claim: Claim) -> datetime | None:
        if claim.patient_status in EXPIRED_DISCHARGE_STATUS_CODES:
            if claim.thru_date is not None:
                return claim.thru_date
            else:
                raise ValueError(
                    "Claim has expired discharge status but no thru_date is set."
                )
        return None

    def siu_units(self, claim: Claim) -> list[int]:
        siu_units = list([0] * 7)  # Initialize a list for 7 days
        date_of_death = self.determine_date_of_death(claim)
        if date_of_death is None:
            return siu_units
        routine_care_ranges = RoutineCareRanges(self)
        routine_care_ranges.create_ranges(claim)
        non_covered_ranges = NonCoveredRanges()
        non_covered_ranges.create_ranges(claim)
        for line in claim.lines:
            if not (
                line.revenue_code.startswith("055") and line.hcpcs == "G0299"
            ) and not (
                line.revenue_code.startswith("056") and line.revenue_code != "0569"
            ):
                continue
            if line.service_date is None:
                continue
            if non_covered_ranges.is_non_covered(line.service_date):
                continue
            if not routine_care_ranges.in_any_range(line.service_date):
                continue
            days_since_death = (date_of_death - line.service_date).days
            if days_since_death < 0 or days_since_death >= 7:
                continue
            siu_units[days_since_death] += line.units
        return siu_units

    def get_provider_cbsa(self, claim: Claim) -> None | str:
        for val_code in claim.value_codes:
            if val_code.code == "G8":
                # Convert the float val amount to an integer and return it as a string
                return str(int(val_code.amount))
        return None

    def create_input_claim(self, claim: Claim) -> jpype.JObject:
        claim_object = self.hospice_pricer_claim_data_class()
        pricing_request = self.hospice_pricer_request_class()
        patient_cbsa = self.get_patient_cbsa(claim)
        provider_cbsa = self.get_provider_cbsa(claim)
        billing_groups = BillingGroups(self)
        billing_groups.build_billing_groups(claim)
        siu_units = self.siu_units(claim)
        if claim.from_date is not None:
            claim_object.setServiceFromDate(self.py_date_to_java_date(claim.from_date))
        if claim.admit_date is not None:
            claim_object.setAdmissionDate(self.py_date_to_java_date(claim.admit_date))
        elif claim.from_date is not None:
            claim_object.setAdmissionDate(self.py_date_to_java_date(claim.from_date))
        else:
            raise ValueError("Claim has no from_date or admit_date.")
        # @TODO: Add a way for the user to provide prior benefit days and reporting quality data flag
        claim_object.setPriorBenefitDayUnits(0)
        claim_object.setReportingQualityData("0")
        claim_object.setPatientCbsa(patient_cbsa if patient_cbsa is not None else "")
        claim_object.setProviderCbsa(provider_cbsa if provider_cbsa is not None else "")

        billing_group_list = self.array_list_class()
        for group in billing_groups.groups.values():
            billing_group = self.hospice_billing_group_class()
            billing_group.setDateOfService(
                self.py_date_to_java_date(group.service_date)
            )
            billing_group.setHcpcsCode(self.java_string_class(group.hcpcs_code))
            billing_group.setRevenueCode(self.java_string_class(group.revenue_code))
            billing_group.setUnits(self.java_integer_class(int(group.units)))
            billing_group_list.add(billing_group)
        claim_object.setBillingGroups(billing_group_list)

        eola_days = self.array_list_class()
        for i, units in enumerate(siu_units):
            eola_days.add(self.java_integer_class(int(units)))
        claim_object.setEndOfLifeAddOnDaysUnits(eola_days)
        pricing_request.setClaimData(claim_object)
        return pricing_request

    @handle_java_exceptions
    def process(self, claim: Claim) -> HospiceOutput:
        pricing_request = self.create_input_claim(claim)
        pricing_response = self.dispatch_obj.process(pricing_request)
        hospice_output = HospiceOutput()
        hospice_output.claim_id = claim.claimid
        hospice_output.from_java(pricing_response)
        return hospice_output
