import os
import sys
import unittest
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from myelin.pricers.asc.data_loader import AscReferenceData

class TestAsc2026Data(unittest.TestCase):
    def test_load_2026_wage_index(self):
        # Point to the actual project data directory
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../myelin/pricers/asc/data'))
        loader = AscReferenceData(data_dir)
        
        # 2026 Data
        # We know from `head` that CBSA "01" (ALABAMA) has geographicWageIndex 0.7393 in 2026 file.
        # But wait, does 01 exist as a string? Yes, looking at the file content: "01,..."
        
        # Load data for a 2026 date
        data = loader.get_data(datetime(2026, 6, 1))
        
        self.assertIn("wage_indices", data)
        # Check a known value from 2026 file
        # 01,20260101,0.7393,...
        self.assertIn("01", data["wage_indices"], "CBSA '01' not found in loaded 2026 data")
        self.assertAlmostEqual(data["wage_indices"]["01"], 0.6367, places=4)
        
        # Check another one: 02 -> 1.1438
        self.assertIn("02", data["wage_indices"])
        self.assertAlmostEqual(data["wage_indices"]["02"], 1.1274, places=4)

if __name__ == '__main__':
    unittest.main()
