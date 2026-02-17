import os
import shutil
import sys
import tempfile
import pickle
import time
import unittest
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from myelin.pricers.asc.data_loader import AscReferenceData


class TestAscCaching(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.asc_data_dir = os.path.join(self.test_dir, "myelin/pricers/asc/data")
        os.makedirs(self.asc_data_dir)

        # Quarter dir
        self.q_dir = os.path.join(self.asc_data_dir, "2025", "20250101")
        os.makedirs(self.q_dir)

        # Create minimal valid CSVs
        self._create_csv(
            os.path.join(self.q_dir, "AA.csv"),
            [
                "HCPCS Code,Short Descriptor,Subject to Multiple Procedure Discounting,January 2025 Payment Indicator,January 2025 Payment Rate",
                "10001,Test,Y,A2,$100.00",
            ],
        )
        self._create_csv(os.path.join(self.q_dir, "BB.csv"), [])
        self._create_csv(os.path.join(self.q_dir, "FF.csv"), [])
        self._create_csv(
            os.path.join(self.q_dir, "wage_index.csv"), ["CBSA,Wage Index", "10000,1.0"]
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_csv(self, path, lines):
        with open(path, "w") as f:
            f.write("\n".join(lines))

    def test_cache_creation_and_usage(self):
        loader = AscReferenceData(self.asc_data_dir)
        cache_path = os.path.join(self.q_dir, "data.pkl")

        # 1. Ensure no cache initially
        self.assertFalse(os.path.exists(cache_path))

        # 2. First Load - Should create cache
        loader.get_data(datetime(2025, 1, 15))
        self.assertTrue(
            os.path.exists(cache_path), "Cache file data.pkl should be created"
        )

        # 3. Modify Cache manually to prove it's being used
        with open(cache_path, "rb") as f:
            cached_data = pickle.load(f)

        # Inject a fake rate
        cached_data["rates"]["99999"] = {
            "rate": 999.0,
            "indicator": "XX",
            "subject_to_discount": False,
        }
        with open(cache_path, "wb") as f:
            pickle.dump(cached_data, f)

        # 4. Second Load - Should see hacked data
        # Only if cache timestamp > csv timestamp.
        # We just wrote to cache, so it should be newer.
        loader_new = AscReferenceData(self.asc_data_dir)
        data2 = loader_new.get_data(datetime(2025, 1, 15))

        self.assertIn("99999", data2["rates"], "Should load modified data from cache")
        self.assertEqual(data2["rates"]["99999"]["rate"], 999.0)

    def test_cache_invalidation(self):
        loader = AscReferenceData(self.asc_data_dir)
        cache_path = os.path.join(self.q_dir, "data.pkl")
        csv_path = os.path.join(self.q_dir, "AA.csv")

        # 1. Create cache
        loader.get_data(datetime(2025, 1, 15))
        self.assertTrue(os.path.exists(cache_path))

        # 2. Update CSV to be newer than cache
        time.sleep(1.1)  # Ensure filesystem mtime difference
        self._create_csv(
            csv_path,
            [
                "HCPCS Code,Short Descriptor,Subject to Multiple Procedure Discounting,January 2025 Payment Indicator,January 2025 Payment Rate",
                "10001,Test Updated,Y,A2,$200.00",
            ],
        )

        # 3. Load again - Should ignore cache and reload from CSV (Rate $200)
        loader_new = AscReferenceData(self.asc_data_dir)
        data = loader_new.get_data(datetime(2025, 1, 15))

        self.assertEqual(
            data["rates"]["10001"]["rate"], 200.0, "Should have reloaded from newer CSV"
        )

        # 4. Check cache was updated
        with open(cache_path, "rb") as f:
            new_cache = pickle.load(f)
        self.assertEqual(
            new_cache["rates"]["10001"]["rate"],
            200.0,
            "Cache file should be updated with new data",
        )


if __name__ == "__main__":
    unittest.main()
