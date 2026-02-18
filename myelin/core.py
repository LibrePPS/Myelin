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
from myelin.helpers.utils import JavaRuntimeError, ProviderDataError, PROVIDER_TYPES
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
from myelin.pricers.asc.client import AscClient, AscOutput

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
    Modules.ASC,
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
    ipsf: IPSFProvider | None = None
    opsf: OPSFProvider | None = None
    asc: AscOutput | None = None

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
        self.asc_client: AscClient | None = None

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
        self.irfg_client = IrfgClient()
        self.asc_client = AscClient(
            "./pricers/asc/data", self.logger, preload_data=True
        )

        # Initialize Custom Pricers
        try:
            asc_data_path = os.path.join(
                os.path.dirname(__file__), "pricers", "asc", "data"
            )
            self.asc_client = AscClient(asc_data_path, self.logger)
        except Exception as e:
            self.logger.warning(f"Failed to initialize ASC Client: {e}")

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

    def _generate_auto_modules(
        self,
        claim: Claim,
        ipsf_provider: IPSFProvider | None,
        opsf_provider: OPSFProvider | None,
    ) -> None:
        """Generate a list of modules based on the claim type."""
        provider_type = ""
        if ipsf_provider is not None:
            if ipsf_provider.provider_type and ipsf_provider.provider_type != "":
                provider_type = ipsf_provider.provider_type
        elif opsf_provider is not None:
            if opsf_provider.provider_type and opsf_provider.provider_type != "":
                provider_type = opsf_provider.provider_type

        provider_obj = PROVIDER_TYPES.get(provider_type, None)

        # ----------------------------------------------------------------------
        # Generate modules based on provider type
        # ----------------------------------------------------------------------
        mods_set = False
        if provider_obj is not None:
            modules = provider_obj.get("modules", None)
            if modules is not None:
                for module in modules:
                    if isinstance(module, Modules):
                        claim.modules.append(module)
                        mods_set = True
            # Remove specialized groupers if their assesment data is missing
            if Modules.HHAG in claim.modules and claim.oasis_assessment is None:
                claim.modules.remove(Modules.HHAG)
            if Modules.CMG in claim.modules and claim.irf_pai is None:
                claim.modules.remove(Modules.CMG)

        # --------------------------------------------------------------------------
        # Generate modules based on Bill Type
        # --------------------------------------------------------------------------

        # IRF
        for line in claim.lines:
            if line.revenue_code == "0024":
                if claim.irf_pai is not None:
                    claim.modules.append(Modules.CMG)
                claim.modules.append(Modules.IRF)
                mods_set = True
                break
        # SNF
        for line in claim.lines:
            if line.revenue_code == "0022":
                claim.modules.append(Modules.SNF)
                mods_set = True
                break

        if not mods_set:
            bill_type = claim.bill_type
            if bill_type.startswith("0"):
                bill_type = bill_type[1:]  # Remove leading zero
            if len(bill_type) < 2:
                bill_type = "000"
            bill_type_facility = bill_type[0]
            bill_type_type_of_care = bill_type[1]

            ipsf_ccn: str = (
                ipsf_provider.provider_ccn
                if ipsf_provider is not None and ipsf_provider.provider_ccn is not None
                else ""
            )
            # FQHC
            if bill_type.startswith("77"):
                claim.modules.append(Modules.IOCE)
                claim.modules.append(Modules.FQHC)
            elif bill_type.startswith("72"):  # ESRD
                claim.modules.append(Modules.IOCE)
                claim.modules.append(Modules.ESRD)
            elif bill_type.startswith("83"):  # ASCs
                claim.modules.append(Modules.ASC)
            elif bill_type_facility == "2":  # SNF, secondary to rev code lookup above
                if bill_type_type_of_care in ("2", "3"):
                    claim.modules.append(Modules.IOCE)
                claim.modules.append(Modules.SNF)
            elif bill_type_facility == "3":  # Home Health
                if claim.oasis_assessment is not None:
                    claim.modules.append(Modules.HHAG)
                claim.modules.append(Modules.HHA)
            elif bill_type.startswith("11"):
                claim.modules.append(Modules.MCE)
                claim.modules.append(Modules.MSDRG)
                if len(ipsf_ccn) >= 3:
                    if ipsf_ccn[2] in ("4", "S", "M"):
                        claim.modules.append(Modules.PSYCH)
                    elif ipsf_ccn[2] == "2":
                        claim.modules.append(Modules.LTCH)
                    else:
                        claim.modules.append(Modules.IPPS)
                else:
                    claim.modules.append(Modules.IPPS)
            else:
                claim.modules.append(Modules.IOCE)
                claim.modules.append(Modules.OPPS)

    def process(self, claim: Claim, **kwargs: object) -> MyelinOutput:
        """Process a claim through the appropriate modules based on its configuration."""

        # Validate the claim
        Claim.model_validate(claim)

        results = MyelinOutput()

        # Early validation: no modules specified
        if not claim.modules:
            results.error = "No modules specified in claim"
            return results

        # Deduplicate modules while preserving order (O(n) instead of O(n²))
        seen: set[Modules] = set()
        unique_modules: list[Modules] = []
        for module in claim.modules:
            if module not in seen:
                seen.add(module)
                unique_modules.append(module)

        # Determine required provider type upfront based on all modules
        ipsf_needed = any(m in IPSF_PRICERS for m in unique_modules)
        opsf_needed = any(m in OPSF_PRICERS for m in unique_modules)

        # Create separate providers for IPSF and OPSF pricers
        ipsf_provider: IPSFProvider | None = None
        opsf_provider: OPSFProvider | None = None

        if ipsf_needed:
            ipsf_provider = IPSFProvider()
        if opsf_needed:
            opsf_provider = OPSFProvider()

        # Initialize providers if needed
        if ipsf_provider is not None or opsf_provider is not None:
            if self.db_manager.engine is None:
                results.error = "No database connection to fetch provider information"
                return results
            try:
                if ipsf_provider is not None:
                    ipsf_provider.from_claim(claim, self.db_manager.engine, **kwargs)
                if opsf_provider is not None:
                    opsf_provider.from_claim(claim, self.db_manager.engine, **kwargs)
            except ProviderDataError as e:
                results.error = e.explanation
                return results

        if Modules.AUTO in unique_modules:
            if len(claim.modules) > 1:
                results.error = (
                    "Auto module cannot be paired with any other module request"
                )
                return results
            self._generate_auto_modules(claim, ipsf_provider, opsf_provider)

            # Recalculate unique_modules after auto-generation
            seen = set()
            unique_modules = []
            for module in claim.modules:
                if module not in seen:
                    seen.add(module)
                    unique_modules.append(module)

            # Re-evaluate provider needs
            new_ipsf_needed = any(m in IPSF_PRICERS for m in unique_modules)
            new_opsf_needed = any(m in OPSF_PRICERS for m in unique_modules)

            # Load missing providers
            if (new_ipsf_needed and ipsf_provider is None) or (
                new_opsf_needed and opsf_provider is None
            ):
                if self.db_manager.engine is None:
                    results.error = (
                        "No database connection to fetch provider information"
                    )
                    return results

                try:
                    if new_ipsf_needed and ipsf_provider is None:
                        ipsf_provider = IPSFProvider()
                        ipsf_provider.from_claim(
                            claim, self.db_manager.engine, **kwargs
                        )

                    if new_opsf_needed and opsf_provider is None:
                        opsf_provider = OPSFProvider()
                        opsf_provider.from_claim(
                            claim, self.db_manager.engine, **kwargs
                        )
                except ProviderDataError as e:
                    results.error = e.explanation
                    return results
        else:
            if claim.bill_type.endswith("0"):
                results.error = f"Bill type {claim.bill_type} is a non payment bill"
                return results

        try:
            # Editors
            if Modules.MCE in unique_modules:
                self._process_editor(Modules.MCE, self.mce_client, results, claim)
            if Modules.IOCE in unique_modules:
                self._process_editor(
                    Modules.IOCE,
                    self.ioce_client,
                    results,
                    claim,
                    include_descriptions=True,
                    **kwargs,
                )

            # Groupers
            if Modules.MSDRG in unique_modules:
                self._process_grouper(
                    Modules.MSDRG,
                    self.drg_client,
                    results,
                    claim,
                    icd_converter=self.icd10_converter,
                )
            if Modules.HHAG in unique_modules:
                self._process_grouper(Modules.HHAG, self.hhag_client, results, claim)
            if Modules.CMG in unique_modules:
                self._process_grouper(Modules.CMG, self.irfg_client, results, claim)

            # Pricers - pass the appropriate provider
            if Modules.IPPS in unique_modules:
                self._process_pricer_ipps(
                    self.ipps_client,
                    results,
                    claim,
                    ipsf_provider,
                    results.msdrg,
                    **kwargs,
                )
            if Modules.OPPS in unique_modules:
                self._process_pricer_opps(
                    self.opps_client,
                    results,
                    claim,
                    opsf_provider,
                    results.ioce,
                    **kwargs,
                )
            if Modules.PSYCH in unique_modules:
                self._process_pricer_ipf(
                    self.ipf_client,
                    results,
                    claim,
                    ipsf_provider,
                    results.msdrg,
                    **kwargs,
                )
            if Modules.LTCH in unique_modules:
                self._process_pricer_ltch(
                    self.ltch_client,
                    results,
                    claim,
                    ipsf_provider,
                    results.msdrg,
                    **kwargs,
                )
            if Modules.IRF in unique_modules:
                self._process_pricer_irf(
                    self.irf_client,
                    results,
                    claim,
                    ipsf_provider,
                    results.cmg,
                    **kwargs,
                )
            if Modules.HOSPICE in unique_modules:
                self._process_pricer_hospice(self.hospice_client, results, claim)
            if Modules.SNF in unique_modules:
                self._process_pricer_snf(
                    self.snf_client, results, claim, ipsf_provider, **kwargs
                )
            if Modules.HHA in unique_modules:
                self._process_pricer_hha(
                    self.hha_client,
                    results,
                    claim,
                    ipsf_provider,
                    results.hhag,
                    **kwargs,
                )
            if Modules.ESRD in unique_modules:
                self._process_pricer_esrd(
                    self.esrd_client, results, claim, opsf_provider, **kwargs
                )
            if Modules.FQHC in unique_modules:
                self._process_pricer_fqhc(
                    self.fqhc_client, results, claim, results.ioce
                )
            if Modules.ASC in unique_modules:
                self._process_pricer_asc(
                    self.asc_client, results, claim, opsf_provider, **kwargs
                )

            return results
        except JavaRuntimeError as e:
            results.error = e.explanation
            return results

    def _process_editor(
        self, module: Modules, client, results: MyelinOutput, claim: Claim, **kwargs
    ) -> None:
        """Process an editor module with null-checked client."""
        if client is None:
            results.error = f"{module.value} client not initialized"
            return
        # Map module to correct output attribute
        attr_name = module.value.lower()
        setattr(results, attr_name, client.process(claim, **kwargs))

    def _process_grouper(
        self, module: Modules, client, results: MyelinOutput, claim: Claim, **kwargs
    ) -> None:
        """Process a grouper module with null-checked client."""
        if client is None:
            results.error = f"{module.value} client not initialized"
            return
        # Map module to correct output attribute (e.g., MSDRG -> msdrg, CMG -> cmg)
        attr_name = module.value.lower()
        setattr(results, attr_name, client.process(claim, **kwargs))

    def _process_pricer_ipps(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        provider: IPSFProvider | None,
        msdrg: MsdrgOutput | None,
        **kwargs,
    ) -> None:
        """Process IPPS pricer."""
        if client is None:
            results.error = "IPPS client not initialized"
            return
        results.ipps, results.ipsf = client.process(claim, provider, msdrg, **kwargs)

    def _process_pricer_opps(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        provider: OPSFProvider | None,
        ioce: IoceOutput | None,
        **kwargs,
    ) -> None:
        """Process OPPS pricer."""
        if client is None:
            results.error = "OPPS client not initialized"
            return
        results.opps, results.opsf = client.process(claim, provider, ioce, **kwargs)

    def _process_pricer_ipf(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        provider: IPSFProvider | None,
        msdrg: MsdrgOutput | None,
        **kwargs,
    ) -> None:
        """Process IPF (Psych) pricer."""
        if client is None:
            results.error = "IPF client not initialized"
            return
        results.psych, results.ipsf = client.process(claim, provider, msdrg, **kwargs)

    def _process_pricer_ltch(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        provider: IPSFProvider | None,
        msdrg: MsdrgOutput | None,
        **kwargs,
    ) -> None:
        """Process LTCH pricer."""
        if client is None:
            results.error = "LTCH client not initialized"
            return
        results.ltch, results.ipsf = client.process(claim, provider, msdrg, **kwargs)

    def _process_pricer_irf(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        provider: IPSFProvider | None,
        cmg: IrfgOutput | None,
        **kwargs,
    ) -> None:
        """Process IRF pricer."""
        if client is None:
            results.error = "IRF client not initialized"
            return
        results.irf, results.ipsf = client.process(claim, provider, cmg, **kwargs)

    def _process_pricer_hospice(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
    ) -> None:
        """Process Hospice pricer."""
        if client is None:
            results.error = "Hospice client not initialized"
            return
        results.hospice = client.process(claim)

    def _process_pricer_snf(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        provider: IPSFProvider | None,
        **kwargs,
    ) -> None:
        """Process SNF pricer."""
        if client is None:
            results.error = "SNF client not initialized"
            return
        results.snf, results.ipsf = client.process(claim, provider, **kwargs)

    def _process_pricer_hha(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        provider: IPSFProvider | None,
        hhag: HhagOutput | None,
        **kwargs,
    ) -> None:
        """Process HHA pricer."""
        if client is None:
            results.error = "HHA client not initialized"
            return
        results.hha, results.ipsf = client.process(claim, provider, hhag, **kwargs)

    def _process_pricer_esrd(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        provider: OPSFProvider | None,
        **kwargs,
    ) -> None:
        """Process ESRD pricer."""
        if client is None:
            results.error = "ESRD client not initialized"
            return
        results.esrd, results.opsf = client.process(claim, provider, **kwargs)

    def _process_pricer_fqhc(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        ioce: IoceOutput | None,
    ) -> None:
        """Process FQHC pricer."""
        if client is None:
            results.error = "FQHC client not initialized"
            return
        if ioce is None:
            results.error = "FQHC pricer requires IOCE module to be run"
            return
        results.fqhc = client.process(claim, ioce)

    def _process_pricer_asc(
        self,
        client,
        results: MyelinOutput,
        claim: Claim,
        provider: OPSFProvider | None,
        **kwargs,
    ) -> None:
        """Process ASC pricer."""
        if client is None:
            results.error = "ASC client not initialized"
            return
        results.asc = client.process(claim, provider, **kwargs)
