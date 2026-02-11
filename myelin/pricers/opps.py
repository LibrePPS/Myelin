import os
from datetime import datetime
from logging import Logger, getLogger
from threading import current_thread

import jpype
from pydantic import BaseModel
from sqlalchemy import Engine

from myelin.helpers.utils import (
    PricerRuntimeError,
    ProviderDataError,
    ReturnCode,
    create_supported_years,
    float_or_none,
    handle_java_exceptions,
    py_date_to_java_date,
)
from myelin.input.claim import Claim
from myelin.ioce.ioce_output import IoceOutput
from myelin.plugins import apply_client_methods, run_client_load_classes
from myelin.pricers.opsf import OPSFProvider
from myelin.pricers.url_loader import UrlLoader


class OppsLineOutput(BaseModel):
    blood_deductible: float | None = None
    coinsurance_amount: float | None = None
    line_number: int | None = None
    payment: float | None = None
    reduced_coinsurance_amount: float | None = None
    reimbursement_amount: float | None = None
    total_deductible: float | None = None
    return_code: ReturnCode | None = None

    def from_java(self, java_object: jpype.JObject) -> None:
        """
        Convert a Java OppsLineOutput object to a Python OppsLineOutput object.
        """
        if java_object is None:
            return

        self.blood_deductible = float_or_none(java_object.getBloodDeductible())
        self.coinsurance_amount = float_or_none(java_object.getCoinsuranceAmount())
        self.line_number = java_object.getLineNumber()
        self.payment = float_or_none(java_object.getPayment())
        self.reduced_coinsurance_amount = float_or_none(
            java_object.getReducedCoinsurance()
        )
        self.reimbursement_amount = float_or_none(java_object.getReimbursementAmount())
        self.total_deductible = float_or_none(java_object.getTotalDeductible())
        return_code_data = java_object.getReturnCode()
        if return_code_data is not None:
            self.return_code = ReturnCode()
            self.return_code.from_java(return_code_data)


class OppsOutput(BaseModel):
    """
    Represents the output of the OPPS pricer.
    """

    claim_id: str = ""
    blood_deductible: float | None = None
    final_cbsa: str | None = None
    final_wage_index: float | None = None
    total_claim_charges: float | None = None
    total_claim_deductible: float | None = None
    total_claim_outlier_payment: float | None = None
    total_claim_payment: float | None = None
    blood_pints_used: int | None = None
    calculation_version: str | None = None
    return_code: ReturnCode | None = None
    service_lines: list[OppsLineOutput] | None = None

    def from_java(self, java_object: jpype.JObject) -> None:
        """
        Convert a Java OppsOutput object to a Python OppsOutput object.
        """
        if java_object is None:
            return

        payment_data = java_object.getPaymentData()
        self.blood_deductible = float_or_none(payment_data.getBloodDeductibleDue())
        self.final_cbsa = str(payment_data.getFinalCbsa())
        self.final_wage_index = float_or_none(payment_data.getFinalWageIndex())
        self.total_claim_charges = float_or_none(payment_data.getTotalClaimCharges())
        self.total_claim_deductible = float_or_none(
            payment_data.getTotalClaimDeductible()
        )
        self.total_claim_outlier_payment = float_or_none(
            payment_data.getTotalClaimOutlierPayment()
        )
        self.total_claim_payment = float_or_none(payment_data.getTotalPayment())
        self.blood_pints_used = payment_data.getBloodPintsUsed()

        self.calculation_version = str(java_object.getCalculationVersion())
        return_code_data = java_object.getReturnCodeData()
        if return_code_data is not None:
            self.return_code = ReturnCode()
            self.return_code.from_java(return_code_data)

        service_lines = payment_data.getServiceLinePayments()
        if service_lines is not None:
            self.service_lines = []
            for line in service_lines:
                line_output = OppsLineOutput()
                line_output.from_java(line)
                self.service_lines.append(line_output)


