"""
ASC Code Pair File Normalizer

Converts disparate CMS Code Pair file formats into a common layout for use in the ASC Pricer.

File Format Evolution:
- 2022-2023: Legacy format with modifier columns (Device HCPCS Modifier, ASC Procedure HCPCS Modifier)
- 2024+:    New format with date ranges (Effective Date, End Date) and no modifier columns

Output: A normalized CSV file that can be loaded by data_loader.py
"""

import csv
import os
from typing import Dict, List, Optional
from dataclasses import dataclass


# Source file mapping: (filename_pattern, format_type, year_coverage)
# Format types: "legacy" (2022-2023) or "new" (2024+)
SOURCE_FILES = [
    # Legacy format (2022-2023) - uses Year column, has modifier columns
    (
        "508-Version-of-January_2022_ASC_Code_Pair_File_revised_09.06.22.csv",
        "legacy",
        "2022",
    ),
    (
        "Section 508 version of July_2023_ASC_Code_Pair_File.06122023.csv",
        "legacy",
        "2023",
    ),
    # New format (2024+) - uses Effective Date/End Date, no modifier columns
    (
        "Section 508 version of January_2024_ASC_Code_Pair_File.12112024.txt",
        "new",
        "2024",
    ),
    ("508_Version_April_2024_ASC_Code_Pair_File.03262024.csv", "new", "2024"),
    ("July_2024_ASC_Code_Pair_File.06142024.csv", "new", "2024"),
    ("508-Version-Oct-2024-ASC-Code-Pair-File.csv", "new", "2024"),
    ("508 Version of January 2025 ASC Code Pair File.csv", "new", "2025"),
    ("508 Version of January 2026 ASC Code Pair File.csv", "new", "2026"),
]

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data", "normalized")


@dataclass
class CodePairEntry:
    """Normalized code pair entry."""

    device_hcpcs: str
    procedure_hcpcs: str
    device_modifier: Optional[str]
    procedure_modifier: Optional[str]
    percent_multiplier: float
    effective_date: str
    end_date: str


def normalize_legacy_row(row: Dict[str, str]) -> List[CodePairEntry]:
    """
    Process legacy format (2022-2023) rows.

    Legacy format columns:
    - Device HCPCS, Device HCPCS Modifier, Procedure HCPCS, ASC Procedure HCPCS Modifier,
      Procedure Percent Multiplier, Year

    The Year column represents the start of the calendar year (YYYYMMDD).
    """
    entries = []

    # Extract and clean fields
    device_hcpcs = row.get("Device HCPCS", "").strip()
    device_modifier = row.get("Device HCPCS Modifier", "").strip() or None
    procedure_hcpcs = row.get("Procedure HCPCS", "").strip()
    procedure_modifier = row.get("ASC Procedure HCPCS Modifier", "").strip() or None
    percent_str = row.get("Procedure Percent Multiplier", "0").strip()
    year_str = row.get("Year", "").strip()

    if not device_hcpcs or not procedure_hcpcs:
        return []

    try:
        percent_multiplier = float(percent_str) if percent_str else 0.0
    except ValueError:
        percent_multiplier = 0.0

    # Legacy format: Year is YYYYMMDD representing start of calendar year
    # Effective date is the Year value, end date is Dec 31 of that year
    if year_str and len(year_str) == 8:
        effective_date = year_str
        end_date = year_str[:4] + "1231"  # End of calendar year
    else:
        # Fallback - use a reasonable date range
        effective_date = "20220101"
        end_date = "20221231"

    entry = CodePairEntry(
        device_hcpcs=device_hcpcs,
        procedure_hcpcs=procedure_hcpcs,
        device_modifier=device_modifier,
        procedure_modifier=procedure_modifier,
        percent_multiplier=percent_multiplier,
        effective_date=effective_date,
        end_date=end_date,
    )
    entries.append(entry)

    return entries


