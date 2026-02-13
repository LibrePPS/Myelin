import csv
import os
from datetime import datetime
from multiprocessing import cpu_count
from typing import Any, Iterable, Literal

import jpype
import requests
import sqlalchemy
from pydantic import BaseModel, ConfigDict
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

from myelin.helpers.utils import ProviderDataError
from myelin.input.claim import Claim, Provider
from myelin.plugins import apply_client_methods

OPSF_URL = "https://pds.mps.cms.gov/fiss/v2/outpatient/export?fromDate=2023-01-01&toDate=2030-12-31"

# Column definitions and positional index for CSV parsing.
DATATYPES = {
    "provider_ccn": {"type": "TEXT", "position": 0},
    "effective_date": {"type": "INT", "position": 1},
    "national_provider_identifier": {"type": "TEXT", "position": 2},
    "fiscal_year_begin_date": {"type": "INT", "position": 3},
    "export_date": {"type": "INT", "position": 4},
    "termination_date": {"type": "INT", "position": 5},
    "waiver_indicator": {"type": "TEXT", "position": 6},
    "intermediary_number": {"type": "TEXT", "position": 7},
    "provider_type": {"type": "TEXT", "position": 8},
    "special_locality_indicator": {"type": "TEXT", "position": 9},
    "change_code_wage_index_reclassification": {"type": "TEXT", "position": 10},
    "msa_actual_geographic_location": {"type": "TEXT", "position": 11},
    "msa_wage_index_location": {"type": "TEXT", "position": 12},
    "cost_of_living_adjustment": {"type": "REAL", "position": 13},
    "state_code": {"type": "TEXT", "position": 14},
    "tops_indicator": {"type": "TEXT", "position": 15},
    "hospital_quality_indicator": {"type": "TEXT", "position": 16},
    "operating_cost_to_charge_ratio": {"type": "REAL", "position": 17},
    "cbsa_actual_geographic_location": {"type": "TEXT", "position": 18},
    "cbsa_wage_index_location": {"type": "TEXT", "position": 19},
    "special_wage_index": {"type": "REAL", "position": 20},
    "special_payment_indicator": {"type": "TEXT", "position": 21},
    "esrd_children_quality_indicator": {"type": "TEXT", "position": 22},
    "device_cost_to_charge_ratio": {"type": "REAL", "position": 23},
    "county_code": {"type": "TEXT", "position": 24},
    "payment_cbsa": {"type": "TEXT", "position": 25},
    "payment_model_adjustment": {"type": "REAL", "position": 26},
    "medicare_performance_adjustment": {"type": "REAL", "position": 27},
    "supplemental_wage_index_indicator": {"type": "TEXT", "position": 28},
    "supplemental_wage_index": {"type": "REAL", "position": 29},
    "last_updated": {"type": "TEXT", "position": 30},  # store as TEXT for portability
    "carrier_code": {"type": "TEXT", "position": 31},
    "locality_code": {"type": "TEXT", "position": 32},
}

INT_FIELDS = {k for k, v in DATATYPES.items() if v["type"] == "INT"}
REAL_FIELDS = {k for k, v in DATATYPES.items() if v["type"] == "REAL"}

Base = declarative_base()

# Simple session factory cache (keyed by engine id) to avoid recreating sessionmaker
_SESSION_FACTORY_CACHE: dict[int, sessionmaker] = {}


