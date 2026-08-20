"""잉여 직거래가 상계와 **같은 편익 클래스**를 쓰는가 — `FR-205-AC1.SurplusDirectSale`.

spec 491행 문면은 *「상계와 **같은 산식**, 다른 단가」* 다.
`tests/valuestream/test_settlement.py::test_surplus_direct_sale_uses_a_different_price_than_net_metering`
는 대장이 준 서로 다른 단가로 두 구조의 금액이 실제로 갈리는 것만 본다 —
그것은 「다른 단가」의 절반이다. 이 파일이 붙드는 것은 나머지 절반인
「**같은** 산식」이다: 두 조립기가 정말 같은 편익 클래스(`SurplusSale`)로
계산하는지, 그래서 **단가만 같게 두면 두 구조가 수치까지 같아지는지**다.

spec 이 「같은 단가를 쓰면 두 구조가 수치까지 같아지고 `FR-202` 비교표에
같은 줄이 두 번 나온다」고 적은 것이 이 조항의 위험 서술 그 자체이므로,
그 문장이 실제로 성립하는지(단가를 맞추면 정말 같아지는지)를 검산한다 —
성립하지 않으면(단가를 맞췄는데도 갈리면) 두 조립기가 실은 다른 산식을
쓰고 있다는 뜻이고, spec 이 적은 그 위험은 성립하지 않는 것이 된다.

⚠ 이 검사는 `FR-205-AC1.NetMetering` 을 재지 않는다 — 상계거래는 여기서
**대조**로만 쓰인다. 상계거래 자체의 정산 로직(차감단가가 약관요금인가 등)은
`test_settlement.py` 가 이미 잰다.
"""
from __future__ import annotations

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.contracts.assumptions import AssumptionProvider, PriceBasis
from core.contracts.der import DispatchResult
from core.valuestream import SurplusSale
from core.valuestream.settlement import SURPLUS_SALE_KEY, TARIFF_KEY, assemble


def _provider(price: float) -> AssumptionProvider:
    def item(key: str, value: float) -> AssumptionItem:
        return AssumptionItem(
            key=key, value=value, value_unit="원/kWh", base_year="2026",
            applicable_scope="검사용", derivation_method="검사용",
            source=None, verified_at=None, confidence=ConfidenceLevel.ASSUMED,
        )

    return AssumptionSet(
        name="검사", version="1",
        items={
            TARIFF_KEY: item(TARIFF_KEY, price),
            SURPLUS_SALE_KEY: item(SURPLUS_SALE_KEY, price),
        },
        price_basis=PriceBasis.NOMINAL,
    )


def _dispatch(surplus_kwh: float) -> DispatchResult:
    return DispatchResult(electric=[surplus_kwh], heat=[0.0], cool=[0.0], fuel=[0.0])


@pytest.mark.req("FR-205-AC1.SurplusDirectSale")
def test_the_two_structures_share_the_benefit_class() -> None:
    """★★ 두 조립기가 **같은 `SurplusSale` 클래스**로 계산한다.

    클래스가 다르면 단가를 맞춰도 금액이 같아진다는 보장이 없다 — 그래서
    아래 「단가를 맞추면 같아진다」검사보다 먼저 클래스 자체를 고정한다.
    """
    (net,) = assemble("상계거래", provider=_provider(150.0)).streams
    (direct,) = assemble("잉여 직거래", provider=_provider(150.0)).streams

    assert type(net) is SurplusSale
    assert type(direct) is SurplusSale


@pytest.mark.req("FR-205-AC1.SurplusDirectSale")
def test_prices_made_equal_collapse_the_two_structures_to_the_same_number() -> None:
    """★★★ **단가가 같아지면 두 구조가 수치까지 같아진다** — spec 이 적어 둔 그 사유.

    대장의 실측값(약관요금 150 · 잉여 직거래 110)이 이미 다르다는 것은
    `test_settlement.py` 가 잰다. 이 검사는 그와 반대로 **두 키에 일부러
    같은 값을 넣어** spec 이 우려하는 「단가가 같아진」 상태를 직접 만들고,
    그 상태에서 두 구조가 정말 같은 금액을 내는지 본다.
    """
    same_provider = _provider(150.0)
    (net,) = assemble("상계거래", provider=same_provider).streams
    (direct,) = assemble("잉여 직거래", provider=same_provider).streams

    surplus = _dispatch(500.0)
    assert net.annual_value(surplus, year=1) == direct.annual_value(surplus, year=1), (
        "단가를 같게 두었는데 두 구조의 금액이 다릅니다 — 「같은 산식」이 "
        "깨졌거나, 조립기 중 하나가 다른 편익 클래스를 쓰고 있습니다"
    )
