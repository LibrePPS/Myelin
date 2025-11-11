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
from myelin.ioce.ioce_output import IoceOutput
from myelin.plugins import apply_client_methods, run_client_load_classes
from myelin.pricers.opsf import OPSFProvider
from myelin.pricers.url_loader import UrlLoader


class OppsLineOutput(BaseModel):
    blood_deductible: Optional[float] = None
    coinsurance_amount: Optional[float] = None
    line_number: Optional[int] = None
    payment: Optional[float] = None
    reduced_coinsurance_amount: Optional[float] = None
    reimbursement_amount: Optional[float] = None
    total_deductible: Optional[float] = None
    return_code: Optional[ReturnCode] = None

    def from_java(self, java_object):
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
    blood_deductible: Optional[float] = None
    final_cbsa: Optional[str] = None
    final_wage_index: Optional[float] = None
    total_claim_charges: Optional[float] = None
    total_claim_deductible: Optional[float] = None
    total_claim_outlier_payment: Optional[float] = None
    total_claim_payment: Optional[float] = None
    blood_pints_used: Optional[int] = None
    calculation_version: Optional[str] = None
    return_code: Optional[ReturnCode] = None
    service_lines: Optional[list[OppsLineOutput]] = None

    def from_java(self, java_object):
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
        jar_path=None,
        db: Optional[Engine] = None,
        logger: Optional[Logger] = None,
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

    def load_classes(self):
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

    def pricer_setup(self):
        self.opps_config_obj = self.opps_price_config_class()
        # Get today's year
        supported_years = create_supported_years("OPPS")
        self.opps_config_obj.setSupportedYears(supported_years)
        self.dispatch_obj = self.opps_dispatch_class(self.opps_config_obj)
        if self.dispatch_obj is None:
            raise RuntimeError(
                "Failed to create OppsPricerDispatch object. Check your JAR file and classpath."
            )

    def py_date_to_java_date(self, py_date):
        """
        Convert a Python datetime object to a Java LocalDate object.
        """
        return py_date_to_java_date(self, py_date)

    def create_input_claim(
        self, claim: Claim, ioce_output: Optional[IoceOutput] = None, **kwargs
    ) -> jpype.JObject:
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
                    raise IndexError(
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
                ioce_line.setApcServiceUnits(int(line.units_output))
                if str(line.discounting_formula).isnumeric():
                    ioce_line.setDiscountingFormula((int(line.discounting_formula)))
                else:
                    raise ValueError(
                        f"Invalid discounting formula: {line.discounting_formula}. Expected an integer."
                    )
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
            raise ValueError(
                "Not implemented yet: IOCE output is required for OPPS claims."
            )
        opps_claim_object.setIoceServiceLines(ioce_lines)
        return opps_claim_object

    @handle_java_exceptions
    def process(self, claim: Claim, ioce_output: Optional[IoceOutput] = None, **kwargs):
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

        if claim.billing_provider is not None:
            if isinstance(claim.thru_date, datetime):
                date_int = int(claim.thru_date.strftime("%Y%m%d"))
            else:
                date_int = int(str(claim.thru_date).replace("-", ""))
            opsf_provider = OPSFProvider()

            opsf_provider.from_sqlite(
                self.db, claim.billing_provider, date_int, **kwargs
            )
        elif claim.servicing_provider is not None:
            if isinstance(claim.thru_date, datetime):
                date_int = int(claim.thru_date.strftime("%Y%m%d"))
            else:
                date_int = int(str(claim.thru_date).replace("-", ""))
            opsf_provider = OPSFProvider()
            opsf_provider.from_sqlite(
                self.db, claim.servicing_provider, date_int, **kwargs
            )
        else:
            raise ValueError(
                "Either billing or servicing provider must be provided for IPPS pricing."
            )
        opsf_provider.set_java_values(provider_data, self)

        pricing_request.setProviderData(provider_data)
        pricing_response = self.dispatch_obj.process(pricing_request)
        opps_output = OppsOutput()
        opps_output.claim_id = claim.claimid
        opps_output.from_java(pricing_response)
        if ioce_output is not None:
            opps_output.ioce_output = ioce_output
        return opps_output
