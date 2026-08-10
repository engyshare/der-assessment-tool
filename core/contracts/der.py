"""`DER` 계약 — 작업 1.2 / spec FR-101.

모든 분산자원이 구현하는 공통 추상 인터페이스. **구현은 포함하지 않는다**
(§16.2 — Wave 0에서 고정하는 것은 인터페이스·스키마·단위·계약테스트뿐이다).

**6개 메서드를 전부 추상으로 두는 이유.** 기본 구현을 주면 구현체가 잊어도
통과한다. 잊힌 메서드는 기본값을 돌려주고, 그 기본값이 0원이면 **비용이
조용히 사라진다.** 회수기간이 짧게 나오고 필요 지원액이 과소 산정되는데,
화면상으로는 정상이다. 그래서 잊으면 인스턴스화 자체가 실패하게 둔다.

**v1.1 개정 (계약 개정 1차) — 자원 6종 병렬 구현이 드러낸 구멍을 메운다.**
6개 구획이 같은 계약을 서로 모른 채 구현하자, 계약이 답하지 않은 질문이 각자
다른 답으로 메워졌다. 아래 5건이 그 목록이며 이 판에서 계약이 답한다.

    ① 부분 창 해석      `steps` 가 한 해보다 짧을 때 무엇을 뜻하는가
                        → **연초부터 연속 `steps` 스텝.** `year_fraction` 으로 안분
    ② 부가세 분리       §13.2.2 C-1 이 요구하는데 자리가 없어 6종이 각자 지었다
                        → `capex_vat()` 추상. ESS 는 아예 없어 세액이 사라져 있었다
    ③ 편익 없음 강제    `RC-LD-B0`(부하는 편익을 만들지 않는다)이 성실성에 달려 있었다
                        → `value_streams()` 기본 `()`. 기본값 「편익 없음」은 보수적이다
    ④ 운전 방법 접근자  FR-105-AC5(케이스 그리드 탐색 변수)가 균일 접근을 요구하는데
                        `mode` / `operating_mode` 로 이름이 갈렸다 → 이름 고정
    ⑤ 물가상승률        `inflation_pct`(%) / `inflation_rate`(소수) / `om_escalation`
                        → `escalation_rate` **소수** 하나. 척도가 갈리면 100배 틀린다

**v1.2 개정 (계약 개정 2차) — Wave 1 착수 전에 답해야 하는 두 건.**
v1.1 이 «이미 갈린 것» 을 모았다면 이 판은 «갈리기 직전의 것» 을 막는다.
두 건 모두 `status.md` 「미해결」이 *착수 전 판단*으로 남겨 둔 항목이다.

    ⑥ 요금·연료 단가    자원 다섯이 `elec_price_won_per_kwh` 계열을 각자 들고
                        있어 **요금제 개정이 자원 코드 수정**이 된다. 요금 구조는
                        WP-3 소관이다 → `DispatchContext` 에 **가격 신호**로 싣는다.
                        「요금」이 아니라 「신호」인 것이 요점이다
    ⑦ 전제 대장 읽기    `tax.vat_rate` 가 대장에 있으나 **아무도 읽지 않는다.**
                        `vat_rate=0.0` 은 「세율 0%」가 아니라 「주입되지 않음」이며
                        둘은 프로포마에서 구별되지 않는다
                        → `core.contracts.assumptions.AssumptionProvider` 신설
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sized
from dataclasses import dataclass, field
from typing import ClassVar, cast

from core.contracts.units import (
    SECONDS_PER_HOUR,
    Money,
    Year,
    steps_per_year,
)

#: `FR-104-AC3` 수명 도달 시 처리 — **리터럴을 여기서만 정의한다.**
#: 자원 6종이 각자 `"retire"` 를 적으면 그중 하나의 오타를 아무도 잡지 못한다.
EOL_REPLACE = "replace"
EOL_RETIRE = "retire"
EOL_ACTIONS: frozenset[str] = frozenset({EOL_REPLACE, EOL_RETIRE})

# ── `retire` 의 의미 — 구현 전에 정한 것 (R12, 사용자 결정) ──────────────
#
# ★ **정본은 이제 spec `FR-104-AC3` 아래 「`retire` 의 의미」다** (spec v0.14).
#   R13 에 그리로 옮겼다. **바뀌면 spec 을 먼저 고치고 여기를 맞춘다** —
#   아래는 구현자가 파일을 떠나지 않고 읽을 수 있게 둔 사본이며, 번호(①~⑤)는
#   spec 과 같다. **두 곳이 어긋나면 spec 이 이긴다.**
#
#   R12~R13 사이에는 이 주석만이 유일한 기록이었다. 그동안 **spec 을 읽는
#   사람은 이 다섯을 알 수 없었다** — 구현이 정본을 들고 있는 상태였고,
#   그것이 spec 으로 옮긴 이유다.
#
# 조항(`FR-104-AC3`)은 *「수명 도달 자원은 `replace` / `retire` 선택 가능」*
# 이라고만 적고 **선택의 결과를 정의하지 않았다.** 그 공백을 아래로 메운다.
# 다섯 다 판단이므로 **바뀔 수 있다.**
#
# **① `replace`(기본값) = 수명 도달 다음 해 초에 교체비를 계상하고 계속 쓴다.**
#    지금까지의 유일한 동작이며 기본값으로 남긴다 — *「설비는 수명이 다하면
#    교체 비용이 발생하므로 이를 비용에 고려해야 한다」*(사용자)가 이 사업의
#    전제다. 기본값을 `retire` 로 두면 교체비가 조용히 빠져 **회수기간이
#    실제보다 좋게** 나온다. 되돌릴 수 없는 쪽을 기본값으로 두지 않는다.
#
# **② `retire` = 수명 도달로 그 설비가 끝난다.** 그래서 둘이 함께 일어난다.
#    - 교체비를 계상하지 않는다 (`replacement_schedule()` 이 EOL 이후로 비운다)
#    - **EOL 이후 출력이 0 이다** (`dispatch()`)
#
#    > **비용만 끊고 출력을 두면 안 된다.** 교체비는 안 드는데 편익은 그대로
#    > 나오므로 회수기간이 좋아지고 **필요 지원액이 과소 산정된다.**
#    > 그 상태는 `retire` 를 구현하지 않은 것보다 나쁘다 — 틀린 값이
#    > 「지원되는 기능」의 얼굴로 나오기 때문이다.
#
# **③ 잔존가치(`AC5`)는 EOL 전에는 `replace` 와 같다.** `retire` 는 **미래의
#    선택**이고 EOL 전에는 자산이 정상 가동 중이다. 분석기간이 EOL 前에
#    끝나면 두 선택의 잔존가치가 다를 이유가 없다.
#
# **⑤ `retire` 는 「이 설비 계통을 더는 갱신하지 않는다」다 — 그래서 출력은
#    본체·부속설비 중 **먼저 수명이 끝나는 쪽**에서 멈춘다.**
#    PV 본체 25년 · 인버터 12년에 retire 를 걸었다고 하자. 13년차에 인버터를
#    사지 않으면서 발전은 20년차까지 계속 나온다면, **비용만 끊고 편익은
#    남기는** ②의 그 형태가 부속설비 쪽으로 되살아난다. 인버터 없는 PV 는
#    계통에 못 싣는다.
#    → `retire` 면 **아무것도 교체하지 않고**, 출력은 `min(본체 수명,
#      부속설비 수명)` 이후 0 이다.
#
# **④ 순수 부하 자원(`Load`·`ThermalLoad`)은 부속설비에만 적용한다.**
#    가구는 계속 살고 수요는 계속 발생한다 — 부하 본체가 0 이 될 이유가 없다.
#    그 자원들의 교체 대상은 실제로 **계량기 등 부속설비**(`AC4`)다.
#    → 이 자원들은 `retire` 여도 `dispatch()` 가 바뀌지 않는다.

#: 매체 4종의 계열 이름과 그것을 켜는 플래그. **이 짝을 여기서만 정의한다** —
#: 계약·계약테스트·엔진이 각자 짝지으면 한 곳이 바뀔 때 나머지가 조용히 남는다.
MEDIA: tuple[tuple[str, str], ...] = (
    ("electric", "carries_electric"),
    ("heat", "carries_heat"),
    ("cool", "carries_cool"),
    ("fuel", "consumes_fuel"),
)


@dataclass(frozen=True)
class DispatchResult:
    """한 자원의 운전 결과 — 매체별 시계열 (kWh, 스텝당).

    **매체 4종을 항상 갖는다.** 하나라도 없으면 그 매체를 다루는 자원이 값을
    실을 곳이 없어지고, 구현자는 다른 계열에 섞어 넣는다. 섞인 값은 수지
    분리(FR-101-AC4)를 무의미하게 만들고, 전기 수지에 열이 섞여도
    NFR-102 균형 검사는 통과한다 — 총량은 맞기 때문이다.

    부호 규약: **양수 = 계통·수요 측에 내보냄(발전·방전), 음수 = 받아들임
    (소비·충전).** 자원마다 부호를 뒤집으면 합산이 조용히 상쇄된다.

    **미충족 계열을 함께 싣는다 (v1.1).** `RC-HP-X1`(열부하 미충족)처럼 자원이
    수요를 다 채우지 못한 사실은 **엔진과 리포트가 봐야 하는 결과**다. 자원
    내부 자료구조에만 남기면 `dispatch()` 를 통과한 시점에 사라지고, 남은 것은
    「열이 조금 덜 나온 정상 결과」뿐이다 — 미충족은 그렇게 조용히 없어진다.
    """

    electric: list[float]
    heat: list[float]
    cool: list[float]
    fuel: list[float]

    #: 매체별 **미충족 수요** (kWh, 스텝당, 부호 없는 양수). 채우지 못한 양이며
    #: `electric` 등의 실적과 별개 계열이다. 생략하면 0으로 채운다.
    unmet_electric: list[float] | None = None
    unmet_heat: list[float] | None = None
    unmet_cool: list[float] | None = None
    unmet_fuel: list[float] | None = None

    #: 사람이 읽는 진단 문구 (예: *"3일차 재충전을 접속 시간대에 넣지 못했습니다"*).
    #: 수치가 아니므로 계산에 쓰지 않는다. 리포트 각주용이다
    notes: tuple[str, ...] = ()

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
        steps = lengths.pop()

        for media, _flag in MEDIA:
            name = f"unmet_{media}"
            series = getattr(self, name)
            if series is None:
                object.__setattr__(self, name, [0.0] * steps)
                continue
            if len(series) != steps:
                raise ValueError(
                    f"{name} 길이({len(series)})가 실적 계열({steps})과 다릅니다. "
                    "미충족은 같은 시각에 대응하는 양이므로 길이가 같아야 합니다"
                )
            if any(v < 0.0 for v in series):
                raise ValueError(
                    f"{name} 에 음수가 있습니다. 미충족은 «채우지 못한 양»이므로 "
                    "부호가 없습니다 — 음수로 상계하면 미충족이 사라집니다"
                )

        object.__setattr__(self, "notes", tuple(self.notes))

    def unmet(self, media: str) -> list[float]:
        """매체별 미충족 계열. 이름 조립을 호출부마다 되풀이하지 않는다.

        `getattr` 은 `Any` 를 돌려주므로 `cast` 로 계약을 다시 못 박는다.
        `__post_init__` 이 네 계열을 `list[float]` 로 채운 뒤이므로 이 단언은
        런타임 상태와 일치한다 — **cast 가 검사를 끄는 것이 아니라, 검사가 볼
        수 없는 곳을 사람이 보증한 지점을 표시하는 것**이다.
        """
        return cast(list[float], getattr(self, f"unmet_{media}"))

    def total_unmet(self) -> float:
        """전 매체 미충족 합계 (kWh). 0이 아니면 그 결과는 수요를 못 채웠다."""
        return sum(sum(self.unmet(m)) for m, _ in MEDIA)


@dataclass(frozen=True)
class DispatchContext:
    """디스패치 1회 실행의 입력 맥락.

    엔진이 자원에게 건네는 **유일한 통로**다. 자원이 엔진을 import하지 않고도
    (FR-101-AC3 · NFR-208-AC1) 필요한 것을 받게 하는 것이 목적이다.

    ── 부분 창 규약 (v1.1에서 확정) ─────────────────────────────────────

    `steps` 가 연간 스텝 수보다 작으면 **연초(1년차 첫 스텝)부터 연속된 `steps`
    스텝**을 뜻한다. 다른 해석은 금지한다.

        허용   연초부터 24스텝 = 1월 1일 0시~23시
        금지   「대표일 1일을 365번 반복한 것의 1일분」
        금지   「연간 총량을 24스텝에 몰아 담기」

    **왜 계약이 이것을 정하는가.** 계약이 답하지 않는 동안 자원 6종이 각자
    정했다. 같은 `steps=24` 가 자원마다 다른 시각 구간을 뜻하면, 엔진이 스텝
    `i` 에서 합산하는 값들이 **서로 다른 시각의 값**이 된다. 총량은 그럴듯하고
    수지 균형(NFR-102)도 통과한다 — 시각이 어긋난 것은 균형식이 보지 못한다.

    연간 총량(연간 발전량·연간 열부하·연간 사이클 수)을 부분 창에 실을 때는
    `year_fraction` 을 곱한다. 자원이 각자 `/365` 나 `/8760` 을 쓰면 15분
    해상도에서 4배 어긋나고, 그 어긋남은 부분 창에서만 나타나 골든 시나리오
    (8760 전체)로는 잡히지 않는다.

    ── 가격 신호 규약 (v1.2에서 신설) ──────────────────────────────────

    **여기 실리는 것은 「요금」이 아니라 「신호」다.** 누진 구간·계절시간대·
    특례할인·기반기금의 해석은 WP-3(`core/regulation/`)이 하고, 그 결과인
    **스텝별 단가 하나**만 엔진이 여기 실어 자원에 건넨다.

        자원이 보는 것    「이 스텝의 전력 1 kWh 는 얼마인가」 → 언제 돌릴지
        자원이 못 보는 것 「이 kWh 가 몇 단계 누진에 걸리는가」 → 얼마를 벌었는지

    **왜 자원이 요금을 들면 안 되는가.** v1.1 시점에 다섯 자원이
    `elec_price_won_per_kwh`·`price_profile_won_per_kwh`·
    `avoided_price_won_per_kwh` 를 **각자 생성자 인자로 들고 있었다.**
    요금 구조는 WP-3 소관이므로 그 상태에서는 **요금제 개정이 자원 코드
    수정**이 되고, 자원 6종을 6명이 나눠 고치게 된다 — §16.1 W-1(파일 단위
    배타 소유)이 막으려는 바로 그 형태다. `vat_rate` 에서 이미 같은 유형을
    한 번 닫았고(08-08), **요금 단가는 그보다 크고 자주 바뀐다.**

    **왜 `DispatchContext` 이고 별도 계약이 아닌가.** 이 클래스는 이미
    *"엔진이 자원에게 건네는 유일한 통로"* 로 규정되어 있다. 통로를 하나 더
    만들면 자원이 두 곳을 봐야 하고, 「어느 것이 정본인가」가 다시 생긴다.
    외기온·계통 상한이 여기 실리는 것과 같은 이유이며, 가격도 **운전 결정의
    입력**이라는 점에서 그 둘과 성질이 같다.

    **편익 화폐화용 요금은 여기 싣지 않는다.** 자가소비 절감액(기존요금 −
    신규요금)은 운전이 **끝난 뒤** WP-4(`core/valuestream/`)가 WP-3의 요금
    엔진으로 계산한다. 그것까지 ctx 에 실으면 자원이 다시 편익을 계산하게
    되고, `value_streams()` 가 tag 문자열만 돌려주도록 v1.1 에서 좁힌 것이
    무의미해진다.

    **None 은 「가격 신호 없음」이며 「0원」이 아니다.** 가격 연동 운전
    방법을 쓰는 자원은 신호가 없으면 **멈춰야 한다** — 0원으로 읽으면
    「항상 가장 싼 시각」이 되어 전 스텝이 동등해지고, 결과는 그럴듯하다.
    `require_price_signal()` 이 그 판정을 한 곳에서 한다.
    """

    steps: int
    dt: int
    year: Year
    #: 스텝별 외기온(℃) — 히트펌프 COP 곡선용. 없으면 자원이 기본값을 쓴다
    ambient_temp_c: list[float] | None = field(default=None)
    #: 스텝별 계통 연계 용량 상한(kW). None이면 무제한
    grid_limit_kw: list[float] | None = field(default=None)
    #: 스텝별 전력 가격 신호 (원/kWh). **요금이 아니라 신호다** — 위 규약 참조.
    #: WP-3 이 요금 구조를 해석한 결과를 엔진이 싣는다. None = 신호 없음
    price_signal_won_per_kwh: list[float] | None = field(default=None)
    #: 스텝별 연료 가격 신호 (원/kWh, **열량 기준**). 도시가스·등유 등.
    #: 열량 기준인 이유: 연료 종류마다 물량 단위(㎥·L)가 달라 자원이 환산을
    #: 떠안게 되고, 환산 계수가 자원마다 갈리면 v1.1 의 `inflation_pct` 와
    #: 같은 «어느 쪽도 오류가 아닌» 100배 오차가 생긴다
    fuel_price_signal_won_per_kwh: list[float] | None = field(default=None)

    def __post_init__(self) -> None:
        if self.steps <= 0:
            raise ValueError(f"스텝 수는 1 이상이어야 합니다: {self.steps}")
        # dt 검증은 units 에 위임한다 — 해상도 규약이 두 곳에 있으면 갈린다
        annual = steps_per_year(self.dt)
        if self.steps > annual:
            raise ValueError(
                f"스텝 수 {self.steps} 가 연간 스텝 수 {annual} 를 넘습니다. "
                "한 컨텍스트는 한 해를 넘지 못합니다 — 여러 해는 연도별로 "
                "따로 실행하고, 그래야 물가상승률·열화가 해마다 걸립니다 "
                "(FR-701-AC3)"
            )
        object.__setattr__(self, "year", Year(int(self.year)))

        for name, series in (
            ("ambient_temp_c", self.ambient_temp_c),
            ("grid_limit_kw", self.grid_limit_kw),
            ("price_signal_won_per_kwh", self.price_signal_won_per_kwh),
            ("fuel_price_signal_won_per_kwh", self.fuel_price_signal_won_per_kwh),
        ):
            if series is not None:
                self.check_series(series, name=name)

    @property
    def annual_steps(self) -> int:
        """이 해상도의 연간 스텝 수 (8760 또는 35040)."""
        return steps_per_year(self.dt)

    @property
    def is_full_year(self) -> bool:
        return self.steps == self.annual_steps

    @property
    def year_fraction(self) -> float:
        """이 창이 한 해의 몇 분의 몇인가 (0 < f ≤ 1).

        **연간 총량을 부분 창에 실을 때 곱하는 유일한 계수다.** 자원이 각자
        `/365`·`/8760` 을 쓰면 해상도가 바뀔 때 어긋나고, 부분 창에서만
        나타나므로 8760 골든 시나리오로는 잡히지 않는다.
        """
        return self.steps / self.annual_steps

    @property
    def hours_per_step(self) -> float:
        """스텝 길이 (시간). kW → 스텝당 kWh 변환에 쓴다."""
        return self.dt / SECONDS_PER_HOUR

    def require_price_signal(self, *, media: str = "electric") -> list[float]:
        """가격 연동 운전에 쓸 신호를 꺼낸다. **없으면 멈춘다.**

        `ctx.price_signal_won_per_kwh or [0.0] * ctx.steps` 같은 표현을
        자원마다 쓰지 못하게 하는 것이 이 메서드의 목적이다. 0원으로 메우면
        전 스텝의 단가가 같아져 **가격 연동이 「아무 때나」와 구별되지
        않고**, 그 결과는 총량이 맞으므로 수지 균형(NFR-102)도 통과한다 —
        v1.1 ①(부분 창 해석)에서 만난 «균형식이 볼 수 없는 오류» 와 같은
        종류다.

        멈추는 자리를 계약에 두는 이유는 v1.1 ⑤ 와 같다. 판단이 자원에
        흩어지면 여섯 개의 서로 다른 답이 생기고 **어느 것도 오류가 아니다.**
        """
        series = (
            self.price_signal_won_per_kwh
            if media == "electric"
            else self.fuel_price_signal_won_per_kwh
        )
        if series is None:
            raise ValueError(
                f"{media} 가격 신호가 없습니다. 가격 연동 운전 방법은 신호 "
                "없이 성립하지 않습니다 — 0원으로 메우면 전 스텝 단가가 "
                "같아져 「가장 싼 시각」이 사라지고, 그 결과는 총량이 맞아 "
                "수지 균형 검사를 통과합니다. 요금 구조 해석은 "
                "WP-3(core/regulation)이 하고 엔진이 그 결과를 ctx 에 "
                "싣습니다 (계약 v1.2 가격 신호 규약)"
            )
        return series

    def check_series(self, series: Sized, *, name: str) -> None:
        """시계열 행수 불일치를 **명확한 오류로 중단**한다 (FR-301-AC3).

        `Sized` 를 받는 이유: 이 검사가 실제로 요구하는 것은 `len()` 뿐이다.
        `Sequence[float]` 로 좁히면 `array`·`memoryview` 처럼 정당한 계열
        표현이 타입 오류가 되고, 그것은 자원 구현에 «검사를 통과시키기 위한»
        변환을 강요한다.

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

    #: 이 자원이 지원하는 운전 방법 목록 (FR-105-AC1). **값은 자원이 소유한다** —
    #: 신규 운전 방법 추가가 코어 수정을 부르지 않아야 하므로(AC2) 계약은
    #: 목록의 내용을 정하지 않고 **접근자 이름만** 고정한다. 케이스 그리드가
    #: 운전 방법을 탐색 변수로 쓰려면(AC5) 이름이 균일해야 한다.
    #: 운전 방법 개념이 없는 자원(부하 등)은 빈 튜플로 남긴다.
    OPERATING_MODES: ClassVar[tuple[str, ...]] = ()

    # ── FR-101-AC1 속성 ─────────────────────────────────────────────
    name: str
    dt: int
    carries_electric: bool
    carries_heat: bool
    carries_cool: bool
    consumes_fuel: bool
    lifetime: int
    degradation_rate: float
    #: 선택된 운전 방법 (FR-105-AC3 — 같은 유형의 두 인스턴스가 서로 다를 수
    #: 있으므로 클래스 속성이 아니라 인스턴스 속성이다). 없으면 빈 문자열
    operating_mode: str
    #: 비용 물가상승률 — **소수(0~1)** 다 (§7.5). `%` 로 받는 인자를 두지 않는다
    escalation_rate: float
    #: 수명 도달 시 처리 — `"replace"`(교체) 또는 `"retire"`(폐기). `FR-104-AC3`.
    #: **기본값이 `"replace"` 인 이유는 §「retire 의 의미」 참조.**
    end_of_life_action: str

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
        operating_mode: str | None = None,
        escalation_rate: float = 0.0,
        end_of_life_action: str = EOL_REPLACE,
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
        self.operating_mode = self._check_operating_mode(operating_mode)
        self.escalation_rate = self._check_escalation_rate(escalation_rate)
        self.end_of_life_action = self._check_end_of_life_action(end_of_life_action)

    @staticmethod
    def _check_end_of_life_action(action: str) -> str:
        """`FR-104-AC3` — 값을 **닫힌 집합으로** 받는다.

        오타(`"Retire"` · `"retired"`)를 조용히 통과시키면 `replace` 로 돌면서
        사용자는 `retire` 를 골랐다고 믿는다. 그 차이는 교체비 한 건과 EOL
        이후 편익 전부이므로 **조용히 틀리면 안 되는 자리**다.
        """
        if action not in EOL_ACTIONS:
            raise ValueError(
                f"end_of_life_action 은 {' 또는 '.join(sorted(EOL_ACTIONS))} "
                f"입니다: {action!r} (FR-104-AC3)"
            )
        return action

    def retires_at_end_of_life(self) -> bool:
        """`retire` 를 선택했는가. **문자열 비교를 구현체마다 반복하지 않는다.**

        자원 6종이 각자 `== "retire"` 를 적으면 그중 하나가 오타여도 게이트가
        잡지 못한다 — 이 저장소가 반복해서 세는 「손으로 유지되는 판정」이다.
        """
        return self.end_of_life_action == EOL_RETIRE

    def _check_operating_mode(self, mode: str | None) -> str:
        """운전 방법이 선언 목록 안에 있는지 검사한다 (FR-105-AC1).

        **기본값으로 첫 항목을 골라 주지 않는다.** 골라 주면 운전 방법을 잊은
        자원이 조용히 특정 방법으로 돌고, 리포트에는 그 방법이 «선택된 것»으로
        표기된다 (FR-105-AC4). 무엇을 선택했는지는 계산 결과를 가르는 입력이므로
        추측 대상이 아니다.
        """
        if not self.OPERATING_MODES:
            if mode:
                raise ValueError(
                    f"{self.name}: 운전 방법 {mode!r} 를 받았으나 "
                    f"{type(self).__name__} 은 `OPERATING_MODES` 를 선언하지 "
                    "않았습니다. 지원 목록을 클래스에 선언하십시오 (FR-105-AC1)"
                )
            return ""
        if mode is None:
            raise ValueError(
                f"{self.name}: 운전 방법을 지정해야 합니다 — "
                f"{type(self).__name__} 의 지원 목록: "
                f"{', '.join(self.OPERATING_MODES)} (FR-105-AC1)"
            )
        if mode not in self.OPERATING_MODES:
            raise ValueError(
                f"{self.name}: 알 수 없는 운전 방법 {mode!r}. 지원 목록: "
                f"{', '.join(self.OPERATING_MODES)} (FR-105-AC1)"
            )
        return mode

    def _check_escalation_rate(self, rate: float) -> float:
        """물가상승률은 **소수**다 (§7.5 — 코드 내부는 소수로 정규화).

        `1.0` 이상을 거부하는 이유: 2%를 `2.0`(=200%) 으로 넘기는 실수가 20년
        프로포마에서 비용을 3.6×10⁹ 배로 만든다. 큰 수는 눈에 띄지만, `0.5`
        (=50%) 로 넘긴 실수는 그럴듯한 숫자로 남는다 — 그래서 상한을 둔다.
        """
        r = float(rate)
        if not -1.0 < r < 1.0:
            raise ValueError(
                f"{self.name}: escalation_rate 는 -1~1 소수입니다: {r}. "
                "2%는 0.02 입니다 (§7.5 — %(0~100)는 입력·표시 경계에서만 씁니다)"
            )
        return r

    def escalation_factor(self, *, year: int) -> float:
        """`year` 년차 물가 계수 = `(1 + escalation_rate)^(year−1)`.

        **1년차를 기준연도로 둔다** (계수 1.0). 자원마다 기준연도를 다르게 잡으면
        같은 물가상승률이 자원별로 한 해씩 어긋난 비용을 낸다 — 20년 누계에서
        수 %의 차이이고, 어느 자원이 어긋났는지는 프로포마에 드러나지 않는다.
        """
        return (1.0 + self.escalation_rate) ** (int(Year(year)) - 1)

    def check_context(self, ctx: DispatchContext) -> None:
        """`dispatch()` 진입부에서 호출한다 — 해상도 규약을 한 곳에서 검사한다.

        `ctx.dt` 와 `self.dt` 가 다르면 **거부한다.** 어느 한쪽을 조용히 채택하면
        같은 인덱스가 서로 다른 시각을 가리키고, 스텝 길이를 잘못 곱한 값은
        해상도 비(4배)만큼 어긋난 채 그럴듯하게 남는다 (FR-301-AC3).
        """
        if ctx.dt != self.dt:
            raise ValueError(
                f"{self.name}: 컨텍스트 해상도({ctx.dt}초)가 자원 해상도"
                f"({self.dt}초)와 다릅니다. 같은 인덱스가 서로 다른 시각을 "
                "가리키게 되므로 진행하지 않습니다 (FR-301-AC3)"
            )

    # ── FR-101-AC2 메서드 ───────────────────────────────────────────
    #
    # 금액을 돌려주는 다섯은 전부 `Money`(정수 원)다 — NFR-103 재무 계층.
    # `year` 를 받는 이유: 물가상승률·열화가 연도별로 다르게 걸리므로,
    # 연도 없는 금액은 어느 해의 값인지 판정할 수 없다 (FR-701-AC3).

    @abstractmethod
    def capex(self, *, year: int) -> Money:
        """자본비 (원). 초기 투자는 보통 1년차에만 발생한다.

        **부가세를 포함하지 않는다** — 세액은 `capex_vat()` 로 분리한다
        (§13.2.2 C-1).
        """

    @abstractmethod
    def capex_vat(self, *, year: int) -> Money:
        """자본비의 부가세액 (원). 세액이 없으면 0.

        **추상으로 두는 이유** (v1.1 신설). §13.2.2 C-1이 *"부가세는 별도 항목으로
        분리"* 를 요구하는데 v1.0 계약에는 자리가 없었다. 그래서 자원 6종 중
        여섯이 `capex_vat()` 를 **각자 지어냈고 ESS 하나는 아예 만들지 않아
        세액이 사라져 있었다.** 이름이 갈리면 엔진이 순회 집계를 못 하고,
        만들지 않으면 세액이 조용히 0이 된다.

        기본 구현 `0`을 주지 않는 이유는 나머지 비용 메서드와 같다 — 잊힌 세액은
        비용 과소 계상이고, 비용 과소 계상은 회수기간을 짧게 만든다.

        **관점별 처리는 여기서 하지 않는다** (FR-704): 사업자에게는 매입세액
        공제 대상이고 사회 관점에서는 이전지출이다. 분리해 두면 관점별 합산이
        각자 판단할 수 있고, 합쳐 두면 되돌릴 수 없다.
        """

    @abstractmethod
    def fixed_om(self, *, year: int) -> Money:
        """고정 O&M (원/년). 설비 보유에 비례하며 운전량과 무관하다.

        물가상승률은 `escalation_factor(year=...)` 를 곱해 반영한다.
        """

    @abstractmethod
    def variable_om(self, *, year: int) -> Money:
        """변동 O&M (원/년). 운전량에 비례한다."""

    @abstractmethod
    def replacement_schedule(self, *, horizon: int) -> dict[int, Money]:
        """{교체 연도: 교체비}. 분석기간 안의 것만 담는다.

        **수명 도달 «다음» 연도 초에 계상한다** (§13.2.2 C-4) — 수명 12년이면
        13년차다. 12년차에 넣으면 아직 살아 있는 해에 교체비가 잡힌다.

        **부속설비의 독립 수명을 여기서 표현한다** (FR-104-AC4) — 인버터
        10~12년은 PV 본체 25년과 별개로 교체된다. 본체 수명만 보면 20년
        분석에서 인버터 교체비가 통째로 빠진다.
        """

    @abstractmethod
    def salvage_value(self, *, year: int) -> Money:
        """`year` 년에 분석이 끝날 때의 잔존가치 (원). 잔존 수명에 비례 (FR-104-AC5).

        **명목액을 돌려준다 — 할인하지 않는다** (v1.1에서 명문화).
        §13.2.2 C-5의 오라클은 `4,500,000 × 5/25 = 900,000원`(명목)이고 그
        할인(`900,000 / 1.045^20`)은 **다음 단계**다. 자원이 할인까지 하면

            · 할인율은 사업 단위 전제(FR-701)이지 자원의 속성이 아니다 —
              자원이 들고 있으면 같은 설비가 시나리오마다 다른 잔존가치를 갖는다
            · 관점별 할인율 차이(FR-704)를 적용할 수 없다
            · 재무 계층이 한 번 더 할인하면 **두 번 할인되고, 값이 작아지므로
              «보수적으로 보여서» 검출되지 않는다**

        그래서 이 메서드는 **할인율을 인자로 받지 않는다.** 계약 테스트가
        시그니처에 할인율이 없음을 검사한다.
        """

    @abstractmethod
    def dispatch(self, ctx: DispatchContext) -> DispatchResult:
        """운전 시뮬레이션 — `ctx.steps` 스텝만큼.

        **부분 창은 연초부터의 연속 구간이다** (`DispatchContext` 부분 창 규약).
        연간 총량을 실을 때는 `ctx.year_fraction` 을 곱한다.

        **`ctx.dt` 가 자원의 `dt` 와 다르면 거부한다** — 진입부에서
        `check_context(ctx)` 를 호출한다.

        **플래그가 거짓인 매체에 값을 실으면 안 된다.** 엔진은 플래그를 보고
        수지를 분리 집계하므로, 거짓인 매체의 값은 어느 수지에도 잡히지 않고
        사라진다. 사라진 에너지는 NFR-102 균형 검사도 통과한다 — 애초에
        집계 대상이 아니기 때문이다. 계약 테스트가 이것을 검사한다.

        **수요를 못 채웠으면 `unmet_*` 계열에 싣는다** (`RC-HP-X1`). 자원 내부
        자료구조에만 남기면 엔진과 리포트가 볼 수 없다.
        """

    # ── 편익 (FR-401 · RC-LD-B0) ────────────────────────────────────

    def value_streams(self) -> tuple[str, ...]:
        """이 자원이 생성하는 편익의 tag 목록 (`FR-401-AC2.<키>` 와 같은 리터럴).

        **기본이 「없음」인 이유** (v1.1 신설). `RC-LD-B0` 은 *"부하 자원은 편익을
        생성하지 않는다"* 를 요구하는데 v1.0 계약에 훅이 없어 **상속으로
        강제되지 않고 자원별 성실성에 달려 있었다** — `DERContractTests` 의 설계
        의도(*자원마다 손으로 쓰면 반드시 빠진다*)와 정면으로 어긋난다.

        여기서만 기본 구현을 주는 것은 방향 때문이다. 비용 메서드의 기본값 0은
        **비용을 지우므로** 위험하지만, 편익의 기본값 「없음」은 편익을 지우므로
        **보수적**이다. 잊으면 경제성이 나빠 보이고, 나빠 보이는 결과는 검토를
        부른다 — 좋아 보이는 결과와 달리.

        `ValueStream` 객체가 아니라 tag 를 돌려주는 이유: 편익은 형제 구획
        (`core/valuestream/`, WP-4)이 소유하므로 자원이 직접 참조하면
        NFR-208-AC2(형제 구획 간 직접 import 금지)를 위반한다.
        """
        return ()
