"""10.5 — 기준선 증분 (FR-705-AC1).

설비 미설치 기준선을 명시적으로 계산·표시. **기준선이 없으면 증분의 타당성을
검증할 수 없다** (도메인 원칙 1-2).
"""
from __future__ import annotations

import pytest

from core.cba.baseline import (
    assert_baseline_displayed,
    compare_baseline_vs_new,
    compute_incremental,
)
from core.cba.proforma import benefit_row
from core.contracts.units import Money


@pytest.mark.req("FR-705-AC1")
def test_incremental_is_new_minus_baseline() -> None:
    """편익 증분 = new − baseline. 비용 항목은 음수 편익으로 모델링 (도메인 원칙 1-1).

    오라클: 순위 1 (정의 항등식). 전기요금 비용이 baseline 300만 → new 120만으로
    줄면 «비용» 행은 baseline=-3M, new=-1.2M (음수). 증분 = new − baseline = +1.8M (절감 = 편익).
    """
    baseline = [benefit_row(tag="elec_bill", schedule={1: -3_000_000})]  # 비용=음수
    new = [benefit_row(tag="elec_bill", schedule={1: -1_200_000})]
    comparison = compare_baseline_vs_new(baseline, new)
    assert comparison.incremental_total() == Money(1_800_000)


def test_baseline_must_be_displayed() -> None:
    """기준선 자체 비용이 리포트에 표시되어야 한다 (FR-705-AC1).

    오라클: 순위 4 (정의 항등식 — 표시 여부). 기준선 행이 있고 총액이 0 이
    아니면 표시된 것이다.
    """
    baseline = [benefit_row(tag="baseline", schedule={1: 3_000_000})]
    new = [benefit_row(tag="baseline", schedule={1: 1_200_000})]
    comparison = compare_baseline_vs_new(baseline, new)
    assert_baseline_displayed(comparison)  # 예외 없으면 통과
    assert comparison.baseline_total() == Money(3_000_000)


def test_missing_baseline_raises() -> None:
    """기준선 없으면 assert_baseline_displayed 가 예외 — FR-705-AC1 위반."""
    comparison = compare_baseline_vs_new([], [benefit_row(tag="x", schedule={1: 100})])
    with pytest.raises(ValueError, match="기준선이 표시되지 않았다"):
        assert_baseline_displayed(comparison)


def test_incremental_handles_tag_only_in_new() -> None:
    """new 에만 있는 tag — baseline 0, new 그대로 (증가)."""
    baseline = [benefit_row(tag="A", schedule={1: 100})]
    new = [
        benefit_row(tag="A", schedule={1: 100}),
        benefit_row(tag="B", schedule={1: 50}),
    ]
    inc = compute_incremental(baseline, new)
    inc_tags = {r.tag for r in inc}
    assert "B" in inc_tags


def test_incremental_baseline_is_realistic_alternative() -> None:
    """기준선은 «현실적 대안» (도메인 원칙 1-3).

    히트펌프 기준선은 «난방 안 함» 이 아니라 «기존 보일러 유지» —
    기준선에 연료비(음수 편익)가 있다. 절감 = new − baseline.
    """
    # 기존 보일러 연료비 200만/년 (비용 = 음수 편익)
    baseline = [benefit_row(tag="fuel_cost", schedule={y: -2_000_000 for y in range(1, 6)})]
    # 히트펌프 전력비 80만/년 (비용 = 음수, 더 작음)
    new = [benefit_row(tag="fuel_cost", schedule={y: -800_000 for y in range(1, 6)})]
    comparison = compare_baseline_vs_new(baseline, new)
    # 증분 = 매년 120만 절감 × 5년 = 600만 (양수 편익)
    assert comparison.incremental_total() == Money(6_000_000)
