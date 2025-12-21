import os
import shutil
from datetime import datetime
from logging import Logger, getLogger
from threading import current_thread

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


class AdditionalCapitalVariableData(BaseModel):
    capital_cost_outlier: float | None = 0.0
    capital_disproportionate_share_hospital_adjustment: float | None = 0.0
    capital_disproportionate_share_hospital_amount: float | None = 0.0
    capital_exception_amount: float | None = None
    capital_federal_rate: float | None = 0.0
    capital_federal_specific_portion: float | None = 0.0
    capital_federal_specific_portion_2b: float | None = 0.0
    capital_federal_specific_portion_percent: float | None = 0.0
    capital_geographic_adjustment_factor: float | None = 1.0
    capital_hospital_specific_portion: float | None = None
    capital_hospital_specific_portion_part: float | None = None
    capital_hospital_specific_portion_percent: float | None = None
    capital_indirect_medical_education_adjustment: float | None = 0.0
    capital_indirect_medical_education_amount: float | None = 0.0
    capital_large_urban_factor: float | None = 1
    capital_old_hold_harmless_amount: float | None = None
    capital_old_hold_harmless_rate: float | None = None
    capital_outlier: float | None = None
    capital_outlier_2b: float | None = None
    capital_payment_code: str | None = None
    capital_total_payment: float | None = 0.0

    def from_java(self, java_obj: jpype.JObject) -> None:
        self.capital_cost_outlier = float_or_none(java_obj.getCapitalCostOutlier())
        self.capital_disproportionate_share_hospital_adjustment = float_or_none(
            java_obj.getCapitalDisproportionateShareHospitalAdjustment()
        )
        self.capital_disproportionate_share_hospital_amount = float_or_none(
            java_obj.getCapitalDisproportionateShareHospitalAmount()
        )
        self.capital_exception_amount = float_or_none(
            java_obj.getCapitalExceptionAmount()
        )
        self.capital_federal_rate = float_or_none(java_obj.getCapitalFederalRate())
        self.capital_federal_specific_portion = float_or_none(
            java_obj.getCapitalFederalSpecificPortion()
        )
        self.capital_federal_specific_portion_2b = float_or_none(
            java_obj.getCapitalFederalSpecificPortion2B()
        )
        self.capital_federal_specific_portion_percent = float_or_none(
            java_obj.getCapitalFederalSpecificPortionPercent()
        )
        self.capital_geographic_adjustment_factor = float_or_none(
            java_obj.getCapitalGeographicAdjustmentFactor()
        )
        self.capital_hospital_specific_portion = float_or_none(
            java_obj.getCapitalHospitalSpecificPortion()
        )
        self.capital_hospital_specific_portion_part = float_or_none(
            java_obj.getCapitalHospitalSpecificPortionPart()
        )
        self.capital_hospital_specific_portion_percent = float_or_none(
            java_obj.getCapitalHospitalSpecificPortionPercent()
        )
        self.capital_indirect_medical_education_adjustment = float_or_none(
            java_obj.getCapitalIndirectMedicalEducationAdjustment()
        )
        self.capital_indirect_medical_education_amount = float_or_none(
            java_obj.getCapitalIndirectMedicalEducationAmount()
        )
        self.capital_large_urban_factor = float_or_none(
            java_obj.getCapitalLargeUrbanFactor()
        )
        self.capital_old_hold_harmless_amount = float_or_none(
            java_obj.getCapitalOldHoldHarmlessAmount()
        )
        self.capital_old_hold_harmless_rate = float_or_none(
            java_obj.getCapitalOldHoldHarmlessRate()
        )
        self.capital_outlier = float_or_none(java_obj.getCapitalOutlier())
        self.capital_outlier_2b = float_or_none(java_obj.getCapitalOutlier2B())
        self.capital_payment_code = str(java_obj.getCapitalPaymentCode())
        self.capital_total_payment = float_or_none(java_obj.getCapitalTotalPayment())

    def to_json(self):
        return {
            "capital_cost_outlier": self.capital_cost_outlier,
            "capital_disproportionate_share_hospital_adjustment": self.capital_disproportionate_share_hospital_adjustment,
            "capital_disproportionate_share_hospital_amount": self.capital_disproportionate_share_hospital_amount,
            "capital_exception_amount": self.capital_exception_amount,
            "capital_federal_rate": self.capital_federal_rate,
            "capital_federal_specific_portion": self.capital_federal_specific_portion,
            "capital_federal_specific_portion_2b": self.capital_federal_specific_portion_2b,
            "capital_federal_specific_portion_percent": self.capital_federal_specific_portion_percent,
            "capital_geographic_adjustment_factor": self.capital_geographic_adjustment_factor,
            "capital_hospital_specific_portion": self.capital_hospital_specific_portion,
            "capital_hospital_specific_portion_part": self.capital_hospital_specific_portion_part,
            "capital_hospital_specific_portion_percent": self.capital_hospital_specific_portion_percent,
            "capital_indirect_medical_education_adjustment": self.capital_indirect_medical_education_adjustment,
            "capital_indirect_medical_education_amount": self.capital_indirect_medical_education_amount,
            "capital_large_urban_factor": self.capital_large_urban_factor,
            "capital_old_hold_harmless_amount": self.capital_old_hold_harmless_amount,
            "capital_old_hold_harmless_rate": self.capital_old_hold_harmless_rate,
            "capital_outlier": self.capital_outlier,
            "capital_outlier_2b": self.capital_outlier_2b,
            "capital_payment_code": self.capital_payment_code,
            "capital_total_payment": self.capital_total_payment,
        }


