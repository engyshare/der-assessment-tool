"""REC 수익 — FR-401-AC2.REC.

산식: 발전량 × 가중치 × REC 단가. 가중치는 자원 종류별로 다르다 (PV 1.0,
ESS 방전 0.5 등 — 규제 프로파일이 정한다).

⚠ **단가의 단위는 `원/kWh` 다.** 발전량이 kWh 이므로 그렇게만 곱이 맞는다 —
REC 는 통상 **1매 = 1MWh** 로 거래되므로 `원/REC` 로 받은 값은 **1,000 으로
나누어** 넘겨야 하며, 조항이 그 환산을 예시에 적어 두었다(`FR-401-AC2.REC`).
배포 경로가 이 단가를 받는 자리는 대장 `benefit.rec_price` 다
(`core/report/case_report.py::REC_PRICE_LEDGER_KEY` · 사용자 판정 §4).

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
            # ⚠ **단위는 원/kWh 다** — 왼쪽 항이 kWh 이므로 그렇게만 곱이 맞는다.
            # 종전 이 자리는 `원/REC` 라 적었고, REC 1매 = 1MWh 이므로 그 표기는
            # 산식을 **1,000배로 읽게** 했다. 조항이 이미 그 환산을 적어 두었다
            # (`FR-401-AC2.REC` 의 예: *「REC단가(70,000 원/REC ÷ 1,000)」*) —
            # 값이 아니라 **표기**가 조항과 갈려 있었다(R51/WP-6 이 표기를 고쳤다).
            f"× REC 단가 {self._price:,.0f}원/kWh"  # noqa: RUF001
        )

    @staticmethod
    def _generation_kwh(dispatch: DispatchResult) -> float:
        """발급 대상 발전량 — `electric` 양수 합. 음수(충전/소비)는 대상이 아니다."""
        return sum(max(0.0, e) for e in dispatch.electric)
