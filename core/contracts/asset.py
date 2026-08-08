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

**v1.1 개정 (계약 개정 1차).** 세 가지를 계약이 답한다.

    ① `capex_vat()`      §13.2.2 C-1 은 자원과 공통설비를 가리지 않는다
    ② SW/HW 분리 잔존가치 AC3 이 분리 계상을 요구하는데 잔존가치만 합계
                         하나였다 — SW·HW 잔존 수명이 다르므로 합계만으로는
                         어느 쪽 잔존인지 되짚을 수 없다
    ③ `AllocationResult` 안분 결과는 **구획 경계를 넘는 자료구조**다 (WP-7
                         프로포마·WP-10 리포트가 읽는다). §16.2 「데이터 스키마」
                         이므로 계약이 형(型)을 고정하고, 배분 알고리즘은
                         WP-1f 가 소유한다
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from core.contracts.units import Money, Year, won_sum


class AllocationRule(StrEnum):
    """안분 규칙 (FR-106-AC5). **선언적으로 지정한다.**

    선택한 규칙이 리포트에 명시되어야 한다 — 같은 총액이 규칙에 따라 가구별로
    전혀 다르게 배분되므로, 규칙을 밝히지 않은 가구당 부담액은 해석할 수 없다.
    """

    EQUAL_PER_HOUSEHOLD = "가구 균등 배분"
    BY_CAPACITY = "설비용량 비례"
    NO_ALLOCATION = "안분하지 않고 단지 총계로만 표시"