class AdditionalOperatingVariableData(BaseModel):
    operating_base_drg_payment: float | None = 0.0
    operating_disproportionate_share_hospital_amount: float | None = 0.0
    operating_disproportionate_share_hospital_ratio: float | None = 0.0
    operating_dollar_threshold: float | None = 0.0
    operating_federal_specific_portion_part: float | None = 0.0
    operating_hospital_specific_portion_part: float | None = 0.0
    operating_indirect_medical_education_amount: float | None = 0.0

    def from_java(self, java_obj: jpype.JObject) -> None:
        self.operating_base_drg_payment = float_or_none(
            java_obj.getOperatingBaseDrgPayment()
        )
        self.operating_disproportionate_share_hospital_amount = float_or_none(
            java_obj.getOperatingDisproportionateShareHospitalAmount()
        )
        self.operating_disproportionate_share_hospital_ratio = float_or_none(
            java_obj.getOperatingDisproportionateShareHospitalRatio()
        )
        self.operating_dollar_threshold = float_or_none(
            java_obj.getOperatingDollarThreshold()
        )
        self.operating_federal_specific_portion_part = float_or_none(
            java_obj.getOperatingFederalSpecificPortionPart()
        )
        self.operating_hospital_specific_portion_part = float_or_none(
            java_obj.getOperatingHospitalSpecificPortionPart()
        )
        self.operating_indirect_medical_education_amount = float_or_none(
            java_obj.getOperatingIndirectMedicalEducationAmount()
        )

    def to_json(self):
        return {
            "operating_base_drg_payment": self.operating_base_drg_payment,
            "operating_disproportionate_share_hospital_amount": self.operating_disproportionate_share_hospital_amount,
            "operating_disproportionate_share_hospital_ratio": self.operating_disproportionate_share_hospital_ratio,
            "operating_dollar_threshold": self.operating_dollar_threshold,
            "operating_federal_specific_portion_part": self.operating_federal_specific_portion_part,
            "operating_hospital_specific_portion_part": self.operating_hospital_specific_portion_part,
            "operating_indirect_medical_education_amount": self.operating_indirect_medical_education_amount,
        }


class AdditionalPaymentInformationData(BaseModel):
    bundled_adjustment_payment: float | None = None
    electronic_health_record_adjustment_payment: float | None = None
    hospital_acquired_condition_payment: float | None = None
    hospital_readmission_reduction_adjustment_payment: float | None = 0.0
    standard_value: float | None = 0.0
    uncompensated_care_payment: float | None = 0.0
    value_based_purchasing_adjustment_payment: float | None = 0.0

    def from_java(self, java_obj: jpype.JObject) -> None:
        self.bundled_adjustment_payment = float_or_none(
            java_obj.getBundledAdjustmentPayment()
        )
        self.electronic_health_record_adjustment_payment = float_or_none(
            java_obj.getElectronicHealthRecordAdjustmentPayment()
        )
        self.hospital_acquired_condition_payment = float_or_none(
            java_obj.getHospitalAcquiredConditionPayment()
        )
        self.hospital_readmission_reduction_adjustment_payment = float_or_none(
            java_obj.getHospitalReadmissionReductionAdjustmentPayment()
        )
        self.standard_value = float_or_none(java_obj.getStandardValue())
        self.uncompensated_care_payment = float_or_none(
            java_obj.getUncompensatedCarePayment()
        )
        self.value_based_purchasing_adjustment_payment = float_or_none(
            java_obj.getValueBasedPurchasingAdjustmentPayment()
        )

    def to_json(self):
        return {
            "bundled_adjustment_payment": self.bundled_adjustment_payment,
            "electronic_health_record_adjustment_payment": self.electronic_health_record_adjustment_payment,
            "hospital_acquired_condition_payment": self.hospital_acquired_condition_payment,
            "hospital_readmission_reduction_adjustment_payment": self.hospital_readmission_reduction_adjustment_payment,
            "standard_value": self.standard_value,
            "uncompensated_care_payment": self.uncompensated_care_payment,
            "value_based_purchasing_adjustment_payment": self.value_based_purchasing_adjustment_payment,
        }


