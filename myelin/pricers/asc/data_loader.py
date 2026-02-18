import csv
import glob
import os
import pickle
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TypedDict


# Bump this version whenever the structure of AscRefData changes to
# automatically invalidate stale .pkl cache files.
_CACHE_VERSION = 2


class RateInfo(TypedDict):
    """Per-HCPCS rate entry from Addendum AA/BB."""

    rate: float
    indicator: str
    subject_to_discount: bool
    addendum: str  # "AA" (surgical procedure) or "BB" (covered ancillary service)


class CodePairEntry(TypedDict):
    """Single code pair entry linking a device to a procedure."""

    device_modifier: Optional[str]
    procedure_modifier: Optional[str]
    percent_multiplier: float
    effective_date: str
    end_date: str


class AscRefData(TypedDict):
    """Top-level reference data returned by AscReferenceData.get_data()."""

    rates: Dict[str, RateInfo]
    device_offsets: Dict[str, float]
    wage_indices: Dict[str, float]
    code_pairs: Dict[Tuple[str, str], List[CodePairEntry]]
    _cache_version: int


class AscReferenceData:
    """
    Handles loading and caching of ASC reference data (Addendum AA, BB, FF, and Wage Index).
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._cache: Dict[str, AscRefData] = {}
        self._available_quarters: Optional[List[Tuple[datetime, str]]] = None

    def preload_all_data(self):
        """
        Preloads all available ASC reference data into memory.
        This builds an in-memory index of available quarters and populates the cache.
        """
        all_quarters = []
        for y_dir in glob.glob(os.path.join(self.data_dir, "*")):
            if os.path.isdir(y_dir):
                for q_dir in glob.glob(os.path.join(y_dir, "*")):
                    if os.path.isdir(q_dir):
                        try:
                            # Verify folder name pattern YYYYMMDD
                            dirname = os.path.basename(q_dir)
                            q_date = datetime.strptime(dirname, "%Y%m%d")
                            all_quarters.append((q_date, q_dir))
                        except ValueError:
                            continue

        # Sort descending by date
        all_quarters.sort(key=lambda x: x[0], reverse=True)
        self._available_quarters = all_quarters

        # Load data for each quarter
        for _, path in all_quarters:
            self._cache[path] = self._load_quarter_data(path)

    def get_data(self, date: datetime) -> AscRefData:
        """
        Retrieves reference data for the given date.
        If exact quarter is missing, falls back to the latest available quarter
        ONLY if the requested date is in the future relative to available data.
        """
        target_path = self._find_quarter_directory(date)
        if not target_path:
            # Try to force a preload/re-scan if we haven't found anything and preloading wasn't done?
            # Or just raise error. Existing behavior raises error.
            raise FileNotFoundError(f"No ASC data found for {date} or prior quarters.")

        if target_path in self._cache:
            return self._cache[target_path]

        data = self._load_quarter_data(target_path)
        self._cache[target_path] = data
        return data

    def _find_quarter_directory(self, date: datetime) -> Optional[str]:
        """
        Finds the specific data directory for the date's quarter.
        Uses in-memory index if available, otherwise checks filesystem.
        """
        # Calculate target quarter start date
        year = date.year
        quarter_month = ((date.month - 1) // 3) * 3 + 1
        target_date = datetime(year, quarter_month, 1)

        # FAST PATH: Use preloaded index
        if self._available_quarters is not None:
            # 1. Look for exact match
            for q_date, q_path in self._available_quarters:
                if q_date == target_date:
                    return q_path

            # 2. Check if requested date is AFTER the latest available data
            if self._available_quarters:
                latest_date, latest_path = self._available_quarters[0]
                if date > latest_date:
                    return latest_path

            return None

        # SLOW PATH: Filesystem check (Legacy/On-demand)
        target_folder_name = f"{year}{quarter_month:02d}01"

        # Check specific path first
        year_dir = os.path.join(self.data_dir, str(year))
        specific_path = os.path.join(year_dir, target_folder_name)

        if os.path.exists(specific_path):
            return specific_path

        # If not found, look for latest available
        # Flatten all year/quarter directories to find the absolute latest
        all_quarters = []
        for y_dir in glob.glob(os.path.join(self.data_dir, "*")):
            if os.path.isdir(y_dir):
                for q_dir in glob.glob(os.path.join(y_dir, "*")):
                    if os.path.isdir(q_dir):
                        try:
                            q_date = datetime.strptime(
                                os.path.basename(q_dir), "%Y%m%d"
                            )
                            all_quarters.append((q_date, q_dir))
                        except ValueError:
                            continue

        if not all_quarters:
            return None

        all_quarters.sort(key=lambda x: x[0], reverse=True)
        latest_date, latest_path = all_quarters[0]

        # If requested date is after the latest available date, utilize the latest
        if date > latest_date:
            return latest_path

        return None

    def _load_quarter_data(self, path: str) -> AscRefData:
        """
        Loads data from the specified directory.
        Checks for a binary cache file (data.pkl) first.
        If cache exists and is newer than CSVs, load it.
        Otherwise, load CSVs and update cache.
        """
        cache_path = os.path.join(path, "data.pkl")

        # 1. Try Loading from Cache
        if self._is_cache_valid(path, cache_path):
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except (EOFError, pickle.UnpicklingError, Exception):
                # If cache is corrupt, ignore and reload from source
                pass

        # 2. Load from CSVs
        data: AscRefData = {
            "rates": {},
            "device_offsets": {},
            "wage_indices": {},
            "code_pairs": {},
            "_cache_version": _CACHE_VERSION,
        }

        # Load Rates (AA = surgical procedures, BB = covered ancillary services)
        # BB is loaded second so that if a code appears in both, BB wins.
        self._load_rates(self._find_file(path, "AA"), data["rates"], addendum="AA")
        self._load_rates(self._find_file(path, "BB"), data["rates"], addendum="BB")

        # Load Device Offsets (FF)
        self._load_device_offsets(self._find_file(path, "FF"), data["device_offsets"])

        # Load Code Pairs (from normalized directory)
        self._load_code_pairs(path, data["code_pairs"])

        # Load Wage Index
        # New requirement: check year directory for wage_index.csv or wage_index.txt
        year_dir = os.path.dirname(path)
        wi_path = self._find_file(year_dir, "wage_index")

        # Fallback to old behavior if not found? User said "rework... to ensure we have test...".
        # Let's support both just in case, but prioritize the new one.
        if os.path.exists(wi_path):
            self._load_wage_index(wi_path, data["wage_indices"])
        else:
            # Legacy fallbacks
            wi_files = glob.glob(os.path.join(path, "*wage*.csv"))
            if not wi_files:
                wi_files = glob.glob(os.path.join(path, "WI.csv"))

            if not wi_files:
                wi_files = glob.glob(os.path.join(year_dir, "*wage*.csv"))
                if not wi_files:
                    wi_files = glob.glob(os.path.join(year_dir, "WI.csv"))

            if wi_files:
                self._load_wage_index(wi_files[0], data["wage_indices"])

        # 3. Save to Cache
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(data, f)
        except Exception:
            # If write fails (permissions etc), just continue
            pass

        return data

    def _is_cache_valid(self, dir_path: str, cache_path: str) -> bool:
        """
        Returns True if cache file exists, matches the current cache version,
        and is newer than all CSV/TXT files in the directory and the normalized
        code pairs directory.
        """
        if not os.path.exists(cache_path):
            return False

        # Check cache version before checking mtimes
        try:
            with open(cache_path, "rb") as f:
                import pickle as _pickle

                cached = _pickle.load(f)
            if cached.get("_cache_version") != _CACHE_VERSION:
                return False
        except Exception:
            return False

        cache_mtime = os.path.getmtime(cache_path)

        # Check all data files in the quarter directory
        for ext in ["*.csv", "*.txt"]:
            for f in glob.glob(os.path.join(dir_path, ext)):
                if os.path.getmtime(f) > cache_mtime:
                    return False

        # Also check the normalized code pairs directory for changes
        # The path is like "data/2026/20260101", normalized is at "data/normalized"
        data_root = os.path.dirname(os.path.dirname(dir_path))
        normalized_dir = os.path.join(data_root, "normalized")
        if os.path.exists(normalized_dir):
            # Check year-specific file
            path_basename = os.path.basename(dir_path)  # e.g., "20260101"
            if path_basename.isdigit() and len(path_basename) == 8:
                year = path_basename[:4]
                year_file = os.path.join(normalized_dir, f"code_pairs_{year}.csv")
                if os.path.exists(year_file):
                    if os.path.getmtime(year_file) > cache_mtime:
                        return False
                # Also check combined file
                combined_file = os.path.join(normalized_dir, "code_pairs_combined.csv")
                if os.path.exists(combined_file):
                    if os.path.getmtime(combined_file) > cache_mtime:
                        return False

        return True

    def _find_file(self, directory: str, basename: str) -> str:
        """Finds a file with .csv or .txt extension."""
        for ext in [".csv", ".txt"]:
            path = os.path.join(directory, f"{basename}{ext}")
            if os.path.exists(path):
                return path
        return os.path.join(directory, f"{basename}.csv")  # Default fallback

    def _load_rates(
        self, filepath: str, rates_dict: Dict[str, Any], addendum: str = "AA"
    ):
        if not os.path.exists(filepath):
            return

        reader = self._get_reader(filepath, ["HCPCS Code"])
        if not reader:
            return

        for row in reader:
            hcpcs = row.get("HCPCS Code") or row.get("HCPCS")
            if not hcpcs:
                continue

            # Flexible Column Mapping
            rate = 0.0
            ind = ""
            sub_discount = "N"

            for k, v in row.items():
                if not k:
                    continue
                k_lower = k.lower()

                # Payment Rate
                if "payment rate" in k_lower:
                    rate = self._parse_currency(v)

                # Payment Indicator
                elif "payment indicator" in k_lower or "comment indicator" in k_lower:
                    ind = v

                # Discounting
                elif "discounting" in k_lower:
                    sub_discount = v

            rates_dict[hcpcs] = {
                "rate": rate,
                "indicator": ind,
                "subject_to_discount": sub_discount.upper() == "Y",
                "addendum": addendum,
            }

    def _load_device_offsets(self, filepath: str, offsets_dict: Dict[str, Any]):
        if not os.path.exists(filepath):
            return

        reader = self._get_reader(filepath, ["HCPCS Code"])
        if not reader:
            return

        for row in reader:
            hcpcs = row.get("HCPCS Code") or row.get("HCPCS")
            if not hcpcs:
                continue

            offset = 0.0
            for k, v in row.items():
                if k and "device offset amount" in k.lower():
                    offset = self._parse_currency(v)
                    break

            if offset > 0:
                offsets_dict[hcpcs] = offset

    def _load_code_pairs(
        self, path: str, code_pairs_dict: Dict[Tuple[str, str], List[CodePairEntry]]
    ):
        """
        Load code pair data from normalized CSV files.

        The code_pairs_dict is keyed by (device_hcpcs, procedure_hcpcs) tuple
        with value being a list of entries containing:
        - device_modifier: Optional[str]
        - procedure_modifier: Optional[str]
        - percent_multiplier: float
        - effective_date: str
        - end_date: str
        """
        # Look for normalized code pair files in the data directory
        # The path is like "data/2026/20260101", normalized is at "data/normalized"
        # We need to go up two levels from the quarter path
        data_root = os.path.dirname(os.path.dirname(path))
        normalized_dir = os.path.join(data_root, "normalized")

        # Try to find year-specific file first based on the path
        path_basename = os.path.basename(path)  # e.g., "20240101"
        if path_basename.isdigit() and len(path_basename) == 8:
            year = path_basename[:4]
            year_file = os.path.join(normalized_dir, f"code_pairs_{year}.csv")
            if os.path.exists(year_file):
                self._load_code_pairs_file(year_file, code_pairs_dict)
                return

        # Fallback: try combined file
        combined_file = os.path.join(normalized_dir, "code_pairs_combined.csv")
        if os.path.exists(combined_file):
            self._load_code_pairs_file(combined_file, code_pairs_dict)

    def _load_code_pairs_file(
        self, filepath: str, code_pairs_dict: Dict[Tuple[str, str], List[CodePairEntry]]
    ):
        """Load a single code pairs CSV file."""
        if not os.path.exists(filepath):
            return

        reader = self._get_reader(filepath, ["device_hcpcs"])
        if not reader:
            return

        for row in reader:
            device_hcpcs = row.get("device_hcpcs", "").strip()
            procedure_hcpcs = row.get("procedure_hcpcs", "").strip()

            if not device_hcpcs or not procedure_hcpcs:
                continue

            # Parse percent multiplier
            percent_str = row.get("percent_multiplier", "0").strip()
            try:
                percent_multiplier = float(percent_str) if percent_str else 0.0
            except ValueError:
                percent_multiplier = 0.0

            entry: CodePairEntry = {
                "device_modifier": row.get("device_modifier", "").strip() or None,
                "procedure_modifier": row.get("procedure_modifier", "").strip() or None,
                "percent_multiplier": percent_multiplier,
                "effective_date": row.get("effective_date", "").strip(),
                "end_date": row.get("end_date", "").strip(),
            }

            # Key by (device_hcpcs, procedure_hcpcs)
            key = (device_hcpcs, procedure_hcpcs)
            if key not in code_pairs_dict:
                code_pairs_dict[key] = []
            code_pairs_dict[key].append(entry)

    def _load_wage_index(self, filepath: str, wi_dict: Dict[str, float]):
        if not os.path.exists(filepath):
            return

        reader = self._get_reader(filepath, ["CBSA"])
        if not reader:
            return

        # Determine the WI column name dynamically
        # It's usually WI + 2-digit year (e.g., WI26, WI25, WI21)
        # We can scan the fieldnames on the reader if available or row keys
        wi_col = None
        if reader.fieldnames:
            for field in reader.fieldnames:
                if (
                    field
                    and field.upper().startswith("WI")
                    and len(field) == 4
                    and field[2:].isdigit()
                ):
                    wi_col = field
                    break

        # Fallback if fieldnames not set or found (e.g. DictReader without clear header if sniffing failed slightly differently)
        # But _get_reader sets fieldnames.

        for row in reader:
            # CMS files often have keys like 'cbsa' or 'CBSA'
            cbsa = row.get("CBSA") or row.get("cbsa")
            # Sometimes CBSA might be "CBSA No." or similar
            if not cbsa:
                for k in row.keys():
                    if k and "CBSA" in k.upper():
                        cbsa = row[k]
                        break

            if not cbsa:
                continue

            wi_str = None
            if wi_col and row.get(wi_col):
                wi_str = row.get(wi_col)
            else:
                # Try finding a WIxx column in the row
                for k in row.keys():
                    if (
                        k
                        and k.upper().startswith("WI")
                        and len(k) == 4
                        and k[2:].isdigit()
                    ):
                        wi_str = row[k]
                        break

            if not wi_str:
                wi_str = row.get("Wage Index") or row.get("geographicWageIndex")

            if cbsa and wi_str:
                try:
                    wi_dict[cbsa] = float(wi_str)
                except ValueError:
                    pass

    def _get_reader(
        self, filepath: str, header_keywords: list[str]
    ) -> Optional[csv.DictReader]:
        """
        Scans parsing header line detecting known keywords.
        Supports CSV and TSV sniffing.
        """
        try:
            f = open(filepath, "r", encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return None

        # Scan for header
        header_line = None
        delimiter = ","  # default

        while True:
            line = f.readline()
            if not line:
                break

            # Check if this line looks like a header
            # We check if *any* of the keywords appear
            found = False
            for kw in header_keywords:
                if kw in line:
                    found = True
                    break

            if found:
                header_line = line
                # Sniff delimiter
                if "\t" in line:
                    delimiter = "\t"
                break

        if not header_line:
            f.close()
            return None

        # Check for tab vs comma if not decided
        # Sometimes a CSV line might have tabs in quotes, so simple check isn't perfect but usually file-wide.
        # If it's a .txt usually TSV, .csv usually comma.
        if filepath.endswith(".txt") and "\t" in header_line:
            delimiter = "\t"

        # Construct DictReader
        # We need to parse the header line properly to get fieldnames
        # Standard csv reader can do this
        fieldnames = next(csv.reader([header_line], delimiter=delimiter))

        return csv.DictReader(f, fieldnames=fieldnames, delimiter=delimiter)

    def _parse_currency(self, value: str) -> float:
        if not value:
            return 0.0
        try:
            return float(
                value.replace("$", "").replace(",", "").replace('"', "").strip()
            )
        except ValueError:
            return 0.0
