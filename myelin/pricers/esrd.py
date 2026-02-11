import os
from datetime import datetime
from logging import Logger, getLogger

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
from myelin.plugins import apply_client_methods, run_client_load_classes
from myelin.pricers.opsf import OPSFProvider
from myelin.pricers.url_loader import UrlLoader


class ComorbidityCode(BaseModel):
    category: str
    start_date: datetime
    end_date: datetime


COMORBIDITY_CODES: dict[str, ComorbidityCode] = {
    "K2211": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K250": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K252": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K254": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K256": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K260": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K262": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K264": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K266": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K270": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K272": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K274": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K276": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K280": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K282": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K284": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K286": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K31811": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5521": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5701": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5711": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5713": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5721": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5731": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5733": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5741": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5751": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5753": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5781": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5791": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "K5793": ComorbidityCode(
        category="MA",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "A1884": ComorbidityCode(
        category="MC",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "I300": ComorbidityCode(
        category="MC",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "I301": ComorbidityCode(
        category="MC",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "I308": ComorbidityCode(
        category="MC",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "I309": ComorbidityCode(
        category="MC",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "I32": ComorbidityCode(
        category="MC",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "M3212": ComorbidityCode(
        category="MC",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D550": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D551": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D552": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D553": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D558": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D559": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D560": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D561": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D562": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D563": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D565": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D568": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5700": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5701": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5702": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5703": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5709": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D571": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5720": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57211": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57212": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57213": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57218": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57219": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5740": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57411": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57412": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57413": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57418": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57419": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5742": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57431": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57432": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57433": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57438": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57439": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5744": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57451": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57452": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57453": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57458": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57459": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D5780": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57811": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57812": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57813": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57818": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D57819": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D580": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D581": ComorbidityCode(
        category="MD",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D460": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D461": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D4620": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D4621": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D4622": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D464": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D469": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D46A": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D46B": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D46C": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D46Z": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D471": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
    "D473": ComorbidityCode(
        category="ME",
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2050, 1, 1),
    ),
}


class EsrdBundledPayment(BaseModel):
    blended_composite_rate: float | None = None
    blended_outlier_rate: float | None = None
    blended_payment_rate: float | None = None
    comorbidity_payment_code: str | None = None
    full_composite_rate: float | None = None
    full_outlier_rate: float | None = None
    full_payment_rate: float | None = None

    def from_java(self, java_obj: jpype.JObject) -> None:
        self.blended_composite_rate = float_or_none(java_obj.getBlendedCompositeRate())
        self.blended_outlier_rate = float_or_none(java_obj.getBlendedOutlierRate())
        self.blended_payment_rate = float_or_none(java_obj.getBlendedPaymentRate())
        self.comorbidity_payment_code = str(java_obj.getComorbidityPaymentCode())
        self.full_composite_rate = float_or_none(java_obj.getFullCompositeRate())
        self.full_outlier_rate = float_or_none(java_obj.getFullOutlierRate())
        self.full_payment_rate = float_or_none(java_obj.getFullPaymentRate())


class EsrdAdditionalPayment(BaseModel):
    age_adjustment_factor: float | None = None
    body_mass_index_factor: float | None = None
    body_surface_area_factor: float | None = None
    budget_neutrality_rate: float | None = None
    national_labor_percent: float | None = None
    national_non_labor_percent: float | None = None
    wage_adjustment_rate: float | None = None

    def from_java(self, java_obj: jpype.JObject) -> None:
        self.age_adjustment_factor = float_or_none(java_obj.getAgeAdjustmentFactor())
        self.body_mass_index_factor = float_or_none(java_obj.getBodyMassIndexFactor())
        self.body_surface_area_factor = float_or_none(
            java_obj.getBodySurfaceAreaFactor()
        )
        self.budget_neutrality_rate = float_or_none(java_obj.getBudgetNeutralityRate())
        self.national_labor_percent = float_or_none(java_obj.getNationalLaborPercent())
        self.national_non_labor_percent = float_or_none(
            java_obj.getNationalNonLaborPercent()
        )
        self.wage_adjustment_rate = float_or_none(java_obj.getWageAdjustmentRate())


class EsrdOutput(BaseModel):
    claim_id: str = ""
    return_code: ReturnCode | None = None
    calculation_version: str | None = None
    total_payment: float | None = None
    adj_base_wage_before_etc: float | None = None
    low_volume_amount: float | None = None
    network_reduction_amount: float | None = None
    outlier_non_per_diem_payment: float | None = None
    ppa_adjustment_amount: float | None = None
    pre_ppa_adjustment_amount: float | None = None
    post_ppa_adjustment_amount: float | None = None
    tdapa_adjustment_amount: float | None = None
    tpniescra_adjustment_amount: float | None = None
    tpnies_adjustment_amount: float | None = None
    hdpa_adjustment_amount: float | None = None
    final_wage_index: float | None = None
    additional_payment_data: EsrdAdditionalPayment | None = None
    bundled_payment_data: EsrdBundledPayment | None = None

    def from_java(self, java_obj: jpype.JObject) -> None:
        self.calculation_version = str(java_obj.getCalculationVersion())
        ret_code = java_obj.getReturnCodeData()
        if ret_code:
            self.return_code = ReturnCode()
            self.return_code.from_java(ret_code)
        payment_data = java_obj.getPaymentData()
        if payment_data:
            self.total_payment = float_or_none(payment_data.getTotalPayment())
            self.adj_base_wage_before_etc = float_or_none(
                payment_data.getAdjustedBaseWageBeforeEtcHdpaAmount()
            )
            self.low_volume_amount = float_or_none(payment_data.getLowVolumeAmount())
            self.network_reduction_amount = float_or_none(
                payment_data.getNetworkReductionAmount()
            )
            self.outlier_non_per_diem_payment = float_or_none(
                payment_data.getOutlierNonPerDiemPaymentAmount()
            )
            self.ppa_adjustment_amount = float_or_none(
                payment_data.getPpaAdjustmentAmount()
            )
            self.pre_ppa_adjustment_amount = float_or_none(
                payment_data.getPrePpaAdjustmentAmount()
            )
            self.post_ppa_adjustment_amount = float_or_none(
                payment_data.getPostPpaAdjustmentAmount()
            )
            self.tdapa_adjustment_amount = float_or_none(
                payment_data.getTdapaPaymentAdjustmentAmount()
            )
            self.tpniescra_adjustment_amount = float_or_none(
                payment_data.getTpniesCraPaymentAdjustmentAmount()
            )
            self.tpnies_adjustment_amount = float_or_none(
                payment_data.getTpniesPaymentAdjustmentAmount()
            )
            self.hdpa_adjustment_amount = float_or_none(
                payment_data.getHdpaAdjustmentAmount()
            )
            self.final_wage_index = float_or_none(payment_data.getFinalWageIndex())
            additional_data = payment_data.getAdditionalPaymentInformation()
            if additional_data:
                self.additional_payment_data = EsrdAdditionalPayment()
                self.additional_payment_data.from_java(additional_data)
            bundled_data = payment_data.getBundledPaymentInformation()
            if bundled_data:
                self.bundled_payment_data = EsrdBundledPayment()
                self.bundled_payment_data.from_java(bundled_data)


class EsrdClient:
    def __init__(
        self,
        jar_path: str | None = None,
        db: Engine | None = None,
        logger: Logger | None = None,
    ):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using EsrdClient."
            )
        # We need to use the URL class loader from Java to prevent classpath issues with other CMS pricers
        if jar_path is None:
            raise ValueError("jar_path must be provided to EsrdClient")
        if not os.path.exists(jar_path):
            raise ValueError(f"jar_path does not exist: {jar_path}")
        self.url_loader = UrlLoader()
        # This loads the jar file into our URL class loader
        self.url_loader.load_urls([f"file://{jar_path}"])
        self.db = db
        if logger is not None:
            self.logger = logger
        else:
            self.logger = getLogger("EsrdClient")
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
        self.esrd_pricer_config_class = jpype.JClass(
            "gov.cms.fiss.pricers.esrd.EsrdPricerConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.provider_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.esrd.api.v2.EsrdOutpatientProviderData",
            loader=self.url_loader.class_loader,
        )

        self.esrd_pricer_dispatch_class = jpype.JClass(
            "gov.cms.fiss.pricers.esrd.core.EsrdPricerDispatch",
            loader=self.url_loader.class_loader,
        )
        self.esrd_pricer_request_class = jpype.JClass(
            "gov.cms.fiss.pricers.esrd.api.v2.EsrdClaimPricingRequest",
            loader=self.url_loader.class_loader,
        )
        self.esrd_pricer_response_class = jpype.JClass(
            "gov.cms.fiss.pricers.esrd.api.v2.EsrdClaimPricingResponse",
            loader=self.url_loader.class_loader,
        )
        self.esrd_pricer_payment_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.esrd.api.v2.EsrdPaymentData",
            loader=self.url_loader.class_loader,
        )
        self.esrd_pricer_claim_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.esrd.api.v2.EsrdClaimData",
            loader=self.url_loader.class_loader,
        )
        self.esrd_csv_ingest_class = jpype.JClass(
            "gov.cms.fiss.pricers.common.csv.CsvIngestionConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.esrd_data_table_class = jpype.JClass(
            "gov.cms.fiss.pricers.esrd.core.tables.DataTables",
            loader=self.url_loader.class_loader,
        )
        self.rtn_code_data = jpype.JClass(
            "gov.cms.fiss.pricers.common.api.ReturnCodeData",
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
        self.comorbid_conditions_class = jpype.JClass(
            "gov.cms.fiss.pricers.esrd.api.v2.ComorbidityData",
            loader=self.url_loader.class_loader,
        )

    def pricer_setup(self) -> None:
        self.esrd_config_obj = self.esrd_pricer_config_class()
        self.csv_ingest_obj = self.esrd_csv_ingest_class()
        self.esrd_config_obj.setCsvIngestionConfiguration(self.csv_ingest_obj)

        # Get today's year
        supported_years = create_supported_years("ESRD")
        self.esrd_config_obj.setSupportedYears(supported_years)
        self.esrd_data_table_class.loadDataTables(self.esrd_config_obj)
        self.dispatch_obj = self.esrd_pricer_dispatch_class(self.esrd_config_obj)
        if self.dispatch_obj is None:
            raise RuntimeError(
                "Failed to create EsrdPricerDispatch object. Check your JAR file and classpath."
            )

    def py_date_to_java_date(self, py_date: datetime) -> jpype.JObject:
        return py_date_to_java_date(self, py_date)

    def get_dialysis_rev(self, claim: Claim) -> str:
        for line in claim.lines:
            if (
                line.revenue_code == "0821"
                or line.revenue_code == "0831"
                or line.revenue_code == "0841"
                or line.revenue_code == "0851"
                or line.revenue_code == "0881"
            ):
                return line.revenue_code
        raise PricerRuntimeError(
            "ESRD01",
            "No dialysis revenue code found in claim lines",
            "Please check the claim lines for the correct revenue code.",
        )

    def get_dialysis_session_count(self, claim: Claim, dialysis_rev: str) -> int:
        dialysis_dates = set()
        for line in claim.lines:
            if line.revenue_code == dialysis_rev:
                if line.service_date is not None:
                    dialysis_dates.add(line.service_date)
        return len(dialysis_dates)

    def create_input_claim(
        self, claim: Claim, **kwargs: object
    ) -> tuple[jpype.JObject, OPSFProvider]:
        if self.db is None:
            raise ValueError("Database connection is required for ESRD pricing")
        claim_object = self.esrd_pricer_claim_data_class()
        pricing_request = self.esrd_pricer_request_class()
        provider_data = self.provider_data_class()
        if claim.esrd_initial_date is None:
            raise PricerRuntimeError(
                "ESRD02",
                "ESRD initial date is required for ESRD pricing",
                "Please provide the ESRD initial date in the claim object.",
            )
        claim_object.setDialysisStartDate(
            self.py_date_to_java_date(claim.esrd_initial_date)
        )

        cond_code_list = self.array_list_class()
        for cond in claim.cond_codes:
            cond_code_list.add(cond)
        claim_object.setConditionCodes(cond_code_list)

        dialysis_rev = self.get_dialysis_rev(claim)
        session_count = self.get_dialysis_session_count(claim, dialysis_rev)
        if session_count == 0:
            raise PricerRuntimeError(
                "ESRD03",
                "No dialysis sessions found in claim",
                "Please provide a valid claim with at least one dialysis session.",
            )
        claim_object.setDialysisSessionCount(self.java_integer_class(session_count))
        claim_object.setRevenueCode(dialysis_rev)

        if claim.patient is None:
            raise PricerRuntimeError(
                "ESRD04",
                "Patient is required for ESRD pricing",
                "Please provide a valid claim with a patient.",
            )
        if claim.patient.date_of_birth is None:
            raise PricerRuntimeError(
                "ESRD05",
                "Patient Date of Birth is required for ESRD pricing",
                "Please provide a valid claim with a patient's date of birth.",
            )
        claim_object.setPatientDateOfBirth(
            self.py_date_to_java_date(claim.patient.date_of_birth)
        )

        height_set = False
        weight_set = False
        for val in claim.value_codes:
            if val.code == "A8":
                claim_object.setPatientWeight(self.java_big_decimal_class(val.amount))
                weight_set = True
            elif val.code == "A9":
                claim_object.setPatientHeight(self.java_big_decimal_class(val.amount))
                height_set = True
            if val.code == "Q8":
                claim_object.setTotalTdapaAmountQ8(
                    self.java_big_decimal_class(val.amount)
                )
            elif val.code == "QG":
                claim_object.setTotalTpniesAmountQg(
                    self.java_big_decimal_class(val.amount)
                )
            elif val.code == "QH":
                claim_object.setTotalTpniesCraAmountQh(
                    self.java_big_decimal_class(val.amount)
                )

        if not height_set:
            raise PricerRuntimeError(
                "ESRD06",
                "Patient Height is required for ESRD pricing"
                "Please provide the patient's height in centimeters in Value code A9",
            )
        if not weight_set:
            raise PricerRuntimeError(
                "ESRD07",
                "Patient Weight is required for ESRD pricing"
                "Please provide the patient's weight in kilograms in Value code A8",
            )

        if claim.from_date:
            claim_object.setServiceDate(self.py_date_to_java_date(claim.from_date))
        if claim.thru_date:
            claim_object.setServiceThroughDate(
                self.py_date_to_java_date(claim.thru_date)
            )

        demo_codes = self.array_list_class()
        for code in claim.demo_codes:
            demo_codes.add(str(code))
        claim_object.setDemoCodes(demo_codes)

        ect_choice = ""
        if "esrd" in claim.additional_data and isinstance(
            claim.additional_data["esrd"], dict
        ):
            esrd_data = claim.additional_data["esrd"]
            if "ect_choice" in esrd_data:
                if esrd_data["ect_choice"] in ["H", "P", "B", None, ""]:
                    ect_choice = esrd_data["ect_choice"]
                    if "ppa_adjustment" not in esrd_data and ect_choice in ("P", "B"):
                        raise PricerRuntimeError(
                            "ESRD08",
                            "PPA adjustment is required when ECT is 'P' or 'B'",
                            "Please provide a valid PPA adjustment value",
                        )
                    else:
                        ppa_adjustment = 1
                        if "ppa_adjustment" in esrd_data:
                            if isinstance(esrd_data["ppa_adjustment"], float):
                                ppa_adjustment = esrd_data["ppa_adjustment"]
                                claim_object.setPpaAdjustmentPercent(
                                    self.java_big_decimal_class(ppa_adjustment)
                                )
                else:
                    raise PricerRuntimeError(
                        "ESRD09",
                        "Invalid ECT choice",
                        "ECT choice must be 'H', 'P', 'B', or None/empty",
                    )
        claim_object.setTreatmentChoicesIndicator(str(ect_choice))

        comorbidity_codes = self.array_list_class()
        for code in claim.secondary_dxs:
            comorbidity_code = COMORBIDITY_CODES.get(code.code.replace(".", ""))
            if comorbidity_code:
                if (
                    claim.from_date
                    and claim.thru_date
                    and comorbidity_code.start_date >= claim.from_date
                    and comorbidity_code.end_date <= claim.thru_date
                ):
                    comorbidity_codes.add(comorbidity_code.category)
        comorbidity_obj = self.comorbid_conditions_class()
        comorbidity_obj.setComorbidityCodes(comorbidity_codes)
        claim_object.setComorbidities(comorbidity_obj)

        opsf_provider = OPSFProvider()
        opsf_provider.from_claim(claim, self.db, **kwargs)
        if opsf_provider:
            opsf_provider.set_java_values(provider_data, self)
            if (
                opsf_provider.special_payment_indicator is None
                or opsf_provider.special_payment_indicator.strip() == ""
            ):
                provider_data.setSpecialPaymentIndicator("")
            pricing_request.setProviderData(provider_data)
        pricing_request.setClaimData(claim_object)
        return pricing_request, opsf_provider

    def process_claim(
        self, claim: Claim, pricing_request: jpype.JObject
    ) -> jpype.JObject:
        if hasattr(self.dispatch_obj, "process"):
            return self.dispatch_obj.process(pricing_request)
        raise ValueError("Dispatch object does not have a process method.")

    @handle_java_exceptions
    def process(
        self, claim: Claim, **kwargs: object
    ) -> tuple[EsrdOutput, OPSFProvider]:
        """
        Process the claim and return the SNF pricing response.

        :param claim: Claim object to process.
        :return: SnfOutput object.
        """
        opsf_provider = None
        if not isinstance(claim, Claim):
            raise ValueError("claim must be an instance of Claim")
        try:
            pricing_request, opsf_provider = self.create_input_claim(claim, **kwargs)
        except ProviderDataError as e:
            self.logger.warning(
                f"Provider data error for claim {claim.claimid}: {e.description} — {e.explanation}"
            )
            esrd_output = EsrdOutput()
            esrd_output.claim_id = claim.claimid
            esrd_output.return_code = e.to_return_code()
            return esrd_output, OPSFProvider()
        except PricerRuntimeError as e:
            esrd_output = EsrdOutput()
            esrd_output.claim_id = claim.claimid
            esrd_output.return_code = e.to_return_code()
            return (
                esrd_output,
                opsf_provider if opsf_provider is not None else OPSFProvider(),
            )
        except Exception as e:
            self.logger.error(f"Unexpected error occurred: {e}")
            esrd_output = EsrdOutput()
            esrd_output.claim_id = claim.claimid
            esrd_output.return_code = ReturnCode(
                code="UNX",
                description="Unexpected error",
                explanation="Unexpected/Uncaught error occurred",
            )
            return (
                esrd_output,
                opsf_provider if opsf_provider is not None else OPSFProvider(),
            )

        pricing_response = self.process_claim(claim, pricing_request)
        esrd_output = EsrdOutput()
        esrd_output.claim_id = claim.claimid
        esrd_output.from_java(pricing_response)
        return esrd_output, opsf_provider
