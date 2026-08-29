"""진입점에서 「상계거래」와 「잉여 직거래」의 NPV 가 갈리는가 — `FR-205-AC1.SurplusDirectSale`.

`tests/valuestream/test_settlement.py::test_surplus_direct_sale_uses_a_different_price_than_net_metering`
는 **조립기 수준**(`assemble()` 을 직접 부른다)에서 두 구조가 다른 금액을 내는
것을 본다. `tests/casegrid/test_e2e_settlement_wiring.py` 는 상계거래 **하나만**
「구조 없음」과 대조해 진입점(`run_single_case_e2e`)을 지나는지 본다 — **두
구조를 진입점에서 나란히 놓고 갈리는지는 아무도 보지 않는다.**

★ 왜 이 자리가 따로 필요한가: 조립기에서 두 구조가 갈려도, 진입점의
파이프라인이 그 결과를 버리거나 뭉개면(예: `plan.streams` 배선이 구조를
무시하면) 케이스 표에는 **같은 줄이 두 번** 나온다 — spec 491행이 우려하는
바로 그 상태이며, 조립기 단위 검사는 진입점을 부르지 않으므로 그것을 볼 수
없다.
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from core.assumption.item import AssumptionItem, ConfidenceLevel
from core.assumption.provider import AssumptionSet
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import design_levels
from core.contracts.assumptions import AssumptionProvider, PriceBasis
from core.valuestream.settlement import SURPLUS_SALE_KEY, TARIFF_KEY

#: 분석기간 탐침값 — 이 파일의 관심이 아니다.
_PROBE_HORIZON = 18

#: 대장을 읽지 않는다 — 이 파일이 보는 것은 배선이지 금액의 크기가 아니다.
_LEVEL_MAP = {
    "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
    "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
    "discount_rate": MappingProxyType({"base": 0.045}),
    "grid_purchase_price": MappingProxyType({"base": 100.0}),
    "surplus_sale_price": MappingProxyType({"base": 90.0}),
    # 교체 설비단가의 실질 추세 — 러너가 요구한다(R42 에 스윕 축으로 올렸다).
    # **0 은 대장의 사본이 아니라 중립값이다** — 0 이면 명목 교체단가가 물가
    # 계수만 타므로 이 축을 흔들지 않는 것과 같다. 이 파일은 그 축을 재지
    # 않으므로 중립을 고른다(대장의 base 가 바뀌어도 여기는 따라오지 않아야
    # 한다 — 따라오면 이 파일이 대장의 사본을 갖게 된다).
    "replacement_real_trend": MappingProxyType({"base": 0.0}),
    **design_levels(),
}


def _provider() -> AssumptionProvider:
    def item(key: str, value: float) -> AssumptionItem:
        return AssumptionItem(
            key=key, value=value, value_unit="원/kWh", base_year="2026",
            applicable_scope="검사용", derivation_method="검사용",
            source=None, verified_at=None, confidence=ConfidenceLevel.ASSUMED,
        )

    return AssumptionSet(
        name="검사", version="1",
        items={
            TARIFF_KEY: item(TARIFF_KEY, 150.0),
            SURPLUS_SALE_KEY: item(SURPLUS_SALE_KEY, 110.0),
        },
        price_basis=PriceBasis.NOMINAL,
    )


@pytest.mark.req("FR-205-AC1.SurplusDirectSale")
def test_the_two_structures_diverge_through_the_entry_point() -> None:
    """★★★ 진입점을 지나서도 두 구조의 NPV 가 다르다.

    같은 입력(같은 전제 대장·같은 수준표)으로 **구조만** 바꿔 돌린다 —
    조립기가 갈라도 파이프라인이 뭉개면 여기서 같아진다.
    """
    net = run_single_case_e2e(
        {}, level_map=_LEVEL_MAP, horizon_years=_PROBE_HORIZON,
        structure="상계거래", provider=_provider(),
    )
    direct = run_single_case_e2e(
        {}, level_map=_LEVEL_MAP, horizon_years=_PROBE_HORIZON,
        structure="잉여 직거래", provider=_provider(),
    )

    assert net.metrics["npv"] != direct.metrics["npv"], (
        "구조를 「상계거래」→「잉여 직거래」로 바꿨는데 진입점의 NPV 가 "
        "같습니다 — 조립기 결과가 파이프라인에서 버려지거나 뭉개지고 있습니다"
    )