class OPSF(Base):
    __tablename__ = "opsf"
    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_ccn = Column(String)
    effective_date = Column(Integer, index=True)
    national_provider_identifier = Column(String, index=True)
    fiscal_year_begin_date = Column(Integer)
    export_date = Column(Integer)
    termination_date = Column(Integer)
    waiver_indicator = Column(String)
    intermediary_number = Column(String)
    provider_type = Column(String)
    special_locality_indicator = Column(String)
    change_code_wage_index_reclassification = Column(String)
    msa_actual_geographic_location = Column(String)
    msa_wage_index_location = Column(String)
    cost_of_living_adjustment = Column(Float)
    state_code = Column(String)
    tops_indicator = Column(String)
    hospital_quality_indicator = Column(String)
    operating_cost_to_charge_ratio = Column(Float)
    cbsa_actual_geographic_location = Column(String)
    cbsa_wage_index_location = Column(String)
    special_wage_index = Column(Float)
    special_payment_indicator = Column(String)
    esrd_children_quality_indicator = Column(String)
    device_cost_to_charge_ratio = Column(Float)
    county_code = Column(String)
    payment_cbsa = Column(String)
    payment_model_adjustment = Column(Float)
    medicare_performance_adjustment = Column(Float)
    supplemental_wage_index_indicator = Column(String)
    supplemental_wage_index = Column(Float)
    last_updated = Column(String)
    carrier_code = Column(String)
    locality_code = Column(String)

    __table_args__ = (
        Index("idx_opsf_ccn_effective", "provider_ccn", "effective_date"),
        Index(
            "idx_opsf_npi_effective", "national_provider_identifier", "effective_date"
        ),
    )

    def to_provider_model(self) -> "OPSFProvider":
        data = {k: getattr(self, k) for k in DATATYPES.keys() if hasattr(self, k)}
        return OPSFProvider(**data)


# Prepared statements (defined after model) reused in provider lookups
OPSF_BY_CCN = (
    select(OPSF)
    .where(
        OPSF.provider_ccn == bindparam("ccn"),
        OPSF.effective_date <= bindparam("date_int"),
    )
    .order_by(OPSF.effective_date.desc())
    .limit(1)
)

OPSF_BY_NPI = (
    select(OPSF)
    .where(
        OPSF.national_provider_identifier == bindparam("npi"),
        OPSF.effective_date <= bindparam("date_int"),
    )
    .order_by(OPSF.effective_date.desc())
    .limit(1)
)


