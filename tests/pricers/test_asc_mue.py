"""
Tests for AscClient MUE (Medically Unlikely Edit) check logic.

MUEs cap the number of units billable for a given HCPCS code on a single date
of service. Two enforcement modes exist:

- up_to_limit=False (line edit): Total units > limit → ALL lines for that
  HCPCS/date are denied. No partial payment.

- up_to_limit=True (date-of-service edit): Units up to the limit are paid;
  excess units are denied. Lines are filled greedily in claim order.

MUEs are applied per HCPCS per date of service, so the same code on two
different dates is evaluated independently.
"""

import pytest
from datetime import datetime

from myelin.input.claim import Claim, LineItem
from myelin.pricers.asc.client import AscClient, AscMueLimit


DATE_A = datetime(2025, 1, 15)
DATE_B = datetime(2025, 1, 16)


@pytest.fixture
def data_dir(tmp_path):
    """
    Minimal ASC reference data:
      - 10001: $100, subject to discount (A2)
      - 10002: $200, not subject to discount (G2)
      - 20001: denied (C5) — for testing MUE skips non-payable lines
    Wage index 1.0 for CBSA 10000 (no adjustment).
    """
    q_dir = tmp_path / "2025" / "20250101"
    q_dir.mkdir(parents=True)

    aa = [
        "HCPCS Code,Short Descriptor,Subject to Multiple Procedure Discounting,"
        "January 2025 Payment Indicator,January 2025 Payment Rate",
        "10001,Proc A,Y,A2,$100.00",
        "10002,Proc B,N,G2,$200.00",
        "20001,Denied Proc,N,C5,$0.00",
    ]
    (q_dir / "AA.csv").write_text("\n".join(aa))
    (q_dir / "wage_index.csv").write_text("CBSA,Wage Index\n10000,1.0\n")
    return str(tmp_path)


@pytest.fixture
def client(data_dir):
    return AscClient(data_dir)


def _claim(*lines: LineItem) -> Claim:
    return Claim(
        thru_date=DATE_A,
        additional_data={"cbsa": "10000"},
        lines=list(lines),
    )


def _line(hcpcs: str, units: int, service_date: datetime = DATE_A) -> LineItem:
    return LineItem(hcpcs=hcpcs, units=units, service_date=service_date)


# ---------------------------------------------------------------------------
# No MUE supplied — passthrough
# ---------------------------------------------------------------------------


