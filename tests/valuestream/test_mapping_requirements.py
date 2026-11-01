"""Focused FR-402/FR-404 acceptance mapping tests."""

from __future__ import annotations

import pytest

from core.contracts.der import DispatchResult
from core.contracts.units import to_won
from core.contracts.valuestream import ExclusionType
from core.valuestream import (
    DistributedBenefit,
    DistributedSubItems,
)
from core.valuestream.exclusion_table import DEFAULT_EXCLUSION_RULES, ExclusionRule


def _dispatch_zeros(steps: int = 4) -> DispatchResult:
    z = [0.0] * steps
    return DispatchResult(electric=list(z), heat=list(z), cool=list(z), fuel=list(z))


@pytest.mark.req("FR-402-AC4")
def test_exclusion_rules_are_declarative_table_rows() -> None:
    """Spec expects fields A, B, type A-E, rationale, and optional regulation profile."""
    assert isinstance(DEFAULT_EXCLUSION_RULES, tuple)
    assert DEFAULT_EXCLUSION_RULES
    for rule in DEFAULT_EXCLUSION_RULES:
        assert isinstance(rule, ExclusionRule)
        assert rule.benefit_a
        assert rule.benefit_b
        assert rule.exclusion_type in set(ExclusionType)
        assert rule.rationale
        assert rule.applies_to_profile is None or rule.applies_to_profile


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


@pytest.mark.req("FR-404-AC2")
def test_distributed_sub_items_each_land_in_their_own_slot() -> None:
    """R54/WP-3 판정 ④ — 다섯 칸에 **서로 다른** 값을 주면 `formula()` 가 그
    다섯을 각각 제 이름표에 적는다.

    ⚠ 다섯에 같은 값을 주면 자리가 뒤바뀌어도 초록이 된다 — 그래서 다섯을
    모두 다르게 준다. ⚠ 0으로만 재면 「0이라 맞다」와 「자리가 맞다」가
    구별되지 않는다 — 그래서 전부 0이 아니다.
    """
    stream = DistributedBenefit(
        sub_items=DistributedSubItems(
            transmission_avoidance_won=11.0,
            loss_reduction_won=22.0,
            grid_service_won=33.0,
            ghg_reduction_won=44.0,
            resilience_won=55.0,
        )
    )
    formula = stream.formula(_dispatch_zeros(), year=1)

    assert "송배전 회피 11원 (특구 안에서 소비된 kWh)" in formula
    assert "손실 감소 22원 (특구 안에서 소비된 kWh)" in formula
    assert "계통서비스 33원 (계통에 제공한 양)" in formula
    assert "온실가스 44원 (특구 안에서 소비된 kWh)" in formula
    assert "회복력 55원 (미공급전력량 × 정전비용)" in formula  # noqa: RUF001
    assert stream.annual_value(_dispatch_zeros(), year=1) == to_won(11 + 22 + 33 + 44 + 55)


@pytest.mark.req("FR-404-AC4")
def test_sub_item_quantity_ids_keys_match() -> None:
    import dataclasses

    from core.valuestream.distributed_benefit import SUB_ITEM_QUANTITY_IDS, DistributedSubItems
    fields = {f.name for f in dataclasses.fields(DistributedSubItems)}
    keys = set(SUB_ITEM_QUANTITY_IDS.keys())
    assert fields == keys, (
        "하위 항목을 늘렸으면 그 항목이 무엇에 비례하는지 SUB_ITEM_QUANTITY_IDS 에 선언하라. "
        "「사용량 × 단가」 한 줄로 묶으면 계통서비스·리질리언스가 틀린 물량에 비례한다(판정 정본 §3)"  # noqa: E501, RUF001
    )
