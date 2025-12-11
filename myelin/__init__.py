"""Top-level public API for the myelin package.

This module re-exports commonly used classes and functions so users can write
concise imports like:

    from myelin import (
        Claim, DiagnosisCode, ProcedureCode, PoaType, DxType,
        DrgClient, MsdrgOutput,
        MceClient, MceOutput,
        IoceClient, IoceOutput,
        IppsClient, IppsOutput, OppsClient, OppsOutput,
        IpfClient, IpfOutput, LtchClient, LtchOutput, HospiceClient, HospiceOutput,
        CMSDownloader, IPSFDatabase, OPSFDatabase, IPSFProvider, OPSFProvider, UrlLoader,
        Myelin,
    )
"""

# Core input models
# Helper utilities
from .converter import (
    ICD10Conversion,
    ICD10ConvertOutput,
    ICDConverter,
    create_database,
    expand_code_range,
    parse_icd_conversion_table,
)

# High-level orchestrator
from .core import Myelin, MyelinOutput, MyelinIO
from .helpers.cms_downloader import CMSDownloader
from .helpers.utils import ReturnCode

# HHA Grouper
from .hhag import HhagClient, HhagEdit, HhagOutput
from .input.claim import (
    Address,
    Claim,
    DiagnosisCode,
    DxType,
    ICDConvertOption,
    ICDConvertOptions,
    IrfPai,
    LineItem,
    Modules,
    OasisAssessment,
    OccurrenceCode,
    Patient,
    PoaType,
    ProcedureCode,
    Provider,
    SpanCode,
    ValueCode,
)

# IOCE (OPPS code editor)
from .ioce.ioce_client import IoceClient
from .ioce.ioce_output import IoceOutput

# CMG Grouper
from .irfg.irfg_client import IrfgClient
from .irfg.irfg_output import IrfgOutput

# MCE editor
from .mce import MceClient, MceOutput, MceOutputDxCode, MceOutputPrCode

# MSDRG grouper
from .msdrg import DrgClient, MsdrgOutput, MsdrgOutputDxCode, MsdrgOutputPrCode
from .pricers.esrd import EsrdClient, EsrdOutput
from .pricers.fqhc import FqhcClient, FqhcOutput
from .pricers.hha import HhaClient, HhaOutput
from .pricers.hospice import HospiceClient, HospiceOutput
from .pricers.ipf import IpfClient, IpfOutput

# Pricers
from .pricers.ipps import IppsClient, IppsOutput

# Provider data access and classpath utilities
from .pricers.ipsf import IPSFDatabase, IPSFProvider
from .pricers.irf import IrfClient, IrfOutput
from .pricers.ltch import LtchClient, LtchOutput
from .pricers.opps import OppsClient, OppsOutput
from .pricers.opsf import OPSFDatabase, OPSFProvider
from .pricers.snf import SnfClient, SnfOutput
from .pricers.url_loader import UrlLoader

__all__ = [
    # Input models
    "Address",
    "Patient",
    "Provider",
    "Claim",
    "ValueCode",
    "ProcedureCode",
    "OccurrenceCode",
    "SpanCode",
    "DxType",
    "DiagnosisCode",
    "LineItem",
    "PoaType",
    "ICDConvertOption",
    "ICDConvertOptions",
    "IrfPai",
    "OasisAssessment",
    "Modules",
    # MSDRG
    "DrgClient",
    "MsdrgOutput",
    "MsdrgOutputDxCode",
    "MsdrgOutputPrCode",
    # CMG
    "IrfgClient",
    "IrfgOutput",
    # HHA
    "HhagClient",
    "HhagOutput",
    "HhagEdit",
    # MCE
    "MceClient",
    "MceOutput",
    "MceOutputDxCode",
    "MceOutputPrCode",
    # IOCE
    "IoceClient",
    "IoceOutput",
    # Pricers
    "IppsClient",
    "IppsOutput",
    "OppsClient",
    "OppsOutput",
    "IpfClient",
    "IpfOutput",
    "LtchClient",
    "LtchOutput",
    "HospiceClient",
    "HospiceOutput",
    "SnfClient",
    "SnfOutput",
    "HhaClient",
    "HhaOutput",
    "IrfClient",
    "IrfOutput",
    "EsrdClient",
    "EsrdOutput",
    "FqhcClient",
    "FqhcOutput",
    # Helpers and utilities
    "CMSDownloader",
    "IPSFDatabase",
    "OPSFDatabase",
    "IPSFProvider",
    "OPSFProvider",
    "UrlLoader",
    # Converter
    "ICD10Conversion",
    "ICDConverter",
    "create_database",
    "parse_icd_conversion_table",
    "expand_code_range",
    "ICD10ConvertOutput",
    # Orchestrator
    "Myelin",
    "MyelinOutput",
    "ReturnCode",
    "MyelinIO",
]
