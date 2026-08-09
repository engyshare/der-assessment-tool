"""열 비용 절감 (히트펌프) — FR-41-AAC2.HeatCostSaving.

산식: (기존 열원 연료비 − 히트펌프 전력비). 히트펌프가 기존 보일러(가스·등유)를
대체할 때, 기존 열원이 들 연료비에서 히트펌프가 들 전력비를 뺀 증분.

**기준선은 «난방 안 함»이 아니라 «기존 보일러 유지»다** (도메인 원칙 1-3).
노후 보일러 교체 시점이면 교체 비용이 기준선에도 발생하므로, 신규 설비 비용
전액을 증분으로 잡으면 과대계상 — 이 편익은 «연료비 차이»만 계상한다.

**오라클**: 순위 1 (해석해).
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import Payer, ValueStream


class HeatCostSaving(ValueStream):
    """열비용 절감 — 기존 열원 연료비 − 히트펌프 전력비."""

    tag = "HeatCostSaving"
    payer = Payer.RESIDENT

    def __init__(
        self,
        *,
        baseline_fuel_cost_won_per_year: float,
        hp_electricity_cost_won_per_year: float,
        enabled: bool = True,
    ) -> None:
        super().__init__(name="열 비용 절감 (히트펌프)", enabled=enabled)
        self._baseline = baseline_fuel_cost_won_per_year
        self._hp = hp_electricity_cost_won_per_year

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return to_won(0)
        saving = self._baseline - self._hp
        return to_won(saving)
