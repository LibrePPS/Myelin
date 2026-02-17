import functools
import io
from contextlib import redirect_stderr
from datetime import datetime
from os import getenv
from typing import Callable, ParamSpec, Protocol, TypeVar
from myelin.input.claim import Modules

import jpype
from pydantic import BaseModel

PROVIDER_TYPES = {
    "00": {"description": "Short Term Facility", "modules": [Modules.MCE, Modules.MSDRG, Modules.PSYCH]},
    "02": {"description": "Long Term", "modules": [Modules.MCE, Modules.MSDRG, Modules.LTCH]},
    "03": {"description": "Psychiatric", "modules": [Modules.MCE, Modules.MSDRG, Modules.PSYCH]},
    "04": {"description": "Rehabilitation Facility", "modules": [Modules.MCE, Modules.CMG, Modules.IRF]},
    "05": {"description": "Pediatric"},
    "06": {"description": "Hospital Distinct Parts"},
    "07": {"description": "Rural Referral Center"},
    "08": {"description": "Indian Health Service"},
    "13": {"description": "Cancer Facility"},
    "14": {"description": "Medicare Dependent Hospital"},
    "15": {"description": "Medicare Dependent Hospital/Referral Center"},
    "16": {"description": "Re-based Sole Community Hospital"},
    "17": {"description": "Re-based Sole Community Hospital/Referral Center"},
    "18": {"description": "Medical Assistance Facility"},
    "21": {"description": "Essential Access Community Hospital"},
    "22": {"description": "Essential Access Community Hospital/Referral Center"},
    "23": {"description": "Rural Primary Care Hospital"},
    "24": {"description": "Rural Emergency Hospitals"},
    "32": {"description": "Nursing Home Case Mix Quality Demo Project Phase II"},
    "33": {"description": "Nursing Home Case Mix Quality Demo Project Phase III"},
    "34": {"description": "Reserved"},
    "35": {"description": "Hospice", "modules": [Modules.HOSPICE]},
    "36": {"description": "Home Health Agency", "modules": [Modules.HHAG, Modules.HHA]},
    "37": {"description": "Critical Access Hospital"},
    "38": {"description": "Skilled Nursing Facility (SNF)", "modules": [Modules.IOCE,Modules.SNF]},
    "40": {"description": "Hospital Based ESRD Facility", "modules": [Modules.IOCE, Modules.ESRD]},
    "41": {"description": "Independent ESRD Facility", "modules": [Modules.IOCE, Modules.ESRD]},
    "42": {"description": "Federally Qualified Health Centers", "modules": [Modules.IOCE, Modules.FQHC]},
    "43": {"description": "Religious Non-Medical Health Care Institutions"},
    "44": {"description": "Rural Health Clinics-Free Standing"},
    "45": {"description": "Rural Health Clinics-Provider Based"},
    "46": {"description": "Comprehensive Outpatient Rehab Facilities"},
    "47": {"description": "Community Mental Health Centers"},
    "48": {"description": "Outpatient Physical Therapy Services"},
    "49": {"description": "Psychiatric Distinct Part", "modules": [Modules.MCE, Modules.MSDRG,Modules.PSYCH]},
    "50": {"description": "Rehabilitation Distinct Part"},
    "51": {"description": "Short-Term Hospital Swing Bed"},
    "52": {"description": "Long-Term Care Hospital Swing Bed"},
    "53": {"description": "Rehabilitation Facility Swing Bed"},
    "54": {"description": "Critical Access Hospital Swing Bed"},
}


class HasJavaDateClasses(Protocol):
    """Protocol for classes that have Java date formatting classes."""

    java_date_class: jpype.JClass
    java_data_formatter: jpype.JClass


class ReturnCode(BaseModel):
    code: str | None = None
    description: str | None = None
    explanation: str | None = None

    def from_java(self, java_return_code: jpype.JObject | None):
        """
        Convert a Java ReturnCode object to a Python ReturnCode object.
        """
        if java_return_code is None:
            return
        self.code = str(java_return_code.getCode())
        self.description = str(java_return_code.getDescription())
        self.explanation = str(java_return_code.getExplanation())
        return


class JavaRuntimeError(Exception):
    def __init__(self, code: str, description: str, explanation: str = ""):
        self.code = code
        self.description = description
        self.explanation = explanation
        super().__init__(description)

    def to_return_code(self) -> ReturnCode:
        """Convert this error into a :class:`ReturnCode` for output objects."""
        return ReturnCode(
            code=self.code,
            description=self.description,
            explanation=self.explanation,
        )


class PricerRuntimeError(Exception):
    def __init__(self, code: str, description: str, explanation: str = ""):
        self.code = code
        self.description = description
        self.explanation = explanation
        super().__init__(description)

    def to_return_code(self) -> ReturnCode:
        """Convert this error into a :class:`ReturnCode` for output objects."""
        return ReturnCode(
            code=self.code,
            description=self.description,
            explanation=self.explanation,
        )


