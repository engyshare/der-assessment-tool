"""`DER` 계약 — 작업 1.2 / spec FR-101.

모든 분산자원이 구현하는 공통 추상 인터페이스. **구현은 포함하지 않는다**
(§16.2 — Wave 0에서 고정하는 것은 인터페이스·스키마·단위·계약테스트뿐이다).

**6개 메서드를 전부 추상으로 두는 이유.** 기본 구현을 주면 구현체가 잊어도
통과한다. 잊힌 메서드는 기본값을 돌려주고, 그 기본값이 0원이면 **비용이
조용히 사라진다.** 회수기간이 짧게 나오고 필요 지원액이 과소 산정되는데,
화면상으로는 정상이다. 그래서 잊으면 인스턴스화 자체가 실패하게 둔다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from core.contracts.units import (
    SECONDS_PER_HOUR,
    Money,
    Year,
    steps_per_year,
)


@dataclass(frozen=True)
class DispatchResult:
    """한 자원의 한 해 운전 결과 — 매체별 시계열 (kWh, 스텝당).

    **매체 4종을 항상 갖는다.** 하나라도 없으면 그 매체를 다루는 자원이 값을
    실을 곳이 없어지고, 구현자는 다른 계열에 섞어 넣는다. 섞인 값은 수지
    분리(FR-101-AC4)를 무의미하게 만들고, 전기 수지에 열이 섞여도
    NFR-102 균형 검사는 통과한다 — 총량은 맞기 때문이다.

    부호 규약: **양수 = 계통·수요 측에 내보냄(발전·방전), 음수 = 받아들임
    (소비·충전).** 자원마다 부호를 뒤집으면 합산이 조용히 상쇄된다.
    """

    electric: list[float]
    heat: list[float]
    cool: list[float]
    fuel: list[float]

    @classmethod
    def zeros(cls, steps: int) -> DispatchResult:
        return cls(
            electric=[0.0] * steps,
            heat=[0.0] * steps,
            cool=[0.0] * steps,
            fuel=[0.0] * steps,
        )

    def __post_init__(self) -> None:
        lengths = {
            len(self.electric), len(self.heat), len(self.cool), len(self.fuel)
        }
        if len(lengths) != 1:
            raise ValueError(
                f"매체별 시계열 길이가 다릅니다: {lengths}. "
                "길이가 다르면 스텝별 수지 합산이 어긋난 시각끼리 더해집니다"
            )


@dataclass(frozen=True)
class DispatchContext:
    """디스패치 1회 실행의 입력 맥락.

    엔진이 자원에게 건네는 **유일한 통로**다. 자원이 엔진을 import하지 않고도
    (FR-101-AC3 · NFR-208-AC1) 필요한 것을 받게 하는 것이 목적이다.
    """

    steps: int
    dt: int
    year: Year
    #: 스텝별 외기온(℃) — 히트펌프 COP 곡선용. 없으면 자원이 기본값을 쓴다
    ambient_temp_c: list[float] | None = field(default=None)
    #: 스텝별 계통 연계 용량 상한(kW). None이면 무제한
    grid_limit_kw: list[float] | None = field(default=None)

    def __post_init__(self) -> None:
        if self.steps <= 0:
            raise ValueError(f"스텝 수는 1 이상이어야 합니다: {self.steps}")
        # dt 검증은 units 에 위임한다 — 해상도 규약이 두 곳에 있으면 갈린다
        steps_per_year(self.dt)
        object.__setattr__(self, "year", Year(int(self.year)))

        for name, series in (("ambient_temp_c", self.ambient_temp_c),
                             ("grid_limit_kw", self.grid_limit_kw)):
            if series is not None:
                self.check_series(series, name=name)

    def check_series(self, series, *, name: str) -> None:
        """시계열 행수 불일치를 **명확한 오류로 중단**한다 (FR-301-AC3).

        조용히 자르거나 0으로 채우면 어느 해의 어느 시각이 어긋났는지 영영
        모른다. 8760행짜리 부하에 8759행 발전을 붙이면 마지막 한 시간이
        통째로 사라지는데, 연 합계로는 0.01% 차이라 눈에 띄지 않는다.
        """
        if len(series) != self.steps:
            raise ValueError(
                f"{name} 시계열 스텝 수가 맞지 않습니다: "
                f"{len(series)}행, 기대 {self.steps}행"
            )


class DER(ABC):
    """분산자원 공통 계약 (FR-101).

    구현체는 `core/der/<tag>.py` 에 **파일 1개 = 자원 1종**으로 둔다 (§16.3).
    """

    #: 레지스트리 키이자 클래스명. spec FR-102-AC1.<tag> 의 키와 같은 리터럴을
    #: 쓴다 — 여기서 슬러그화하거나 대소문자를 바꾸면 spec의 조항 ID와
    #: 어긋나고, 어긋난 순간 NFR-106 레지스트리 순회 검사가 헛돈다.
    tag: ClassVar[str]

    # ── FR-101-AC1 속성 ─────────────────────────────────────────────
    name: str
    dt: int
    carries_electric: bool
    carries_heat: bool
    carries_cool: bool
    consumes_fuel: bool
    lifetime: int
    degradation_rate: float

    def __init__(
        self,
        *,
        name: str,
        dt: int = SECONDS_PER_HOUR,
        lifetime: int,
        degradation_rate: float = 0.0,
        carries_electric: bool = False,
        carries_heat: bool = False,
        carries_cool: bool = False,
        consumes_fuel: bool = False,
    ) -> None:
        if not name:
            raise ValueError("자원 인스턴스는 이름을 갖습니다 — 리포트에서 "
                             "같은 유형의 두 인스턴스를 구분하는 유일한 수단입니다 "
                             "(FR-103)")
        steps_per_year(dt)
        if lifetime <= 0:
            raise ValueError(f"lifetime 은 1년 이상입니다: {lifetime}")
        if not 0.0 <= degradation_rate < 1.0:
            raise ValueError(
                f"degradation_rate 는 0~1 소수입니다: {degradation_rate}. "
                "3%는 0.03 입니다 (§7.5 비율 — 코드 내부는 소수로 정규화)"
            )
        if not any((carries_electric, carries_heat, carries_cool, consumes_fuel)):
            raise ValueError(
                f"{name}: 매체 플래그가 전부 거짓입니다. 어느 수지에도 잡히지 "
                "않는 자원은 비용만 계상되고 편익은 사라집니다. "
                "발전도 소비도 하지 않는 설비라면 `DER` 이 아니라 "
                "`CommonAsset` 입니다 (FR-106)"
            )

        self.name = name
        self.dt = dt
        self.lifetime = lifetime
        self.degradation_rate = degradation_rate
        self.carries_electric = carries_electric
        self.carries_heat = carries_heat
        self.carries_cool = carries_cool
        self.consumes_fuel = consumes_fuel

    # ── FR-101-AC2 메서드 ───────────────────────────────────────────
    #
    # 금액을 돌려주는 넷은 전부 `Money`(정수 원)다 — NFR-103 재무 계층.
    # `year` 를 받는 이유: 물가상승률·열화가 연도별로 다르게 걸리므로,
    # 연도 없는 금액은 어느 해의 값인지 판정할 수 없다 (FR-701-AC3).

    @abstractmethod
    def capex(self, *, year: int) -> Money:
        """자본비 (원). 초기 투자는 보통 1년차에만 발생한다."""

    @abstractmethod
    def fixed_om(self, *, year: int) -> Money:
        """고정 O&M (원/년). 설비 보유에 비례하며 운전량과 무관하다."""

    @abstractmethod
    def variable_om(self, *, year: int) -> Money:
        """변동 O&M (원/년). 운전량에 비례한다."""

    @abstractmethod
    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """{교체 연도: 교체비}. 분석기간 안의 것만 담는다.

        **부속설비의 독립 수명을 여기서 표현한다** (FR-104-AC4) — 인버터
        10~12년은 PV 본체 25년과 별개로 교체된다. 본체 수명만 보면 20년
        분석에서 인버터 교체비가 통째로 빠진다.
        """

    @abstractmethod
    def salvage_value(self, *, year: int) -> Money:
        """분석기간 종료 시 잔존가치 (원). 잔존 수명에 비례 (FR-104-AC5)."""

    @abstractmethod
    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        """한 해 운전 시뮬레이션.

        **플래그가 거짓인 매체에 값을 실으면 안 된다.** 엔진은 플래그를 보고
        수지를 분리 집계하므로, 거짓인 매체의 값은 어느 수지에도 잡히지 않고
        사라진다. 사라진 에너지는 NFR-102 균형 검사도 통과한다 — 애초에
        집계 대상이 아니기 때문이다. 계약 테스트가 이것을 검사한다.
        """
