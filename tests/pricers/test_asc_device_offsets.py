import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock

from myelin.input.claim import Claim, LineItem, Modules
from myelin.pricers.asc.client import AscClient


def _make_opsf(cbsa: str = "10000") -> MagicMock:
    opsf = MagicMock()
    opsf.cbsa_wage_index_location = cbsa
    opsf.cbsa_actual_geographic_location = cbsa
    opsf.provider_type = "ASC"
    return opsf


def _make_claim(hcpcs: str, modifiers: list[str]) -> Claim:
    return Claim(
        thru_date=datetime(2025, 1, 15),
        modules=[Modules.AUTO],
        lines=[
            LineItem(
                line_number=1,
                hcpcs=hcpcs,
                modifiers=modifiers,
                units=1,
                charges=9999.0,  # High enough to never be the lower-of
                revenue_code="0490",
            )
        ],
    )


class TestAscDeviceOffsets(unittest.TestCase):
    """
    Tests for FB (full credit) and FC (partial credit) device offset modifiers.

    Setup:
      - HCPCS 10001: payment rate $100, device offset $20, subject to discount.
      - Wage index for CBSA 10000 = 1.5
      - Adjusted rate = (100 * 0.5 * 1.5) + (100 * 0.5) = 75 + 50 = 125.0
      - FB reduction = $20.00 → adjusted_rate = 125.0 - 20.0 = 105.0
      - FC reduction = $10.00 → adjusted_rate = 125.0 - 10.0 = 115.0
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.asc_data_dir = os.path.join(self.test_dir, "asc_data")
        q1 = os.path.join(self.asc_data_dir, "2025", "20250101")
        os.makedirs(q1)

        def csv(path, lines):
            with open(path, "w") as f:
                f.write("\n".join(lines))

        csv(
            os.path.join(q1, "AA.csv"),
            [
                "HCPCS Code,Short Descriptor,Subject to Multiple Procedure Discounting,"
                "January 2025 Payment Indicator,January 2025 Payment Rate",
                "10001,Device Proc,Y,A2,$100.00",
            ],
        )
        csv(
            os.path.join(q1, "BB.csv"),
            [
                "HCPCS Code,Short Descriptor,Drug Pass-Through,"
                "January 2025 Payment Indicator,January 2025 Payment Rate",
            ],
        )
        csv(
            os.path.join(q1, "FF.csv"),
            [
                "HCPCS Code,Short Descriptor,Indicator,APC,Offset %,OPPS Rate,Offset %,"
                "Device Offset Amount",
                "10001,Device Proc,A2,123,20%,$200.00,20%,$20.00",
            ],
        )
        csv(
            os.path.join(q1, "wage_index.csv"),
            ["CBSA,Wage Index", "10000,1.5"],
        )

        self.client = AscClient(self.asc_data_dir)
        self.opsf = _make_opsf("10000")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    # -------------------------------------------------------------------------
    # Modifier FB — full device offset (100%)
    # -------------------------------------------------------------------------

    def test_fb_applies_full_device_offset(self):
        """Modifier FB removes 100% of the device offset from the adjusted rate."""
        claim = _make_claim("10001", ["FB"])
        result = self.client.process(claim, self.opsf)

        line = result.lines[0]
        self.assertTrue(line.device_credit)
        self.assertAlmostEqual(line.device_offset_amount, 20.0)
        # 125.0 - 20.0 = 105.0
        self.assertAlmostEqual(line.adjusted_rate, 105.0)
        self.assertIn("Mod FB", line.details)

    def test_fb_sets_device_credit_true(self):
        """Modifier FB sets device_credit flag to True."""
        claim = _make_claim("10001", ["FB"])
        result = self.client.process(claim, self.opsf)
        self.assertTrue(result.lines[0].device_credit)

    def test_fb_total_payment_reflects_full_offset(self):
        """Total payment with FB reflects the full device offset reduction."""
        claim = _make_claim("10001", ["FB"])
        result = self.client.process(claim, self.opsf)
        # Single line, subject to discount, first procedure → 100% of adjusted_rate
        self.assertAlmostEqual(result.total_payment, 105.0)

    # -------------------------------------------------------------------------
    # Modifier FC — partial device offset (50%)
    # -------------------------------------------------------------------------

    def test_fc_applies_half_device_offset(self):
        """Modifier FC removes 50% of the device offset from the adjusted rate."""
        claim = _make_claim("10001", ["FC"])
        result = self.client.process(claim, self.opsf)

        line = result.lines[0]
        self.assertTrue(line.device_credit)
        self.assertAlmostEqual(line.device_offset_amount, 10.0)  # 50% of $20
        # 125.0 - 10.0 = 115.0
        self.assertAlmostEqual(line.adjusted_rate, 115.0)
        self.assertIn("Mod FC", line.details)

    def test_fc_sets_device_credit_true(self):
        """Modifier FC sets device_credit flag to True."""
        claim = _make_claim("10001", ["FC"])
        result = self.client.process(claim, self.opsf)
        self.assertTrue(result.lines[0].device_credit)

    def test_fc_total_payment_reflects_half_offset(self):
        """Total payment with FC reflects the 50% device offset reduction."""
        claim = _make_claim("10001", ["FC"])
        result = self.client.process(claim, self.opsf)
        self.assertAlmostEqual(result.total_payment, 115.0)

    # -------------------------------------------------------------------------
    # FB vs FC produce different results
    # -------------------------------------------------------------------------

    def test_fb_reduces_more_than_fc(self):
        """FB (full credit) reduces payment more than FC (partial credit)."""
        fb_claim = _make_claim("10001", ["FB"])
        fc_claim = _make_claim("10001", ["FC"])

        fb_result = self.client.process(fb_claim, self.opsf)
        fc_result = self.client.process(fc_claim, self.opsf)

        self.assertLess(fb_result.lines[0].adjusted_rate, fc_result.lines[0].adjusted_rate)
        self.assertGreater(
            fb_result.lines[0].device_offset_amount,
            fc_result.lines[0].device_offset_amount,
        )

    # -------------------------------------------------------------------------
    # Modifier 73 takes precedence — FB/FC ignored per CMS §40.10
    # -------------------------------------------------------------------------

    def test_mod73_overrides_fb(self):
        """When modifier 73 is present, FB is ignored (CMS §40.10)."""
        claim = _make_claim("10001", ["73", "FB"])
        result = self.client.process(claim, self.opsf)

        line = result.lines[0]
        self.assertFalse(line.device_credit)
        self.assertEqual(line.device_offset_amount, 0.0)
        self.assertIn("Mod 73 present, FB/FC Ignored", line.details)

    def test_mod73_overrides_fc(self):
        """When modifier 73 is present, FC is ignored (CMS §40.10)."""
        claim = _make_claim("10001", ["73", "FC"])
        result = self.client.process(claim, self.opsf)

        line = result.lines[0]
        self.assertFalse(line.device_credit)
        self.assertEqual(line.device_offset_amount, 0.0)
        self.assertIn("Mod 73 present, FB/FC Ignored", line.details)

    # -------------------------------------------------------------------------
    # No modifier — no device credit applied
    # -------------------------------------------------------------------------

    def test_no_fb_fc_no_device_credit(self):
        """Without FB or FC, no device credit is applied."""
        claim = _make_claim("10001", [])
        result = self.client.process(claim, self.opsf)

        line = result.lines[0]
        self.assertFalse(line.device_credit)
        self.assertEqual(line.device_offset_amount, 0.0)
        # Full adjusted rate: 125.0
        self.assertAlmostEqual(line.adjusted_rate, 125.0)

    # -------------------------------------------------------------------------
    # Procedure not in FF.csv — no device offset available
    # -------------------------------------------------------------------------

    def test_fb_on_non_device_intensive_proc_no_reduction(self):
        """FB on a procedure not in FF.csv results in no device credit reduction."""
        # 10001 is in FF.csv; use a different code that isn't
        # We'll reuse 10001 but test that device_credit is only set when offset exists
        # This is already tested above — here we verify the inverse:
        # If the FF.csv had no entry, device_credit would be False.
        # Since we can't easily remove from FF.csv, we test a code not in FF.
        # Add a second procedure to AA without an FF entry.
        q1 = os.path.join(self.asc_data_dir, "2025", "20250101")
        with open(os.path.join(q1, "AA.csv"), "a") as f:
            f.write("\n10002,Non-Device Proc,Y,A2,$80.00")

        # Reload client to pick up new data
        client = AscClient(self.asc_data_dir)
        claim = _make_claim("10002", ["FB"])
        result = client.process(claim, self.opsf)

        line = result.lines[0]
        self.assertFalse(line.device_credit)
        self.assertEqual(line.device_offset_amount, 0.0)


if __name__ == "__main__":
    unittest.main()
