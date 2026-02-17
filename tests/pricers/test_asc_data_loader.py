import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from myelin.pricers.asc.data_loader import AscReferenceData


class TestAscReferenceData(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # Create a mock data structure inside temp dir
        self.asc_data_dir = os.path.join(self.test_dir, "myelin/pricers/asc/data")
        os.makedirs(self.asc_data_dir)

        # Create structure: 2025/20250101
        self.q1_2025 = os.path.join(self.asc_data_dir, "2025", "20250101")
        os.makedirs(self.q1_2025)

        # Create dummy data files
        self._create_csv(
            os.path.join(self.q1_2025, "AA.csv"),
            [
                "HCPCS Code,Short Descriptor,Subject to Multiple Procedure Discounting,January 2025 Payment Indicator,January 2025 Payment Rate",
                "10001,Test Proc 1,Y,A2,$100.00",
                "10002,Test Proc 2,N,G2,$50.50",
            ],
        )

        self._create_csv(
            os.path.join(self.q1_2025, "BB.csv"),
            [
                "HCPCS Code,Short Descriptor,Drug Pass-Through,January 2025 Payment Indicator,January 2025 Payment Rate",
                "J9000,Test Drug,N,K2,$10.00",
            ],
        )

        self._create_csv(
            os.path.join(self.q1_2025, "FF.csv"),
            [
                "HCPCS Code,Short Descriptor,Indicator,APC,Offset %,OPPS Rate,Offset %,Device Offset Amount / Device Portion",
                "10001,Test Proc 1,J8,123,0.5,200.00,50%,$40.00",
            ],
        )

        self._create_csv(
            os.path.join(self.q1_2025, "wage_index.csv"),
            ["CBSA,Wage Index", "35614,1.25", "10000,0.85"],
        )

        # Create a "wage_index_legacy.csv" scenario helper
        # Not needed if main test covers wage_index.csv logic

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_csv(self, path, lines):
        with open(path, "w") as f:
            f.write("\n".join(lines))

    def test_load_exact_quarter(self):
        loader = AscReferenceData(self.asc_data_dir)
        data = loader.get_data(datetime(2025, 2, 15))

        # Check Rates
        self.assertIn("10001", data["rates"])
        self.assertEqual(data["rates"]["10001"]["rate"], 100.00)
        self.assertEqual(data["rates"]["10001"]["indicator"], "A2")
        self.assertTrue(data["rates"]["10001"]["subject_to_discount"])

        # Check BB rates
        self.assertIn("J9000", data["rates"])
        self.assertEqual(data["rates"]["J9000"]["rate"], 10.00)
        self.assertEqual(data["rates"]["J9000"]["indicator"], "K2")

        # Check Device Offsets
        self.assertIn("10001", data["device_offsets"])
        self.assertEqual(data["device_offsets"]["10001"], 40.00)

        # Check Wage Index
        self.assertEqual(data["wage_indices"]["35614"], 1.25)

    def test_fallback_to_latest(self):
        # Request 2026 date, should fallback to 2025 data
        loader = AscReferenceData(self.asc_data_dir)
        data = loader.get_data(datetime(2026, 6, 1))

        self.assertIsNotNone(data)
        self.assertIn("10001", data["rates"])

    def test_missing_historical_date(self):
        # Request 2024 date, should be FileNotFoundError
        loader = AscReferenceData(self.asc_data_dir)
        with self.assertRaises(FileNotFoundError):
            loader.get_data(datetime(2024, 1, 1))

    def test_wage_index_in_year_directory(self):
        # Setup: Q2 2025 has rates but NO wage index in quarter dir
        q2_2025 = os.path.join(self.asc_data_dir, "2025", "20250401")
        os.makedirs(q2_2025)
        
        self._create_csv(os.path.join(q2_2025, "AA.csv"), ["HCPCS Code", "10001"]) # Min valid
        self._create_csv(os.path.join(q2_2025, "BB.csv"), [])
        self._create_csv(os.path.join(q2_2025, "FF.csv"), [])
        
        # Place Wage Index in Year Dir (2025/)
        year_dir = os.path.join(self.asc_data_dir, "2025")
        self._create_csv(
            os.path.join(year_dir, "cbsa-wage-index-2025.csv"),
            ["CBSA,Wage Index", "99999,2.0"]
        )
        
        loader = AscReferenceData(self.asc_data_dir)
        data = loader.get_data(datetime(2025, 5, 1)) # Q2
        
        self.assertIn("99999", data["wage_indices"])
        self.assertEqual(data["wage_indices"]["99999"], 2.0)

if __name__ == "__main__":
    unittest.main()
