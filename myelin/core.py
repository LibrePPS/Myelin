import logging
import os
from contextlib import ExitStack
from threading import RLock
from types import TracebackType
from typing import Literal, Annotated

import jpype
from pydantic import BaseModel, Field, ConfigDict

from myelin.converter import ICDConverter
from myelin.database.manager import DatabaseManager
from myelin.helpers.cms_downloader import CMSDownloader
from myelin.helpers.utils import JavaRuntimeError, ProviderDataError
from myelin.hhag import HhagClient, HhagOutput
from myelin.input.claim import Claim, Modules
from myelin.ioce import IoceClient, IoceOutput
from myelin.irfg import IrfgClient, IrfgOutput
from myelin.mce import MceClient, MceOutput
from myelin.msdrg import DrgClient, MsdrgOutput
from myelin.pricers.esrd import EsrdClient, EsrdOutput
from myelin.pricers.fqhc import FqhcClient, FqhcOutput
from myelin.pricers.hha import HhaClient, HhaOutput
from myelin.pricers.hospice import HospiceClient, HospiceOutput
from myelin.pricers.ipf import IpfClient, IpfOutput
from myelin.pricers.ipps import IppsClient, IppsOutput
from myelin.pricers.irf import IrfClient, IrfOutput
from myelin.pricers.ltch import LtchClient, LtchOutput
from myelin.pricers.opps import OppsClient, OppsOutput
from myelin.pricers.snf import SnfClient, SnfOutput
from myelin.pricers.ipsf import IPSFProvider
from myelin.pricers.opsf import OPSFProvider

PRICERS: dict[str, str] = {
    "Esrd": "esrd-pricer",
    "Fqhc": "fqhc-pricer",
    "Hha": "hha-pricer",
    "Hospice": "hospice-pricer",
    "Ipf": "ipf-pricer",
    "Ipps": "ipps-pricer",
    "Irf": "irf-pricer",
    "Ltch": "ltch-pricer",
    "Opps": "opps-pricer",
    "Snf": "snf-pricer",
}

IPSF_PRICERS: set[Modules] = {
    Modules.IPPS,
    Modules.PSYCH,
    Modules.LTCH,
    Modules.IRF,
    Modules.SNF,
    Modules.HHA,
}
OPSF_PRICERS: set[Modules] = {
    Modules.OPPS,
    Modules.ESRD,
}

class MyelinOutput(BaseModel):
    model_config = ConfigDict(json_schema_mode_override="validation")
    error: str | None = None
    # Editors
    ioce: IoceOutput | None = None
    mce: MceOutput | None = None
    # Groupers
    hhag: HhagOutput | None = None
    msdrg: MsdrgOutput | None = None
    cmg: IrfgOutput | None = None
    # Pricers
    ipps: IppsOutput | None = None
    opps: OppsOutput | None = None
    psych: IpfOutput | None = None
    ltch: LtchOutput | None = None
    irf: IrfOutput | None = None
    hospice: HospiceOutput | None = None
    snf: SnfOutput | None = None
    hha: HhaOutput | None = None
    esrd: EsrdOutput | None = None
    fqhc: FqhcOutput | None = None
    ipsf: IPSFProvider | None = None
    opsf: OPSFProvider | None = None

    def to_excel(self, filepath: str, claim: "Claim | None" = None) -> None:
        """
        Export this output to an Excel file.

        Args:
            filepath: Path where the Excel file should be saved
            claim: Optional input Claim to include in the export

        Raises:
            ImportError: If openpyxl is not installed

        Example:
            >>> result = myelin.process(claim)
            >>> result.to_excel("output.xlsx", claim=claim)
        """
        from myelin.helpers.excel_exporter import export_to_excel

        export_to_excel(self, filepath, claim=claim)

    def to_excel_bytes(self, claim: "Claim | None" = None) -> bytes:
        """
        Export this output to Excel format as bytes.

        Useful for web applications that need to return the file as a response.

        Args:
            claim: Optional input Claim to include in the export

        Returns:
            Excel file content as bytes

        Raises:
            ImportError: If openpyxl is not installed

        Example:
            >>> result = myelin.process(claim)
            >>> excel_bytes = result.to_excel_bytes(claim=claim)
        """
        from myelin.helpers.excel_exporter import export_to_excel_bytes

        return export_to_excel_bytes(self, claim=claim)


