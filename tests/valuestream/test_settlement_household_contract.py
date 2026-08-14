"""「개별 세대 직접계약」 조립 — `FR-205-AC1` / R32 (spec v0.16 결정).

R31 이 이 구조를 `NOT_YET_ASSEMBLED` 에 남긴 사유는 **값이 아니라 「정산 대상
미정」**이었다: 잉여 순액인지 자가소비 절감인지 조항이 적지 않았고, 배타 규칙표가
둘을 **유형 A**(동일 물리량 이중 판매)로 두므로 하나만 켤 수 있다.

**정한 것**: 정산 대상은 **계통 역송 전력(잉여)**, 판매 주체는 **가구**.
조항이 *「가구가 구매자와 **직접** 계약」* 이라 적으므로 파는 쪽이 가구이고,
계약의 대상이 될 수 있는 전력은 계량점 **밖으로 나가는 것**뿐이다.
근거는 spec `FR-205-AC1` v0.16 결정과 `docs/decisions-2026-08-14-R32.md` §3이며
**잠정이다**(실물 계약서가 결합형이면 대상이 넓어진다).

붙드는 것 다섯:

    ① 잉여 × 계약단가                손계산 오라클
    ② ★ 자가소비를 켜지 않는다        **결정을 값이 아니라 구조로 붙든다**
    ③ 지불 주체가 가구다              사업자로 두면 주민 편익이 사라진다
    ④ 단가가 없으면 거부한다          0 으로 메우면 계약 없는 사업과 같아진다
    ⑤ ★ 단가 필드를 다른 구조와 공유하지 않는다

②가 요점이다. ①만 두면 「무언가 계산된다」를 볼 뿐이고, **자가소비 절감으로
바꿔치기해도 그 값은 그럴듯하다** — 정산 대상이 무엇인지는 금액만 보고는
구별되지 않는다.
"""

from __future__ import annotations

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import AssumptionProvider, PriceBasis
from core.contracts.der import DispatchResult
from core.contracts.validation import ValidationError
from core.contracts.valuestream import Payer
from core.valuestream import SurplusSale
from core.valuestream.settlement import SettlementInputs, assemble

STRUCTURE = "개별 세대 직접계약"

#: 가구–구매자 계약단가. **협상값이므로 대장에 없다** — 손으로 적는다.
CONTRACT_PRICE = 130.0


def _provider() -> AssumptionProvider:
    """대장을 **비워** 둔다 — 이 구조가 대장 값을 하나도 읽지 않는 것이 뜻이다.

    항목이 있는 대장을 주면 「읽지 않았다」와 「읽었는데 안 썼다」가 구별되지
    않는다. 비워 두면 무엇이라도 읽는 구현은 `MissingAssumption` 으로 죽는다.
    """
    return AssumptionSet(
        name="검사", version="1", items={}, price_basis=PriceBasis.NOMINAL
    )


def _provider_with_items() -> AssumptionProvider:
    def item(key: str, value: float) -> AssumptionItem:
        return AssumptionItem(
            key=key, value=value, value_unit="원/kWh", base_year="2026",
            applicable_scope="검사용", derivation_method="검사용",
            source=None, verified_at=None, confidence=ConfidenceLevel.ASSUMED,
        )

    return AssumptionSet(
        name="검사", version="1",
        items={"tariff.hv_single_contract.avg": item("tariff.hv_single_contract.avg", 150.0)},
        price_basis=PriceBasis.NOMINAL,
    )


def _dispatch(surplus_kwh: float) -> DispatchResult:
    return DispatchResult(electric=[surplus_kwh], heat=[0.0], cool=[0.0], fuel=[0.0])


def _inputs(price: float | None = CONTRACT_PRICE) -> SettlementInputs:
    return SettlementInputs(household_contract_price_won_per_kwh=price)


@pytest.mark.req("FR-205-AC1.HouseholdDirect")
def test_the_household_sells_its_surplus_at_the_contract_price() -> None:
    """① 손계산 오라클 — 잉여 400 kWh × 130 원/kWh = **52,000 원**."""
    plan = assemble(STRUCTURE, provider=_provider(), inputs=_inputs())
    (stream,) = plan.streams

    assert stream.annual_value(_dispatch(400.0), year=1) == 400 * CONTRACT_PRICE


