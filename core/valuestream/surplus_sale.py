"""잉여전력 판매 — FR-401-AC2.SurplusSale.

산식: 잉여량 × 판매단가(직거래/상계/SMP). 잉여는 계통으로 내보낸 전력
(``DispatchResult.electric`` 의 양수 합)이다.

**오라클**: 순위 1 (해석해) — 총량 × 단가의 곱으로 손계산 재현 가능.
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ExclusionType, Payer, ValueStream


class SurplusSale(ValueStream):
    """잉여전력 판매 — 계통으로 내보낸 양 × 단가.

    판매단가는 판매 경로(직거래·상계·SMP)에 따라 다르다. 단일 단가를
    생성자에서 받고, 여러 경로가 섞이면 인스턴스를 여러 개 둔다 (FR-401-AC1).
    """

    tag = "SurplusSale"
    payer = Payer.OPERATOR

    def __init__(
        self, *, sale_price_won_per_kwh: float, enabled: bool = True
    ) -> None:
        super().__init__(name="잉여전력 판매", enabled=enabled)
        if sale_price_won_per_kwh < 0:
            raise ValueError(
                f"판매단가는 음수일 수 없습니다: {sale_price_won_per_kwh}. "
                "음수 단가는 판매가 아닌 지불이며, 입력 부호가 바뀐 것인지 확인하십시오"
            )
        self._price = sale_price_won_per_kwh

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return to_won(0)
        # electric 양수 = 계통으로 내보낸 전력(잉여). 음수(소비)는 0으로 클램프.
        surplus_kwh = sum(max(0.0, e) for e in dispatch.electric)
        return to_won(surplus_kwh * self._price)

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        # 자가소비한 kWh 와 잉여 kWh 는 같은 1 kWh 를 두 용도로 쓸 수 없다 (유형 A).
        return [(
            "SelfConsumption",
            ExclusionType.A,
            "잉여로 판 매 kWh 는 자가소비가 아님 — 동일 물리량 이중 판매 (유형 A)",
        )]
