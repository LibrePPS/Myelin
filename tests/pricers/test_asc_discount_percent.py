import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from myelin.pricers.asc.client import AscLineOutput
from myelin.input.claim import Claim, LineItem
from myelin.pricers.asc.client import AscClient
from decimal import Decimal
from datetime import datetime
from unittest.mock import MagicMock

class TestAscDiscountPercent(unittest.TestCase):
    def test_discount_percent_calculation(self):
        # Create a mock client
        # We can bypass reading from actual csvs if we just inject ref_data directly into process or mock _process_line
        # Alternatively, we can just call AscClient's summation block.
        # It's easiest to mock _process_line to return specific AscLineOutputs, then run just the loop,
        # but the summation logic is deeply embedded in `process`.
        
        client = AscClient(data_dir="/tmp/dummy", preload_data=False)
        
        # We will mock _process_line and validate the end result of process.
        # We need to mock _get_cbsa, get_data
        
        client._get_cbsa = MagicMock()
        client.data_loader.get_data = MagicMock(return_value={"wage_indices": {"10000": 1.0}, "rates": {}, "code_pairs": {}})
        
        # Let's craft a claim
        claim = Claim(
            from_date=datetime(2025, 1, 1),
            thru_date=datetime(2025, 1, 1),
            additional_data={"cbsa": "10000"}
        )
        
        # We will manually set the lines on the claim and their corresponding line outputs
        claim.lines = [
            LineItem(line_number=1, hcpcs="A", units=1), # First procedure, 1 unit
            LineItem(line_number=2, hcpcs="B", units=2), # Second procedure, 2 units (higher rate, so it gets sorted first)
            LineItem(line_number=3, hcpcs="C", units=1), # Third procedure
            LineItem(line_number=4, hcpcs="D", units=1), # Non-discountable
        ]
        
        # B will sort first ($200.0) -> 1 unit @ 100%, 1 unit @ 50%.
        # A will sort second ($100.0) -> 1 unit @ 50%.
        # C will sort third ($50.0) -> 1 unit @ 50%.
        # D is non-discountable ($50.0) -> 1 unit @ 100%.

        out_A = AscLineOutput(line_number=1, hcpcs="A", units=1, adjusted_rate=100.0, subject_to_discount=True, status="payable")
        out_B = AscLineOutput(line_number=2, hcpcs="B", units=2, adjusted_rate=200.0, subject_to_discount=True, status="payable")
        out_C = AscLineOutput(line_number=3, hcpcs="C", units=1, adjusted_rate=50.0, subject_to_discount=True, status="payable")
        out_D = AscLineOutput(line_number=4, hcpcs="D", units=1, adjusted_rate=50.0, subject_to_discount=False, status="payable")
        
        # Mock _process_line to return these in order
        def mock_process_line(line, idx, *args, **kwargs):
            return [out_A, out_B, out_C, out_D][idx]
            
        client._process_line = mock_process_line
        
        # disable MUEs
        claim.additional_data["asc_no_mue"] = True
        
        # Call process
        output = client.process(claim)
        
        # Check discount_percent
        # B is sorted first. Expected: 2 * 200 = 400. Payment: 200 + 100 = 300. Discount percent = 300 / 400 = 75%
        res_B = next(l for l in output.lines if l.hcpcs == "B")
        self.assertEqual(res_B.discount_applied, False) # Because it's mpr_idx 0
        self.assertEqual(res_B.discount_percent, 0.75)
        
        # A is sorted second. Expected: 1 * 100 = 100. Payment: 50. Discount percent = 50 / 100 = 50%
        res_A = next(l for l in output.lines if l.hcpcs == "A")
        self.assertEqual(res_A.discount_applied, True)
        self.assertEqual(res_A.discount_percent, 0.5)
        
        # C is sorted third. Expected: 1 * 50 = 50. Payment: 25. Discount percent = 25 / 50 = 50%
        res_C = next(l for l in output.lines if l.hcpcs == "C")
        self.assertEqual(res_C.discount_applied, True)
        self.assertEqual(res_C.discount_percent, 0.5)
        
        # D is non-discountable. Expected: 1 * 50 = 50. Payment = 50. Discount percent = 100%
        res_D = next(l for l in output.lines if l.hcpcs == "D")
        self.assertEqual(res_D.discount_percent, 1.0)

if __name__ == "__main__":
    unittest.main()
