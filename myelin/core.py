import logging
import os
from contextlib import ExitStack
from threading import RLock
from typing import Literal, Optional

import jpype
from pydantic import BaseModel

from myelin.database.manager import DatabaseManager
from myelin.helpers.cms_downloader import CMSDownloader
from myelin.helpers.utils import handle_java_exceptions
from myelin.hhag.hhag_client import HhagClient, HhagOutput
from myelin.input.claim import Claim, Modules
from myelin.ioce.ioce_client import IoceClient, IoceOutput
from myelin.irfg.irfg_client import IrfgClient, IrfgOutput
from myelin.mce.mce_client import MceClient, MceOutput
from myelin.msdrg.drg_client import DrgClient, MsdrgOutput
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

PRICERS = {
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


class MyelinOutput(BaseModel):
    # Editors
    ioce: Optional[IoceOutput] = None
    mce: Optional[MceOutput] = None
    # Groupers
    hhag: Optional[HhagOutput] = None
    msdrg: Optional[MsdrgOutput] = None
    cmg: Optional[IrfgOutput] = None
    # Pricers
    ipps: Optional[IppsOutput] = None
    opps: Optional[OppsOutput] = None
    psych: Optional[IpfOutput] = None
    ltch: Optional[LtchOutput] = None
    irf: Optional[IrfOutput] = None
    hospice: Optional[HospiceOutput] = None
    snf: Optional[SnfOutput] = None
    hha: Optional[HhaOutput] = None
    esrd: Optional[EsrdOutput] = None
    fqhc: Optional[FqhcOutput] = None
    error: Optional[str] = None


class Myelin:
    # Class-level locks and tracking for thread safety
    _jvm_lock = RLock()  # Thread-safe JVM operations
    _jvm_started = False  # Track if we started the JVM

    def __init__(
        self,
        build_jar_dirs: bool = True,
        jar_path: str = "./jars",
        db_path: str = "./data/myelin.db",
        build_db: bool = False,
        log_level: int = logging.INFO,
        extra_classpaths: list[str] = [],
        db_backend: Literal["sqlite", "postgresql"] = "sqlite",
    ):
        # Store configuration
        self.extra_classpaths = extra_classpaths or []
        self.jar_path = jar_path
        self.db_path = db_path
        self.build_jar_dirs = build_jar_dirs
        self.build_db = build_db

        # Initialize resource management
        self._exit_stack = ExitStack()
        self._initialized = False

        # Pricer Clients @TODO: Add more pricer clients as needed
        self.ipps_client: Optional[IppsClient] = None
        self.opps_client: Optional[OppsClient] = None
        self.ipf_client: Optional[IpfClient] = None
        self.ltch_client: Optional[LtchClient] = None
        self.irf_client: Optional[IrfClient] = None
        self.hospice_client: Optional[HospiceClient] = None
        self.snf_client: Optional[SnfClient] = None
        self.hha_client: Optional[HhaClient] = None
        self.esrd_client: Optional[EsrdClient] = None
        self.fqhc_client: Optional[FqhcClient] = None
        self.irfg_client: Optional[IrfgClient] = None
        # End of Pricer Clients

        # Initialize logger first
        self.logger = logging.getLogger("Myelin")
        self.logger.setLevel(log_level)

        # Setup directories
        self._ensure_directories()

        # Setup databases with resource management
        self.db_manager = DatabaseManager(db_path, db_backend, build_db, log_level)
        self._exit_stack.enter_context(self.db_manager)
        self.icd10_converter = self.db_manager.icd10_converter

        # Setup CMS downloader if requested
        if self.build_jar_dirs:
            self.cms_downloader = CMSDownloader(
                jars_dir=self.jar_path, log_level=self.logger.level
            )
            self.cms_downloader.build_jar_environment(False)

        # Setup JVM with thread safety
        self._setup_jvm()

    def __enter__(self):
        """Context manager entry"""
        if not self._initialized:
            self.setup_clients()
            self._initialized = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with proper cleanup"""
        self.cleanup()
        return False  # Don't suppress exceptions

    def cleanup(self):
        """Comprehensive cleanup of all resources"""
        self._exit_stack.close()

    def _ensure_directories(self):
        """Ensure required directories exist"""
        if not os.path.exists(self.jar_path):
            os.makedirs(self.jar_path)
        if not os.path.exists(os.path.dirname(self.db_path)):
            os.makedirs(os.path.dirname(self.db_path))

    def _setup_jvm(self):
        """Thread-safe JVM initialization"""
        with Myelin._jvm_lock:
            if not jpype.isJVMStarted():
                try:
                    classpath = [f"{self.jar_path}/*", *self.extra_classpaths]
                    jpype.startJVM(classpath=classpath)
                    Myelin._jvm_started = True
                    self.logger.info("JVM started successfully")

                    # Register JVM shutdown with exit stack
                    self._exit_stack.callback(self._shutdown_jvm)
                except Exception as e:
                    self.logger.error(f"Failed to start JVM: {e}")
                    raise RuntimeError(f"JVM startup failed: {e}") from e
            else:
                self.logger.debug("JVM already started")

    def _shutdown_jvm(self):
        """Thread-safe JVM shutdown"""
        with Myelin._jvm_lock:
            if jpype.isJVMStarted() and Myelin._jvm_started:
                try:
                    jpype.shutdownJVM()
                    Myelin._jvm_started = False
                    self.logger.info("JVM shutdown successfully")
                except Exception as e:
                    self.logger.warning(f"Error shutting down JVM: {e}")

    def setup_clients(self):
        """Initialize the CMS clients."""
        self.drg_client = DrgClient()
        self.mce_client = MceClient()
        self.ioce_client = IoceClient()
        self.hhag_client = HhagClient()
        self.irfg_client = IrfgClient()
        # check for pricer sub directory
        if os.path.exists(os.path.join(self.jar_path, "pricers")):
            self.pricers_path = os.path.abspath(os.path.join(self.jar_path, "pricers"))
            self.pricer_jars = [
                os.path.join(self.pricers_path, f)
                for f in os.listdir(self.pricers_path)
                if f.endswith(".jar")
            ]
        if self.pricer_jars:
            self.setup_pricers()

    def setup_pricers(self):
        # check if pricer jars exist by looking for value from PRICERS dictionary in file names of pricer_jars
        for pricer, jar_name in PRICERS.items():
            if any(jar_name in jar for jar in self.pricer_jars):
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

    @handle_java_exceptions
    def process(self, claim: Claim, **kwargs) -> MyelinOutput:
        """Process a claim through the appropriate modules based on its configuration."""

        if not isinstance(claim, Claim):
            raise ValueError("Input must be an instance of Claim")
        # Validate the claim
        Claim.model_validate(claim)

        results = MyelinOutput()
        if len(claim.modules) == 0:
            results.error = "No modules specified in claim"
            return results
        # Claims Flow Editors -> Groupers -> Pricers
        # Create unique list of modules preserving order
        unique_modules = []
        for module in claim.modules:
            if module not in unique_modules:
                unique_modules.append(module)
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
            results.ioce = self.ioce_client.process(claim,include_descriptions=True, **kwargs)
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
            else:
                results.ipps = self.ipps_client.process(claim, results.msdrg, **kwargs)
        if Modules.OPPS in unique_modules:
            if self.opps_client is None:
                results.error = "OPPS client not initialized"
                return results
            results.opps = self.opps_client.process(claim, results.ioce, **kwargs)
        if Modules.PSYCH in unique_modules:
            if self.ipf_client is None:
                results.error = "IPF client not initialized"
                return results
            results.psych = self.ipf_client.process(claim, results.msdrg, **kwargs)
        if Modules.LTCH in unique_modules:
            if self.ltch_client is None:
                results.error = "LTCH client not initialized"
                return results
            results.ltch = self.ltch_client.process(claim, results.msdrg, **kwargs)
        if Modules.IRF in unique_modules:
            if self.irf_client is None:
                results.error = "IRF client not initialized"
                return results
            results.irf = self.irf_client.process(claim, results.cmg, **kwargs)
        if Modules.HOSPICE in unique_modules:
            if self.hospice_client is None:
                results.error = "Hospice client not initialized"
                return results
            results.hospice = self.hospice_client.process(claim)
        if Modules.SNF in unique_modules:
            if self.snf_client is None:
                results.error = "SNF client not initialized"
                return results
            results.snf = self.snf_client.process(claim, **kwargs)
        if Modules.HHA in unique_modules:
            if self.hha_client is None:
                results.error = "HHA client not initialized"
                return results
            results.hha = self.hha_client.process(claim, results.hhag, **kwargs)
        if Modules.ESRD in unique_modules:
            if self.esrd_client is None:
                results.error = "ESRD client not initialized"
                return results
            results.esrd = self.esrd_client.process(claim, **kwargs)
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