@dataclass(frozen=True)
class AllocationResult:
    """안분 결과 — **구획 경계 스키마** (§16.2 · FR-106-AC5).

    **스스로 합계 보존을 검사한다.** 자료구조가 검사하지 않으면, 다른 경로로
    만들어진 안분 결과가 리포트까지 흘러간 뒤에야 "가구 합계 ≠ 단지 총계"가
    발견된다. 그때는 어느 단계에서 어긋났는지 되짚을 수 없다 (NFR-103-M1).

    **배분 알고리즘은 여기 없다.** 규칙별 가중치 계산과 반올림 잔차 처리는
    WP-1f(`core/asset/`)가 소유한다 — 계약은 형(型)만 고정한다 (§16.2:
    *"구현은 포함하지 않는다"*).
    """

    rule: AllocationRule
    #: 안분 전 원액 (단지 총계)
    source_total: Money
    #: 가구별 부담액. 길이 = 가구 수
    per_household: tuple[Money, ...]
    #: 가구에 싣지 않고 단지 총계에만 남긴 금액 (미안분 규칙에서만 0이 아니다)
    unallocated: Money

    def __post_init__(self) -> None:
        got = won_sum([*self.per_household, self.unallocated])
        if got != self.source_total:
            raise ValueError(
                f"안분 합계가 원액과 다릅니다: {got} ≠ {self.source_total} "
                f"(규칙 {self.rule.value}). 안분 전후 합계는 오차 0원이어야 합니다 "
                "(FR-106-AC5 · NFR-103)"
            )

    @property
    def households(self) -> int:
        return len(self.per_household)

    @property
    def total(self) -> Money:
        """가구 합계 + 미안분. 정의상 항상 `source_total` 과 같다."""
        return won_sum([*self.per_household, self.unallocated])

    def describe(self) -> str:
        """리포트 표기용 한 줄. **규칙을 반드시 드러낸다** (FR-106-AC5).

        같은 총액이 규칙에 따라 다르게 배분되므로 규칙 없는 부담액은 해석 불가다.
        """
        return (
            f"안분 규칙: {self.rule.value} / 대상 {self.households}가구 / "
            f"총액 {self.source_total:,}원"
        )


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
    #: 운영비 물가상승률 — **소수(0~1)** (§7.5). `DER` 과 같은 이름·같은 척도다
    escalation_rate: float

    def __init__(
        self,
        *,
        name: str,
        lifetime_sw: int,
        lifetime_hw: int,
        allocation: AllocationRule = AllocationRule.EQUAL_PER_HOUSEHOLD,
        escalation_rate: float = 0.0,
    ) -> None:
        if not name:
            raise ValueError("공통설비 인스턴스는 이름을 갖습니다")
        for label, v in (("lifetime_sw", lifetime_sw), ("lifetime_hw", lifetime_hw)):
            if v <= 0:
                raise ValueError(f"{label} 은 1년 이상입니다: {v}")
        if not -1.0 < float(escalation_rate) < 1.0:
            raise ValueError(
                f"{name}: escalation_rate 는 -1~1 소수입니다: {escalation_rate}. "
                "2%는 0.02 입니다 (§7.5 — %(0~100)는 입력·표시 경계에서만 씁니다)"
            )
        self.name = name
        self.lifetime_sw = lifetime_sw
        self.lifetime_hw = lifetime_hw
        self.allocation = allocation
        self.escalation_rate = float(escalation_rate)

    @property
    def lifetime(self) -> int:
        """대표 수명 — SW·HW 중 **짧은 쪽**.

        긴 쪽을 쓰면 짧은 쪽의 교체 시점이 분석기간 밖으로 밀려 교체비가
        빠진다. 실제 교체 일정은 `replacement_schedule()` 이 둘을 각각
        계산하며, 이 값은 표시·정렬용 대표치일 뿐이다.
        """
        return min(self.lifetime_sw, self.lifetime_hw)

    def escalation_factor(self, *, year: int) -> float:
        """`year` 년차 물가 계수 = `(1 + escalation_rate)^(year−1)`. 1년차가 기준."""
        return (1.0 + self.escalation_rate) ** (int(Year(year)) - 1)

    # ── FR-106-AC3: SW/HW 분리 계상 ─────────────────────────────────
    #
    # 감가상각 내용연수와 교체 주기가 다르고(SW는 재개발, HW는 교체)
    # 잔존가치 산정도 다르다. 합쳐 두면 어느 쪽 주기로 교체할지 정할 수 없다.

    @abstractmethod
    def capex_software(self, *, year: int) -> Money:
        """소프트웨어 개발비 (원). **부가세 제외** — 세액은 `capex_vat()`."""

    @abstractmethod
    def capex_hardware(self, *, year: int) -> Money:
        """하드웨어 구축비 (원). **부가세 제외** — 세액은 `capex_vat()`."""

    def capex(self, *, year: int) -> Money:
        """총 자본비 — SW + HW. **부가세 제외.**

        구현체가 덮어쓰지 않는다. 합계 규칙이 자원마다 달라지면 SW/HW 분리
        계상(AC3)의 의미가 사라진다.
        """
        return won_sum([self.capex_software(year=year),
                        self.capex_hardware(year=year)])

    @abstractmethod
    def capex_vat(self, *, year: int) -> Money:
        """자본비의 부가세액 (원). 세액이 없으면 0.

        §13.2.2 C-1은 자원과 공통설비를 가리지 않는다 — CEMS 구축비도 부가세를
        낸다. v1.0 계약에 자리가 없어 WP-1f가 스스로 만들었고, 계약에 없는
        메서드는 엔진이 순회 집계할 수 없다.
        """

    @abstractmethod
    def fixed_om(self, *, year: int) -> Money:
        """연간 운영비 (원/년) — 라이선스·클라우드·유지보수·관제 인건비.

        물가상승률을 적용한다 (FR-106-AC4) — `escalation_factor(year=...)`.
        이 항목을 빼면 CEMS가 초기 구축비만 드는 설비로 보이는데, 실제로는
        20년 누계가 구축비를 넘길 수 있다.
        """

    @abstractmethod
    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """{교체 연도: 교체비}. SW 재개발과 HW 교체를 **각각** 반영한다.

        수명 도달 **다음** 연도 초에 계상한다 (§13.2.2 C-4).
        """

    # ── 잔존가치 — SW·HW 를 각각 돌려준다 (v1.1) ────────────────────
    #
    # v1.0 은 합계 하나만 요구했다. 그러면 AC3 「분리 계상」이 잔존가치에서만
    # 성립하지 않고, 리포트가 SW 잔존과 HW 잔존을 나눠 보여줄 수 없다.
    # SW 5년·HW 10년이면 8년차 잔존은 «SW 0 + HW 2/10» 이지 «합계의 2/10» 이
    # 아니다 — 합계만 받으면 그 차이를 되짚을 수 없다.

    @abstractmethod
    def salvage_software(self, *, year: int) -> Money:
        """SW 잔존가치 (원). **명목액** — 할인하지 않는다 (§13.2.2 C-5)."""

    @abstractmethod
    def salvage_hardware(self, *, year: int) -> Money:
        """HW 잔존가치 (원). **명목액** — 할인하지 않는다 (§13.2.2 C-5)."""

    def salvage_value(self, *, year: int) -> Money:
        """잔존가치 합계 (원) = SW + HW. **명목액이며 할인하지 않는다.**

        구현체가 덮어쓰지 않는다 — 합계 규칙이 설비마다 달라지면 분리 계상의
        의미가 사라진다. 할인은 재무 계층(WP-7)의 몫이며, 두 곳에서 하면
        두 번 할인되고 값이 작아지므로 「보수적으로 보여서」 검출되지 않는다.
        """
        return won_sum([self.salvage_software(year=year),
                        self.salvage_hardware(year=year)])