class AdditionalCalculationVariableData(BaseModel):
    additional_capital_variables: AdditionalCapitalVariableData = (
        AdditionalCapitalVariableData()
    )
    additional_operating_variables: AdditionalOperatingVariableData = (
        AdditionalOperatingVariableData()
    )
    additional_payment_information: AdditionalPaymentInformationData = (
        AdditionalPaymentInformationData()
    )
    cost_threshold: float | None = 0.0
    discharge_fraction: float | None = 1.0
    drg_relative_weight: float | None = 0.0
    drg_relative_weight_fraction: float | None = 0.0
    federal_specific_portion_percent: float | None = 1.0
    flx7_payment: float | None = 0.0
    hospital_readmission_reduction_adjustment: float | None = 1.0
    hospital_readmission_reduction_indicator: str | None = ""
    hospital_specific_portion_percent: float | None = None
    hospital_specific_portion_rate: float | None = 0.0
    islet_isolation_add_on_payment: float | None = None
    low_volume_payment: float | None = None
    national_labor_cost: float | None = 0.0
    national_labor_percent: float | None = 0.62
    national_non_labor_cost: float | None = 0.0
    national_non_labor_percent: float | None = 0.38
    national_percent: float | None = 1.0
    new_technology_add_on_payment: float | None = None
    passthrough_total_plus_misc: float | None = None
    regular_labor_cost: float | None = 0.0
    regular_non_labor_cost: float | None = 0.0
    regular_percent: float | None = None
    value_based_purchasing_adjustment_amount: float | None = 1.0
    value_based_purchasing_participant_indicator: str | None = "Y"
    wage_index: float | None = 1.0

    def from_java(self, java_obj: jpype.JObject) -> None:
        self.additional_payment_information = AdditionalPaymentInformationData()
        self.additional_payment_information.from_java(
            java_obj.getAdditionalPaymentInformation()
        )
        self.additional_capital_variables = AdditionalCapitalVariableData()
        self.additional_capital_variables.from_java(
            java_obj.getAdditionalCapitalVariables()
        )
        self.additional_operating_variables = AdditionalOperatingVariableData()
        self.additional_operating_variables.from_java(
            java_obj.getAdditionalOperatingVariables()
        )
        self.cost_threshold = float_or_none(java_obj.getCostThreshold())
        self.discharge_fraction = float_or_none(java_obj.getDischargeFraction())
        self.drg_relative_weight = float_or_none(java_obj.getDrgRelativeWeight())
        self.drg_relative_weight_fraction = float_or_none(
            java_obj.getDrgRelativeWeightFraction()
        )
        self.federal_specific_portion_percent = float_or_none(
            java_obj.getFederalSpecificPortionPercent()
        )
        self.flx7_payment = float_or_none(java_obj.getFlx7Payment())
        self.hospital_readmission_reduction_adjustment = float_or_none(
            java_obj.getHospitalReadmissionReductionAdjustment()
        )
        self.hospital_readmission_reduction_indicator = str(
            java_obj.getHospitalReadmissionReductionIndicator()
        )
        self.hospital_specific_portion_percent = float_or_none(
            java_obj.getHospitalSpecificPortionPercent()
        )
        self.hospital_specific_portion_rate = float_or_none(
            java_obj.getHospitalSpecificPortionRate()
        )
        self.islet_isolation_add_on_payment = float_or_none(
            java_obj.getIsletIsolationAddOnPayment()
        )
        self.low_volume_payment = float_or_none(java_obj.getLowVolumePayment())
        self.national_labor_cost = float_or_none(java_obj.getNationalLaborCost())
        self.national_labor_percent = float_or_none(java_obj.getNationalLaborPercent())
        self.national_non_labor_cost = float_or_none(java_obj.getNationalNonLaborCost())
        self.national_non_labor_percent = float_or_none(
            java_obj.getNationalNonLaborPercent()
        )
        self.national_percent = float_or_none(java_obj.getNationalPercent())
        self.new_technology_add_on_payment = float_or_none(
            java_obj.getNewTechnologyAddOnPayment()
        )
        self.passthrough_total_plus_misc = float_or_none(
            java_obj.getPassthroughTotalPlusMisc()
        )
        self.regular_labor_cost = float_or_none(java_obj.getRegularLaborCost())
        self.regular_non_labor_cost = float_or_none(java_obj.getRegularNonLaborCost())
        self.regular_percent = float_or_none(java_obj.getRegularPercent())
        self.value_based_purchasing_adjustment_amount = float_or_none(
            java_obj.getValueBasedPurchasingAdjustmentAmount()
        )
        self.value_based_purchasing_participant_indicator = str(
            java_obj.getValueBasedPurchasingParticipantIndicator()
        )
        self.wage_index = float_or_none(java_obj.getWageIndex())

    def to_json(self):
        return {
            "cost_threshold": self.cost_threshold,
            "discharge_fraction": self.discharge_fraction,
            "drg_relative_weight": self.drg_relative_weight,
            "drg_relative_weight_fraction": self.drg_relative_weight_fraction,
            "federal_specific_portion_percent": self.federal_specific_portion_percent,
            "flx7_payment": self.flx7_payment,
            "hospital_readmission_reduction_adjustment": self.hospital_readmission_reduction_adjustment,
            "hospital_readmission_reduction_indicator": self.hospital_readmission_reduction_indicator,
            "hospital_specific_portion_percent": self.hospital_specific_portion_percent,
            "hospital_specific_portion_rate": self.hospital_specific_portion_rate,
            "islet_isolation_add_on_payment": self.islet_isolation_add_on_payment,
            "low_volume_payment": self.low_volume_payment,
            "national_labor_cost": self.national_labor_cost,
            "national_labor_percent": self.national_labor_percent,
            "national_non_labor_cost": self.national_non_labor_cost,
            "national_non_labor_percent": self.national_non_labor_percent,
            "national_percent": self.national_percent,
            "new_technology_add_on_payment": self.new_technology_add_on_payment,
            "passthrough_total_plus_misc": self.passthrough_total_plus_misc,
            "regular_labor_cost": self.regular_labor_cost,
            "regular_non_labor_cost": self.regular_non_labor_cost,
            "regular_percent": self.regular_percent,
            "value_based_purchasing_adjustment_amount": self.value_based_purchasing_adjustment_amount,
            "value_based_purchasing_participant_indicator": self.value_based_purchasing_participant_indicator,
            "wage_index": self.wage_index,
            "additional_capital_variables": self.additional_capital_variables.to_json(),
            "additional_operating_variables": self.additional_operating_variables.to_json(),
            "additional_payment_information": self.additional_payment_information.to_json(),
        }


