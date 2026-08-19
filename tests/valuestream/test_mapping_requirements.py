"""Focused FR-402/FR-404 acceptance mapping tests."""

from __future__ import annotations

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ExclusionType, Payer, ValueStream
from core.valuestream import (
    DistributedBenefit,
    DistributedSubItems,
    SelfConsumption,
    SurplusSale,
    payer_gate,
)
from core.valuestream.exclusion_table import DEFAULT_EXCLUSION_RULES, ExclusionRule
from core.valuestream.report import build_report
from tests.valuestream.test_report import _dispatch_zeros


class _FixedBenefit(ValueStream):
    tag = "FixedBenefit"
    #: 검사용 편익 — 창을 읽지 않으므로 연간화 대상이 아니다 (R34 계약).
    scales_with_dispatch_window = False
    payer = Payer.RESIDENT

    def __init__(self, value: int, *, enabled: bool = True) -> None:
        super().__init__(name="fixed test benefit", enabled=enabled)
        self._value = Money(value)

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        return self._value if self.enabled else Money(0)

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        return f"검사용 고정값 {int(self._value):,}원"


@pytest.mark.req("FR-402-AC4")
def test_exclusion_rules_are_declarative_table_rows() -> None:
    """Spec expects fields A, B, type A-D, rationale, and optional regulation profile."""
    assert isinstance(DEFAULT_EXCLUSION_RULES, tuple)
    assert DEFAULT_EXCLUSION_RULES
    for rule in DEFAULT_EXCLUSION_RULES:
        assert isinstance(rule, ExclusionRule)
        assert rule.benefit_a
        assert rule.benefit_b
        assert rule.exclusion_type in set(ExclusionType)
        assert rule.rationale
        assert rule.applies_to_profile is None or rule.applies_to_profile


@pytest.mark.req("FR-402-AC5")
def test_four_question_gate_requires_specified_payer_before_activation() -> None:
    """Manual oracle: Q1 is mandatory; Q2-Q4 stay false until caller records evidence."""
    stream = _FixedBenefit(100)
    verdict = payer_gate.assess(stream)

    assert verdict.stream_tag == "FixedBenefit"
    assert verdict.q1_payer_specified is True
    assert verdict.q2_increment_only is False
    assert verdict.q3_physical_overlap_registered is False
    assert verdict.q4_institutional_check_done is False
    payer_gate.assert_activation_allowed(stream)


@pytest.mark.req("FR-402-AC6")
def test_report_lists_all_benefit_accounting_buckets() -> None:
    """Spec buckets: accounted, excluded, increment-only, and enabled-but-zero."""
    accounted = build_report([_FixedBenefit(100)], _dispatch_zeros(), year=1)

    from core.contracts.validation import ValidationError
    with pytest.raises(ValidationError, match="SelfConsumption ↔ SurplusSale"):
        build_report(
            [
                SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120),
                SurplusSale(sale_price_won_per_kwh=0.0),
            ],
            _dispatch_zeros(),
            year=1,
        )

    increment = build_report(
        [
            SelfConsumption(baseline_annual_bill_won=300, new_annual_bill_won=120),
            DistributedBenefit(
                sub_items=DistributedSubItems(transmission_avoidance_won=40.0)
            ),
        ],
        _dispatch_zeros(),
        year=1,
    )

    zero = build_report([DistributedBenefit()], _dispatch_zeros(), year=1)

    assert [line.tag for line in accounted.accounted] == ["FixedBenefit"]
    assert [line.tag for line in increment.increment_only] == ["DistributedBenefit"]
    assert [line.tag for line in zero.unmonetized_zero] == ["DistributedBenefit"]


@pytest.mark.req("FR-404-AC2")
def test_distributed_credit_is_separate_from_main_benefit_total() -> None:
    """Hand calc: main 1,000 won; distributed credit 100 + 25 = 125 won."""
    report = build_report(
        [
            SelfConsumption(baseline_annual_bill_won=1_500, new_annual_bill_won=500),
            DistributedBenefit(
                sub_items=DistributedSubItems(
                    transmission_avoidance_won=100.0,
                    loss_reduction_won=25.0,
                )
            ),
        ],
        _dispatch_zeros(),
        year=1,
    )

    credit_total = sum(line.annual_value for line in report.increment_only)
    assert report.total_accounted() == Money(1_000)
    assert credit_total == Money(125)
    assert report.total_accounted() + credit_total == Money(1_125)


@pytest.mark.req("FR-404-AC3")
def test_distributed_network_items_are_type_b_increment_only() -> None:
    """Hand calc: transmission 100 + loss 25 = 125; rule says keep only increment."""
    stream = DistributedBenefit(
        sub_items=DistributedSubItems(
            transmission_avoidance_won=100.0,
            loss_reduction_won=25.0,
        )
    )
    exclusions = stream.exclusions()

    assert stream.annual_value(_dispatch_zeros(), year=1) == to_won(125)
    assert exclusions == [
        (
            "SelfConsumption",
            ExclusionType.B,
            exclusions[0][2],
        )
    ]
