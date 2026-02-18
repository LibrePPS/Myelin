"""
Tests for ASC Payment Indicator Denials (CMS §60.3)

Per CMS §60.3, certain payment indicators result in denial or rejection:
- C5, M6, U5, X5, E5, Y5: Denied (no payment)
- D5, B5: Returned as unprocessable
- L1, NI, S1: Denied as packaged (no separate payment)
"""

import pytest
from datetime import datetime

from myelin.input.claim import Claim, LineItem
from myelin.pricers.asc.client import (
    AscClient,
)


class TestAscPaymentIndicators:
    """Tests for payment indicator denial logic."""

    @pytest.fixture
    def data_dir(self, tmp_path):
        """Create a temp data directory with test reference files."""
        q_dir = tmp_path / "2025" / "20250101"
        q_dir.mkdir(parents=True)

        # AA.csv with various payment indicators
        aa_lines = [
            "HCPCS Code,Short Descriptor,Subject to Multiple Procedure Discounting,January 2025 Payment Indicator,January 2025 Payment Rate",
            # Payable
            "10001,Normal Proc,Y,A2,$100.00",
            # Deny indicators
            "20001,Inpatient Only,N,C5,$0.00",
            "20002,Other Fee Sched,N,M6,$0.00",
            "20003,Unlisted Surg,N,U5,$0.00",
            "20004,Unsafe Surg,N,X5,$0.00",
            "20005,Not Valid Coverage,N,E5,$0.00",
            "20006,Non-Surg Not Valid,N,Y5,$0.00",
            # Unprocessable indicators
            "30001,Deleted Code,N,D5,$0.00",
            "30002,Alt Code Avail,N,B5,$0.00",
            # Packaged denial indicators
            "40001,Influenza Vaccine,N,L1,$0.00",
            "40002,Packaged Svc,N,NI,$0.00",
            "40003,Not Surgical Pkg,N,S1,$0.00",
            # Edge case: deny indicator with non-zero rate
            "50001,Rate But Denied,N,C5,$200.00",
        ]
        (q_dir / "AA.csv").write_text("\n".join(aa_lines))

        # Wage index
        (q_dir / "wage_index.csv").write_text("CBSA,Wage Index\n10000,1.0\n")

        return str(tmp_path)

    @pytest.fixture
    def client(self, data_dir):
        return AscClient(data_dir)

    def _make_claim(self, hcpcs: str) -> Claim:
        return Claim(
            thru_date=datetime(2025, 1, 15),
            additional_data={"cbsa": "10000"},
            lines=[LineItem(hcpcs=hcpcs, units=1)],
        )

    # --- Payable baseline ---

    def test_payable_indicator_has_payment(self, client):
        """Normal payable indicator should produce payment."""
        result = client.process(self._make_claim("10001"))
        line = result.lines[0]
        assert line.status == "payable"
        assert line.adjusted_rate > 0
        assert result.total_payment > 0

    # --- Deny indicators (C5, M6, U5, X5, E5, Y5) ---

    @pytest.mark.parametrize(
        "hcpcs,indicator",
        [
            ("20001", "C5"),
            ("20002", "M6"),
            ("20003", "U5"),
            ("20004", "X5"),
            ("20005", "E5"),
            ("20006", "Y5"),
        ],
    )
    def test_deny_indicators_produce_zero_payment(self, client, hcpcs, indicator):
        """HCPCS with deny indicators should have status='denied' and $0 payment."""
        result = client.process(self._make_claim(hcpcs))
        line = result.lines[0]
        assert line.status == "denied", f"Indicator {indicator} should be denied"
        assert line.adjusted_rate == 0.0
        assert f"Indicator {indicator}" in line.details
        assert result.total_payment == 0.0

    # --- Unprocessable indicators (D5, B5) ---

    @pytest.mark.parametrize(
        "hcpcs,indicator",
        [
            ("30001", "D5"),
            ("30002", "B5"),
        ],
    )
    def test_unprocessable_indicators(self, client, hcpcs, indicator):
        """HCPCS with unprocessable indicators should have status='unprocessable' and $0."""
        result = client.process(self._make_claim(hcpcs))
        line = result.lines[0]
        assert line.status == "unprocessable", (
            f"Indicator {indicator} should be unprocessable"
        )
        assert line.adjusted_rate == 0.0
        assert f"Indicator {indicator}" in line.details
        assert result.total_payment == 0.0

    # --- Packaged denial indicators (L1, NI, S1) ---

    @pytest.mark.parametrize(
        "hcpcs,indicator",
        [
            ("40001", "L1"),
            ("40002", "NI"),
            ("40003", "S1"),
        ],
    )
    def test_packaged_denial_indicators(self, client, hcpcs, indicator):
        """HCPCS with packaged indicators should have status='packaged' and $0."""
        result = client.process(self._make_claim(hcpcs))
        line = result.lines[0]
        assert line.status == "packaged", f"Indicator {indicator} should be packaged"
        assert line.adjusted_rate == 0.0
        assert result.total_payment == 0.0

    # --- Edge case: deny indicator overrides non-zero rate ---

    def test_deny_indicator_overrides_rate(self, client):
        """Even if a deny-indicator code has a non-zero rate, it should be denied with $0."""
        result = client.process(self._make_claim("50001"))
        line = result.lines[0]
        assert line.status == "denied"
        assert line.adjusted_rate == 0.0
        assert line.payment_rate == 200.0  # Original rate preserved for reference
        assert result.total_payment == 0.0

    # --- Mixed claim: denied + payable lines ---

    def test_mixed_claim_denied_and_payable(self, client):
        """Denied lines should not affect payment for payable lines on the same claim."""
        claim = Claim(
            thru_date=datetime(2025, 1, 15),
            additional_data={"cbsa": "10000"},
            lines=[
                LineItem(hcpcs="10001", units=1),  # Payable ($100)
                LineItem(hcpcs="20001", units=1),  # Denied (C5)
                LineItem(hcpcs="30001", units=1),  # Unprocessable (D5)
            ],
        )
        result = client.process(claim)

        payable = result.lines[0]
        denied = result.lines[1]
        unprocessable = result.lines[2]

        assert payable.status == "payable"
        assert payable.adjusted_rate > 0

        assert denied.status == "denied"
        assert denied.adjusted_rate == 0.0

        assert unprocessable.status == "unprocessable"
        assert unprocessable.adjusted_rate == 0.0

        # total_payment is the 80% Medicare portion; total is the 100% allowed amount
        assert result.total == payable.adjusted_rate

    # --- Real data: L1 indicator ---

    def test_real_data_l1_indicator(self):
        """Test with real 2026 data: HCPCS 90611 has L1 indicator (packaged vaccine)."""
        client = AscClient("myelin/pricers/asc/data")
        claim = Claim(
            thru_date=datetime(2026, 1, 15),
            additional_data={"cbsa": "47900"},
            lines=[LineItem(hcpcs="90611", units=1)],
        )
        result = client.process(claim)
        line = result.lines[0]

        assert line.payment_indicator == "L1"
        assert line.status == "packaged"
        assert line.adjusted_rate == 0.0
        assert result.total_payment == 0.0


