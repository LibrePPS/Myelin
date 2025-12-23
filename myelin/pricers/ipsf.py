import csv
from datetime import datetime
import os
from typing import Any, Iterable, Literal

import requests
import sqlalchemy
from pydantic import BaseModel
from sqlalchemy import (
    Column,
    Engine,
    Float,
    Index,
    Integer,
    String,
    bindparam,
    create_engine,
    select,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from myelin.input.claim import Provider, Claim
from myelin.plugins import apply_client_methods

IPSF_URL = "https://pds.mps.cms.gov/fiss/v2/inpatient/export?fromDate=2023-01-01&toDate=2030-12-31"

DATATYPES = {
    "provider_ccn": {"type": "TEXT", "position": 0},
    "effective_date": {"type": "INT", "position": 1},
    "fiscal_year_begin_date": {"type": "INT", "position": 2},
    "export_date": {"type": "INT", "position": 3},
    "termination_date": {"type": "INT", "position": 4},
    "waiver_indicator": {"type": "TEXT", "position": 5},
    "intermediary_number": {"type": "TEXT", "position": 6},
    "provider_type": {"type": "TEXT", "position": 7},
    "census_division": {"type": "TEXT", "position": 8},
    "msa_actual_geographic_location": {"type": "TEXT", "position": 9},
    "msa_wage_index_location": {"type": "TEXT", "position": 10},
    "msa_standardized_amount_location": {"type": "TEXT", "position": 11},
    "sole_community_or_medicare_dependent_hospital_base_year": {
        "type": "TEXT",
        "position": 12,
    },
    "change_code_for_lugar_reclassification": {"type": "TEXT", "position": 13},
    "temporary_relief_indicator": {"type": "TEXT", "position": 14},
    "federal_pps_blend": {"type": "TEXT", "position": 15},
    "state_code": {"type": "TEXT", "position": 16},
    "pps_facility_specific_rate": {"type": "REAL", "position": 17},
    "cost_of_living_adjustment": {"type": "REAL", "position": 18},
    "interns_to_beds_ratio": {"type": "REAL", "position": 19},
    "bed_size": {"type": "INT", "position": 20},
    "operating_cost_to_charge_ratio": {"type": "REAL", "position": 21},
    "case_mix_index": {"type": "REAL", "position": 22},
    "supplemental_security_income_ratio": {"type": "REAL", "position": 23},
    "medicaid_ratio": {"type": "REAL", "position": 24},
    "special_provider_update_factor": {"type": "REAL", "position": 25},
    "operating_dsh": {"type": "REAL", "position": 26},
    "fiscal_year_end_date": {"type": "INT", "position": 27},
    "special_payment_indicator": {"type": "TEXT", "position": 28},
    "hosp_quality_indicator": {"type": "TEXT", "position": 29},
    "cbsa_actual_geographic_location": {"type": "TEXT", "position": 30},
    "cbsa_wi_location": {"type": "TEXT", "position": 31},
    "cbsa_standardized_amount_location": {"type": "TEXT", "position": 32},
    "special_wage_index": {"type": "REAL", "position": 33},
    "pass_through_amount_for_capital": {"type": "REAL", "position": 34},
    "pass_through_amount_for_direct_medical_education": {
        "type": "REAL",
        "position": 35,
    },
    "pass_through_amount_for_organ_acquisition": {"type": "REAL", "position": 36},
    "pass_through_total_amount": {"type": "REAL", "position": 37},
    "capital_pps_payment_code": {"type": "TEXT", "position": 38},
    "hospital_specific_capital_rate": {"type": "REAL", "position": 39},
    "old_capital_hold_harmless_rate": {"type": "REAL", "position": 40},
    "new_capital_hold_harmless_rate": {"type": "REAL", "position": 41},
    "capital_cost_to_charge_ratio": {"type": "REAL", "position": 42},
    "new_hospital": {"type": "TEXT", "position": 43},
    "capital_indirect_medical_education_ratio": {"type": "REAL", "position": 44},
    "capital_exception_payment_rate": {"type": "REAL", "position": 45},
    "vpb_participant_indicator": {"type": "TEXT", "position": 46},
    "vbp_adjustment": {"type": "REAL", "position": 47},
    "hrr_participant_indicator": {"type": "INT", "position": 48},
    "hrr_adjustment": {"type": "REAL", "position": 49},
    "bundle_model_discount": {"type": "REAL", "position": 50},
    "hac_reduction_participant_indicator": {"type": "TEXT", "position": 51},
    "uncompensated_care_amount": {"type": "REAL", "position": 52},
    "ehr_reduction_indicator": {"type": "TEXT", "position": 53},
    "low_volume_adjustment_factor": {"type": "REAL", "position": 54},
    "county_code": {"type": "TEXT", "position": 55},
    "medicare_performance_adjustment": {"type": "REAL", "position": 56},
    "ltch_dpp_indicator": {"type": "TEXT", "position": 57},
    "supplemental_wage_index": {"type": "REAL", "position": 58},
    "supplemental_wage_index_indicator": {"type": "TEXT", "position": 59},
    "change_code_wage_index_reclassification": {"type": "TEXT", "position": 60},
    "national_provider_identifier": {"type": "TEXT", "position": 61},
    "pass_through_amount_for_allogenic_stem_cell_acquisition": {
        "type": "REAL",
        "position": 62,
    },
    "pps_blend_year_indicator": {"type": "TEXT", "position": 63},
    "last_updated": {"type": "TEXT", "position": 64},
    "pass_through_amount_for_direct_graduate_medical_education": {
        "type": "REAL",
        "position": 65,
    },
    "pass_through_amount_for_kidney_acquisition": {"type": "REAL", "position": 66},
    "pass_through_amount_for_supply_chain": {"type": "REAL", "position": 67},
}

INT_FIELDS = {k for k, v in DATATYPES.items() if v["type"] == "INT"}
REAL_FIELDS = {k for k, v in DATATYPES.items() if v["type"] == "REAL"}

Base = declarative_base()

# Simple session factory cache to avoid recreating sessionmaker repeatedly
_SESSION_FACTORY_CACHE: dict[int, sessionmaker] = {}


class IPSF(Base):
    __tablename__ = "ipsf"
    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_ccn = Column(String, index=True)
    effective_date = Column(Integer, index=True)
    fiscal_year_begin_date = Column(Integer)
    export_date = Column(Integer)
    termination_date = Column(Integer)
    waiver_indicator = Column(String)
    intermediary_number = Column(String)
    provider_type = Column(String)
    census_division = Column(String)
    msa_actual_geographic_location = Column(String)
    msa_wage_index_location = Column(String)
    msa_standardized_amount_location = Column(String)
    sole_community_or_medicare_dependent_hospital_base_year = Column(String)
    change_code_for_lugar_reclassification = Column(String)
    temporary_relief_indicator = Column(String)
    federal_pps_blend = Column(String)
    state_code = Column(String)
    pps_facility_specific_rate = Column(Float)
    cost_of_living_adjustment = Column(Float)
    interns_to_beds_ratio = Column(Float)
    bed_size = Column(Integer)
    operating_cost_to_charge_ratio = Column(Float)
    case_mix_index = Column(Float)
    supplemental_security_income_ratio = Column(Float)
    medicaid_ratio = Column(Float)
    special_provider_update_factor = Column(Float)
    operating_dsh = Column(Float)
    fiscal_year_end_date = Column(Integer)
    special_payment_indicator = Column(String)
    hosp_quality_indicator = Column(String)
    cbsa_actual_geographic_location = Column(String)
    cbsa_wi_location = Column(String)
    cbsa_standardized_amount_location = Column(String)
    special_wage_index = Column(Float)
    pass_through_amount_for_capital = Column(Float)
    pass_through_amount_for_direct_medical_education = Column(Float)
    pass_through_amount_for_organ_acquisition = Column(Float)
    pass_through_total_amount = Column(Float)
    capital_pps_payment_code = Column(String)
    hospital_specific_capital_rate = Column(Float)
    old_capital_hold_harmless_rate = Column(Float)
    new_capital_hold_harmless_rate = Column(Float)
    capital_cost_to_charge_ratio = Column(Float)
    new_hospital = Column(String)
    capital_indirect_medical_education_ratio = Column(Float)
    capital_exception_payment_rate = Column(Float)
    vpb_participant_indicator = Column(String)
    vbp_adjustment = Column(Float)
    hrr_participant_indicator = Column(Integer)
    hrr_adjustment = Column(Float)
    bundle_model_discount = Column(Float)
    hac_reduction_participant_indicator = Column(String)
    uncompensated_care_amount = Column(Float)
    ehr_reduction_indicator = Column(String)
    low_volume_adjustment_factor = Column(Float)
    county_code = Column(String)
    medicare_performance_adjustment = Column(Float)
    ltch_dpp_indicator = Column(String)
    supplemental_wage_index = Column(Float)
    supplemental_wage_index_indicator = Column(String)
    change_code_wage_index_reclassification = Column(String)
    national_provider_identifier = Column(String, index=True)
    pass_through_amount_for_allogenic_stem_cell_acquisition = Column(Float)
    pps_blend_year_indicator = Column(String)
    last_updated = Column(String)
    pass_through_amount_for_direct_graduate_medical_education = Column(Float)
    pass_through_amount_for_kidney_acquisition = Column(Float)
    pass_through_amount_for_supply_chain = Column(Float)

    __table_args__ = (
        Index("idx_ipsf_ccn_effective", "provider_ccn", "effective_date"),
        Index(
            "idx_ipsf_npi_effective", "national_provider_identifier", "effective_date"
        ),
    )

    def to_provider_model(self) -> "IPSFProvider":
        data = {k: getattr(self, k) for k in DATATYPES.keys() if hasattr(self, k)}
        return IPSFProvider(**data)


# Prepared statements (defined after IPSF is declared)
IPSF_BY_CCN = (
    select(IPSF)
    .where(
        IPSF.provider_ccn == bindparam("ccn"),
        IPSF.effective_date <= bindparam("date_int"),
    )
    .order_by(IPSF.effective_date.desc())
    .limit(1)
)

IPSF_BY_NPI = (
    select(IPSF)
    .where(
        IPSF.national_provider_identifier == bindparam("npi"),
        IPSF.effective_date <= bindparam("date_int"),
    )
    .order_by(IPSF.effective_date.desc())
    .limit(1)
)


class IPSFDatabase:
    """Unified IPSF database helper supporting sqlite & postgres via SQLAlchemy ORM."""

    def __init__(
        self, db_path: str, db_backend: Literal["sqlite", "postgres"] = "sqlite"
    ):
        self.db_path = db_path
        self.db_backend = db_backend
        self._engine: sqlalchemy.Engine | None = None
        self._Session: sessionmaker | None = None
        self._init_engine()

    def _init_engine(self):
        if self._engine is not None:
            return
        if self.db_backend == "sqlite":
            engine_str = f"sqlite:///{self.db_path}"
            self._engine = create_engine(
                engine_str, future=True, pool_pre_ping=True, echo=False
            )
        else:
            host = os.getenv("MYELIN_PG_HOST", "localhost")
            port = os.getenv("MYELIN_PG_PORT", "5432")
            user = os.getenv("MYELIN_PG_USER", "user")
            password = os.getenv("MYELIN_PG_PASSWORD", "password")
            database = os.getenv("MYELIN_PG_DATABASE", "database")
            engine_str = (
                f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"
            )
            self._engine = create_engine(
                engine_str,
                future=True,
                pool_pre_ping=True,
                echo=False,
            )
        self._Session = sessionmaker(
            bind=self._engine, expire_on_commit=False, future=True
        )
        Base.metadata.create_all(self._engine)

    @property
    def engine(self) -> sqlalchemy.Engine:
        if self._engine is None:
            self._init_engine()
        return self._engine  # type: ignore

    def session(self) -> Session:
        if self._Session is None:
            self._init_engine()
        return self._Session()  # type: ignore

    def download(self, url: str = IPSF_URL, download_dir: str | None = None) -> str:
        download_dir = download_dir or os.path.dirname(self.db_path) or "."
        os.makedirs(download_dir, exist_ok=True)
        filename = os.path.join(download_dir, "ipsf_data.csv")
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(filename, "wb") as fh:
            for chunk in response.iter_content(chunk_size=1 << 15):
                if chunk:
                    fh.write(chunk)
        return filename

    def _row_iter(self, csv_path: str) -> Iterable[dict[str, Any]]:
        with open(csv_path, "r", newline="") as fh:
            reader = csv.reader(fh)
            next(reader, None)  # Skip header
            for row in reader:
                if not row or len(row) < len(DATATYPES):
                    continue
                rec: dict[str, Any] = {}
                for name, meta in DATATYPES.items():
                    pos = int(meta["position"])
                    val = row[pos] if pos < len(row) else None
                    if val == "":
                        val = None
                    if name in INT_FIELDS and val is not None:
                        try:
                            val = int(val)
                        except ValueError:
                            val = None
                    elif name in REAL_FIELDS and val is not None:
                        try:
                            val = float(val)
                        except ValueError:
                            val = None
                    rec[name] = val
                yield rec

    def populate(
        self, download: bool = True, batch_size: int = 4000, truncate: bool = True
    ) -> int:
        csv_path = (
            self.download()
            if download
            else os.path.join(os.path.dirname(self.db_path), "ipsf_data.csv")
        )
        total = 0
        from sqlalchemy import insert as sql_insert

        insert_stmt = sql_insert(IPSF)
        with self.session() as sess:
            if truncate:
                sess.query(IPSF).delete()
                sess.commit()
            batch: list[dict[str, Any]] = []
            for rec in self._row_iter(csv_path):
                batch.append(rec)
                if len(batch) >= batch_size:
                    sess.execute(insert_stmt, batch)
                    sess.commit()
                    total += len(batch)
                    batch.clear()
            if batch:
                sess.execute(insert_stmt, batch)
                sess.commit()
                total += len(batch)
        if download and os.path.exists(csv_path):
            try:
                os.remove(csv_path)
            except OSError:
                pass
        return total

    # Backwards compatibility convenience
    def to_sqlite(self, create_table: bool = True):  # type: ignore
        if create_table:
            Base.metadata.create_all(self.engine)
        self.populate(download=True, truncate=True)

    def close(self):
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._Session = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class IPSFProvider(BaseModel):
    provider_ccn: str | None = ""
    effective_date: int | None = 19000101
    fiscal_year_begin_date: int | None = 19000101
    export_date: int | None = 19000101
    termination_date: int | None = 19000101
    waiver_indicator: str | None = ""
    intermediary_number: str | None = ""
    provider_type: str | None = ""
    census_division: str | None = ""
    msa_actual_geographic_location: str | None = ""
    msa_wage_index_location: str | None = ""
    msa_standardized_amount_location: str | None = ""
    sole_community_or_medicare_dependent_hospital_base_year: str | None = ""
    change_code_for_lugar_reclassification: str | None = ""
    temporary_relief_indicator: str | None = ""
    federal_pps_blend: str | None = ""
    state_code: str | None = ""
    pps_facility_specific_rate: float | None = 0.0
    cost_of_living_adjustment: float | None = 0.0
    interns_to_beds_ratio: float | None = 0.0
    bed_size: int | None = 0
    operating_cost_to_charge_ratio: float | None = 0.0
    case_mix_index: float | None = 0.0
    supplemental_security_income_ratio: float | None = 0.0
    medicaid_ratio: float | None = 0.0
    special_provider_update_factor: float | None = 0.0
    operating_dsh: float | None = 0.0
    fiscal_year_end_date: int | None = 19000101
    special_payment_indicator: str | None = ""
    hosp_quality_indicator: str | None = ""
    cbsa_actual_geographic_location: str | None = ""
    cbsa_wi_location: str | None = ""
    cbsa_standardized_amount_location: str | None = ""
    special_wage_index: float | None = 0.0
    pass_through_amount_for_capital: float | None = 0.0
    pass_through_amount_for_direct_medical_education: float | None = 0.0
    pass_through_amount_for_organ_acquisition: float | None = 0.0
    pass_through_total_amount: float | None = 0.0
    capital_pps_payment_code: str | None = ""
    hospital_specific_capital_rate: float | None = 0.0
    old_capital_hold_harmless_rate: float | None = 0.0
    new_capital_hold_harmless_rate: float | None = 0.0
    capital_cost_to_charge_ratio: float | None = 0.0  # Default to 0.0 if not provided in data.
    new_hospital: str | None = ""
    capital_indirect_medical_education_ratio: float | None = (
        0.0  # Default to 0.0 if not provided in data.
    )
    capital_exception_payment_rate: float | None = (
        0.0  # Default to 0.0 if not provided in data.
    )
    vpb_participant_indicator: str | None = ""
    vbp_adjustment: float | None = 0.0  # Default to 0.0 if not provided in data.
    hrr_participant_indicator: int | None = 0  # Default to 0 if not provided in data.
    hrr_adjustment: float | None = 0.0  # Default to 0.0 if not provided in data.
    bundle_model_discount: float | None = 0.0  # Default to 0.0 if not provided in data.
    hac_reduction_participant_indicator: str | None = ""
    uncompensated_care_amount: float | None = 0.0  # Default to 0.0 if not provided in data.
    ehr_reduction_indicator: str | None = ""
    low_volume_adjustment_factor: float | None = 0.0  # Default to 0.0 if not provided in data.
    county_code: str | None = ""
    medicare_performance_adjustment: float | None = (
        0.0  # Default to 0.0 if not provided in data.
    )
    ltch_dpp_indicator: str | None = ""
    supplemental_wage_index: float | None = 0.0  # Default to 0.0 if not provided in data.
    supplemental_wage_index_indicator: str | None = ""
    change_code_wage_index_reclassification: str | None = ""
    national_provider_identifier: str | None = ""
    pass_through_amount_for_allogenic_stem_cell_acquisition: float | None = (
        0.0  # Default to 0.0 if not provided in data.
    )
    pps_blend_year_indicator: str | None = ""
    last_updated: str | None = ""
    pass_through_amount_for_direct_graduate_medical_education: float | None = (
        0.0  # Default to 0.0 if not provided in data.
    )
    pass_through_amount_for_kidney_acquisition: float | None = (
        0.0  # Default to 0.0 if not provided in data.
    )
    pass_through_amount_for_supply_chain: float | None = (
        0.0  # Default to 0.0 if not provided in data.
    )

    def model_post_init(self, __context: Any) -> None:
        self.model_config["extra"] = "allow"
        try:
            apply_client_methods(self)
        except Exception as e:
            raise RuntimeError("Error applying client methods") from e

    def from_db(
        self,
        engine: sqlalchemy.Engine,
        provider: Provider,
        date_int: int,
        **kwargs: object,
    ):
        local_session = False
        eng_id = id(engine)
        sess_factory = _SESSION_FACTORY_CACHE.get(eng_id)
        if sess_factory is None:
            sess_factory = sessionmaker(bind=engine, future=True)
            _SESSION_FACTORY_CACHE[eng_id] = sess_factory
        session = None
        if "session" in kwargs:
            session = kwargs["session"]
            if not isinstance(session, Session):
                raise ValueError("Provided session is not a valid SQLAlchemy Session.")
        if session is None:
            session = sess_factory()
            local_session = True

        params: dict[str, int | str] = {"date_int": date_int}
        if provider.other_id:
            params["ccn"] = provider.other_id
            query = IPSF_BY_CCN
        elif provider.npi:
            params["npi"] = provider.npi
            query = IPSF_BY_NPI
        else:
            raise ValueError("Provider must have either an NPI or other_id")
        row = session.execute(query, params).scalar_one_or_none()
        if row is None:
            raise ValueError(
                f"No IPSF data found for provider {provider.other_id or provider.npi} on date {date_int}."
            )
        for field in DATATYPES.keys():
            if hasattr(row, field):
                setattr(self, field, getattr(row, field))
        if self.termination_date in (19000101, 0, None):
            self.termination_date = 20991231
        extra = (
            provider.additional_data.get("ipsf")
            if hasattr(provider, "additional_data")
            else None
        )
        if isinstance(extra, dict):
            for k, v in extra.items():
                if hasattr(self, k):
                    setattr(self, k, v)
        if local_session:
            session.close()
        return self

    def from_sqlite(
        self,
        conn: sqlalchemy.Engine,
        provider: Provider,
        date_int: int,
        **kwargs: object,
    ):  # backward compat
        return self.from_db(conn, provider, date_int, **kwargs)

    def from_claim(self, claim: Claim, db: Engine, **kwargs: object) -> None:
        date_int = int(claim.thru_date.strftime("%Y%m%d")) if isinstance(claim.thru_date, datetime) else 19000101
        if claim.billing_provider is not None:
            self.from_sqlite(db, claim.billing_provider, date_int, **kwargs)
        elif claim.servicing_provider is not None:
            self.from_sqlite(db, claim.servicing_provider, date_int, **kwargs)
        else:
            raise ValueError(
                "Either billing or servicing provider must be provided for pricing."
            )
        return

    def set_java_values(self, java_provider, client):
        if not hasattr(client, "java_integer_class") or not hasattr(
            client, "java_big_decimal_class"
        ):
            raise AttributeError(
                "Client must have java_integer_class and java_big_decimal_class attributes."
            )

        java_provider.setBedSize(
            client.java_integer_class(self.bed_size)
            if self.bed_size
            else client.java_integer_class(0)
        )
        java_provider.setBundleModel1Discount(
            client.java_big_decimal_class(self.bundle_model_discount)
            if self.bundle_model_discount
            else client.java_big_decimal_class(0)
        )
        java_provider.setCapitalCostToChargeRatio(
            client.java_big_decimal_class(self.capital_cost_to_charge_ratio)
            if self.capital_cost_to_charge_ratio
            else client.java_big_decimal_class(0)
        )
        java_provider.setOperatingCostToChargeRatio(
            client.java_big_decimal_class(self.operating_cost_to_charge_ratio)
            if self.operating_cost_to_charge_ratio
            else client.java_big_decimal_class(0)
        )
        java_provider.setCapitalExceptionPaymentRate(
            client.java_big_decimal_class(self.capital_exception_payment_rate)
            if self.capital_exception_payment_rate
            else client.java_big_decimal_class(0)
        )
        java_provider.setCapitalIndirectMedicalEducationRatio(
            client.java_big_decimal_class(self.capital_indirect_medical_education_ratio)
            if self.capital_indirect_medical_education_ratio
            else client.java_big_decimal_class(0)
        )
        java_provider.setCapitalPpsPaymentCode(
            self.capital_pps_payment_code if self.capital_pps_payment_code else ""
        )
        java_provider.setCbsaActualGeographicLocation(
            str(self.cbsa_actual_geographic_location)
            if self.cbsa_actual_geographic_location
            else ""
        )
        java_provider.setCbsaWageIndexLocation(
            str(self.cbsa_wi_location) if self.cbsa_wi_location else ""
        )
        java_provider.setCbsaStandardizedAmountLocation(
            str(self.cbsa_standardized_amount_location)
            if self.cbsa_standardized_amount_location
            else ""
        )
        java_provider.setEhrReductionIndicator(
            str(self.ehr_reduction_indicator) if self.ehr_reduction_indicator else ""
        )
        java_provider.setFederalPpsBlend(
            str(self.federal_pps_blend) if self.federal_pps_blend else ""
        )
        java_provider.setHacReductionParticipantIndicator(
            str(self.hac_reduction_participant_indicator)
            if self.hac_reduction_participant_indicator
            else ""
        )
        java_provider.setHrrAdjustment(
            client.java_big_decimal_class(self.hrr_adjustment)
            if self.hrr_adjustment
            else client.java_big_decimal_class(0)
        )
        java_provider.setHrrParticipantIndicator(
            str(self.hrr_participant_indicator)
            if self.hrr_participant_indicator
            else ""
        )
        java_provider.setInternsToBedsRatio(
            client.java_big_decimal_class(self.interns_to_beds_ratio)
            if self.interns_to_beds_ratio
            else client.java_big_decimal_class(0)
        )
        java_provider.setLowVolumeAdjustmentFactor(
            client.java_big_decimal_class(self.low_volume_adjustment_factor)
            if self.low_volume_adjustment_factor
            else client.java_big_decimal_class(0)
        )
        java_provider.setLtchDppIndicator(
            str(self.ltch_dpp_indicator) if self.ltch_dpp_indicator else ""
        )
        java_provider.setMedicaidRatio(
            client.java_big_decimal_class(self.medicaid_ratio)
            if self.medicaid_ratio
            else client.java_big_decimal_class(0)
        )
        java_provider.setNewHospital(
            str(self.new_hospital) if self.new_hospital else ""
        )
        java_provider.setOldCapitalHoldHarmlessRate(
            client.java_big_decimal_class(self.old_capital_hold_harmless_rate)
            if self.old_capital_hold_harmless_rate
            else client.java_big_decimal_class(0)
        )
        java_provider.setPassThroughAmountForAllogenicStemCellAcquisition(
            client.java_big_decimal_class(
                self.pass_through_amount_for_allogenic_stem_cell_acquisition
                if self.pass_through_amount_for_allogenic_stem_cell_acquisition
                else 0
            )
        )
        java_provider.setPassThroughAmountForCapital(
            client.java_big_decimal_class(self.pass_through_amount_for_capital)
            if self.pass_through_amount_for_capital
            else client.java_big_decimal_class(0)
        )
        java_provider.setPassThroughAmountForDirectMedicalEducation(
            client.java_big_decimal_class(
                self.pass_through_amount_for_direct_medical_education
                if self.pass_through_amount_for_direct_medical_education
                else 0
            )
        )
        java_provider.setPassThroughAmountForSupplyChainCosts(
            client.java_big_decimal_class(self.pass_through_amount_for_supply_chain)
            if self.pass_through_amount_for_supply_chain
            else client.java_big_decimal_class(0)
        )
        java_provider.setPassThroughAmountForOrganAcquisition(
            client.java_big_decimal_class(
                self.pass_through_amount_for_organ_acquisition
                if self.pass_through_amount_for_organ_acquisition
                else 0
            )
        )
        java_provider.setPassThroughTotalAmount(
            client.java_big_decimal_class(self.pass_through_total_amount)
            if self.pass_through_total_amount
            else client.java_big_decimal_class(0)
        )
        java_provider.setPpsFacilitySpecificRate(
            client.java_big_decimal_class(self.pps_facility_specific_rate)
            if self.pps_facility_specific_rate
            else client.java_big_decimal_class(0)
        )
        java_provider.setSupplementalSecurityIncomeRatio(
            client.java_big_decimal_class(self.supplemental_security_income_ratio)
            if self.supplemental_security_income_ratio
            else client.java_big_decimal_class(0)
        )
        java_provider.setTemporaryReliefIndicator(
            str(self.temporary_relief_indicator)
            if self.temporary_relief_indicator
            else ""
        )
        java_provider.setUncompensatedCareAmount(
            client.java_big_decimal_class(self.uncompensated_care_amount)
            if self.uncompensated_care_amount
            else client.java_big_decimal_class(0)
        )
        java_provider.setVbpAdjustment(
            client.java_big_decimal_class(self.vbp_adjustment)
            if self.vbp_adjustment
            else client.java_big_decimal_class(0)
        )
        java_provider.setVbpParticipantIndicator(
            str(self.vpb_participant_indicator)
            if self.vpb_participant_indicator
            else ""
        )
        java_provider.setStateCode(self.state_code if self.state_code else "")
        java_provider.setCountyCode(self.county_code if self.county_code else "")
        java_provider.setSpecialWageIndex(
            client.java_big_decimal_class(self.special_wage_index)
            if self.special_wage_index
            else client.java_big_decimal_class(0)
        )
        java_provider.setProviderType(self.provider_type if self.provider_type else "")
        java_provider.setHospitalQualityIndicator(
            self.hosp_quality_indicator if self.hosp_quality_indicator else ""
        )
        java_provider.setSpecialPaymentIndicator(
            self.special_payment_indicator if self.special_payment_indicator else ""
        )
        java_provider.setMedicarePerformanceAdjustment(
            client.java_big_decimal_class(self.medicare_performance_adjustment)
            if self.medicare_performance_adjustment
            else client.java_big_decimal_class(0)
        )
        java_provider.setWaiverIndicator(
            self.waiver_indicator if self.waiver_indicator else ""
        )
        java_provider.setCostOfLivingAdjustment(
            client.java_big_decimal_class(self.cost_of_living_adjustment)
            if self.cost_of_living_adjustment
            else client.java_big_decimal_class(0)
        )
        java_provider.setEffectiveDate(
            client.py_date_to_java_date(self.effective_date)
            if self.effective_date
            else client.py_date_to_java_date(19000101)
        )
        java_provider.setTerminationDate(
            client.py_date_to_java_date(self.termination_date)
            if self.termination_date
            else client.py_date_to_java_date(19000101)
        )
        java_provider.setFiscalYearBeginDate(
            client.py_date_to_java_date(self.fiscal_year_begin_date)
            if self.fiscal_year_begin_date
            else client.py_date_to_java_date(19000101)
        )
        java_provider.setProviderCcn(self.provider_ccn if self.provider_ccn else "")


__all__ = ["IPSFDatabase", "IPSFProvider", "IPSF"]
