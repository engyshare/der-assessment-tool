"""집합 PPA 수익 — `FR-401-AC2.AggregatedPPA` (v0.16 신설) / R32.

산식: **발전량 전량** × PPA 계약단가. 계약단가는 약관요금 × 비율(`Q-15`)이며
비율은 대장이 갖는다 — 절대 단가를 대장에 두지 않는 이유는 약관요금이 개정될 때
둘이 어긋나기 때문이다(그 어긋남은 아무 예외도 내지 않는다).

## ★★ 왜 `SurplusSale` 로 대신하지 않는가

R31 이 `NOT_YET_ASSEMBLED` 에 적어 둔 사유가 이것이다: **PPA 는 발전량 전량의
일괄 판매이고 `SurplusSale` 은 계통 역송분(잉여)만 본다.** 잉여판매로 대신하면
**자가소비분이 빠져 편익이 조용히 작아진다** — 금액은 그럴듯하고, 작아진 쪽이
보수적으로 보이기까지 한다. 그래서 파일을 하나 더 둔다(편익 1종 = 파일 1개,
`FR-401-AC1`).

## 발전량을 생성자에서 받는 이유

`DispatchResult.electric` 은 **순 계통 흐름**이다(양수 = 역송). 전량 발전량은
거기서 복원할 수 없다 — 자가소비분이 이미 상계되어 있기 때문이다. 디스패치에서
「양수 합」을 쓰면 그것이 곧 잉여이고, 그 순간 이 클래스는 `SurplusSale` 의
사본이 된다. `DirectTrade` 가 거래량을 생성자에서 받는 것과 같은 형태다.

## 지불 주체 — **잠정**

집합 PPA 는 여러 세대·자원을 **묶어** 파는 구조이므로 판매 당사자는 집합 대표
(사업자)로 두었다(기본값 `OPERATOR`). ⚠ **관리규약·집합 계약서에 따라 정산금이
세대로 직접 배분되는 형태면 `RESIDENT` 로 바뀐다** — 그때 바뀌는 것은
`payer_by_structure` 한 줄이다(`docs/decisions-2026-08-14-R32.md` §4).
"""
from __future__ import annotations

from core.contracts.der import DispatchResult
from core.contracts.units import Money, to_won
from core.contracts.valuestream import ExclusionType, Payer, ValueStream


class AggregatedPPA(ValueStream):
    """집합 PPA 수익 — 발전량 **전량** × 계약단가."""

    tag = "AggregatedPPA"
    #: 생성자의 **연간 전량** 발전량으로 계산한다 — 디스패치를 보지 않는다.
    #: ⚠ 이 선언이 없던 동안 러너가 365를 곱해 **365배**로 계상했다(R34).
    scales_with_dispatch_window = False
    payer = Payer.OPERATOR

    def __init__(
        self,
        *,
        ppa_price_won_per_kwh: float,
        annual_generation_kwh: float,
        enabled: bool = True,
        structure: str | None = None,
    ) -> None:
        super().__init__(name="집합 PPA 수익", enabled=enabled, structure=structure)
        if ppa_price_won_per_kwh < 0:
            raise ValueError(
                f"PPA 계약단가는 음수일 수 없습니다: {ppa_price_won_per_kwh}. "
                "음수 단가는 판매가 아닌 지불이며, 입력 부호가 바뀐 것인지 "
                "확인하십시오"
            )
        if annual_generation_kwh < 0:
            raise ValueError(
                f"연간 발전량은 음수일 수 없습니다: {annual_generation_kwh}. "
                "음수 발전량은 소비이며, 계통 순흐름을 그대로 넘긴 것인지 "
                "확인하십시오 — 이 편익이 받는 것은 **전량 발전량**입니다"
            )
        self._price = ppa_price_won_per_kwh
        self._generation = annual_generation_kwh

    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        """전량 × 단가. **디스패치를 보지 않는다** — 위 독스트링의 근거다."""
        if not self.enabled:
            return to_won(0)
        return to_won(self._generation * self._price)

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        """전량을 팔았으므로 **잉여판매도 자가소비도 함께 켤 수 없다** (유형 A).

        둘을 함께 적는 것이 요점이다. 잉여판매만 막으면 **자가소비 절감과 PPA 를
        동시에 켤 수 있고**, 그러면 계약 상대에게 넘긴 kWh 를 집에서 또 쓴 것으로
        계상된다 — 같은 1 kWh 를 두 번 화폐화하는 유형 A 그대로다.
        """
        return [
            (
                "SurplusSale",
                ExclusionType.A,
                "집합 PPA 는 발전량 전량을 팔았으므로 잉여판매로 다시 팔 수 없다 "
                "(유형 A)",
            ),
            (
                "SelfConsumption",
                ExclusionType.A,
                "집합 PPA 로 넘긴 kWh 는 자가소비가 아니다 — 동일 물리량 이중 "
                "계상 (유형 A)",
            ),
        ]