class OPSFProvider(BaseModel):
    provider_ccn: str | None = None
    effective_date: int | None = None
    national_provider_identifier: str | None = None
    fiscal_year_begin_date: int | None = None
    export_date: int | None = None
    termination_date: int | None = None
    waiver_indicator: str | None = None
    intermediary_number: str | None = None
    provider_type: str | None = None
    special_locality_indicator: str | None = None
    change_code_wage_index_reclassification: str | None = None
    msa_actual_geographic_location: str | None = None
    msa_wage_index_location: str | None = None
    cost_of_living_adjustment: float | None = None
    state_code: str | None = None
    tops_indicator: str | None = None
    hospital_quality_indicator: str | None = None
    operating_cost_to_charge_ratio: float | None = None
    cbsa_actual_geographic_location: str | None = None
    cbsa_wage_index_location: str | None = None
    special_wage_index: float | None = None
    special_payment_indicator: str | None = None
    esrd_children_quality_indicator: str | None = None
    device_cost_to_charge_ratio: float | None = None
    county_code: str | None = None
    payment_cbsa: str | None = None
    payment_model_adjustment: float | None = None
    medicare_performance_adjustment: float | None = None
    supplemental_wage_index_indicator: str | None = None
    supplemental_wage_index: float | None = None
    last_updated: str | None = None  # Date in YYYY-MM-DD format
    carrier_code: str | None = None
    locality_code: str | None = None
    model_config = ConfigDict(extra='allow')

    def model_post_init(self, __context: Any) -> None:
        try:
            apply_client_methods(self)
        except Exception as e:
            raise RuntimeError("Error applying client methods") from e

    def from_db(
        self, engine: sqlalchemy.Engine, provider: Provider, date_int: int, **kwargs
    ):
        """Populate this model using prepared statements + cached sessionmaker."""
        local_session = False
        eng_id = id(engine)
        sess_factory = _SESSION_FACTORY_CACHE.get(eng_id)
        if sess_factory is None:
            sess_factory = sessionmaker(bind=engine, future=True)
            _SESSION_FACTORY_CACHE[eng_id] = sess_factory
        session = None
        # Check if a session was passed in kwargs
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
            query = OPSF_BY_CCN
        elif provider.npi:
            params["npi"] = provider.npi
            query = OPSF_BY_NPI
        else:
            raise ProviderDataError(
                code="P0002",
                description="Provider missing NPI and CCN",
                explanation="Provider must have either an NPI or other_id (CCN) to look up OPSF data.",
            )
        result = session.execute(query, params).scalar_one_or_none()
        if result is None:
            raise ProviderDataError(
                code="P0003",
                description="Provider not found in OPSF",
                explanation=f"No OPSF data found for provider {provider.other_id or provider.npi} on date {date_int}.",
            )
        # if field is TEXT, strip whitespace
        for field in DATATYPES:
            val = getattr(result, field)
            if val is not None:
                if DATATYPES[field]["type"] == "TEXT":
                    val = val.strip()
                setattr(self, field, val)
        if self.termination_date in (19000101, 0, None):
            self.termination_date = 20991231
        extra = (
            provider.additional_data.get("opsf")
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

    # Backwards compatibility alias
    def from_sqlite(
        self,
        conn: sqlalchemy.Engine,
        provider: Provider,
        date_int: int,
        **kwargs: object,
    ) -> "OPSFProvider":
        return self.from_db(conn, provider, date_int, **kwargs)

    def from_claim(self, claim: Claim, db: Engine, **kwargs: object) -> None:
        if claim.billing_provider is not None:
            if isinstance(claim.thru_date, datetime):
                date_int = int(claim.thru_date.strftime("%Y%m%d"))
            else:
                date_int = int(claim.thru_date.replace("-", ""))
            self.from_sqlite(db, claim.billing_provider, date_int, **kwargs)
        elif claim.servicing_provider is not None:
            if isinstance(claim.thru_date, datetime):
                date_int = int(claim.thru_date.strftime("%Y%m%d"))
            else:
                date_int = int(claim.thru_date.replace("-", ""))
            self.from_sqlite(db, claim.servicing_provider, date_int, **kwargs)
        else:
            raise ProviderDataError(
                code="P0001",
                description="No provider on claim",
                explanation="Either billing or servicing provider must be provided for pricing.",
            )
        return

    def set_java_values(self, java_obj: jpype.JObject, client):
        if (
            not hasattr(client, "java_integer_class")
            or not hasattr(client, "java_big_decimal_class")
            or not hasattr(client, "py_date_to_java_date")
        ):
            raise AttributeError(
                "Client must have java_integer_class,java_big_decimal_class and py_date_to_java_date attributes."
            )
        java_obj.setCbsaActualGeographicLocation(
            self.cbsa_actual_geographic_location
            if self.cbsa_actual_geographic_location
            else ""
        )
        java_obj.setCbsaWageIndexLocation(
            self.cbsa_wage_index_location if self.cbsa_wage_index_location else ""
        )
        java_obj.setCostOfLivingAdjustment(
            client.java_big_decimal_class(self.cost_of_living_adjustment)
            if self.cost_of_living_adjustment is not None
            else client.java_big_decimal_class(0)
        )
        java_obj.setCountyCode(self.county_code if self.county_code else "0")
        java_obj.setHospitalQualityIndicator(
            self.hospital_quality_indicator if self.hospital_quality_indicator else ""
        )
        java_obj.setIntermediaryNumber(
            self.intermediary_number if self.intermediary_number else ""
        )
        java_obj.setMedicarePerformanceAdjustment(
            client.java_big_decimal_class(self.medicare_performance_adjustment)
            if self.medicare_performance_adjustment is not None
            else client.java_big_decimal_class(0)
        )
        java_obj.setOperatingCostToChargeRatio(
            client.java_big_decimal_class(self.operating_cost_to_charge_ratio)
            if self.operating_cost_to_charge_ratio is not None
            else client.java_big_decimal_class(0)
        )
        java_obj.setProviderCcn(self.provider_ccn if self.provider_ccn else "")
        java_obj.setProviderType(self.provider_type if self.provider_type else "")
        java_obj.setSpecialPaymentIndicator(
            self.special_payment_indicator if self.special_payment_indicator else ""
        )
        java_obj.setPaymentModelAdjustment(
            client.java_big_decimal_class(self.payment_model_adjustment)
            if self.payment_model_adjustment is not None
            else client.java_big_decimal_class(0)
        )
        java_obj.setSpecialLocalityIndicator(
            self.special_locality_indicator if self.special_locality_indicator else ""
        )
        java_obj.setPaymentCbsa(self.payment_cbsa if self.payment_cbsa else "")
        java_obj.setDeviceCostToChargeRatio(
            client.java_big_decimal_class(self.device_cost_to_charge_ratio)
            if self.device_cost_to_charge_ratio is not None
            else client.java_big_decimal_class(0)
        )
        java_obj.setSpecialWageIndex(
            client.java_big_decimal_class(self.special_wage_index)
            if self.special_wage_index is not None
            else client.java_big_decimal_class(0)
        )
        java_obj.setStateCode(self.state_code if self.state_code else "")
        java_obj.setSupplementalWageIndex(
            client.java_big_decimal_class(self.supplemental_wage_index)
            if self.supplemental_wage_index is not None
            else client.java_big_decimal_class(0)
        )
        java_obj.setSupplementalWageIndexIndicator(
            self.supplemental_wage_index_indicator
            if self.supplemental_wage_index_indicator
            else ""
        )
        java_obj.setWaiverIndicator(
            self.waiver_indicator if self.waiver_indicator else ""
        )
        java_obj.setEffectiveDate(client.py_date_to_java_date(self.effective_date))
        java_obj.setTerminationDate(client.py_date_to_java_date(self.termination_date))
        java_obj.setFiscalYearBeginDate(
            client.py_date_to_java_date(self.fiscal_year_begin_date)
        )


class OPSFDatabase:
    """Unified OPSF database helper supporting sqlite & postgres via SQLAlchemy ORM."""

    def __init__(
        self, db_path: str, db_backend: Literal["sqlite", "postgres"] = "sqlite"
    ):
        self.db_path = db_path
        self.db_backend = db_backend
        self._engine: sqlalchemy.Engine | None = None
        self._Session: sessionmaker | None = None
        self._init_engine()

    # -----------------------------------------------------
    # Engine / Session Management
    # -----------------------------------------------------
    def _init_engine(self):
        if self._engine is not None:
            return
        if self.db_backend == "sqlite":
            engine_str = f"sqlite:///{self.db_path}"
            self._engine = create_engine(
                engine_str,
                future=True,
                pool_pre_ping=True,
                echo=False,
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
                pool_size=min(cpu_count(), 8),
                max_overflow=8,
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

    # -----------------------------------------------------
    # Data Acquisition
    # -----------------------------------------------------
    def download(self, url: str = OPSF_URL, download_dir: str | None = None) -> str:
        download_dir = download_dir or os.path.dirname(self.db_path) or "."
        os.makedirs(download_dir, exist_ok=True)
        filename = os.path.join(download_dir, "opsf_data.csv")
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(filename, "wb") as fh:
            for chunk in response.iter_content(chunk_size=1 << 15):
                if chunk:
                    fh.write(chunk)
        return filename

    # -----------------------------------------------------
    # Loading Logic (stream + bulk_insert_mappings)
    # -----------------------------------------------------
    def _row_iter(self, csv_path: str) -> Iterable[dict[str, Any]]:
        with open(csv_path, "r", newline="") as fh:
            reader = csv.reader(fh)
            next(reader, None)  # discard header
            for row in reader:
                if not row or len(row) < len(DATATYPES):
                    continue
                record: dict[str, Any] = {}
                for name, meta in DATATYPES.items():
                    pos = meta["position"]
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
                    record[name] = val
                yield record

    def populate(
        self, download: bool = True, batch_size: int = 5000, truncate: bool = True
    ) -> int:
        """Populate (or refresh) the OPSF table.

        Parameters:
            download: if True, fetch latest CSV before loading
            batch_size: number of rows per bulk insert
            truncate: delete existing rows first

        Returns: total inserted rows.
        """
        csv_path = (
            self.download()
            if download
            else os.path.join(os.path.dirname(self.db_path), "opsf_data.csv")
        )
        total = 0
        with self.session() as sess:
            if truncate:
                sess.query(OPSF).delete()
                sess.commit()
            batch: list[dict[str, Any]] = []
            from sqlalchemy import insert as sql_insert

            insert_stmt = sql_insert(OPSF)
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
        # Cleanup downloaded file if we initiated it
        if download and os.path.exists(csv_path):
            try:
                os.remove(csv_path)
            except OSError:
                pass
        return total

    # Backwards compatibility name
    def to_sqlite(self, create_table: bool = True) -> None:
        if create_table:
            Base.metadata.create_all(self.engine)
        self.populate(download=True, truncate=True)

    def close(self) -> None:
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._Session = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