class IppsOutput(BaseModel):
    """
    Represents the output of the IPPS pricer.
    """

    claim_id: str = ""
    return_code: ReturnCode | None = None
    calculation_version: str | None = None
    average_length_of_stay: float | None = None
    days_cutoff: float | None = None
    lifetime_reserved_days_used: int | None = 0
    operating_dsh_adjustment: float | None = 0.0
    operating_fsp_part: float | None = 0.0
    operating_hsp_part: float | None = 0.0
    operating_ime_adjustment: float | None = 0.0
    operating_outlier_payment_part: float | None = 0.0
    outlier_days: int | None = 0
    regular_days_used: int | None = 0
    final_cbsa: str | None = None
    final_wage_index: float | None = 1.0
    total_payment: float | None = 0.0
    additional_calculation_variables: AdditionalCalculationVariableData = (
        AdditionalCalculationVariableData()
    )

    def from_java(self, java_obj: jpype.JObject) -> None:
        self.calculation_version = str(java_obj.getCalculationVersion())
        return_code_value = java_obj.getReturnCodeData()
        if return_code_value:
            self.return_code = ReturnCode()
            self.return_code.from_java(return_code_value)
        payment_data = java_obj.getPaymentData()
        self.average_length_of_stay = float_or_none(
            payment_data.getAverageLengthOfStay()
        )
        self.days_cutoff = float_or_none(payment_data.getDaysCutoff())
        self.lifetime_reserved_days_used = (
            payment_data.getLifetimeReserveDaysUsed()
            if payment_data.getLifetimeReserveDaysUsed() is not None
            else 0
        )
        self.operating_dsh_adjustment = float_or_none(
            payment_data.getOperatingDisproportionateShareHospitalAdjustment()
        )
        self.operating_fsp_part = float_or_none(
            payment_data.getOperatingFederalSpecificPortionPart()
        )
        self.operating_hsp_part = float_or_none(
            payment_data.getOperatingHospitalSpecificPortionPart()
        )
        self.operating_ime_adjustment = float_or_none(
            payment_data.getOperatingIndirectMedicalEducationAdjustment()
        )
        self.operating_outlier_payment_part = float_or_none(
            payment_data.getOperatingOutlierPaymentPart()
        )
        self.outlier_days = (
            payment_data.getOutlierDays()
            if payment_data.getOutlierDays() is not None
            else 0
        )
        self.regular_days_used = (
            payment_data.getRegularDaysUsed()
            if payment_data.getRegularDaysUsed() is not None
            else 0
        )
        self.final_cbsa = (
            str(payment_data.getFinalCbsa())
            if payment_data.getFinalCbsa() is not None
            else None
        )
        self.final_wage_index = float_or_none(payment_data.getFinalWageIndex())
        self.total_payment = float_or_none(payment_data.getTotalPayment())
        self.additional_calculation_variables.from_java(
            java_obj.getAdditionalCalculationVariables()
        )

    def to_json(self):
        return {
            "additional_calculation_variables": self.additional_calculation_variables.to_json(),
        }


