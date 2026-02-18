# ASC Pricer Implementation

This directory contains the implementation of the Ambulatory Surgical Center (ASC) Pricer for Myelin.

## Overview

The ASC Pricer calculates reimbursement rates for ASC claims based on CMS regulations, specifically utilizing the Addendum AA (Covered Surgical Procedures), Addendum BB (Ancillary Services), Addendum FF (Device Intensive Procedures), and Wage Index data.

## Features

-   **Robust Data Loading**: Automatically detects and parses CMS data files in various formats (CSV, TSV) and structures (Legacy vs. New layouts).
-   **Binary Caching**: Optimizes startup time by caching parsed reference data in binary `.pkl` files.
-   **Wage Index Support**: Supports year-specific Wage Index files (`wage_index.csv/txt`) and dynamic column mapping (`WI{YY}`).
-   **Medically Unlikely Edits (MUE)**: Enforces unit limits per HCPCS per date of service with support for multiple enforcement modes.
-   **Complex Pricing Logic**: Implements:
    -   **Geographic Adjustment**: Applies labor-share (50%) adjustment using CBSA Wage Indices.
    -   **Device Intensive Logic**: Handles device offsets and credits (Modifiers FB/FC).
    -   **Multiple Procedure Discounting (MPR)**: Implements standard 100%/50% ranking logic.
    -   **Terminated/Reduced Procedures**: Special handling for Modifiers 73, 52, and 74.

## Supported Modifiers

| Modifier | Description | Logic Applied |
| :--- | :--- | :--- |
| **73** | Discontinued Outpatient/ASC Procedure Prior to Anesthesia | **50% Payment**. Device offset is removed *before* reduction if device-intensive. **Exempt from MPR**. |
| **52** | Reduced Services | **50% Payment**. **Exempt from MPR**. |
| **74** | Discontinued Outpatient/ASC Procedure After Anesthesia | **100% Payment**. Subject to normal Multiple Procedure Discounting. |
| **FB/FC** | Device Provided at No/Reduced Cost | Payment reduced by the full Device Offset amount. |
| **PT** | Colorectal Cancer Screening | (Informational currently, logic available for waiver of coinsurance if needed). |

## Logic Flow

1.  **Validation & Setup**:
    -   Requires an `OPSFProvider` for Wage Index lookup.
    -   **CBSA Fallback**: If no wage index is found in the provider data, the pricer checks `claim.additional_data["cbsa"]`.
2.  **Reference Data**: Loads data for the claim's `thru_date` (with fallback to the latest available quarter).
3.  **HCPCS Normalization**: Matches claim lines to Addendum AA (Surgical) or Addendum BB (Ancillary).
4.  **MUE Check**: Enforces Medically Unlikely Edits based on the provided `mues` dictionary.
    -   **Scope**: Grouped by **HCPCS + Service Date**.
    -   **Line Edit (`up_to_limit=False`)**: If the total units for a code on a given date exceed the limit, the entire set of lines for that code is denied.
    -   **Date-of-Service Edit (`up_to_limit=True`)**: Units are allowed up to the limit (greedy fill by claim order), and subsequent units/lines are denied.
    -   *Note: MUE check runs before the ancillary check so that MUE-denied surgical lines trigger ancillary unprocessability.*
5.  **Ancillary Check (CMS §60.2)**: Ancillary services (BB) require at least one payable related surgical procedure (AA) on the same claim. If none exist, BB lines are marked as `unprocessable`.
6.  **Line Calculation**:
    -   Calculates **Adjusted Rate**: `(Rate * 0.5 * WI) + (Rate * 0.5)`.
    -   Applies reductions for Modifiers 73/52/FB/FC.
7.  **Final Summation & MPR**:
    -   Sorts eligible lines by Adjusted Rate for Multiple Procedure Reduction.
    -   Units > 1 (or subsequent lines in the discount pool) pay 50% of the adjusted rate.
    -   Calculates line-level `line_payment`, `line_copayment`, and `line_total`.

## Optional Inputs

The `process` method accepts several optional parameters:

-   **`provider`**: An `OPSFProvider` instance containing wage index information.
-   **`mues`**: A dictionary mapping HCPCS codes to `AscMueLimit` objects:
    ```python
    mues = {
        "31020": AscMueLimit(code="31020", mue_limit=1, up_to_limit=True)
    }
    ```
-   **`claim.additional_data["cbsa"]`**: A string CBSA code (e.g., `"35660"`) used for geographic adjustment if provider data is unavailable.

## Data Structure

Data is stored in `myelin/pricers/asc/data/{Year}/{Quarter}/`:

-   `AA.csv`: Covered Surgical Procedures (Rates, Indicators).
-   `BB.csv`: Ancillary Services (Radiology, Drugs).
-   `FF.csv`: Device Offset amounts.
-   `../wage_index.{csv,txt}`: Year-specific Wage Index files.
-   `normalized/`: Normalized Code Pair files for device-intensive logic.

## Reporting & Exports

The results can be exported directly to Excel using `MyelinOutput.to_excel()`:
```python
output = myelin.process(claim)
output.to_excel("results.xlsx", claim=claim)
```
The exporter includes a dedicated **ASC** sheet with line-level details and specific callouts for MUE denials and ancillary status.

## Testing

Comprehensive testing is available:
-   `tests/pricers/test_asc_mue.py`: Dedicated tests for MUE unit caps and enforcement modes.
-   `tests/pricers/test_asc_all_years.py`: Verifies loading of all data years (2021-2026).
-   `tests/pricers/test_asc_integration.py`: End-to-end logic and integration verification.
-   `tests/pricers/test_asc_wage_index_all_years.py`: Verifies Wage Index lookup for all years.
