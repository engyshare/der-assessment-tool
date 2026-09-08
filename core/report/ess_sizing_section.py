"""ESS 적정용량 역산의 **배선과 인쇄** — 붙임 10 (R64/WP-8b · 사용자 요구 4).

## 왜 이 모듈이 생겼는가 — 산식은 섰는데 **부르는 배포 코드가 0곳이었다**

R64/WP-8a 가 `core/report/ess_sizing.py` 에 역산 산식을 세웠다. 그런데 그
함수를 부르는 코드는 `tests/report/test_ess_sizing.py` 뿐이었고 **화면·리포트에
한 자도 나오지 않았다** — 이 저장소가 R32·R33 에서 여섯 번 만난 「선언·계산은
있는데 읽는 쪽이 없다」와 같은 형태이며, 그 형태를 잡으려고 선 검사가
`scripts/check_unread_extension_points.py` 다. 이 모듈이 그 배선이다.

    실행이 낸 계절별 운전   →  시각별 결손 = max(0, 부하 − PV 발전)
                            →  `build_ess_daily_sizing` 로 계절마다 역산
                            →  붙임 10 의 소절로 인쇄

## 왜 `ess_sizing.py` 안에 넣지 않았는가

그 파일은 **산식**이고, 그 머리말이 *「시각별 부하와 시각별 PV 발전을 **인자로만**
받아 역산할 뿐」* 이라고 스스로 못 박았다 — 실행 결과(`SeasonRun`)·자원(`ESS`)·
탐색 구간을 아는 것은 **배선**의 일이다. 그리고 그 파일은 294줄이라 배선과 인쇄를
더하면 NFR-206 상한(500줄)에 닿는다. ⛔ 상한을 올려 푸는 것은 금지다(spec §16.5) —
이 저장소가 이미 다섯 번 쓴 방법(`pv_allocation.py`·`ess_build.py`·
`household_scale.py`·`ess_schedule.py`·`measured_run.py`)이 새 모듈로 뽑는 것이다.

## ★★★ 판정 — **역산 결과를 실행에 되먹이지 않는다**

역산은 *「이만큼 필요하다」* 를 **말하는** 것이지 설비를 **바꾸는** 것이 아니다.
되먹이면 사업이 스스로 자기 설비를 키우고 결론축이 그 크기를 따라 움직인다 —
**어느 수가 입력이고 어느 수가 결과인지 말할 수 없게 된다.** PV 역산
(`core/report/sizing.py::self_sufficiency_section`)이 이미 그렇게 서 있고(인쇄만
한다) 이 소절도 같다. ⇒ **이 모듈은 결론축을 한 자리도 움직이지 않는다.**
⚠ 골든 회귀(`tests/golden/`)가 그 불변을 잰다.

## ★★ 어느 연차로 역산하나 — **분석기간 말**이다

`ESS.usable_capacity_kwh` 는 SOH 를 곱하므로 같은 정격용량이 해마다 덜 낸다.
사용자 요구 4 가 요구하는 것은 **분석기간 내내** 그 결손을 감당하는 용량이므로,
매는 연차는 **가장 덜 내는 해**, 곧 분석기간 말(`CaseBasis.horizon_years`)이다.
⛔ 1년차로 재지 않는다 — 그러면 20년차에 미달인 용량을 「적정」이라 인쇄한다.

⚠⚠ **그러면서 이 수는 하한이다.** 결손 **형상**은 1년차 운전에서 읽는다 — 운전
창이 `DispatchContext(..., year=Year(1))` 하나이고(`core/casegrid/
seasonal_dispatch.py`) 이 모듈은 자원을 다시 세워 다른 해를 돌리지 않는다(다시
세우면 인쇄된 하루와 결론이 선 하루가 갈린다). 연차가 가면 PV 도 열화해 결손
자체가 커지므로 말년차의 참 결손은 여기 인쇄된 것보다 크다. **소절이 그 사실을
글자로 적는다** — 적지 않으면 검토자가 이 수를 상한으로 읽는다.

## 탐색 구간을 넓히지 않는다

역산 용량이 `core/casegrid/ledger_levels.py::_DESIGN_VARS` 의 `ess_capacity_kwh`
탐색 상한을 넘을 수 있다 — 그때 넓히지 않고 **「밖이다」를 인쇄한다**
(`ESSDailySizing.within_search_range`). 구간을 넓히는 것은 결론축(4.4 적정 용량
검토)이 훑는 폭 자체를 바꾸는 일이고, 넘는 점을 지우지도 않는다.
⛔ **넘는데 넘지 않는 것처럼 적지 않는다.**

## 못 하는 것은 산출물이 말한다

역산할 수 없는 실행이 셋 있다 — 저장장치가 없는 실행 · 잴 운전이 없는 실행 ·
부하 자원이 없는 실행. 그때 절을 **지우지 않고** 사유를 글자로 적는다
(`ESSSizingReview.unmeasurable_reason`). 지우면 검토자가 *「역산이 필요 없었다」*
와 *「역산을 싣지 못했다」* 를 가릴 수 없다.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from core.casegrid.models import SeasonRun
from core.contracts.der import DER
from core.der.ess import ESS
from core.report.capacity import search_range_note
from core.report.dispatch_notes import (
    DispatchHour,
    build_hourly_profile,
    split_by_direction,
)
from core.report.ess_sizing import ESSDailySizing, UsableCapacityKwh, build_ess_daily_sizing

#: 하루의 시각 수. `core/report/dispatch_sections.py::_hour_label` 이 같은 층에서
#: 같은 수를 갖는다 — `core/contracts/units.py` 는 이 값을 내놓지 않고(`HOURS_PER_YEAR`
#: 만 있다), 자원 구획의 사적 상수(`core/der/ess_schedule.py::HOURS_PER_DAY`)를
#: 리포트가 import 하면 표시 층이 한 자원의 하루 정의에 매인다.
_HOURS_PER_DAY: Final[int] = 24

#: 계절이 서지 않은 실행에서 그 하루를 부르는 이름. `CaseReport.dispatch_hours`
#: 독스트링이 그 하루를 「연간등가 하루」라고 부르며, 같은 말을 쓴다.
ANNUAL_EQUIVALENT_LABEL: Final[str] = "연간등가 하루"


@dataclass(frozen=True)
class ESSSeasonSizing:
    """계절 하나의 역산 결과 — **이름과 일수를 함께 든다.**

    ⚠ 일수를 여기 싣는 이유는 *「그 결손이 한 해에 며칠인가」* 가 표를 읽는
    사람의 첫 물음이기 때문이다. 계절이 서지 않은 실행에서는 그 하루가 계절이
    아니므로 `days` 가 `None` 이고, 소절은 그것을 「—」로 적는다.
    """

    season_name: str
    days: int | None
    sizing: ESSDailySizing


@dataclass(frozen=True)
class ESSSizingReview:
    """붙임 10 의 ESS 소절이 그리는 것 한 벌.

    ⚠ **못 한 것을 「없음」으로 두지 않는다** — 역산할 수 없는 실행에서는
    `seasons` 가 비고 `unmeasurable_reason` 이 그 사유를 글자로 갖는다(머리말
    마지막 절).
    """

    #: 어느 해에 그 결손을 감당하는가 — 분석기간 말이다(머리말 ★★).
    year: int
    #: 한 스텝의 시간(h). 24스텝 대표일이면 1.0.
    step_hours: float
    #: 정격용량 1kWh 가 `year` 년차에 낼 수 있는 양(kWh). 산식 줄이 이것을
    #: 분모로 적는다 — **적지 않으면 검토자가 SOC 창·SOH·백업 예비의 곱을
    #: 저장소 밖에서 찾아야 한다.**
    usable_per_capacity_kwh: float | None
    seasons: tuple[ESSSeasonSizing, ...]
    unmeasurable_reason: str | None
    search_low_kwh: float
    search_high_kwh: float


def usable_capacity_probe(ess: ESS) -> UsableCapacityKwh:
    """그 배터리를 **정격용량에 대해 열어** 준다 — `UsableCapacityKwh` 모양.

    ## ⚠ 산식을 옮겨 적지 않는다

    `(SOC상한 − SOC하한) × SOH × (1 − 백업예비)` 를 여기 다시 쓰지 않고, 그
    자원의 `usable_capacity_kwh` 를 **그 자원의 정격용량으로 나눠 비율을 되물어**
    얻는다. 그 곱이 용량에 비례하지 않는 항만으로 이루어져 있다는 사실은
    `core/report/ess_sizing.py::required_ess_capacity_kwh` 독스트링이 이미
    근거로 삼고 있는 것과 같다.

    ## ⚠ 새 `ESS` 를 세우지 않는 이유

    `ESS` 는 dataclass 가 아니라 손으로 쓴 `__init__` 을 가지며 인자가 스물
    남짓이다 — `dataclasses.replace` 가 듣지 않고, 인자를 여기 다시 적으면
    **그것이 사본**이 되어 러너가 SOC 창을 바꾸는 날 조용히 갈린다.
    """

    def usable(*, capacity_kwh: float, year: int) -> float:
        return capacity_kwh * ess.usable_capacity_kwh(year=year) / ess.capacity_kwh

    return usable


def _unmeasurable(reason: str, *, year: int, low: float, high: float) -> ESSSizingReview:
    return ESSSizingReview(
        year=year,
        step_hours=0.0,
        usable_per_capacity_kwh=None,
        seasons=(),
        unmeasurable_reason=reason,
        search_low_kwh=low,
        search_high_kwh=high,
    )


def _windows(
    hours: Sequence[DispatchHour], seasons: Sequence[SeasonRun]
) -> tuple[tuple[str, int | None, tuple[DispatchHour, ...]], ...]:
    """역산할 하루들 — 계절이 서면 계절마다, 안 서면 연간등가 하루 하나.

    ⚠ **계절을 접어 한 벌로 재지 않는다.** 결손은 스텝마다 `max(0, 부하 − PV)`
    이고 그 `max` 는 비선형이라, 계절을 일수로 가중 평균한 하루에서 재면 겨울의
    부족과 여름의 잉여가 **같은 시각에서 상쇄돼** 결손이 사라진다 — R64/WP-4 가
    운전에서 푼 그 상쇄를 역산 쪽에서 다시 접는 것이 된다.
    """
    if seasons:
        return tuple(
            (season.name, season.days, build_hourly_profile(season.dispatch))
            for season in seasons
        )
    return ((ANNUAL_EQUIVALENT_LABEL, None, tuple(hours)),)


def build_ess_sizing_review(
    *,
    hours: Sequence[DispatchHour],
    seasons: Sequence[SeasonRun],
    resources: Sequence[DER],
    year: int,
    search_low_kwh: float,
    search_high_kwh: float,
) -> ESSSizingReview:
    """실행이 낸 운전에서 **계절마다** ESS 적정용량을 역산한다.

    ⚠ **자원을 다시 세우지 않는다** — 배터리는 `resources`(러너가 실제로 세운
    것)에서 고르고, 결손은 `seasons`(러너가 실제로 돌린 하루)에서 읽는다. 다시
    세우면 인쇄된 하루와 결론이 선 하루가 갈릴 수 있다(`CaseOutcome.resources`
    독스트링이 같은 판단을 이미 받은 자리다).

    ⚠ 배터리가 몫으로 갈린 실행(`ess_shares`)에서는 **첫 배터리**를 고른다 —
    비율(`SOC 창 × SOH × (1 − 백업예비)`)은 몫마다 같고 역산이 쓰는 것은 그
    비율 하나뿐이다(용량은 `usable_capacity_probe` 가 나눠 없앤다).
    """
    ess = next((r for r in resources if isinstance(r, ESS)), None)
    if ess is None or ess.capacity_kwh <= 0.0:
        return _unmeasurable(
            "이 실행에는 저장장치가 없습니다 — 역산할 대상이 없습니다",
            year=year, low=search_low_kwh, high=search_high_kwh,
        )
    usable = usable_capacity_probe(ess)
    sized: list[ESSSeasonSizing] = []
    step_hours = 0.0
    for name, days, profile in _windows(hours, seasons):
        if not profile:
            return _unmeasurable(
                "이 실행에는 잴 운전이 없습니다 — 결손을 읽을 하루가 없습니다",
                year=year, low=search_low_kwh, high=search_high_kwh,
            )
        generation, load = split_by_direction(profile)
        if not load:
            return _unmeasurable(
                f"「{name}」에 부하 자원이 없습니다 — 결손을 잴 분모가 없습니다",
                year=year, low=search_low_kwh, high=search_high_kwh,
            )
        step_hours = _HOURS_PER_DAY / len(profile)
        sized.append(
            ESSSeasonSizing(
                season_name=name,
                days=days,
                sizing=build_ess_daily_sizing(
                    load_kwh_by_step=[
                        -sum(hour.per_resource.get(n, 0.0) for n in load)
                        for hour in profile
                    ],
                    pv_kwh_by_step=[
                        sum(hour.per_resource.get(n, 0.0) for n in generation)
                        for hour in profile
                    ],
                    step_hours=step_hours,
                    usable_capacity_kwh=usable,
                    year=year,
                    search_low_kwh=search_low_kwh,
                    search_high_kwh=search_high_kwh,
                ),
            )
        )
    return ESSSizingReview(
        year=year,
        step_hours=step_hours,
        usable_per_capacity_kwh=usable(capacity_kwh=1.0, year=year),
        seasons=tuple(sized),
        unmeasurable_reason=None,
        search_low_kwh=search_low_kwh,
        search_high_kwh=search_high_kwh,
    )


def _range_note(review: ESSSizingReview, sizing: ESSDailySizing) -> str:
    if sizing.within_search_range:
        return "예"
    if sizing.required_capacity_kwh > review.search_high_kwh:
        return f"아니오 — 구간 상한 {review.search_high_kwh:g}kWh 초과"
    return f"아니오 — 구간 하한 {review.search_low_kwh:g}kWh 미만"


def _binding_lines(review: ESSSizingReview) -> list[str]:
    """가장 큰 용량을 요구하는 계절을 **한 줄로 집어 준다.**

    ⚠ 표에서 사람이 눈으로 고르게 두지 않는다 — 계절이 넷이면 어느 행이 매는
    행인지가 표를 훑는 순서에 달리고, 그 순서는 자산이 계절을 적은 순서다.
    """
    binding = max(review.seasons, key=lambda s: s.sizing.required_capacity_kwh)
    return [
        f"- 매는 하루는 **{binding.season_name}**이다 — 저장용량 "
        f"**{binding.sizing.required_capacity_kwh:,.2f}kWh** · 정격출력 "
        f"**{binding.sizing.required_power_kw:,.2f}kW** 이며, 이 구성이 한 해를 "
        "다 감당하려면 그 계절을 넘겨야 한다",
    ]


def ess_daily_sizing_section(review: ESSSizingReview) -> list[str]:
    """**붙임 10** 의 소절 — 경우 「ESS」(하루 결손) 역산 결과.

    ## 왜 본문 4.4 가 아니라 붙임 10 인가

    PV 역산과 **같은 사유이며 같은 자리다** —
    `core/report/sizing.py::self_sufficiency_section` 독스트링이 그 실측(본문
    분량 상한 219줄을 넘겨 빨간불이 났고, 그 실패 문면이 *「늘어난 것을 붙임으로
    내릴 것」* 이라 적었다)을 갖는다. ⛔ **새 붙임을 만들지 않는다** — 붙임 10 이
    이미 *「설계 변수마다 역산 결과를 적는 자리」* 이고 PV 가 거기 있다.

    이 표도 PV 쪽과 같이 **진단이지 답이 아니다** — `_DESIGN_VARS` 탐색 구간도
    실행의 용량도 여기서 바꾸지 않는다(머리말 ★★★).
    """
    lines = [
        "### 경우 「ESS」 — 하루의 결손을 방전만으로 감당하는 최소 용량 (역산)",
        "",
    ]
    if review.unmeasurable_reason is not None:
        # ⚠ 절을 지우지 않는다 — 머리말 마지막 절.
        lines += [f"- 역산하지 못했다 — {review.unmeasurable_reason}", ""]
        return lines
    lines += [
        "| 하루 | 연 일수 | 하루 결손 합 (kWh) | 첨두 결손 (kWh) | "
        "필요 저장용량 (kWh) | 필요 정격출력 (kW) | "
        "4.4 의 경제성 스윕 구간 안인가 |",
        "|---|---|---|---|---|---|---|",
    ]
    for season in review.seasons:
        sizing = season.sizing
        lines.append(
            f"| {season.season_name} | "
            f"{'—' if season.days is None else f'{season.days:,}'} | "
            f"{sizing.required_discharge_kwh:,.4f} | "
            f"{sizing.peak_shortfall_kwh:,.4f} | "
            f"{sizing.required_capacity_kwh:,.2f} | "
            f"{sizing.required_power_kw:,.2f} | "
            f"{_range_note(review, sizing)} |"
        )
    lines.append("")
    lines += [
        # ⚠ 코드 칸(`max(...)`) 안은 **ASCII 붙임표**다 — 유니코드 마이너스를 쓰면
        # `RUF001` 이 울고, 그 자리는 산식을 그대로 읽는 자리라 ASCII 가 맞다.
        "- 결손 — 시각마다 `max(0, 부하 - PV 발전)` 이며 **음수로 상계하지 "
        "않는다**: 낮에 남은 PV 를 저녁 결손에서 빼면 저장 없이 시간을 건너뛴 "
        "것이 되어 ESS 를 세우는 이유가 사라진다",
        f"- 산식 — 필요 저장용량(kWh) = 하루 결손 합 ÷ (정격용량 1kWh 가 "
        f"{review.year}년차에 낼 수 있는 양 "
        f"{review.usable_per_capacity_kwh:.6f}kWh) · 필요 정격출력(kW) = 첨두 "
        f"결손 ÷ 한 스텝의 시간 {review.step_hours:g}h",
        f"- 연차 **{review.year}년차(분석기간 말)** 기준이다 — SOH 가 해마다 "
        "떨어져 같은 정격용량이 덜 내므로, 분석기간 내내 감당하려면 가장 덜 내는 "
        "해로 재야 한다",
        "- ⚠ **이 수는 하한이다** — 결손 형상은 1년차 운전에서 읽었고(운전 창이 "
        "하나다) 연차가 가면 태양광도 열화해 결손 자체가 커진다",
    ]
    lines += _binding_lines(review)
    lines += [
        # ★ 「구간 밖」이 무슨 뜻인가 — 문면의 정본은 `capacity.py` 다
        # (R67/WP-N2 · 판정 §2-2). 실측에서 겨울 필요 용량이 탐색 상한을 넘어
        # 「밖」이 붙는데, 그것을 *「넘었으니 못 믿는다」* 로 읽으면 사용자 판정
        # (*「용량 범위 제한이 없어야 하며」*)과 반대가 된다.
        f"- {search_range_note(sweep_where='본문 4.4')}",
        "- 이 표는 진단이다 — 이 용량을 채택한 것이 아니다. 역산 결과를 실행에 "
        "되먹이지 않으므로 위 4.4 의 결론축은 이 수에 움직이지 않는다",
        "",
    ]
    return lines
