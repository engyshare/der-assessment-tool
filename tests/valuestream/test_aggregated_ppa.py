"""집합 PPA 수익 — `FR-401-AC2.AggregatedPPA` (spec v0.16 신설) / R32.

R31 이 「집합 PPA」 구조를 미구현으로 남긴 사유는 **없는 편익 클래스**였다.
`SurplusSale` 로 대신하면 **자가소비분이 빠져 편익이 조용히 작아진다** — PPA 는
발전량 **전량**의 일괄 판매이고 잉여판매는 계통 역송분만 본다.

붙드는 것 다섯:

    ① 전량 × 단가                      손계산 오라클
    ② ★★ 디스패치를 보지 않는다        **잉여판매의 사본이 아니다**
    ③ ★ 잉여판매·자가소비와 배타다      유형 A 를 실행 경로가 거부한다
    ④ 음수 입력을 거부한다              부호가 뒤집힌 입력을 통과시키지 않는다
    ⑤ 조립기가 약관요금 × 비율을 쓴다    절대 단가를 대장에 두지 않는다

②가 요점이다. ①만 두면 **잉여 합을 쓰는 구현**도 통과한다(발전량과 잉여가 같은
케이스를 넣으면 값이 같다). 그 상태는 자가소비가 있는 사업에서만 조용히 작아지고,
작아진 쪽이 「보수적」으로 보이기까지 한다.
"""

from __future__ import annotations

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import AssumptionProvider, PriceBasis
from core.contracts.der import DispatchResult
from core.contracts.units import Money
from core.contracts.validation import ValidationError
from core.contracts.valuestream import Payer
from core.valuestream import AggregatedPPA, SelfConsumption, SurplusSale
from core.valuestream.exclusion_table import assert_no_exclusions
from core.valuestream.settlement import (
    PPA_RATIO_KEY,
    TARIFF_KEY,
    SettlementInputs,
    assemble,
)

STRUCTURE = "집합 PPA"

#: 손계산 오라클 — 대장에서 읽어 와 대장과 비교하면 무엇을 넣어도 통과한다.
TARIFF = 150.0
RATIO = 0.85
GENERATION = 10_000.0


def _provider() -> AssumptionProvider:
    def item(key: str, value: float, unit: str) -> AssumptionItem:
        return AssumptionItem(
            key=key, value=value, value_unit=unit, base_year="2026",
            applicable_scope="검사용", derivation_method="검사용",
            source=None, verified_at=None, confidence=ConfidenceLevel.ASSUMED,
        )

    return AssumptionSet(
        name="검사", version="1",
        items={
            TARIFF_KEY: item(TARIFF_KEY, TARIFF, "원/kWh"),
            PPA_RATIO_KEY: item(PPA_RATIO_KEY, RATIO, "소수"),
        },
        price_basis=PriceBasis.NOMINAL,
    )


def _dispatch(surplus_kwh: float) -> DispatchResult:
    return DispatchResult(electric=[surplus_kwh], heat=[0.0], cool=[0.0], fuel=[0.0])


@pytest.mark.req("FR-401-AC2.AggregatedPPA")
def test_the_whole_generation_is_sold_at_the_contract_price() -> None:
    """① 손계산 오라클 — 10,000 kWh × 127.5 원/kWh = **1,275,000 원**.

    127.5 = 약관요금 150 × 비율 0.85.
    """
    ppa = AggregatedPPA(
        ppa_price_won_per_kwh=TARIFF * RATIO, annual_generation_kwh=GENERATION
    )

    assert ppa.annual_value(_dispatch(0.0), year=1) == Money(1_275_000)


@pytest.mark.req("FR-401-AC2.AggregatedPPA")
def test_the_value_does_not_come_from_the_dispatch_surplus() -> None:
    """② ★★ 디스패치를 바꿔도 값이 같다 — **잉여판매의 사본이 아니다.**

    `DispatchResult.electric` 은 **순 계통 흐름**이라 자가소비분이 이미 상계돼
    있다. 거기서 전량을 복원할 수 없으므로 이 편익은 발전량을 생성자에서 받는다.
    잉여 합을 쓰는 구현이라면 잉여를 0 → 10,000 으로 바꿀 때 값이 따라 움직인다.
    """
    ppa = AggregatedPPA(
        ppa_price_won_per_kwh=TARIFF * RATIO, annual_generation_kwh=GENERATION
    )

    assert ppa.annual_value(_dispatch(0.0), year=1) == ppa.annual_value(
        _dispatch(GENERATION), year=1
    ), (
        "잉여를 바꾸자 PPA 수익이 달라졌습니다 — 디스패치의 잉여 합을 쓰고 있으며, "
        "그러면 자가소비가 있는 사업에서 편익이 조용히 작아집니다"
    )


