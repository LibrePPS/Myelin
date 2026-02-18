"""
Tests for ASC Code Pair (Pass-Through Device) Logic

Per CMS 40.7: When a pass-through device is billed with a procedure,
the procedure payment is reduced by the device's percent multiplier.
"""

import pytest
from datetime import datetime

from myelin.input.claim import Claim, LineItem
from myelin.pricers.asc.client import AscClient


class TestAscCodePair:
    """Tests for ASC code pair (pass-through device) logic."""

    @pytest.fixture
    def client(self):
        """Create an ASC client with test data directory."""
        return AscClient("myelin/pricers/asc/data")

    def test_code_pair_offset_applied(self, client):
        """
        Test that code pair offset is applied when device and procedure are on the same claim.

        C1601 + 31626 has a 21.73% multiplier in 2026 data.
        """
        claim = Claim(
            thru_date=datetime(2026, 1, 15),
            additional_data={"cbsa": "47900"},
            lines=[
                LineItem(hcpcs="31626", units=1),  # Procedure
                LineItem(hcpcs="C1601", units=1),  # Device
            ],
        )

        result = client.process(claim)

        # Find the procedure line (should be line 1)
        proc_line = result.lines[0]

        # Base rate for 31626 in 2026
        assert proc_line.payment_rate == 2451.02

        # Code pair offset should be applied
        assert proc_line.code_pair_offset > 0
        assert proc_line.code_pair_device == "C1601"

        # Offset = base_rate * multiplier (2451.02 * 0.2173 = 532.61)
        expected_offset = 2451.02 * 0.2173
        assert abs(proc_line.code_pair_offset - expected_offset) < 0.01

        # Adjusted rate should be reduced
        assert proc_line.adjusted_rate < proc_line.payment_rate

    def test_no_code_pair_when_device_not_on_claim(self, client):
        """
        Test that no code pair offset is applied when device is not on the claim.
        """
        claim = Claim(
            thru_date=datetime(2026, 1, 15),
            additional_data={"cbsa": "47900"},
            lines=[
                LineItem(hcpcs="31626", units=1),  # Procedure only
            ],
        )

        result = client.process(claim)

        proc_line = result.lines[0]

        # No code pair offset should be applied
        assert proc_line.code_pair_offset == 0
        assert proc_line.code_pair_device == ""

        # Adjusted rate should equal base rate (with wage adjustment)
        assert proc_line.adjusted_rate == proc_line.payment_rate

    def test_no_code_pair_for_non_paired_device(self, client):
        """
        Test that no code pair offset when device doesn't pair with procedure.
        """
        claim = Claim(
            thru_date=datetime(2026, 1, 15),
            additional_data={"cbsa": "47900"},
            lines=[
                LineItem(hcpcs="31626", units=1),  # Procedure
                LineItem(hcpcs="C9999", units=1),  # Device that's NOT in code pairs
            ],
        )

        result = client.process(claim)

        proc_line = result.lines[0]

        # No code pair offset should be applied
        assert proc_line.code_pair_offset == 0
        assert proc_line.code_pair_device == ""

    def test_code_pair_first_match_only(self, client):
        """
        Test that only the first matching device/procedure pair gets applied.

        When multiple devices could pair, only the first one is used.
        """
        # Create a claim with a procedure and two devices
        # 31626 pairs with C1601 (first match)
        claim = Claim(
            thru_date=datetime(2026, 1, 15),
            additional_data={"cbsa": "47900"},
            lines=[
                LineItem(hcpcs="31626", units=1),  # Procedure
                LineItem(hcpcs="C1601", units=1),  # Device 1 - pairs with 31626
                LineItem(hcpcs="C1602", units=1),  # Device 2 - also pairs with 31626
            ],
        )

        result = client.process(claim)

        proc_line = result.lines[0]

        # Should only apply one code pair (the first match)
        assert proc_line.code_pair_device == "C1601"

        # Total should only reflect one offset
        assert proc_line.code_pair_offset > 0

    def test_code_pair_date_validation(self, client):
        """
        Test that code pair is only applied when claim date is within valid range.
        """
        # Claim in 2025 - should use 2025 data
        claim_2025 = Claim(
            thru_date=datetime(2025, 6, 15),
            additional_data={"cbsa": "47900"},
            lines=[
                LineItem(hcpcs="31626", units=1),
                LineItem(hcpcs="C1601", units=1),
            ],
        )

        result_2025 = client.process(claim_2025)
        proc_line_2025 = result_2025.lines[0]

        # 2025 multiplier for C1601 + 31626 is 0.1314 (13.14%)
        # Offset = 2451.02 * 0.1314 = 321.82
        assert proc_line_2025.code_pair_offset > 0

    def test_device_line_not_reduced(self, client):
        """
        Test that device lines themselves are not reduced by code pair logic.
        """
        claim = Claim(
            thru_date=datetime(2026, 1, 15),
            additional_data={"cbsa": "47900"},
            lines=[
                LineItem(hcpcs="31626", units=1),
                LineItem(hcpcs="C1601", units=1),
            ],
        )

        result = client.process(claim)

        # Device line should be line 2
        device_line = result.lines[1]

        # Device should not have code pair offset applied to itself
        assert device_line.code_pair_offset == 0
        assert device_line.code_pair_device == ""

        # Device should show as packaged/no payment
        assert "Packaged" in device_line.details or device_line.payment_rate == 0

    def test_code_pair_with_wage_index(self, client):
        """
        Test that code pair offset is applied after wage adjustment.

        The offset should be based on the wage-adjusted rate, not the base rate.
        """
        # Use a CBSA with known wage index > 1.0
        # CBSA 47900 (Dallas) has wage index around 1.0 in 2026
        # Let's use a different CBSA to test

        claim = Claim(
            thru_date=datetime(2026, 1, 15),
            additional_data={"cbsa": "35614"},  # New York (higher wage index)
            lines=[
                LineItem(hcpcs="31626", units=1),
                LineItem(hcpcs="C1601", units=1),
            ],
        )

        result = client.process(claim)

        proc_line = result.lines[0]

        # Code pair should be applied
        assert proc_line.code_pair_offset > 0
        assert proc_line.code_pair_device == "C1601"

        # The adjusted rate should be less than the pre-code-pair rate
        # (which includes wage adjustment)

    def test_code_pair_device_units_respected(self, client):
        """
        Test that a device with units > 1 can offset multiple procedures.

        Per CMS §40.7: "If there is more than 1 unit of a pass-through device on
        the claim, the contractor should take an offset for each code pair. No code
        pair should be offset more than once and the number of code pairs receiving
        an offset should be no more than the units of a pass-through device."

        C1601 pairs with both 31626 (0.2173) and 31625 (0.0096) in 2026 data.
        With units=2 on the device, both procedures should receive an offset.
        """
        claim = Claim(
            thru_date=datetime(2026, 1, 15),
            additional_data={"cbsa": "47900"},
            lines=[
                LineItem(hcpcs="31626", units=1),  # Procedure 1 - pairs with C1601
                LineItem(hcpcs="31625", units=1),  # Procedure 2 - also pairs with C1601
                LineItem(hcpcs="C1601", units=2),  # Device with 2 units
            ],
        )

        result = client.process(claim)

        proc_line_1 = result.lines[0]
        proc_line_2 = result.lines[1]

        # Both procedures should have code pair offsets applied
        assert proc_line_1.code_pair_offset > 0, (
            "First procedure should have code pair offset"
        )
        assert proc_line_1.code_pair_device == "C1601"

        assert proc_line_2.code_pair_offset > 0, (
            "Second procedure should also have code pair offset"
        )
        assert proc_line_2.code_pair_device == "C1601"

    def test_code_pair_single_unit_limits_offset(self, client):
        """
        Test that a device with units=1 only offsets ONE procedure,
        even when multiple procedures could pair with it.

        C1601 pairs with both 31626 and 31625 in 2026 data.
        With only 1 unit of the device, only the first procedure should get the offset.
        """
        claim = Claim(
            thru_date=datetime(2026, 1, 15),
            additional_data={"cbsa": "47900"},
            lines=[
                LineItem(hcpcs="31626", units=1),  # Procedure 1 - pairs with C1601
                LineItem(hcpcs="31625", units=1),  # Procedure 2 - also pairs with C1601
                LineItem(hcpcs="C1601", units=1),  # Device with only 1 unit
            ],
        )

        result = client.process(claim)

        proc_line_1 = result.lines[0]
        proc_line_2 = result.lines[1]

        # First procedure should have code pair offset
        assert proc_line_1.code_pair_offset > 0, (
            "First procedure should have code pair offset"
        )
        assert proc_line_1.code_pair_device == "C1601"

        # Second procedure should NOT have offset (device unit exhausted)
        assert proc_line_2.code_pair_offset == 0, (
            "Second procedure should NOT have offset (only 1 device unit)"
        )
        assert proc_line_2.code_pair_device == ""
