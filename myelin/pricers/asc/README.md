# ASC Pricer Implementation

This directory contains the implementation of the ambulatory Surgical Center (ASC) Pricer for Myelin.

## Overview

The ASC Pricer calculates reimbursement rates for ASC claims based on CMS regulations, specifically utilizing the Addendum AA (Covered Surgical Procedures), Addendum BB (Ancillary Services), Addendum FF (Device Intensive Procedures), and Wage Index data.

## Features

-   **Roboust Data Loading**: Automatically detects and parses CMS data files in various formats (CSV, TSV) and structures (Legacy vs New layouts).
-   **Binary Caching**: optimizing startup time by caching parsed reference data in binary `.pkl` files.
-   **Wage Index Support**: Supports year-specific Wage Index files (`wage_index.csv/txt`) and dynamic column mapping (`WI{YY}`).
-   **Complex Pricing Logic**: NOT just a simple lookup. Implements:
    -   **Geographic Adjustment**: Applies labor-share (50%) adjustment using CBSA Wage Indices.
    -   **Device Intensive Logic**: Handles device offsets and credits (Modifiers FB/FC).
    -   **Multiple Procedure Discounting**: Implements standard 100%/50% ranking logic.
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

1.  **Validation**: Ensures `OPSFProvider` is present for Wage Index lookup.
2.  **Reference Data**: Loads data for the Claim's `thru_date` (with fallback to latest available quarter).
3.  **Wage Index**: Determines the Wage Index factor for the provider's CBSA.
4.  **Line Calculation**:
    -   Retrieves Base Rate and Payment Indicator.
    -   Calculates **Adjusted Rate**: `(Rate * 0.5 * WI) + (Rate * 0.5)`.
    -   **Modifier 73**: `(Adjusted Rate - Device Offset) * 0.5`.
    -   **Modifier 52**: `Adjusted Rate * 0.5`.
    -   **Device Credit (FB/FC)**: `Adjusted Rate - Device Offset`.
5.  **Ranking & Discounting** (MPR):
    -   Sorts eligible lines (Ind `Y` or `A2` etc) by Adjusted Rate.
    -   **Primary**: First unit pays 100%. (Subsequent units of primary pay 50%).
    -   **Secondary**: All units pay 50%.
    -   *(Note: Modifiers 73/52 are excluded from this step as they are already reduced).*

## Data Structure

Data is stored in `myelin/pricers/asc/data/{Year}/{Quarter}/`:

-   `AA.csv`: Covered Surgical Procedures (Rates, Indicators).
-   `BB.csv`: Ancillary Services (Radiology, Drugs).
-   `FF.csv`: Device Offset amounts.
-   `../wage_index.{csv,txt}`: Year-specific Wage Index files.
-   `normalized/`: Pre-processed Code Pair files (see below).

### Code Pair Data

Code pair data defines the relationship between device codes and procedure codes for pass-through device pricing. Source files vary by year:

| Year | Source Format |
|------|---------------|
| 2022-2023 | Legacy format with modifier columns (Device HCPCS Modifier, ASC Procedure HCPCS Modifier) |
| 2024+ | New format with date ranges (Effective Date, End Date), no modifier columns |

The normalizer script (`code_pair_normalizer.py`) converts these disparate formats into a unified layout:

```
device_hcpcs,procedure_hcpcs,device_modifier,procedure_modifier,percent_multiplier,effective_date,end_date
```

Normalized files are stored in `myelin/pricers/asc/data/normalized/`:
-   `code_pairs_combined.csv`: All years combined
-   `code_pairs_{YYYY}.csv`: Year-specific files for faster loading

**Note:** 2021 data uses 2022 code pair file as a placeholder since 2021 source files were not available.

## Testing

Comprehensive testing is available:
-   `tests/pricers/test_asc_all_years.py`: Verifies loading of all data years (2021-2026).
-   `tests/pricers/test_asc_wage_index_all_years.py`: Verifies Wage Index lookup for all years.
-   `tests/pricers/test_asc_integration.py`: End-to-end logic verification.