class TestMueNoOp:
    def test_none_mues_no_effect(self, client):
        """Passing mues=None should not alter any line."""
        claim = _claim(_line("10001", 5))
        result = client.process(claim, mues=None)
        assert result.lines[0].status == "payable"
        # The summation loop sets units from the billed count
        assert result.lines[0].units == 5
        assert result.lines[0].line_total > 0

    def test_empty_mues_no_effect(self, client):
        """Passing mues={} should not alter any line."""
        claim = _claim(_line("10001", 5))
        result = client.process(claim, mues={})
        assert result.lines[0].status == "payable"
        assert result.lines[0].units == 5
        assert result.lines[0].line_total > 0

    def test_mue_for_different_hcpcs_no_effect(self, client):
        """MUE defined for a code not on the claim should not affect other lines."""
        claim = _claim(_line("10001", 3))
        mues = {"99999": AscMueLimit(code="99999", mue_limit=1, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        assert result.lines[0].status == "payable"
        assert result.lines[0].units == 3
        assert result.lines[0].line_total > 0


# ---------------------------------------------------------------------------
# Within limit — no action
# ---------------------------------------------------------------------------


class TestMueWithinLimit:
    def test_exactly_at_limit_not_denied(self, client):
        """Units equal to the MUE limit should not trigger a denial."""
        claim = _claim(_line("10001", 2))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        assert result.lines[0].status == "payable"

    def test_below_limit_not_denied(self, client):
        """Units below the MUE limit should not trigger a denial."""
        claim = _claim(_line("10001", 1))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=3, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        assert result.lines[0].status == "payable"

    def test_multi_line_sum_at_limit_not_denied(self, client):
        """Two lines whose combined units equal the limit should both be payable."""
        claim = _claim(_line("10001", 1), _line("10001", 1))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        for line in result.lines:
            assert line.status == "payable"


# ---------------------------------------------------------------------------
# Line edit (up_to_limit=False) — deny ALL lines for the HCPCS/date
# ---------------------------------------------------------------------------


class TestMueLineEdit:
    def test_single_line_over_limit_denied(self, client):
        """Single line exceeding the limit is denied entirely."""
        claim = _claim(_line("10001", 3))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        line = result.lines[0]
        assert line.status == "denied"
        assert line.adjusted_rate == 0.0
        assert line.units == 0
        assert line.line_payment == 0.0
        assert line.line_copayment == 0.0
        assert line.line_total == 0.0
        assert "MUE exceeded" in line.status_reason

    def test_all_lines_denied_when_sum_exceeds_limit(self, client):
        """When two lines for the same HCPCS/date exceed the limit, BOTH are denied."""
        claim = _claim(_line("10001", 2), _line("10001", 2))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=3, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        for line in result.lines:
            assert line.status == "denied"
            assert line.adjusted_rate == 0.0
            assert line.units == 0

    def test_total_is_zero_after_line_edit_denial(self, client):
        """Total payment should be $0 when all lines are denied by a line edit."""
        claim = _claim(_line("10001", 5))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        assert result.total_payment == 0.0
        assert result.total_copayment == 0.0
        assert result.total == 0.0

    def test_other_hcpcs_unaffected_by_line_edit(self, client):
        """A line edit denial for one HCPCS should not affect other codes."""
        claim = _claim(_line("10001", 5), _line("10002", 1))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        denied = next(g for g in result.lines if g.hcpcs == "10001")
        payable = next(g for g in result.lines if g.hcpcs == "10002")
        assert denied.status == "denied"
        assert payable.status == "payable"
        assert payable.adjusted_rate > 0

    def test_status_reason_includes_unit_counts(self, client):
        """The denial reason should report both billed and limit unit counts."""
        claim = _claim(_line("10001", 5))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        reason = result.lines[0].status_reason
        assert "5" in reason   # billed units
        assert "2" in reason   # limit


# ---------------------------------------------------------------------------
# Date-of-service edit (up_to_limit=True) — deny excess units only
# ---------------------------------------------------------------------------


class TestMueDateOfServiceEdit:
    def test_single_line_excess_units_capped(self, client):
        """Single line over limit: units are capped, line stays payable."""
        claim = _claim(_line("10001", 5))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=3, up_to_limit=True)}
        result = client.process(claim, mues=mues)
        line = result.lines[0]
        assert line.status == "payable"
        assert line.units == 3
        assert "MUE partial" in line.status_reason

    def test_partial_cap_payment_reflects_capped_units(self, client):
        """Payment for a capped line should be based on the allowed units, not billed.

        10001 is subject to MPR discount: first unit = 100%, additional units = 50%.
        With 2 allowed units: payment = $100 + $100*0.5 = $150 total.
        Medicare pays 80% = $120, copay = $30.
        """
        claim = _claim(_line("10001", 4))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=True)}
        result = client.process(claim, mues=mues)
        line = result.lines[0]
        # 2 units allowed (capped from 4)
        assert line.units == 2
        # MPR: unit 1 = $100, unit 2 = $50 → total = $150
        assert line.line_total == pytest.approx(150.0, abs=0.02)
        assert line.line_payment == pytest.approx(120.0, abs=0.02)
        assert line.line_copayment == pytest.approx(30.0, abs=0.02)

    def test_two_lines_first_fills_budget_second_denied(self, client):
        """
        Two lines, same HCPCS/date. First line's units fill the entire budget;
        second line should be denied entirely.

        10001 is subject to MPR discount:
          Line 1: 3 units, limit=3 → all allowed. First unit=100%, units 2-3=50% each.
          Line 2: 2 units, budget exhausted → denied.
        """
        claim = _claim(_line("10001", 3), _line("10001", 2))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=3, up_to_limit=True)}
        result = client.process(claim, mues=mues)
        first = result.lines[0]
        second = result.lines[1]
        # First line: 3 units, exactly at limit — stays payable, units set by summation
        assert first.status == "payable"
        # Second line: budget exhausted — denied
        assert second.status == "denied"
        assert second.units == 0
        assert second.adjusted_rate == 0.0

    def test_two_lines_partial_fill_then_deny(self, client):
        """
        First line partially fills the budget; second line is capped at the remainder.
        """
        claim = _claim(_line("10001", 2), _line("10001", 3))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=3, up_to_limit=True)}
        result = client.process(claim, mues=mues)
        first = result.lines[0]
        second = result.lines[1]
        # First line: 2 units, within remaining budget (3) — stays payable
        assert first.status == "payable"
        # Second line: 3 billed, only 1 remaining — capped at 1
        assert second.status == "payable"
        assert second.units == 1
        assert "MUE partial" in second.status_reason

    def test_dos_edit_total_reflects_allowed_units_only(self, client):
        """Total payment should only include allowed units after DOS edit.

        Line 1: 1 unit allowed. Line 2: 1 unit allowed (budget=2, used 1, 1 left).
        10001 is subject to MPR:
          Line 1 (highest rate, first in MPR): 1 unit = $100
          Line 2 (second in MPR): 1 unit × 50% = $50
          Total = $150, Medicare = $120.
        """
        claim = _claim(_line("10001", 1), _line("10001", 4))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=True)}
        result = client.process(claim, mues=mues)
        # Line 1: 1 unit. Line 2: capped to 1 unit.
        assert result.total == pytest.approx(150.0, abs=0.02)
        assert result.total_payment == pytest.approx(120.0, abs=0.02)

    def test_dos_edit_denied_line_zeroed_completely(self, client):
        """A line denied by DOS edit should have all payment fields zeroed."""
        claim = _claim(_line("10001", 3), _line("10001", 3))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=3, up_to_limit=True)}
        result = client.process(claim, mues=mues)
        denied = result.lines[1]
        assert denied.status == "denied"
        assert denied.adjusted_rate == 0.0
        assert denied.units == 0
        assert denied.line_payment == 0.0
        assert denied.line_copayment == 0.0
        assert denied.line_total == 0.0


