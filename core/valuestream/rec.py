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
    #: 창에서 읽는다 — `dispatch.electric` 의 양수 합이 발급 대상 발전량이다.
    scales_with_dispatch_window = True
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
        return to_won(self._generation_kwh(dispatch) * self._weight * self._price)

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        """발전량 × 가중치 × 단가 — `ValueStream.formula` 계약.

        ★ **가중치를 산식에 싣는다.** 규제 프로파일이 정하는 값이라 대장·단가와
        다른 사람이 고치는데, 빠지면 검토자가 발전량과 단가만 곱해 보고 금액이
        맞지 않는다고 읽는다.
        """
        return (
            f"발전 {self._generation_kwh(dispatch):,.2f}kWh "
            f"× 가중치 {self._weight:,.2f} "  # noqa: RUF001
            f"× REC 단가 {self._price:,.0f}원/REC"  # noqa: RUF001
        )

    @staticmethod
    def _generation_kwh(dispatch: DispatchResult) -> float:
        """발급 대상 발전량 — `electric` 양수 합. 음수(충전/소비)는 대상이 아니다."""
        return sum(max(0.0, e) for e in dispatch.electric)