class OppsClient:
    def __init__(
        self,
        jar_path: str | None = None,
        db: Engine | None = None,
        logger: Logger | None = None,
    ):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using OppsClient."
            )
        # We need to use the URL class loader from Java to prevent classpath issues with other CMS pricers
        if jar_path is None:
            raise ValueError("jar_path must be provided to OppsClient")
        if not os.path.exists(jar_path):
            raise ValueError(f"jar_path does not exist: {jar_path}")
        self.url_loader = UrlLoader()
        # This loads the jar file into our URL class loader
        self.url_loader.load_urls([f"file://{jar_path}"])
        self.db = db
        if logger is not None:
            self.logger = logger
        else:
            self.logger = getLogger("OppsClient")
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
        """
        Load the necessary Java classes for the OPPS pricer.
        """
        self.opps_claim_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.opps.api.v2.OppsClaimData",
            loader=self.url_loader.class_loader,
        )
        self.opps_price_request_class = jpype.JClass(
            "gov.cms.fiss.pricers.opps.api.v2.OppsClaimPricingRequest",
            loader=self.url_loader.class_loader,
        )
        self.opps_price_response_class = jpype.JClass(
            "gov.cms.fiss.pricers.opps.api.v2.OppsClaimPricingResponse",
            loader=self.url_loader.class_loader,
        )
        self.opps_payment_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.opps.api.v2.OppsPaymentData",
            loader=self.url_loader.class_loader,
        )
        self.opps_price_config_class = jpype.JClass(
            "gov.cms.fiss.pricers.opps.OppsPricerConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.opps_dispatch_class = jpype.JClass(
            "gov.cms.fiss.pricers.opps.core.OppsPricerDispatch",
            loader=self.url_loader.class_loader,
        )
        self.outpatient_prov_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.opps.api.v2.OppsOutpatientProviderData",
            loader=self.url_loader.class_loader,
        )
        self.rtn_code_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.common.api.ReturnCodeData",
            loader=self.url_loader.class_loader,
        )
        self.svc_line_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.opps.api.v2.ServiceLinePaymentData",
            loader=self.url_loader.class_loader,
        )
        self.ioce_srvc_line_class = jpype.JClass(
            "gov.cms.fiss.pricers.opps.api.v2.IoceServiceLineData",
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

    def pricer_setup(self) -> None:
        self.opps_config_obj = self.opps_price_config_class()
        # Get today's year
        supported_years = create_supported_years("OPPS")
        self.opps_config_obj.setSupportedYears(supported_years)
        self.dispatch_obj = self.opps_dispatch_class(self.opps_config_obj)
        if self.dispatch_obj is None:
            raise RuntimeError(
                "Failed to create OppsPricerDispatch object. Check your JAR file and classpath."
            )

    def py_date_to_java_date(
        self, py_date: datetime | str | int | None
    ) -> jpype.JObject:
        """
        Convert a Python datetime object to a Java LocalDate object.
        """
        return py_date_to_java_date(self, py_date)

    def create_input_claim(
        self, claim: Claim, ioce_output: IoceOutput | None = None, **kwargs: object
    ) -> tuple[jpype.JObject, OPSFProvider]:
        opps_claim_object = self.opps_claim_data_class()

        opps_claim_object.setTypeOfBill(claim.bill_type)
        opps_claim_object.setServiceFromDate(self.py_date_to_java_date(claim.from_date))

        ioce_lines = self.array_list_class()
        if ioce_output is not None:
            for i, line in enumerate(ioce_output.line_item_list):
                ioce_line = self.ioce_srvc_line_class()
                try:
                    input_line = claim.lines[i]
                except IndexError:
                    raise PricerRuntimeError(
                        "OPPS05",
                        "Mismatching number of lines between IOCE output and claim lines",
                        f"IOCE output has more lines ({len(ioce_output.line_item_list)}) than claim lines ({len(claim.lines)})"
                    )
                ioce_line.setActionFlag(line.action_flag_output)
                ioce_line.setPaymentMethodFlag(line.payment_method_flag)
                ioce_line.setCompositeAdjustmentFlag(line.composite_adjustment_flag)
                ioce_line.setCoveredCharges(
                    self.java_big_decimal_class(input_line.charges)
                )
                ioce_line.setDenyOrRejectFlag(line.rejection_denial_flag)
                ioce_line.setHcpcsApc(line.hcpcs_apc)
                ioce_line.setRevenueCode(input_line.revenue_code)
                ioce_line.setPaymentApc(line.payment_apc)
                ioce_line.setHcpcsCode(line.hcpcs)
                ioce_line.setStatusIndicator(line.status_indicator)
                ioce_line.setPaymentIndicator(line.payment_indicator)
                ioce_line.setPackageFlag(line.packaging_flag.flag)
                ioce_line.setLineNumber(self.java_integer_class(i + 1))
                if line.units_output is not None:
                    ioce_line.setApcServiceUnits(int(line.units_output))
                if line.discounting_formula is not None:
                    if str(line.discounting_formula).isnumeric():
                        ioce_line.setDiscountingFormula((int(line.discounting_formula)))
                ioce_line.setDateOfService(
                    self.py_date_to_java_date(input_line.service_date)
                )

                adjustment_flags = self.array_list_class()
                adjustment_flags.add(line.payment_adjustment_flag01.flag)
                adjustment_flags.add(line.payment_adjustment_flag02.flag)
                ioce_line.setPaymentAdjustmentFlags(adjustment_flags)

                if len(input_line.modifiers) > 0:
                    modifiers = self.array_list_class()
                    for modifier in input_line.modifiers:
                        modifiers.add(self.java_string_class(modifier))
                    ioce_line.setHcpcsModifiers(modifiers)
                ioce_lines.add(ioce_line)
        else:
            raise PricerRuntimeError(
                "OPPS01",
                "Not implemented yet: IOCE output is required for OPPS claims.",
                "The IOCE output is required for OPPS processing",
            )
        opps_claim_object.setIoceServiceLines(ioce_lines)
        return opps_claim_object

    @handle_java_exceptions
    def process(
        self, claim: Claim, ioce_output: IoceOutput | None = None, **kwargs: object
    ) -> tuple[OppsOutput, OPSFProvider]:
        """
        Process the python claim object through the CMS OPPS Java Pricer.
        """
        if self.db is None:
            raise ValueError("Database connection is required for OppsClient.")
        self.logger.debug(
            f"OppsClient processing claim on thread {current_thread().ident}"
        )
        opps_claim_object = self.create_input_claim(claim, ioce_output, **kwargs)
        pricing_request = self.opps_price_request_class()
        pricing_request.setClaimData(opps_claim_object)
        provider_data = self.outpatient_prov_data_class()

        opsf_provider = OPSFProvider()
        try:
            opsf_provider.from_claim(claim, self.db, **kwargs)
        except ProviderDataError as e:
            self.logger.warning(
                f"Provider data error for claim {claim.claimid}: {e.description} — {e.explanation}"
            )
            opps_output = OppsOutput()
            opps_output.claim_id = claim.claimid
            opps_output.return_code = e.to_return_code()
            return opps_output, opsf_provider
        except PricerRuntimeError as e:
            opps_output = OppsOutput()
            opps_output.claim_id = claim.claimid
            opps_output.return_code = e.to_return_code()
            return (
                opps_output,
                opsf_provider if opsf_provider is not None else OPSFProvider(),
            )
        except Exception as e:
            opps_output = OppsOutput()
            opps_output.claim_id = claim.claimid
            opps_output.return_code = ReturnCode(
                code="UNX",
                description="Unexpected error",
                explanation="An unexpected error occurred while processing the claim.",
            )
            self.logger.error(f"Unexpected error for claim {claim.claimid}: {e}")
            return (
                opps_output,
                opsf_provider if opsf_provider is not None else OPSFProvider(),
            )
        opsf_provider.set_java_values(provider_data, self)

        pricing_request.setProviderData(provider_data)
        pricing_response = self.dispatch_obj.process(pricing_request)
        opps_output = OppsOutput()
        opps_output.claim_id = claim.claimid
        opps_output.from_java(pricing_response)
        return opps_output, opsf_provider