# ---------------------------------------------------------------------------
# Date-of-service scoping — same HCPCS on different dates is independent
# ---------------------------------------------------------------------------


class TestMueDateScoping:
    def test_same_hcpcs_different_dates_evaluated_independently(self, client):
        """
        Two lines for the same HCPCS on different dates should each be checked
        against the MUE limit independently, not summed together.
        """
        claim = _claim(
            _line("10001", 2, service_date=DATE_A),
            _line("10001", 2, service_date=DATE_B),
        )
        # Limit = 2; each date has exactly 2 units → both should be payable
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        for line in result.lines:
            assert line.status == "payable", (
                f"Line on {line} should be payable — dates are independent"
            )

    def test_same_hcpcs_one_date_over_limit_other_fine(self, client):
        """
        Exceeding the limit on one date should not affect lines on a different date.
        """
        claim = _claim(
            _line("10001", 5, service_date=DATE_A),  # over limit
            _line("10001", 1, service_date=DATE_B),  # within limit
        )
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        line_a = next(g for g in result.lines if g.line_number == 1)
        line_b = next(g for g in result.lines if g.line_number == 2)
        assert line_a.status == "denied"
        assert line_b.status == "payable"

    def test_both_dates_over_limit_both_denied(self, client):
        """Both dates exceeding the limit should both be denied independently."""
        claim = _claim(
            _line("10001", 5, service_date=DATE_A),
            _line("10001", 5, service_date=DATE_B),
        )
        mues = {"10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        for line in result.lines:
            assert line.status == "denied"

    def test_no_service_date_lines_grouped_together(self, client):
        """
        Lines without a service_date (None) should be grouped together and
        evaluated as a single date bucket.
        """
        # Both lines have no service_date → grouped under (hcpcs, None)
        line1 = LineItem(hcpcs="10001", units=2)
        line2 = LineItem(hcpcs="10001", units=2)
        claim = Claim(
            thru_date=DATE_A,
            additional_data={"cbsa": "10000"},
            lines=[line1, line2],
        )
        # Combined = 4 units, limit = 3 → line edit should deny both
        mues = {"10001": AscMueLimit(code="10001", mue_limit=3, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        for line in result.lines:
            assert line.status == "denied"


# ---------------------------------------------------------------------------
# Interaction with pre-existing denied/packaged lines
# ---------------------------------------------------------------------------


class TestMueInteractionWithDenials:
    def test_mue_skips_already_denied_lines(self, client):
        """
        Lines already denied by payment indicator should not be counted toward
        the MUE unit total, and should remain denied (not double-processed).
        """
        # 20001 has indicator C5 → denied before MUE check
        claim = _claim(_line("20001", 5))
        mues = {"20001": AscMueLimit(code="20001", mue_limit=2, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        line = result.lines[0]
        # Still denied, but by payment indicator — not MUE
        assert line.status == "denied"
        assert "MUE" not in line.status_reason

    def test_payable_and_denied_same_hcpcs_only_payable_counted(self, client):
        """
        If one line is denied by indicator and another is payable, only the
        payable line's units count toward the MUE total.
        """
        # Two lines for 10001: one payable (1 unit), one... we can't easily
        # pre-deny a payable code, so test with a mixed-code claim instead.
        # 10001 (payable, 1 unit) + 20001 (denied by C5, 5 units).
        # MUE on 10001 limit=1 → 10001 is within limit, stays payable.
        claim = _claim(_line("10001", 1), _line("20001", 5))
        mues = {
            "10001": AscMueLimit(code="10001", mue_limit=1, up_to_limit=False),
            "20001": AscMueLimit(code="20001", mue_limit=2, up_to_limit=False),
        }
        result = client.process(claim, mues=mues)
        payable = next(g for g in result.lines if g.hcpcs == "10001")
        denied = next(g for g in result.lines if g.hcpcs == "20001")
        assert payable.status == "payable"
        assert denied.status == "denied"
        assert "MUE" not in denied.status_reason  # denied by indicator, not MUE

    def test_multiple_mues_applied_independently(self, client):
        """MUE limits for different codes are applied independently."""
        claim = _claim(
            _line("10001", 5),  # over limit for 10001
            _line("10002", 1),  # within limit for 10002
        )
        mues = {
            "10001": AscMueLimit(code="10001", mue_limit=2, up_to_limit=False),
            "10002": AscMueLimit(code="10002", mue_limit=3, up_to_limit=False),
        }
        result = client.process(claim, mues=mues)
        line_10001 = next(g for g in result.lines if g.hcpcs == "10001")
        line_10002 = next(g for g in result.lines if g.hcpcs == "10002")
        assert line_10001.status == "denied"
        assert line_10002.status == "payable"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestMueEdgeCases:
    def test_mue_limit_of_zero_denies_all(self, client):
        """An MUE limit of 0 should deny any line with units >= 1."""
        claim = _claim(_line("10001", 1))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=0, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        assert result.lines[0].status == "denied"

    def test_mue_limit_of_one_single_unit_payable(self, client):
        """MUE limit of 1 with exactly 1 unit billed should be payable."""
        claim = _claim(_line("10001", 1))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=1, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        assert result.lines[0].status == "payable"

    def test_mue_limit_of_one_two_units_line_edit_denied(self, client):
        """MUE limit of 1 with 2 units billed (line edit) should deny the line."""
        claim = _claim(_line("10001", 2))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=1, up_to_limit=False)}
        result = client.process(claim, mues=mues)
        assert result.lines[0].status == "denied"

    def test_mue_limit_of_one_two_units_dos_edit_capped(self, client):
        """MUE limit of 1 with 2 units billed (DOS edit) should cap to 1 unit."""
        claim = _claim(_line("10001", 2))
        mues = {"10001": AscMueLimit(code="10001", mue_limit=1, up_to_limit=True)}
        result = client.process(claim, mues=mues)
        line = result.lines[0]
        assert line.status == "payable"
        assert line.units == 1

    def test_three_lines_dos_edit_greedy_fill(self, client):
        """
        Three lines, DOS edit, limit=4. Greedy fill:
          Line 1: 2 units → allowed (remaining=2)
          Line 2: 3 units → capped at 2 (remaining=0)
          Line 3: 1 unit  → denied (budget exhausted)
        """
        claim = _claim(
            _line("10001", 2),
            _line("10001", 3),
            _line("10001", 1),
        )
        mues = {"10001": AscMueLimit(code="10001", mue_limit=4, up_to_limit=True)}
        result = client.process(claim, mues=mues)
        l1, l2, l3 = result.lines[0], result.lines[1], result.lines[2]

        assert l1.status == "payable"

        assert l2.status == "payable"
        assert l2.units == 2
        assert "MUE partial" in l2.status_reason

        assert l3.status == "denied"
        assert l3.units == 0
