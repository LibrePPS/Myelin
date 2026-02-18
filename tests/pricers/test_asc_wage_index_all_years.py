import os
import sys
import unittest
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from myelin.pricers.asc.data_loader import AscReferenceData


class TestAscWageIndexAllYears(unittest.TestCase):
    def setUp(self):
        self.data_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../myelin/pricers/asc/data")
        )
        self.loader = AscReferenceData(self.data_dir)

    def test_2021_wage_index(self):
        # 2021 has wage_index.txt
        # Expecting WI21 column.
        # CBSA 01 (ALABAMA) -> 0.6724
        data = self.loader.get_data(datetime(2021, 1, 15))
        self.assertIn("wage_indices", data)
        self.assertIn("01", data["wage_indices"])
        self.assertAlmostEqual(data["wage_indices"]["01"], 0.6724, places=4)

    def test_2022_wage_index(self):
        # 2022
        data = self.loader.get_data(datetime(2022, 1, 15))
        self.assertIn("wage_indices", data)
        self.assertGreater(len(data["wage_indices"]), 0)

    def test_2023_wage_index(self):
        # 2023
        data = self.loader.get_data(datetime(2023, 1, 15))
        self.assertIn("wage_indices", data)
        self.assertGreater(len(data["wage_indices"]), 0)

    def test_2024_wage_index(self):
        # 2024
        data = self.loader.get_data(datetime(2024, 1, 15))
        self.assertIn("wage_indices", data)
        self.assertGreater(len(data["wage_indices"]), 0)

    def test_2025_wage_index(self):
        # 2025 - wage_index.txt
        # CBSA 02 (ALASKA) -> 1.1396
        data = self.loader.get_data(datetime(2025, 1, 15))
        self.assertIn("wage_indices", data)
        self.assertIn("02", data["wage_indices"])
        self.assertAlmostEqual(data["wage_indices"]["02"], 1.1396, places=4)

    def test_2026_wage_index(self):
        # 2026 - wage_index.csv
        # CBSA 02 (ALASKA) -> 1.1274
        data = self.loader.get_data(datetime(2026, 6, 1))
        self.assertIn("wage_indices", data)
        self.assertIn("02", data["wage_indices"])
        self.assertAlmostEqual(data["wage_indices"]["02"], 1.1274, places=4)


if __name__ == "__main__":
    unittest.main()
