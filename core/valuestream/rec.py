"""REC 수익 — FR-401-AC2.REC.

산식: 발전량 × 가중치 × REC 단가. 가중치는 자원 종류별로 다르다 (PV 1.0,
ESS 방전 0.5 등 — 규제 프로파일이 정한다).

**오라클**: 순위 1 (해석해) — 곱셈으로 손계산 재현 가능.
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import Payer, ValueStream


class REC(ValueStream):
    """REC 수익 — 발전량 × 가중치 × 단가."""

    tag = "REC"
    payer = Payer.OPERATOR

    def __init__(
        self,
        *,
        weight: float,
        rec_price_won_per_unit: float,
        enabled: bool = True,
        structure: str | None = None,
    ) -> None:
        super().__init__(name="REC 수익", enabled=enabled, structure=structure)
        if weight < 0:
            raise ValueError(
                f"REC 가중치는 음수일 수 없습니다: {weight}. "
                "규제 프로파일(REG-REC-W)의 값을 확인하십시오"
            )
        if rec_price_won_per_unit < 0:
            raise ValueError(
                f"REC 단가는 음수일 수 없습니다: {rec_price_won_per_unit}"
            )
        self._weight = weight
        self._price = rec_price_won_per_unit

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return to_won(0)
        # 발전량 = electric 양수 합. 음수(충전/소비)는 REC 대상이 아니다.
        generation_kwh = sum(max(0.0, e) for e in dispatch.electric)
        return to_won(generation_kwh * self._weight * self._price)