class IppsClient:
    def __init__(
        self,
        jar_path: str | None = None,
        db: Engine | None = None,
        logger: Logger | None = None,
    ):
        if not jpype.isJVMStarted():
            raise RuntimeError(
                "JVM is not started. Please start the JVM before using IppsClient."
            )
        # We need to use the URL class loader from Java to prevent classpath issues with other CMS pricers
        if jar_path is None:
            raise ValueError("jar_path must be provided to IppsClient")
        if not os.path.exists(jar_path):
            raise ValueError(f"jar_path does not exist: {jar_path}")
        self.url_loader = UrlLoader()
        # This loads the jar file into our URL class loader
        self.url_loader.load_urls([f"file://{jar_path}"])
        self.db = db
        if logger is not None:
            self.logger = logger
        else:
            self.logger = getLogger("IppsClient")
        self.add_hmo(jar_path)
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

    def extract_resource(self, resource_file_name: str) -> bytes:
        """
        Extracts a resource file from the IPPS pricer JAR file to memory.

        Args:
            resource_file_name: Name of the resource file to extract
        Returns:
            bytes: The extracted resource file as bytes
        """
        BufferedInputStream = jpype.JClass("java.io.BufferedInputStream")
        ByteArrayOutputStream = jpype.JClass("java.io.ByteArrayOutputStream")

        stream = self.ipps_csv_ingest_class.class_.getResourceAsStream(
            f"/{resource_file_name}"
        )
        if stream is None:
            raise FileNotFoundError(f"{resource_file_name} not found in that JAR")

        bis = BufferedInputStream(stream)
        baos = ByteArrayOutputStream()
        buf = jpype.JArray(jpype.JByte)(4096)

        while True:
            n = bis.read(buf)
            if n == -1:
                break
            baos.write(buf, 0, n)

        data = bytes(baos.toByteArray())  # Python bytes
        bis.close()
        return data

    def extract_resource_file(
        self, resource_file_name: str, extract_dir: str | None = None
    ):
        """
        Extracts a resource file from the IPPS pricer JAR file.

        Args:
            resource_file_name: Name of the resource file to extract
            extract_dir: Directory to extract the resource file to
        """
        ins = self.ipps_csv_ingest_class.class_.getResourceAsStream(
            f"/{resource_file_name}"
        )
        if ins is None:
            raise FileNotFoundError(f"{resource_file_name} not found in that JAR")

        Files = jpype.JClass("java.nio.file.Files")
        Paths = jpype.JClass("java.nio.file.Paths")
        StandardCopyOption = jpype.JClass("java.nio.file.StandardCopyOption")

        Files.copy(
            ins, Paths.get(resource_file_name), StandardCopyOption.REPLACE_EXISTING
        )
        if extract_dir:
            os.makedirs(extract_dir, exist_ok=True)
            shutil.move(
                resource_file_name, os.path.join(extract_dir, resource_file_name)
            )
        ins.close()

    def add_hmo(self, jar_path: str) -> None:
        """
        Adds HMO functionality to the IPPS pricer by dynamically modifying Java classes.

        This method uses Javassist to:
        1. Add an hmoClaim field to IppsClaimPricingRequest
        2. Modify the pricing logic to handle HMO claims
        3. Enable the HMO totals calculation rule

        Args:
            jar_path: Path to the IPPS pricer JAR file
        """
        # Load Javassist classes with the custom class loader
        ct_field = jpype.JClass(
            "javassist.CtField", loader=self.url_loader.class_loader
        )
        ct_new_method = jpype.JClass(
            "javassist.CtNewMethod", loader=self.url_loader.class_loader
        )
        class_pool = jpype.JClass(
            "javassist.ClassPool", loader=self.url_loader.class_loader
        )
        loader_class_path = jpype.JClass(
            "javassist.LoaderClassPath", loader=self.url_loader.class_loader
        )

        # Set up ClassPool with system path and custom class loader
        cp = class_pool()
        cp.appendSystemPath()  # Include core Java classes
        cp.insertClassPath(loader_class_path(self.url_loader.class_loader))
        cp.appendClassPath(jar_path)

        # Step 1: Add hmoClaim field to IppsClaimPricingRequest
        claim_request_class = cp.get(
            "gov.cms.fiss.pricers.ipps.api.v2.IppsClaimPricingRequest"
        )

        try:
            # Check if hmoClaim field already exists
            claim_request_class.getField("hmoClaim")
            self.logger.info("hmoClaim field already exists in IppsClaimPricingRequest")
            return
        except Exception:
            # Add the hmoClaim field and its getter/setter methods
            hmo_field = ct_field.make(
                "public boolean hmoClaim = false;", claim_request_class
            )
            claim_request_class.addField(hmo_field)

            # Add getter method
            getter = ct_new_method.make(
                "public boolean getHmoClaim() { return $0.hmoClaim; }",
                claim_request_class,
            )
            claim_request_class.addMethod(getter)

            # Add setter method
            setter = ct_new_method.make(
                "public void setHmoClaim(boolean value) { $0.hmoClaim = value; }",
                claim_request_class,
            )
            claim_request_class.addMethod(setter)

            # Load the modified class (required for Java 19+)
            neighbor_class = jpype.JClass(
                "gov.cms.fiss.pricers.ipps.api.v2.IppsClaimPricingResponse",
                loader=self.url_loader.class_loader,
            )
            claim_request_class.toClass(neighbor_class)

        # Step 2: Modify RuleContextExecutor to handle HMO claims
        self._modify_rule_context_executor(cp)

        # Step 3: Enable HMO totals calculation
        self._enable_hmo_totals_calculation(cp)

    def _modify_rule_context_executor(self, class_pool: jpype.JClass) -> None:
        """
        Modifies the RuleContextExecutor to extract and set HMO flag during pricing.

        Args:
            class_pool: Javassist ClassPool instance
        """
        ctx_class = class_pool.get(
            "gov.cms.fiss.pricers.common.application.rules.RuleContextExecutor"
        )
        price_claim_method = ctx_class.getDeclaredMethod("priceClaim")

        # New method body that extracts HMO flag and sets it in the context
        new_method_body = """{
            gov.cms.fiss.pricers.common.application.rules.CalculationContext calculationContext = $0.contextFor($1);
            boolean hmo = ((gov.cms.fiss.pricers.ipps.api.v2.IppsClaimPricingRequest)calculationContext.getInput()).getHmoClaim();
            ((gov.cms.fiss.pricers.ipps.core.IppsPricerContext)calculationContext).setHmoClaim(hmo);
            $0.ruleEvaluator.evaluateRulesForContext(calculationContext);
            gov.cms.fiss.pricers.common.application.rules.ContextCapture.captureClaim(calculationContext, $0.getClass());
            gov.cms.fiss.pricers.common.application.rules.ContextCapture.resetRuleSequence();
            return calculationContext.getOutput();
        }"""

        price_claim_method.setBody(new_method_body)

        # Load the modified class
        ctx_neighbor = jpype.JClass(
            "gov.cms.fiss.pricers.common.application.rules.CalculationContext",
            loader=self.url_loader.class_loader,
        )
        ctx_class.toClass(ctx_neighbor)

    def _enable_hmo_totals_calculation(self, class_pool: jpype.JClass) -> None:
        """
        Enables the HMO totals calculation rule by overriding shouldExecute to always return true.

        Args:
            class_pool: Javassist ClassPool instance
        """
        hmo_class = class_pool.get(
            "gov.cms.fiss.pricers.ipps.core.rules.calculate_payment.totals.CalculateHmoTotals"
        )
        should_execute_method = hmo_class.getDeclaredMethod("shouldExecute")
        should_execute_method.setBody("{ return true; }")

        # Load the modified class
        hmo_neighbor = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.core.rules.calculate_payment.totals.CalculateOperatingTotals",
            loader=self.url_loader.class_loader,
        )
        hmo_class.toClass(hmo_neighbor)

    def load_classes(self) -> None:
        self.ipps_csv_ingest_class = jpype.JClass(
            "gov.cms.fiss.pricers.common.csv.CsvIngestionConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.ipps_claim_data_class = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.api.v2.IppsClaimData",
            loader=self.url_loader.class_loader,
        )
        self.ipps_price_request = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.api.v2.IppsClaimPricingRequest",
            loader=self.url_loader.class_loader,
        )
        self.ipps_price_response = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.api.v2.IppsClaimPricingResponse",
            loader=self.url_loader.class_loader,
        )
        self.ipps_payment_data = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.api.v2.IppsPaymentData",
            loader=self.url_loader.class_loader,
        )
        self.ipps_add_calc_vars = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.api.v2.AdditionalCalculationVariableData",
            loader=self.url_loader.class_loader,
        )
        self.ipps_add_capital_vars = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.api.v2.AdditionalCapitalVariableData",
            loader=self.url_loader.class_loader,
        )
        self.ipps_add_operating_vars = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.api.v2.AdditionalOperatingVariableData",
            loader=self.url_loader.class_loader,
        )
        self.ipps_add_payment_info = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.api.v2.AdditionalPaymentInformationData",
            loader=self.url_loader.class_loader,
        )
        self.ipps_price_config = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.IppsPricerConfiguration",
            loader=self.url_loader.class_loader,
        )
        self.ipps_dispatch = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.core.IppsPricerDispatch",
            loader=self.url_loader.class_loader,
        )
        self.inpatient_prov_data = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.api.v2.IppsInpatientProviderData",
            loader=self.url_loader.class_loader,
        )
        self.rtn_code_data = jpype.JClass(
            "gov.cms.fiss.pricers.common.api.ReturnCodeData",
            loader=self.url_loader.class_loader,
        )
        self.ipps_data_tables_class = jpype.JClass(
            "gov.cms.fiss.pricers.ipps.core.tables.DataTables",
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

    def create_dispatch(self) -> jpype.JObject:
        return self.ipps_dispatch(self.ipps_config_obj)

    def pricer_setup(self):
        self.ipps_config_obj = self.ipps_price_config()
        self.csv_ingest_obj = self.ipps_csv_ingest_class()
        self.ipps_config_obj.setCsvIngestionConfiguration(self.csv_ingest_obj)

        # Get today's year
        supported_years = create_supported_years("IPPS")
        self.ipps_config_obj.setSupportedYears(supported_years)
        self.ipps_data_tables_class.loadDataTables(self.ipps_config_obj)
        self.dispatch_obj = self.create_dispatch()
        if self.dispatch_obj is None:
            raise RuntimeError(
                "Failed to create IppsPricerDispatch object. Check your JAR file and classpath."
            )

    def py_date_to_java_date(
        self, py_date: datetime | str | int | None
    ) -> jpype.JObject:
        return py_date_to_java_date(self, py_date)

    def create_input_claim(
        self, claim: Claim, drg_output: MsdrgOutput | None = None, **kwargs: object
    ) -> tuple[jpype.JObject, IPSFProvider]:
        claim_object = self.ipps_claim_data_class()
        provider_data = self.inpatient_prov_data()
        pricing_request = self.ipps_price_request()
        if self.db is None:
            raise ValueError("Database connection is required for IppsClient.")

        # @TODO Probably a better way to handle this
        # Also need to document that the 'ipps' key needs to be present in additional_data
        review_code = "00"
        demo_codes = self.array_list_class()
        for code in claim.demo_codes:
            demo_codes.add(code)
        claim_object.setDemoCodes(demo_codes)

        lifetime_reserve_days = 0
        midnight_adjustment_geolocation = ""
        if isinstance(claim.additional_data, dict):
            if "ipps" in claim.additional_data:
                ipps_data = claim.additional_data["ipps"]
                if not isinstance(ipps_data, dict):
                    pass
                review_code = str(ipps_data.get("review_code", "00"))
                lifetime_reserve_days = int(ipps_data.get("lifetime_reserve_days", 0))
                midnight_adjustment_geolocation = str(
                    ipps_data.get("midnight_adjustment_geolocation", "")
                )
        claim_object.setReviewCode(review_code)
        claim_object.setLifetimeReserveDays(
            self.java_integer_class(lifetime_reserve_days)
        )
        claim_object.setMidnightAdjustmentGeolocation(midnight_adjustment_geolocation)
        claim_object.setCoveredCharges(self.java_big_decimal_class(claim.total_charges))
        if claim.los < claim.non_covered_days:
            raise ValueError("LOS cannot be less than non-covered days")
        claim_object.setCoveredDays(
            self.java_integer_class(claim.los - claim.non_covered_days)
        )
        if claim.thru_date is not None:
            claim_object.setDischargeDate(self.py_date_to_java_date(claim.thru_date))
        else:
            raise ValueError("Thru date is required.")
        claim_object.setLengthOfStay(self.java_integer_class(claim.los))
        if claim.billing_provider is not None:
            claim_object.setProviderCcn(claim.billing_provider.other_id)

        java_dxs = self.array_list_class()
        if claim.principal_dx is not None:
            java_dxs.add(claim.principal_dx.code)
        if claim.admit_dx is not None:
            java_dxs.add(claim.admit_dx.code)
        for dx in claim.secondary_dxs:
            java_dxs.add(dx.code)
        claim_object.setDiagnosisCodes(java_dxs)

        java_procedures = self.array_list_class()
        for pr in claim.inpatient_pxs:
            java_procedures.add(pr.code)

        ndc_list = self.array_list_class()
        for line in claim.lines:
            if line.ndc != "":
                ndc_list.add(line.ndc)
        claim_object.setNationalDrugCodes(ndc_list)

        cond_codes = self.array_list_class()
        for code in claim.cond_codes:
            cond_codes.add(code)
        claim_object.setConditionCodes(cond_codes)

        if drg_output is not None:
            claim_object.setDiagnosisRelatedGroup(str(drg_output.final_drg_value))
            claim_object.setDiagnosisRelatedGroupSeverity(
                str(drg_output.final_severity)
            )
        else:
            if "drg" in claim.additional_data:
                drg = claim.additional_data["drg"]
                claim_object.setDiagnosisRelatedGroup(str(drg))
            else:
                raise ValueError(
                    "Either MS DRG Grouper output or DRG code in additional data is required."
                )
        pricing_request.setClaimData(claim_object)

        ipsf_provider = IPSFProvider()
        ipsf_provider.from_claim(claim, self.db, **kwargs)
        ipsf_provider.set_java_values(provider_data, self)
        pricing_request.setProviderData(provider_data)
        pricing_request.setHmoClaim(claim.hmo)
        return pricing_request, ipsf_provider

    def process_claim(
        self, claim: Claim, pricing_request: jpype.JObject
    ) -> jpype.JObject:
        if hasattr(self.dispatch_obj, "process"):
            return self.dispatch_obj.process(pricing_request)
        raise ValueError("Dispatch object does not have a process method.")

    @handle_java_exceptions
    def process(
        self, claim: Claim, drg_output: MsdrgOutput | None = None, **kwargs: object
    ) -> tuple[IppsOutput, IPSFProvider]:
        """
        Process the claim and return the IPPS pricing response.

        :param claim: Claim object to process.
        :param drg_output: MsdrgOutput object containing DRG information.
        :return: IppsClaimPricingResponse object.
        """
        if not isinstance(claim, Claim):
            raise ValueError("claim must be an instance of Claim")
        self.logger.debug(
            f"IppsClient processing claim on thread {current_thread().ident}"
        )
        pricing_request, ipsf_provider = self.create_input_claim(
            claim, drg_output, **kwargs
        )
        pricing_response = self.process_claim(claim, pricing_request, **kwargs)
        ipps_output = IppsOutput()
        ipps_output.claim_id = claim.claimid
        ipps_output.from_java(pricing_response)
        return ipps_output, ipsf_provider
