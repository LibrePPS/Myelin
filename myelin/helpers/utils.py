import functools
import io
from contextlib import redirect_stderr
from datetime import datetime
from os import getenv
from typing import Callable, ParamSpec, Protocol, TypeVar

import jpype
from pydantic import BaseModel


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
                raise ValueError(
                    f"Invalid date format: {py_date}. Expected format is YYYY-MM-DD or YYYYMMDD."
                )
    else:
        # Assuming the int is in YYYYMMDD format
        date_str = str(py_date)
        if len(date_str) != 8:
            raise ValueError(
                f"Invalid date integer: {py_date}. Expected format is YYYYMMDD."
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

            raise RuntimeError(error_msg) from java_ex

    return wrapper