class ProviderDataError(Exception):
    """Raised when provider data cannot be loaded for pricing.

    Instead of halting claim processing with an unhandled exception, pricer
    ``process()`` methods catch this and surface the information as a
    :class:`ReturnCode` on the output object so callers always receive a
    structured result.

    Attributes:
        code: A short error code (e.g. ``"P0001"``).
        description: A human-readable summary of the error.
        explanation: A longer explanation with contextual details.
    """

    def __init__(self, code: str, description: str, explanation: str = ""):
        self.code = code
        self.description = description
        self.explanation = explanation
        super().__init__(description)

    def to_return_code(self) -> ReturnCode:
        """Convert this error into a :class:`ReturnCode` for output objects."""
        return ReturnCode(
            code=self.code,
            description=self.description,
            explanation=self.explanation,
        )


def float_or_none(value: jpype.JObject | None) -> float | None:
    """
    Convert a value to float or return None if conversion fails.
    """
    if value is None:
        return None
    try:
        return float(value.floatValue())
    except (ValueError, TypeError):
        return None


def py_date_to_java_date(
    self: HasJavaDateClasses, py_date: datetime | str | int | None
) -> jpype.JObject | None:
    """
    Convert a Python datetime object to a Java Date object.
    """
    if py_date is None:
        return None
    if isinstance(py_date, datetime):
        date = py_date.strftime("%Y%m%d")
        formatter = self.java_data_formatter.ofPattern("yyyyMMdd")
        return self.java_date_class.parse(date, formatter)
    elif isinstance(py_date, str):
        # Check that we're in YYYY-MM-DD format
        try:
            date = datetime.strptime(py_date, "%Y-%m-%d")
            return py_date_to_java_date(self, date)
        except ValueError:
            # Try to parse as YYYYMMDD
            try:
                date = datetime.strptime(py_date, "%Y%m%d")
                return py_date_to_java_date(self, date)
            except ValueError:
                raise PricerRuntimeError(
                    "DT01",
                    f"Invalid date format: {py_date}. Expected format is YYYY-MM-DD or YYYYMMDD.",
                    "The date format is invalid. Please provide a date in the format YYYY-MM-DD or YYYYMMDD.",
                )
    else:
        # Assuming the int is in YYYYMMDD format
        date_str = str(py_date)
        if len(date_str) != 8:
            raise PricerRuntimeError(
                "DT02",
                f"Invalid date integer: {py_date}. Expected format is YYYYMMDD.",
                "The date integer is invalid. Please provide a date in the format YYYYMMDD.",
            )
        formatter = self.java_data_formatter.ofPattern("yyyyMMdd")
        return self.java_date_class.parse(date_str, formatter)


def create_supported_years(pps: str) -> jpype.JObject:
    today = datetime.now()
    year = today.year
    java_integer_class = jpype.JClass("java.lang.Integer")
    java_array = jpype.JClass("java.util.ArrayList")()
    if getenv(f"{pps}_SUPPORTED_YEARS") is not None:
        supported_years_env = str(getenv(f"{pps}_SUPPORTED_YEARS")).split(",")
        if len(supported_years_env) > 0:
            for year_str in supported_years_env:
                try:
                    year_int = int(year_str.strip())
                    if year_int >= today.year - 3:
                        java_array.add(java_integer_class(year_int))
                except ValueError:
                    raise ValueError(
                        f"Invalid year in {pps}_SUPPORTED_YEARS: {year_str}"
                    )
    else:
        while year >= today.year - 3:
            java_array.add(java_integer_class(year))
            year -= 1
    return java_array


P = ParamSpec("P")
T = TypeVar("T")


def handle_java_exceptions(func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator to catch and handle Java exceptions from jpype calls.

    This decorator wraps methods that call Java code and provides detailed
    error information when Java exceptions occur, including the Java stack trace.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except jpype.JException as java_ex:
            # Extract Java exception details
            java_class = java_ex.__class__.__name__
            java_message = str(java_ex)

            # Try to get more detailed information from the Java exception
            java_stack_trace = None
            if hasattr(java_ex, "stacktrace"):
                java_stack_trace = java_ex.stacktrace()
            elif hasattr(java_ex, "printStackTrace"):
                string_io = io.StringIO()
                try:
                    with redirect_stderr(string_io):
                        java_ex.printStackTrace()
                    java_stack_trace = string_io.getvalue()
                except Exception:
                    java_stack_trace = "Stack trace not available"

            error_msg = f"Java exception occurred in {func.__name__}:\n"
            error_msg += f"Java Exception Type: {java_class}\n"
            error_msg += f"Java Message: {java_message}\n"
            if java_stack_trace:
                error_msg += f"Java Stack Trace:\n{java_stack_trace}"

            # Check if self exists, if so, check if logger exists on self and log error
            if args and hasattr(args[0], "logger"):
                args[0].logger.error(error_msg)
            else:
                print(error_msg)

            raise JavaRuntimeError(
                code="JERR",
                description="An internal error occurred during processing through a CMS Java module.",
                explanation="An internal error occurred in the Java processing module. Please contact the system administrator for assistance.",
            )

    return wrapper