@pytest.mark.req("FR-205-AC1.HouseholdDirect", "FR-402-AC2.A")
def test_the_settlement_target_is_the_surplus_not_self_consumption() -> None:
    """② ★★ **정산 대상이 잉여다** — 자가소비 절감으로 바꿔치기하지 않았다.

    배타 규칙표가 둘을 유형 A 로 두므로 **하나만** 켤 수 있고, 그 선택이 편익을
    통째로 바꾼다. 금액만 보면 어느 쪽이든 그럴듯하므로 **자료형으로** 붙든다.

    조항이 *「가구가 구매자와 직접 계약」* 이라 적으므로 계약의 대상은 계량점
    **밖으로 나가는 전력**이다 — 자가소비분은 계약 상대에게 인도되지 않는다.
    """
    plan = assemble(STRUCTURE, provider=_provider(), inputs=_inputs())

    assert [type(s).tag for s in plan.streams] == ["SurplusSale"], (
        "정산 대상이 잉여가 아닙니다 — spec FR-205-AC1 v0.16 결정과 어긋납니다"
    )


@pytest.mark.req("FR-205-AC1.HouseholdDirect", "FR-402-AC5")
def test_the_payer_is_the_household() -> None:
    """③ 지불 주체가 **가구**다 — 사업자를 거치지 않는 것이 이 구조의 정의다.

    사업자로 두면 관점별 NPV 에서 주민 수익이 통째로 사라지고 **합계는 맞아서**
    드러나지 않는다(상계거래에서 같은 판단을 했다).

    **구조를 주지 않은 인스턴스와 대조한다** — 대조 없이 한쪽만 보면 클래스
    기본값이 우연히 같은 경우와 구별되지 않는다.
    """
    (stream,) = assemble(STRUCTURE, provider=_provider(), inputs=_inputs()).streams

    assert stream.effective_payer is Payer.RESIDENT
    assert SurplusSale(sale_price_won_per_kwh=1.0).effective_payer is Payer.OPERATOR


@pytest.mark.req("FR-205-AC1.HouseholdDirect", "NFR-202-M1")
def test_the_contract_price_does_not_come_from_the_ledger() -> None:
    """④의 짝 — 대장 값을 **하나도** 읽지 않는다(협상값이다).

    대장에 넣으면 「가정한 협상 결과」가 되고, 그것은 민감도로 드러나지 않는
    종류의 허구다. 빈 대장으로 조립이 성립하는 것이 그 증거다.
    """
    plan = assemble(STRUCTURE, provider=_provider(), inputs=_inputs())

    assert plan.assumption_keys == ()
    # 항목이 있는 대장을 주어도 결과가 같다 — 대장을 읽고 섞는 구현이 아니다
    other = assemble(STRUCTURE, provider=_provider_with_items(), inputs=_inputs())
    assert other.streams[0].annual_value(_dispatch(400.0), year=1) == plan.streams[
        0
    ].annual_value(_dispatch(400.0), year=1)


@pytest.mark.req("FR-205-AC1.HouseholdDirect", "NFR-303-M1")
def test_a_missing_contract_price_is_refused() -> None:
    """④ 단가가 없으면 거부한다 — 0 으로 메우지 않는다.

    0 이면 편익이 0 이 되어 **「계약이 없는 사업」과 구별되지 않고**, 그 결과는
    아무 예외 없이 그럴듯하다.
    """
    with pytest.raises(ValidationError) as caught:
        assemble(STRUCTURE, provider=_provider(), inputs=_inputs(price=None))

    assert caught.value.field == "model.contract.settlement_inputs"
    assert "household_contract_price_won_per_kwh" in (caught.value.reason or "")
    assert (caught.value.action or "").strip()


@pytest.mark.req("FR-205-AC1.HouseholdDirect")
def test_the_price_field_is_not_shared_with_the_district_trade_structure() -> None:
    """⑤ ★ 「분산특구 직접거래」의 단가로 이 구조가 조립되지 않는다.

    둘 다 협상값이지만 **서로 다른 협상의 결과**다. 한 필드를 공유하면 특구
    직접거래용으로 준 단가가 이 구조에 조용히 쓰이고, 거부 메시지도 어느 단가가
    없는지 말할 수 없게 된다.
    """
    with pytest.raises(ValidationError):
        assemble(
            STRUCTURE,
            provider=_provider(),
            inputs=SettlementInputs(
                trade_price_won_per_kwh=CONTRACT_PRICE, trade_volume_kwh=1_000.0
            ),
        )
