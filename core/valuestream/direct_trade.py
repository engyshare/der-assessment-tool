"""분산특구 직접거래 차익 — FR-401-AC2.DirectTrade.

산식: (약관요금 − 직접거래단가) × 거래량 − 거래지원수수료.

**직접거래는 단독으로 성립하지 않는다.** 계약구조·요금 엔진(5.0)이 풀어야
하는 의존성을 여기서 직접 import 하지 않는다 (NFR-208-AC2). 단가와 수수료를
생성자에서 받아 산식만 계상한다 — 요금 엔진 통합은 별도 작업.

**오라클**: 순위 1 (해석해).
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ExclusionType, Payer, ValueStream


class DirectTrade(ValueStream):
    """직접거래 차익 — (약관요금 − 직접거래단가) × 거래량 − 수수료."""

    tag = "DirectTrade"
    #: 생성자의 **연간** 거래량으로 계산한다 — 디스패치를 보지 않는다.
    #: ⚠ 이 선언이 없던 동안 러너가 365를 곱해 **365배**로 계상했다(R34).
    scales_with_dispatch_window = False
    payer = Payer.OPERATOR

    def __init__(
        self,
        *,
        tariff_won_per_kwh: float,
        trade_price_won_per_kwh: float,
        trade_volume_kwh: float,
        support_fee_won: float = 0.0,
        enabled: bool = True,
        structure: str | None = None,
    ) -> None:
        super().__init__(
            name="분산특구 직접거래 차익", enabled=enabled, structure=structure
        )
        if trade_volume_kwh < 0:
            raise ValueError(
                f"거래량은 음수일 수 없습니다: {trade_volume_kwh}"
            )
        if support_fee_won < 0:
            raise ValueError(
                f"거래지원수수료는 음수일 수 없습니다: {support_fee_won}"
            )
        self._tariff = tariff_won_per_kwh
        self._trade = trade_price_won_per_kwh
        self._volume = trade_volume_kwh
        self._fee = support_fee_won

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        if not self.enabled:
            return to_won(0)
        spread = self._tariff - self._trade
        return to_won(spread * self._volume - self._fee)

    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        """(약관요금 − 직접거래단가) × 거래량 − 수수료 — `ValueStream.formula` 계약.

        ⚠ **괄호를 적는다.** 차를 먼저 내고 곱하는데, 괄호 없이 적으면
        `약관 − 거래단가 × 거래량` 으로 읽혀 **연산 순서가 뒤집힌다.**

        ★ **이 편익이 버는 것은 단가가 아니라 차익이다** — 두 단가를 각각
        적어야 어느 쪽이 움직여 금액이 바뀌었는지 검토자가 가린다.
        """
        return (
            f"(약관요금 {self._tariff:,.0f}원/kWh "
            f"− 직접거래단가 {self._trade:,.0f}원/kWh) "  # noqa: RUF001
            f"× 거래량 {self._volume:,.0f}kWh "  # noqa: RUF001
            f"− 거래지원수수료 {self._fee:,.0f}원"  # noqa: RUF001
        )

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        # 잉여를 직접거래와 상계거래로 동시에 팔 수 없다 (유형 A, domain-rules §2-A 표).
        return [(
            "SurplusSale",
            ExclusionType.A,
            "같은 잉여량을 직접거래와 상계거래(SurplusSale 의 한 형태)로 "
            "동시 정산할 수 없다 (유형 A)",
        )]