def normalize_new_row(row: Dict[str, str]) -> List[CodePairEntry]:
    """
    Process new format (2024+) rows.

    New format columns:
    - Device HCPCS, Procedure HCPCS, Procedure Percent Multiplier, Effective Date, End Date

    No modifier columns - the same device/procedure combo applies to all modifier scenarios.
    """
    # Extract and clean fields
    device_hcpcs = row.get("Device HCPCS", "").strip()
    procedure_hcpcs = row.get("Procedure HCPCS", "").strip()
    percent_str = row.get("Procedure Percent Multiplier", "0").strip()
    effective_date = row.get("Effective Date", "").strip()
    end_date = row.get("End Date", "").strip()

    if not device_hcpcs or not procedure_hcpcs:
        return []

    try:
        percent_multiplier = float(percent_str) if percent_str else 0.0
    except ValueError:
        percent_multiplier = 0.0

    # New format has explicit date ranges
    entry = CodePairEntry(
        device_hcpcs=device_hcpcs,
        procedure_hcpcs=procedure_hcpcs,
        device_modifier=None,  # No modifier column in new format
        procedure_modifier=None,  # No modifier column in new format
        percent_multiplier=percent_multiplier,
        effective_date=effective_date,
        end_date=end_date,
    )

    return [entry]


def detect_delimiter(filepath: str) -> str:
    """Detect if file is comma or tab delimited."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline()
            if "\t" in first_line:
                return "\t"
            return ","
    except Exception:
        return ","


def load_csv(filepath: str, delimiter: str = ",") -> List[Dict[str, str]]:
    """Load CSV/TSV file and return list of row dictionaries."""
    rows = []
    try:
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                # Strip whitespace and BOM from all keys to handle inconsistent column names
                cleaned_row = {
                    k.strip().replace("\ufeff", ""): v for k, v in row.items()
                }
                rows.append(cleaned_row)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
    return rows


def process_file(filepath: str, format_type: str) -> List[CodePairEntry]:
    """Process a single source file and return normalized entries."""
    print(f"Processing: {os.path.basename(filepath)} (format: {format_type})")

    delimiter = detect_delimiter(filepath)
    rows = load_csv(filepath, delimiter)

    all_entries = []
    for row in rows:
        if format_type == "legacy":
            entries = normalize_legacy_row(row)
        else:
            entries = normalize_new_row(row)
        all_entries.extend(entries)

    print(f"  -> {len(all_entries)} entries extracted")
    return all_entries


def write_normalized_output(entries: List[CodePairEntry], output_path: str):
    """Write normalized entries to CSV file."""
    fieldnames = [
        "device_hcpcs",
        "procedure_hcpcs",
        "device_modifier",
        "procedure_modifier",
        "percent_multiplier",
        "effective_date",
        "end_date",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for entry in entries:
            writer.writerow(
                {
                    "device_hcpcs": entry.device_hcpcs,
                    "procedure_hcpcs": entry.procedure_hcpcs,
                    "device_modifier": entry.device_modifier or "",
                    "procedure_modifier": entry.procedure_modifier or "",
                    "percent_multiplier": entry.percent_multiplier,
                    "effective_date": entry.effective_date,
                    "end_date": entry.end_date,
                }
            )

    print(f"Written: {output_path}")


def main():
    """Main entry point for the normalizer."""
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_entries: List[CodePairEntry] = []

    print("=" * 60)
    print("ASC Code Pair File Normalizer")
    print("=" * 60)

    for filename, format_type, year in SOURCE_FILES:
        filepath = os.path.join(DATA_DIR, filename)

        if not os.path.exists(filepath):
            print(f"WARNING: File not found: {filename}")
            continue

        entries = process_file(filepath, format_type)
        all_entries.extend(entries)

    # Sort by effective_date and device_hcpcs for consistent output
    all_entries.sort(
        key=lambda x: (x.effective_date, x.device_hcpcs, x.procedure_hcpcs)
    )

    # Write combined output
    combined_output = os.path.join(OUTPUT_DIR, "code_pairs_combined.csv")
    write_normalized_output(all_entries, combined_output)

    # Also create year-specific files for efficient loading
    # Group entries by year (using effective_date year)
    by_year: Dict[str, List[CodePairEntry]] = {}
    for entry in all_entries:
        year = entry.effective_date[:4]
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(entry)

    for year, year_entries in by_year.items():
        year_output = os.path.join(OUTPUT_DIR, f"code_pairs_{year}.csv")
        write_normalized_output(year_entries, year_output)

    print("=" * 60)
    print(f"Total entries processed: {len(all_entries)}")
    print(f"Years covered: {sorted(by_year.keys())}")
    print("=" * 60)


if __name__ == "__main__":
    main()