class MyelinIO(BaseModel):
    """Container for claim input/output pairs - used for batch results and exports."""

    input: Annotated[
        Claim | None, Field(default=None, json_schema_extra={"readOnly": False})
    ]
    output: Annotated[
        MyelinOutput | None, Field(default=None, json_schema_extra={"readOnly": True})
    ]


class Myelin:
    # Class-level locks and tracking for thread safety
    _jvm_lock: RLock = RLock()  # Thread-safe JVM operations
    _jvm_started: bool = False  # Track if we started the JVM

    def __init__(
        self,
        build_jar_dirs: bool = True,
        jar_path: str = "./jars",
        db_path: str = "./data/myelin.db",
        build_db: bool = False,
        log_level: int = logging.INFO,
        extra_classpaths: list[str] | None = None,
        db_backend: Literal["sqlite", "postgresql"] = "sqlite",
    ):
        self.extra_classpaths: list[str] = extra_classpaths or []
        self.jar_path: str = jar_path
        self.db_path: str = db_path
        self.build_jar_dirs: bool = build_jar_dirs
        self.build_db: bool = build_db

        self._exit_stack: ExitStack = ExitStack()
        self._initialized: bool = False

        self.ipps_client: IppsClient | None = None
        self.opps_client: OppsClient | None = None
        self.ipf_client: IpfClient | None = None
        self.ltch_client: LtchClient | None = None
        self.irf_client: IrfClient | None = None
        self.hospice_client: HospiceClient | None = None
        self.snf_client: SnfClient | None = None
        self.hha_client: HhaClient | None = None
        self.esrd_client: EsrdClient | None = None
        self.fqhc_client: FqhcClient | None = None
        self.irfg_client: IrfgClient | None = None
        self.drg_client: DrgClient | None = None
        self.mce_client: MceClient | None = None
        self.ioce_client: IoceClient | None = None
        self.hhag_client: HhagClient | None = None

        self.pricers_path: str | None = None
        self.pricer_jars: list[str] = []
        self.cms_downloader: CMSDownloader | None = None

        self.logger: logging.Logger = logging.getLogger("Myelin")
        self.logger.setLevel(log_level)

        self._ensure_directories()

        self.db_manager: DatabaseManager = DatabaseManager(
            db_path, db_backend, build_db, log_level
        )
        _ = self._exit_stack.enter_context(self.db_manager)
        self.icd10_converter: ICDConverter | None = self.db_manager.icd10_converter

        if self.build_jar_dirs:
            self.cms_downloader = CMSDownloader(
                jars_dir=self.jar_path, log_level=self.logger.level
            )
            self.cms_downloader.build_jar_environment(False)

        self._setup_jvm()

    def __enter__(self) -> "Myelin":
        """Context manager entry"""
        if not self._initialized:
            self.setup_clients()
            self._initialized = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """Context manager exit with proper cleanup"""
        self.cleanup()
        return False  # Don't suppress exceptions

    def cleanup(self) -> None:
        """Comprehensive cleanup of all resources"""
        self._exit_stack.close()

    def _ensure_directories(self) -> None:
        """Ensure required directories exist"""
        if not os.path.exists(self.jar_path):
            os.makedirs(self.jar_path)
        if not os.path.exists(os.path.dirname(self.db_path)):
            os.makedirs(os.path.dirname(self.db_path))

    def _setup_jvm(self) -> None:
        """Thread-safe JVM initialization"""
        with Myelin._jvm_lock:
            if not jpype.isJVMStarted():
                try:
                    classpath = [f"{self.jar_path}/*", *self.extra_classpaths]
                    jpype.startJVM(classpath=classpath)
                    Myelin._jvm_started = True
                    self.logger.info("JVM started successfully")

                    _ = self._exit_stack.callback(self._shutdown_jvm)
                except Exception as e:
                    self.logger.error(f"Failed to start JVM: {e}")
                    raise RuntimeError(f"JVM startup failed: {e}") from e
            else:
                self.logger.debug("JVM already started")

    def _shutdown_jvm(self) -> None:
        """Thread-safe JVM shutdown"""
        with Myelin._jvm_lock:
            if jpype.isJVMStarted() and Myelin._jvm_started:
                try:
                    jpype.shutdownJVM()
                    Myelin._jvm_started = False
                    self.logger.info("JVM shutdown successfully")
                except Exception as e:
                    self.logger.warning(f"Error shutting down JVM: {e}")

    def setup_clients(self) -> None:
        """Initialize the CMS clients."""
        self.drg_client = DrgClient()
        self.mce_client = MceClient()
        self.ioce_client = IoceClient()
        self.hhag_client = HhagClient()
        self.irfg_client = IrfgClient()
        if os.path.exists(os.path.join(self.jar_path, "pricers")):
            self.pricers_path = os.path.abspath(os.path.join(self.jar_path, "pricers"))
            self.pricer_jars = [
                os.path.join(self.pricers_path, f)
                for f in os.listdir(self.pricers_path)
                if f.endswith(".jar")
            ]
        if self.pricer_jars:
            self.setup_pricers()

    def setup_pricers(self) -> None:
        for pricer, jar_name in PRICERS.items():
            if self.pricer_jars and any(jar_name in jar for jar in self.pricer_jars):
                try:
                    jar_path = os.path.abspath(
                        next(jar for jar in self.pricer_jars if jar_name in jar)
                    )
                    setattr(
                        self,
                        f"{pricer.lower()}_client",
                        globals()[f"{pricer}Client"](
                            jar_path, self.db_manager.engine, self.logger
                        ),
                    )
                except KeyError:
                    self.logger.warning(
                        f"Client for {pricer} not found. This is a warning only, a client for {pricer} may not be implemented yet."
                    )
            else:
                self.logger.warning(
                    f"{pricer} pricer JAR not found in {self.pricers_path}. Please ensure it is downloaded."
                )

    def process(self, claim: Claim, **kwargs: object) -> MyelinOutput:
        """Process a claim through the appropriate modules based on its configuration."""

        if not isinstance(claim, Claim):
            raise ValueError("Input must be an instance of Claim")

        # Validate the claim
        _ = Claim.model_validate(claim)

        results = MyelinOutput()
        provider: IPSFProvider | OPSFProvider | None = None
        try:
            if len(claim.modules) == 0:
                results.error = "No modules specified in claim"
                return results
            # Claims Flow Editors -> Groupers -> Pricers
            # Create unique list of modules preserving order
            unique_modules: list[Modules] = []
            for module in claim.modules:
                if module not in unique_modules:
                    if module in IPSF_PRICERS:
                        provider = IPSFProvider()
                    elif module in OPSF_PRICERS:
                        provider = OPSFProvider()
                    unique_modules.append(module)
            if provider is not None:
                if self.db_manager.engine is not None:
                    try:
                        provider.from_claim(claim, self.db_manager.engine, **kwargs)
                    except ProviderDataError as e:
                        results.error = e.explanation
                        return results
                else:
                    results.error = "No database connection to fetch provider information"
                    return results
            # Editors
            if Modules.MCE in unique_modules:
                if self.mce_client is None:
                    results.error = "MCE client not initialized"
                    return results
                results.mce = self.mce_client.process(claim)
            if Modules.IOCE in unique_modules:
                if self.ioce_client is None:
                    results.error = "IOCE client not initialized"
                    return results
                results.ioce = self.ioce_client.process(
                    claim, include_descriptions=True, **kwargs
                )
            # Groupers
            if Modules.MSDRG in unique_modules:
                if self.drg_client is None:
                    results.error = "DRG client not initialized"
                    return results
                results.msdrg = self.drg_client.process(
                    claim, icd_converter=self.icd10_converter
                )
            if Modules.HHAG in unique_modules:
                if self.hhag_client is None:
                    results.error = "HHAG client not initialized"
                    return results
                results.hhag = self.hhag_client.process(claim)
            if Modules.CMG in unique_modules:
                if self.irfg_client is None:
                    results.error = "IRFG client not initialized"
                    return results
                results.cmg = self.irfg_client.process(claim)
            # Pricers
            if Modules.IPPS in unique_modules:
                if self.ipps_client is None:
                    results.error = "IPPS client not initialized"
                    return results
                if not isinstance(provider, IPSFProvider):
                    results.error = "IPSF provider not initialized"
                    return results
                results.ipps, results.ipsf = self.ipps_client.process(
                    claim, provider, results.msdrg, **kwargs
                )
            if Modules.OPPS in unique_modules:
                if self.opps_client is None:
                    results.error = "OPPS client not initialized"
                    return results
                if not isinstance(provider, OPSFProvider):
                    results.error = "OPSF provider not initialized"
                    return results
                results.opps, results.opsf = self.opps_client.process(
                    claim, provider, results.ioce, **kwargs
                )
            if Modules.PSYCH in unique_modules:
                if self.ipf_client is None:
                    results.error = "IPF client not initialized"
                    return results
                if not isinstance(provider, IPSFProvider):
                    results.error = "IPSF provider not initialized"
                    return results
                results.psych, results.ipsf = self.ipf_client.process(
                    claim, provider, results.msdrg, **kwargs
                )
            if Modules.LTCH in unique_modules:
                if self.ltch_client is None:
                    results.error = "LTCH client not initialized"
                    return results
                if not isinstance(provider, IPSFProvider):
                    results.error = "IPSF provider not initialized"
                    return results
                results.ltch, results.ipsf = self.ltch_client.process(
                    claim, provider, results.msdrg, **kwargs
                )
            if Modules.IRF in unique_modules:
                if self.irf_client is None:
                    results.error = "IRF client not initialized"
                    return results
                if not isinstance(provider, IPSFProvider):
                    results.error = "IPSF provider not initialized"
                    return results
                results.irf, results.ipsf = self.irf_client.process(
                    claim, provider, results.cmg, **kwargs
                )
            if Modules.HOSPICE in unique_modules:
                if self.hospice_client is None:
                    results.error = "Hospice client not initialized"
                    return results
                results.hospice = self.hospice_client.process(claim)
            if Modules.SNF in unique_modules:
                if self.snf_client is None:
                    results.error = "SNF client not initialized"
                    return results
                if not isinstance(provider, IPSFProvider):
                    results.error = "IPSF provider not initialized"
                    return results
                results.snf, results.ipsf = self.snf_client.process(claim, provider, **kwargs)
            if Modules.HHA in unique_modules:
                if self.hha_client is None:
                    results.error = "HHA client not initialized"
                    return results
                if not isinstance(provider, IPSFProvider):
                    results.error = "IPSF provider not initialized"
                    return results
                results.hha, results.ipsf = self.hha_client.process(
                    claim, provider, results.hhag, **kwargs
                )
            if Modules.ESRD in unique_modules:
                if self.esrd_client is None:
                    results.error = "ESRD client not initialized"
                    return results
                if not isinstance(provider, OPSFProvider):
                    results.error = "OPSF provider not initialized"
                    return results
                results.esrd, results.opsf = self.esrd_client.process(claim, provider, **kwargs)
            if Modules.FQHC in unique_modules:
                if self.fqhc_client is None:
                    results.error = "FQHC client not initialized"
                    return results
                if results.ioce is None:
                    results.error = "FQHC pricer requires IOCE module to be run"
                    return results
                else:
                    results.fqhc = self.fqhc_client.process(claim, results.ioce)
            return results
        except JavaRuntimeError as e:
            results.error = e.explanation
            return results