@pytest.mark.req("FR-401-AC2.AggregatedPPA", "FR-402-AC2.A")
@pytest.mark.parametrize("other_tag", ["SurplusSale", "SelfConsumption"])
def test_the_ppa_excludes_both_surplus_sale_and_self_consumption(
    other_tag: str,
) -> None:
    """③ ★ 유형 A — **둘 다** 막힌다.

    잉여판매만 막으면 **자가소비와 PPA 를 동시에 켤 수 있고**, 그 조합은 계약
    상대에게 넘긴 kWh 를 집에서 또 쓴 것으로 계상한다. 편익이 커지는 방향으로
    틀리므로 필요 지원 규모가 과소 산정된다(원칙 2-1 이 막으려는 방향).
    """
    other = (
        SurplusSale(sale_price_won_per_kwh=100.0)
        if other_tag == "SurplusSale"
        else SelfConsumption(
            baseline_annual_bill_won=100.0, new_annual_bill_won=50.0
        )
    )
    ppa = AggregatedPPA(
        ppa_price_won_per_kwh=TARIFF * RATIO, annual_generation_kwh=GENERATION
    )

    with pytest.raises(ValidationError) as caught:
        assert_no_exclusions([ppa, other])

    assert caught.value.rule == "DV-12"
    assert other_tag in (caught.value.reason or "")


@pytest.mark.req("FR-401-AC2.AggregatedPPA", "NFR-303-M1")
@pytest.mark.parametrize(
    ("price", "generation"), [(-1.0, GENERATION), (TARIFF, -1.0)]
)
def test_negative_inputs_are_refused(price: float, generation: float) -> None:
    """④ 음수 단가·음수 발전량을 거부한다.

    음수 발전량은 소비이며, **계통 순흐름을 그대로 넘긴 경우**에 실제로 생긴다 —
    통과시키면 수익이 음수가 되어 「손해 보는 PPA」가 그럴듯하게 계산된다.
    """
    with pytest.raises(ValueError):
        AggregatedPPA(
            ppa_price_won_per_kwh=price, annual_generation_kwh=generation
        )


@pytest.mark.req("FR-401-AC2.AggregatedPPA", "FR-401-AC1")
def test_the_benefit_can_be_toggled_off() -> None:
    """편익 개별 토글 — `FR-401-AC1`. 끄면 0 원이다."""
    ppa = AggregatedPPA(
        ppa_price_won_per_kwh=TARIFF * RATIO,
        annual_generation_kwh=GENERATION,
        enabled=False,
    )

    assert ppa.annual_value(_dispatch(0.0), year=1) == Money(0)


@pytest.mark.req("FR-205-AC1.AggregatedPPA", "NFR-202-M1")
def test_the_assembler_multiplies_the_tariff_by_the_ledger_ratio() -> None:
    """⑤ 조립기가 **약관요금 × 비율**을 쓴다 — 절대 단가를 대장에 두지 않는다.

    손계산 오라클: 10,000 × (150 × 0.85) = **1,275,000 원**. 두 대장 키를 함께
    나르는 것도 본다 — 리포트가 「이 단가가 어디서 왔는가」에 답해야 한다.
    """
    plan = assemble(
        STRUCTURE,
        provider=_provider(),
        inputs=SettlementInputs(annual_generation_kwh=GENERATION),
    )
    (stream,) = plan.streams

    assert stream.annual_value(_dispatch(0.0), year=1) == Money(1_275_000)
    assert plan.assumption_keys == (TARIFF_KEY, PPA_RATIO_KEY)
    assert stream.effective_payer is Payer.OPERATOR


@pytest.mark.req("FR-205-AC1.AggregatedPPA", "NFR-303-M1")
def test_the_assembler_refuses_without_the_generation() -> None:
    """발전량이 없으면 거부한다 — 0 이면 「PPA 가 없는 사업」과 구별되지 않는다."""
    with pytest.raises(ValidationError) as caught:
        assemble(STRUCTURE, provider=_provider(), inputs=SettlementInputs())

    assert "annual_generation_kwh" in (caught.value.reason or "")
    assert (caught.value.action or "").strip()
