import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from myelin.core import Myelin
from myelin.input.claim import Claim, LineItem, Modules
from myelin.pricers.asc.client import AscClient


class TestAscIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.asc_data_dir = os.path.join(self.test_dir, "myelin/pricers/asc/data")
        os.makedirs(self.asc_data_dir)

        # Create structure: 2025/20250101
        self.q1_2025 = os.path.join(self.asc_data_dir, "2025", "20250101")
        os.makedirs(self.q1_2025)

        # Create dummy data files
        # Rate: $100. WI: 1.0. Device Offset: $20.
        self._create_csv(
            os.path.join(self.q1_2025, "AA.csv"),
            [
                "HCPCS Code,Short Descriptor,Subject to Multiple Procedure Discounting,January 2025 Payment Indicator,January 2025 Payment Rate",
                "10001,Test Proc 1,Y,A2,$100.00",
                "10002,Test Proc 2,N,G2,$50.00",
                "10003,Test Device Proc,Y,J8,$100.00",
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
                "HCPCS Code,Short Descriptor,Indicator,APC,Offset %,OPPS Rate,Offset %,Device Offset Amount",
                "10001,Test Proc 1,J8,123,0.5,200.00,50%,$20.00",
                "10003,Test Device Proc,J8,123,0.5,200.00,30%,$30.00",
            ],
        )

        self._create_csv(
            os.path.join(self.q1_2025, "wage_index.csv"),
            ["CBSA,Wage Index", "10000,1.5"],
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_csv(self, path, lines):
        with open(path, "w") as f:
            f.write("\n".join(lines))

    @patch("myelin.core.DatabaseManager")
    @patch("myelin.core.OPSFProvider")
    @patch("myelin.core.Myelin._setup_jvm")  # Prevent JVM startup
    def test_asc_pricing_flow(
        self, MockSetupJvm, MockOPSFProvider, MockDatabaseManager
    ):
        # Setup Myelin with mocked DB
        myelin = Myelin(build_db=False, build_jar_dirs=False)
        myelin.db_manager.engine = MagicMock()

        # Mock IOCE Client to avoid "client not initialized" error
        myelin.ioce_client = MagicMock()
        myelin.ioce_client.process.return_value = (None, None)  # Mock output if needed

        # Inject our temp data dir into the client
        data_loader_path = self.asc_data_dir
        myelin.asc_client = AscClient(data_loader_path, myelin.logger)

        # Configure Mock OPSFProvider instance
        mock_opsf_instance = MockOPSFProvider.return_value
        mock_opsf_instance.cbsa_wage_index_location = "10000"  # WI = 1.5
        mock_opsf_instance.provider_type = "ASC"

        # Create Claim
        claim = Claim(
            bill_type="831",  # Triggers ASC
            from_date=datetime(2025, 1, 15),
            thru_date=datetime(2025, 1, 15),
            modules=[Modules.AUTO],
            lines=[
                LineItem(
                    line_number=1,
                    hcpcs="10001",
                    units=1,
                    modifiers=["FB"],
                    revenue_code="0490",
                ),  # Device Credit!
                LineItem(line_number=2, hcpcs="10002", units=1, revenue_code="0490"),
            ],
        )

        # Run Process
        result = myelin.process(claim)

        # Assertions
        self.assertIsNotNone(result.asc)
        self.assertIsNone(result.error)

        # Verify Payment
        # Line 1: Rate 100. WI 1.5. 50% Labor Share.
        # Adjusted = (100 * 0.5 * 1.5) + (100 * 0.5) = 75 + 50 = 125.
        # Device Offset: "FB" modifier present. Offset in FF is $20.
        # Final Line 1 = 125 - 20 = 105.

        # Line 2: Rate 50. WI 1.5.
        # Adjusted = (50 * 0.5 * 1.5) + (50 * 0.5) = 37.5 + 25 = 62.5.
        # Not subject to discount (N in AA).

        # Total = 105 + 62.5 = 167.5

        self.assertEqual(len(result.asc.lines), 2)

        # Find lines
        l1 = next(h for h in result.asc.lines if h.hcpcs == "10001")
        l2 = next(g for g in result.asc.lines if g.hcpcs == "10002")

        self.assertAlmostEqual(l1.adjusted_rate, 105.0)
        self.assertTrue(l1.device_credit)
        self.assertEqual(l1.device_offset_amount, 20.0)

        self.assertAlmostEqual(l2.adjusted_rate, 62.5)

        self.assertAlmostEqual(result.asc.total_payment, 167.5)


        self.assertAlmostEqual(result.asc.total_payment, 167.5)

    @patch("myelin.core.DatabaseManager")
    @patch("myelin.core.OPSFProvider")
    @patch("myelin.core.Myelin._setup_jvm")
    def test_asc_modifiers(self, MockSetupJvm, MockOPSFProvider, MockDatabaseManager):
        # Setup
        myelin = Myelin(build_db=False, build_jar_dirs=False)
        myelin.db_manager.engine = MagicMock()
        myelin.ioce_client = MagicMock()
        myelin.ioce_client.process.return_value = (None, None)
        myelin.asc_client = AscClient(self.asc_data_dir, myelin.logger)
        
        mock_opsf = MockOPSFProvider.return_value
        mock_opsf.cbsa_wage_index_location = "10000" # WI = 1.5
        mock_opsf.provider_type = "ASC"

        # Rate 10003 = $100. WI=1.5. Labor=50%.
        # Adj Rate = (100 * 0.5 * 1.5) + (100 * 0.5) = 75 + 50 = 125.0
        # Device Offset = $30.

        # 1. Test Modifier 73 (Terminated Pre-Anesthesia)
        # Rule: (Adj Rate - Full Offset) * 50%
        # (125 - 30) * 0.5 = 95 * 0.5 = 47.5
        
        # 2. Test Modifier 52 (Reduced)
        # Rule: Adj Rate * 50%
        # 125 * 0.5 = 62.5
        
        # 3. Test Modifier 74 (Terminated Post-Anesthesia)
        # Rule: Full Payment (125.0).
        
        claim = Claim(
            bill_type="831",
            from_date=datetime(2025, 1, 15),
            thru_date=datetime(2025, 1, 15),
            modules=[Modules.AUTO],
            lines=[
                LineItem(line_number=1, hcpcs="10003", units=1, modifiers=["73"], revenue_code="0490"),
                LineItem(line_number=2, hcpcs="10003", units=1, modifiers=["52"], revenue_code="0490"),
                LineItem(line_number=3, hcpcs="10003", units=1, modifiers=["74"], revenue_code="0490"),
            ]
        )
        
        result = myelin.process(claim)
        
        self.assertIsNotNone(result.asc)
        l1 = result.asc.lines[0] # 73
        l2 = result.asc.lines[1] # 52
        l3 = result.asc.lines[2] # 74
        
        self.assertAlmostEqual(l1.adjusted_rate, 47.5)
        self.assertFalse(l1.subject_to_discount, "Mod 73 should be exempt from MPR")
        
        self.assertAlmostEqual(l2.adjusted_rate, 62.5)
        self.assertFalse(l2.subject_to_discount, "Mod 52 should be exempt from MPR")
        
        self.assertAlmostEqual(l3.adjusted_rate, 125.0)
        # 74 is subject to discount? 10003 has "Y" ind.
        # But it's the only one left in the discount pool (others are exempt).
        # So it pays 100%.
        self.assertAlmostEqual(result.asc.total_payment, 47.5 + 62.5 + 125.0) 

if __name__ == "__main__":
    unittest.main()
