"""10.1 — 프로포마 합계 항등식 (NFR-103-M1).

20년 합계 == 항목별 합계, **원 단위 완전 일치**. float 가 섞이면 어긋나고,
그 어긋남은 화면상 정상으로 보인다 — 이 저장소가 가장 위험으로 보는 오류 유형.

``CashFlowRow`` 가 원 단위 정수만 받으므로 항등식은 구조적으로 성립해야 한다.
성립하지 않으면 validator 를 우회한 곳이 있다.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from core.cba import (
    aggregate,
    assert_proforma_identity,
    benefit_row,
    capex_row,
    fixed_om_row,
    replacement_row,
    total_row,
)
from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money


@pytest.mark.req("FR-701-AC1")
def test_proforma_sum_identity_20_years() -> None:
    """20년 합계 == 항목별 합계, 원 단위 완전 일치.

    오라클: 순위 1 (정의 항등식). capex + O&M(에스컬레이션) + 교체비 + 편익.
    """
    capex = capex_row(tag="PV", year=1, amount_won=10_000_000)
    om = fixed_om_row(
        tag="PV", start_year=1, end_year=20,
        annual_amount_won=300_000, escalation_rate=0.02,
    )
    repl = replacement_row(
        tag="PV_INV", replacement_years=[11],
        unit_cost_won=1_500_000,
        asset_lifetime_years=10, analysis_end_year=20,
    )
    benefit = benefit_row(
        tag="SelfConsumption",
        schedule={y: 1_200_000 for y in range(1, 21)},
    )
    rows = [capex, om, *repl, benefit]

    sum_of_row_totals = aggregate(rows)
    grand_total = total_row(rows).total()
    assert sum_of_row_totals == grand_total, (
        f"항등식 위반: 항목별 합 {sum_of_row_totals} != 총합 {grand_total}"
    )


@pytest.mark.req("FR-701-AC2")
def test_proforma_rows_cover_analysis_year_columns() -> None:
    row = fixed_om_row(
        tag="PV",
        start_year=1,
        end_year=20,
        annual_amount_won=300_000,
        escalation_rate=0.02,
    )

    assert tuple(row.amounts) == tuple(range(1, 21))


def test_assert_proforma_identity_passes_for_valid_rows() -> None:
    """assert_proforma_identity 는 정상 행 목록에서 예외 없이 통과."""
    rows = [
        capex_row(tag="A", year=1, amount_won=1_000_000),
        benefit_row(tag="B", schedule={y: 100_000 for y in range(1, 6)}),
    ]
    assert_proforma_identity(rows)  # 예외 없으면 통과


def test_total_row_sums_per_year() -> None:
    """total_row 는 year 을 key 로 합산 — 각 년도별 총계를 가진다."""
    r1 = CashFlowRow(label="A", tag="A", amounts={1: Decimal(100), 2: Decimal(200)})
    r2 = CashFlowRow(label="B", tag="B", amounts={1: Decimal(300), 3: Decimal(400)})
    total = total_row([r1, r2])
    assert total.amounts == {1: Decimal(400), 2: Decimal(200), 3: Decimal(400)}


def test_aggregate_equals_sum_of_totals() -> None:
    """aggregate(rows) == sum(row.total() for row in rows) — NFR-103-M1 항등식."""
    rows = [
        capex_row(tag="A", year=1, amount_won=500_000),
        fixed_om_row(tag="A", start_year=1, end_year=5, annual_amount_won=100_000),
        benefit_row(tag="X", schedule={y: 200_000 for y in range(1, 6)}),
    ]
    lhs = aggregate(rows)
    rhs = Money(sum((r.total() for r in rows), Decimal(0)))
    assert lhs == rhs


# ── FR-701-AC4 — 수명 종료 자원 이후 연도 0 ──────────────────────────────

@pytest.mark.req("FR-701-AC4")
def test_replacement_after_analysis_end_is_not_accounted() -> None:
    """분석 종료 이후 교체는 행을 만들지 않는다 — 잔존가치(10.8)로 처리.

    오라클: 순위 4 (정의 항등식). analysis_end_year=20 인데 교체 연도가 25 면
    그 교체는 0 이다 (행 자체가 없다).
    """
    rows = replacement_row(
        tag="X",
        replacement_years=[11, 21, 31],  # 21, 31 은 분석 종료(20) 이후
        unit_cost_won=1_000_000,
        asset_lifetime_years=10,
        analysis_end_year=20,
    )
    # 11년차 교체 1건만 행으로 나와야 — 21, 31 은 제외
    assert len(rows) == 1
    assert 11 in rows[0].amounts
    assert 21 not in rows[0].amounts


# ── FR-701-AC3 — 항목별 상이한 에스컬레이션 ──────────────────────────────

@pytest.mark.req("FR-701-AC3")
def test_fixed_om_applies_per_item_escalation() -> None:
    """항목별 escalation_rate 가 다르게 적용된다.

    오라클: 순위 1 (등비수열). 연 100,000, 2%/년, 3년 → [100000, 102000, 104040].
    """
    row = fixed_om_row(
        tag="X", start_year=1, end_year=3,
        annual_amount_won=100_000, escalation_rate=0.02,
    )
    assert int(row.amounts[1]) == 100_000
    assert int(row.amounts[2]) == 102_000
    assert int(row.amounts[3]) == 104_040


def test_negative_escalction_rejected() -> None:
    """escalation_rate 음수 거부 — 비용이 해마다 줄어드는 자원은 드물며,
    음수면 회수기간이 단축되어 경제성이 과대 계상된다."""
    with pytest.raises(ValueError, match="음수"):
        fixed_om_row(
            tag="X", start_year=1, end_year=3,
            annual_amount_won=100_000, escalation_rate=-0.01,
        )