class TestAscAncillaryValidation:
    """
    Tests for CMS §60.2: Ancillary services (Addendum BB) require a related
    surgical procedure (Addendum AA) on the same claim. If no approved surgical
    procedure is present, ancillary lines are returned as unprocessable.
    """

    @pytest.fixture
    def data_dir(self, tmp_path):
        """Create a temp data directory with AA (surgical) and BB (ancillary) codes."""
        q_dir = tmp_path / "2025" / "20250101"
        q_dir.mkdir(parents=True)

        # Addendum AA: surgical procedures
        aa_lines = [
            "HCPCS Code,Short Descriptor,Subject to Multiple Procedure Discounting,January 2025 Payment Indicator,January 2025 Payment Rate",
            "10001,Surgical Proc,Y,A2,$200.00",
            "10002,Denied Surg,N,C5,$0.00",  # Denied surgical — does NOT count
        ]
        (q_dir / "AA.csv").write_text("\n".join(aa_lines))

        # Addendum BB: covered ancillary services
        bb_lines = [
            "HCPCS Code,Short Descriptor,Subject to Multiple Procedure Discounting,January 2025 Payment Indicator,January 2025 Payment Rate",
            "C1234,Pass-Through Device,N,J7,$500.00",
            "90999,Drug Ancillary,N,K2,$75.00",
        ]
        (q_dir / "BB.csv").write_text("\n".join(bb_lines))

        (q_dir / "wage_index.csv").write_text("CBSA,Wage Index\n10000,1.0\n")
        return str(tmp_path)

    @pytest.fixture
    def client(self, data_dir):
        return AscClient(data_dir)

    def _make_claim(self, *hcpcs_codes) -> Claim:
        return Claim(
            thru_date=datetime(2025, 1, 15),
            additional_data={"cbsa": "10000"},
            lines=[LineItem(hcpcs=h, units=1) for h in hcpcs_codes],
        )

    def test_ancillary_only_claim_is_unprocessable(self, client):
        """BB-only claim: ancillary lines should be unprocessable (no surgical procedure)."""
        result = client.process(self._make_claim("C1234"))
        line = result.lines[0]
        assert line.status == "unprocessable"
        assert "CMS §60.2" in line.status_reason
        assert line.adjusted_rate == 0.0
        assert result.total_payment == 0.0

    def test_ancillary_with_payable_surgical_is_paid(self, client):
        """BB + payable AA: ancillary line should be payable."""
        result = client.process(self._make_claim("10001", "C1234"))
        surgical = result.lines[0]
        ancillary = result.lines[1]

        assert surgical.status == "payable"
        assert ancillary.status == "payable"
        assert ancillary.adjusted_rate > 0
        assert result.total_payment > 0

    def test_denied_surgical_does_not_unlock_ancillary(self, client):
        """BB + denied AA: denied surgical does not count — ancillary should be unprocessable."""
        result = client.process(self._make_claim("10002", "C1234"))
        surgical = result.lines[0]
        ancillary = result.lines[1]

        assert surgical.status == "denied"
        assert ancillary.status == "unprocessable"
        assert "CMS §60.2" in ancillary.status_reason
        assert result.total_payment == 0.0

    def test_multiple_ancillary_all_unprocessable_without_surgical(self, client):
        """Multiple BB lines with no AA: all should be unprocessable."""
        result = client.process(self._make_claim("C1234", "90999"))
        for line in result.lines:
            assert line.status == "unprocessable"
            assert "CMS §60.2" in line.status_reason
        assert result.total_payment == 0.0
