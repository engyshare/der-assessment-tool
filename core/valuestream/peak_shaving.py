"""기본요금(피크) 절감 — FR-401-AC2.PeakShaving.

산식: 월 최대수요 저감분 × 기본요금 단가. 월별 피크 저감량에 기본요금
단가(원/kW·월)를 곱한다.

**주의 — 자가소비·잉여판매와 동시 계상된다.** 이것은 중복이 아니다:
- 자가소비·잉여판매는 «전력량(kWh)» 에 대한 «전력량요금»
- 피크저감은 «전력(kW)» 에 대한 «기본요금»

물리량이 다르고 지불 주체(같은 주민이라도 다른 요금 항목)가 다르다 —
domain-rules §2 «동시 발생하는 다중 효과는 중복이 아님» (FR-402-AC1).

**오라클**: 순위 1 (해석해).
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import Payer, ValueStream


class PeakShaving(ValueStream):
    """피크(기본요금) 절감 — 월 최대수요 저감분 × 기본요금 단가.

    `monthly_peak_reduction_kw` 는 12개월 치 저감량(kW). `demand_charge_won_per_kw_month`
    는 기본요금 단가(원/kW·월).
    """

    tag = "PeakShaving"
    #: 생성자의 **월별 12개월** 감축량으로 계산한다 — 이미 연간값이다.
    scales_with_dispatch_window = False
    payer = Payer.RESIDENT

    MONTHS = 12

    def __init__(
        self,
        *,
        monthly_peak_reduction_kw: list[float],
        demand_charge_won_per_kw_month: float,
        enabled: bool = True,
    ) -> None:
        super().__init__(name="기본요금(피크) 절감", enabled=enabled)
        if len(monthly_peak_reduction_kw) != self.MONTHS:
            raise ValueError(
                f"월별 피크 저감량은 {self.MONTHS}개월 치여야 합니다: "
                f"받은 길이 {len(monthly_peak_reduction_kw)}"
            )
        if demand_charge_won_per_kw_month < 0:
            raise ValueError(
                f"기본요금 단가는 음수일 수 없습니다: {demand_charge_won_per_kw_month}"
            )
        self._monthly = list(monthly_peak_reduction_kw)
        self._charge = demand_charge_won_per_kw_month

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return to_won(0)
        total_kw_months = sum(self._monthly)
        return to_won(total_kw_months * self._charge)
