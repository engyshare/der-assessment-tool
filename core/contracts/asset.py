"""`CommonAsset` 계약 — 작업 1.3 / spec FR-106.

비에너지 공통설비(CEMS·HEMS·공용 계량/통신). **`DER` 을 상속하지 않는다.**

왜 별도 계약인가 (FR-106):
    CEMS·HEMS는 발전하지도 소비하지도 않으므로 `dispatch()`·매체 플래그·
    성능 저하가 성립하지 않는다. `DER` 에 끼워 넣으면 전 자원이 무의미한
    메서드를 구현하게 된다. 반대로 비용 계상에서 빼면 회수기간이 과소
    산정된다 — 10~20가구 실증에서 CEMS 개발·구축비와 연간 운영비는
    무시할 수 있는 규모가 아니다.

구현 위치는 `core/asset/` 이며 `core/der/` 가 아니다 — 정의와 디렉터리를
일치시킨다 (§16.3 WP-1f). v0.5는 정의만 분리하고 디렉터리는 `core/der/` 에
두어 어긋나 있었다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import ClassVar

from core.contracts.units import Money, won_sum


class AllocationRule(StrEnum):
    """안분 규칙 (FR-106-AC5). **선언적으로 지정한다.**

    선택한 규칙이 리포트에 명시되어야 한다 — 같은 총액이 규칙에 따라 가구별로
    전혀 다르게 배분되므로, 규칙을 밝히지 않은 가구당 부담액은 해석할 수 없다.
    """

    EQUAL_PER_HOUSEHOLD = "가구 균등 배분"
    BY_CAPACITY = "설비용량 비례"
    NO_ALLOCATION = "안분하지 않고 단지 총계로만 표시"


class CommonAsset(ABC):
    """비에너지 공통설비 계약 (FR-106-AC1).

    `capex()` / `fixed_om()` / `lifetime` / `replacement_schedule()` /
    `salvage_value()` 를 보유하되 **`dispatch()` 와 매체 플래그를 갖지 않는다.**
    """

    #: 기본 제공 유형은 `CEMS` · `HEMS` · `공용 계량·통신 설비` (FR-106-AC2)
    tag: ClassVar[str]

    name: str
    lifetime_sw: int
    lifetime_hw: int
    allocation: AllocationRule

    def __init__(
        self,
        *,
        name: str,
        lifetime_sw: int,
        lifetime_hw: int,
        allocation: AllocationRule = AllocationRule.EQUAL_PER_HOUSEHOLD,
    ) -> None:
        if not name:
            raise ValueError("공통설비 인스턴스는 이름을 갖습니다")
        for label, v in (("lifetime_sw", lifetime_sw), ("lifetime_hw", lifetime_hw)):
            if v <= 0:
                raise ValueError(f"{label} 은 1년 이상입니다: {v}")
        self.name = name
        self.lifetime_sw = lifetime_sw
        self.lifetime_hw = lifetime_hw
        self.allocation = allocation

    @property
    def lifetime(self) -> int:
        """대표 수명 — SW·HW 중 **짧은 쪽**.

        긴 쪽을 쓰면 짧은 쪽의 교체 시점이 분석기간 밖으로 밀려 교체비가
        빠진다. 실제 교체 일정은 `replacement_schedule()` 이 둘을 각각
        계산하며, 이 값은 표시·정렬용 대표치일 뿐이다.
        """
        return min(self.lifetime_sw, self.lifetime_hw)

    # ── FR-106-AC3: SW/HW 분리 계상 ─────────────────────────────────
    #
    # 감가상각 내용연수와 교체 주기가 다르고(SW는 재개발, HW는 교체)
    # 잔존가치 산정도 다르다. 합쳐 두면 어느 쪽 주기로 교체할지 정할 수 없다.

    @abstractmethod
    def capex_software(self, *, year: int) -> Money:
        """소프트웨어 개발비 (원)."""

    @abstractmethod
    def capex_hardware(self, *, year: int) -> Money:
        """하드웨어 구축비 (원)."""

    def capex(self, *, year: int) -> Money:
        """총 자본비 — SW + HW.

        구현체가 덮어쓰지 않는다. 합계 규칙이 자원마다 달라지면 SW/HW 분리
        계상(AC3)의 의미가 사라진다.
        """
        return won_sum([self.capex_software(year=year),
                        self.capex_hardware(year=year)])

    @abstractmethod
    def fixed_om(self, *, year: int) -> Money:
        """연간 운영비 (원/년) — 라이선스·클라우드·유지보수·관제 인건비.

        물가상승률을 적용한다 (FR-106-AC4). 이 항목을 빼면 CEMS가 초기
        구축비만 드는 설비로 보이는데, 실제로는 20년 누계가 구축비를 넘길
        수 있다.
        """

    @abstractmethod
    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """{교체 연도: 교체비}. SW 재개발과 HW 교체를 **각각** 반영한다."""

    @abstractmethod
    def salvage_value(self, *, year: int) -> Money:
        """잔존가치 (원). SW·HW의 잔존 수명이 다르므로 따로 계산해 합친다."""
