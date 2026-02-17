import os
import sys
import unittest
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from myelin.pricers.asc.data_loader import AscReferenceData

class TestAscDataLoadingAllYears(unittest.TestCase):
    def setUp(self):
        self.data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../myelin/pricers/asc/data'))
        self.loader = AscReferenceData(self.data_dir)

    def test_2021_loading(self):
        # 2021 is TSV
        # 0100T cost $3,475.50
        data = self.loader.get_data(datetime(2021, 1, 15))
        self.assertIn("rates", data)
        self.assertIn("0100T", data["rates"])
        self.assertEqual(data["rates"]["0100T"]["rate"], 3475.50)
        
        # Wage Index for 2021 (from file list: cbsa-wage-index-2021.csv)
        self.assertIn("wage_indices", data)
        self.assertGreater(len(data["wage_indices"]), 0)

    def test_2022_loading(self):
        # 2022 is CSV with quote-wrapped currency "$1,360.34 " for 0101T
        data = self.loader.get_data(datetime(2022, 1, 15))
        self.assertIn("rates", data)
        self.assertIn("0101T", data["rates"])
        self.assertEqual(data["rates"]["0101T"]["rate"], 1360.34)
        
        self.assertIn("wage_indices", data)
        self.assertGreater(len(data["wage_indices"]), 0)

    def test_2023_loading(self):
        # 2023 is CSV with "Jan 2023 Payment Rate"
        # 0101T is $1,414.73
        data = self.loader.get_data(datetime(2023, 1, 15))
        self.assertIn("rates", data)
        self.assertIn("0101T", data["rates"])
        self.assertEqual(data["rates"]["0101T"]["rate"], 1414.73)

    def test_2024_loading(self):
        # 2024 is TXT (TSV likely) with "January 2024 Payment Rate"
        # 0101T is $122.33
        data = self.loader.get_data(datetime(2024, 1, 15))
        self.assertIn("rates", data)
        self.assertIn("0101T", data["rates"])
        self.assertEqual(data["rates"]["0101T"]["rate"], 122.33)

    def test_2025_loading(self):
        # 2025 is CSV (as seen in example.py debugging)
        # 45378 is $489.47
        data = self.loader.get_data(datetime(2025, 1, 15))
        self.assertIn("rates", data)
        self.assertIn("45378", data["rates"])
        self.assertEqual(data["rates"]["45378"]["rate"], 489.47)

    def test_2026_loading(self):
        # 2026 verified in separate test, but good to include here for completeness
        # We need a rate.. 2026 AA file was not head-ed, but let's assume it works if WI works
        data = self.loader.get_data(datetime(2026, 6, 1))
        self.assertIn("wage_indices", data)
        self.assertIn("01", data["wage_indices"])
        self.assertAlmostEqual(data["wage_indices"]["01"], 0.6367, places=4)

if __name__ == '__main__':
    unittest.main()
