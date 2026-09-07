"""**본 실행의 운전에서 잰 수량** — 자가소비·부하·수전·송전 (kWh).

## 왜 `unreflected.py` 에서 갈라냈나 (R64/WP-4)

R64/WP-4 가 러너에 계절 합산을 세우면서 이 계산이 **계절마다 재어 일수로 가중
평균**해야 하게 됐고(`measured_over_seasons` 독스트링의 실측), 그만큼 늘어난
코드가 `core/report/unreflected.py` 를 `NFR-206` 코드 줄 상한(500) **위로**
밀어 올렸다(실측 507/500 · `check_file_size.py --code-strict` 가 「코드 스프롤」로
빨간불을 냈다). ⛔ **상한을 올리는 것은 spec 개정(§16.5)이므로 하지 않았고**,
근거 주석을 지워 줄이는 것은 조항이 지키려던 것을 정면으로 해친다 —
`core/casegrid/operating_lines.py`(R43-F)·`core/casegrid/lifecycle.py`(R39-E2)가
같은 자리에서 같은 판단을 했다.

**가르는 선은 「재는 것」과 「판정하는 것」이다.** 이 파일은 운전 결과에서 수량을
**재기만** 하고, 그 수량으로 *「미반영인가」* 를 판정하는 것은 `unreflected.py`
가 계속 한다.

⚠ `unreflected.py` 는 이 세 이름을 **재수출한다** — `_measured_quantities` 를
`core/report/unreflected.py::_measured_quantities` 로 가리키는 문면들이 그대로
참이다(`ess_build.py`·`pv_allocation.py` 가 쓴 것과 같은 재수출 규약 ·
`scripts/check_docstring_references.py`).
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from core.casegrid.models import SeasonRun
from core.casegrid.operating_lines import DAYS_PER_YEAR
from core.report.dispatch_notes import (
    DispatchHour,
    build_hourly_profile,
    split_by_direction,
)

__all__ = (
    "DischargeCoverage",
    "MeasuredQuantities",
    "discharge_coverage",
    "discharge_coverage_over_seasons",
    "measured_over_seasons",
)


@dataclass(frozen=True)
class MeasuredQuantities:
    """**본 실행**의 운전에서 잰 수량 (대표일, kWh).

    ⚠ 이름이 `_AssumedQuantities` 였다. R48 이 본 실행에 가구 부하를 세우기
    전에는 이 수를 붙임 7 **둘째 표**(형상을 가정해 다시 돌린 운전)에서 재었기
    때문이다. R49/★A 가 그 둘째 표를 지웠고, 지금 재는 대상은 **결론이 그 위에
    서 있는 본 실행**(`CaseReport.dispatch_hours`)이다 — 「가정(assumed)」
    어휘를 남겨 두면 다음 사람이 이 수를 *결론과 무관한 곁가지*로 읽는다.

    ⚠ **밑줄이 떨어졌다** (R64/WP-4) — 모듈 밖에서 부르는 이름이 됐기 때문이며,
    `core/casegrid/ess_build.py`·`case_metrics.py` 가 갈라져 나오며 한 것과 같다.
    """

    self_consumption: float
    #: 부하 자원의 대표일 소비 합계(양수). 자가소비량이 무엇의 일부인지를
    #: 붙임 8 이 밝히려면 분모가 필요하다.
    load: float
    grid_import: float
    grid_export: float


def _measured_quantities(
    hours: tuple[DispatchHour, ...],
) -> MeasuredQuantities | None:
    """본 실행의 운전에서 자가소비·부하·수전·송전을 잰다.

    **자가소비 = 스텝마다 min(발전, 부하)** 다. 발전 쪽과 부하 쪽을 가르는 것은
    `core/report/dispatch_notes.py::split_by_direction` 이며 **부호로** 가른다 —
    이름으로 가르면 자원이 늘 때마다 그곳을 고쳐야 하고, 고치지 않으면 조용히
    0 이 된다. 충·방전을 함께 하는 자원(ESS)은 어느 쪽도 아니므로 빠진다.

    ⚠ **가르는 규칙을 여기 적지 않는다** (R64/WP-8b). 붙임 10 의 결손 측정
    (`core/report/ess_sizing_section.py`)이 **같은 발전·같은 부하**를 봐야 하고,
    각자 적으면 한쪽만 고쳐지는 날 두 붙임이 서로 다른 하루를 잰다.

    ⚠ **이 함수는 「창 하나」를 잰다.** 계절이 선 실행에서 배포 경로가 부르는
    것은 아래 `measured_over_seasons` 이며, 그 이유는 그쪽 독스트링에 있다.
    """
    if not hours:
        return None
    generation, load = split_by_direction(hours)
    if not load:
        return None
    matched = sum(
        min(
            sum(hour.per_resource.get(name, 0.0) for name in generation),
            -sum(hour.per_resource.get(name, 0.0) for name in load),
        )
        for hour in hours
    )
    return MeasuredQuantities(
        self_consumption=matched,
        load=-sum(
            hour.per_resource.get(name, 0.0) for hour in hours for name in load
        ),
        grid_import=sum(hour.grid_import for hour in hours),
        grid_export=sum(hour.grid_export for hour in hours),
    )


def measured_over_seasons(
    hours: tuple[DispatchHour, ...], seasons: Sequence[SeasonRun] = ()
) -> MeasuredQuantities | None:
    """위 넷을 **계절마다 재어 계절일수로 가중 평균**한다 (R64/WP-4).

    ## ⚠⚠⚠ 왜 접힌 하루에서 재면 안 되는가 — 두 층이 갈린다

    자가소비는 스텝마다 `min(발전, 부하)` 이고 **그 min 은 비선형**이다. 계절을
    일수로 가중 평균한 하루에서 재면 `min(평균 발전, 평균 부하)` 가 나오는데,
    실제로 한 해 동안 자가소비되는 양은 `Σ 계절 min(그 계절 발전, 그 계절 부하)
    × 계절일수` 다. 평균의 min 은 min 의 평균보다 **크므로**(옌센) 접힌 하루에서
    재면 **자가소비를 과대 계상한다.**

    그 어긋남은 **실측됐다** — R64/WP-4 가 러너에 계절 합산을 세우자 리포트 0절의
    자가소비율(잉여 시계열에서 오므로 **계절을 안다**)과 붙임 8 의 자가소비량
    (접힌 하루에서 재므로 **계절을 몰랐다**)이 8.856 대 8.9415kWh/일로 갈렸다
    (`tests/casegrid/test_pv_surplus_allocation_priority.py::
    test_household_first_self_consumption_ratio_matches_unreflected_layer` 가 그
    자리를 붙든다). 같은 어긋남이 ⓒ 갈래의 「포기한 자가소비」 물량에서도 났다
    (`tests/report/test_pool_branch_calculated.py`).

    ⚠ **계절이 없으면 종전 그대로다** — 형상 자산이 없는 실행에서 `seasons` 는
    비어 있고, 그때 이 함수는 접힌 하루를 그대로 잰다.

    ⚠⚠ **잴 운전이 없으면 계절을 보지 않는다.** `hours` 가 비어 있다는 것은
    *「잴 본 실행이 없다」* 이고, 그때 계절별 하루로 대신 재면 **비운 통로가
    비워지지 않는다** — 붙임 8 이 없는 운전 위에 방향을 인쇄하게 된다. 계절은
    같은 실행을 더 잘게 본 것이지 다른 실행이 아니므로, 판정도 함께 없다
    (`tests/report/test_unreflected.py::
    test_without_a_run_to_measure_the_self_consumption_row_is_unmeasured` 가
    그 자리를 붙든다 — R64/WP-4 에 실제로 이 통로가 새는 것을 잡았다).
    """
    if not hours or not seasons:
        return _measured_quantities(hours)
    parts = [
        (_measured_quantities(build_hourly_profile(season.dispatch)), season.days)
        for season in seasons
    ]
    measured = [(part, days) for part, days in parts if part is not None]
    if len(measured) != len(parts):
        return None
    return MeasuredQuantities(
        self_consumption=math.fsum(
            part.self_consumption * days / DAYS_PER_YEAR for part, days in measured
        ),
        load=math.fsum(part.load * days / DAYS_PER_YEAR for part, days in measured),
        grid_import=math.fsum(
            part.grid_import * days / DAYS_PER_YEAR for part, days in measured
        ),
        grid_export=math.fsum(
            part.grid_export * days / DAYS_PER_YEAR for part, days in measured
        ),
    )


@dataclass(frozen=True)
class DischargeCoverage:
    """**방전이 난 시각과 그 밖에 남는 가구 수요** (대표일, kWh · R64/WP-6b).

    사용자 요구 5(*「ESS는 가구의 전력 수요를 최우선적으로 대응할 수 있도록
    운전되야 함」*)를 배선하면서 남은 결손을 재는 자리다. 방전 **배분**은
    수요를 따라가게 됐지만 방전 **창**은 여전히 운전 방법이 정하므로, 창 밖의
    수요(예: 아침 피크)는 대응되지 않는다. 그 크기를 재지 않고 두면 산출물이
    *「수요에 최우선 대응한다」* 로만 읽힌다 — 창 안에서만 참인 문장이다.

    ⛔ **창을 넓혀 푸는 길은 순환한다** —
    `core/der/ess_schedule.py::pv_surplus_charge_kwh_by_hour` 가 **「방전창을
    뺀 시각」**에 충전하므로, 창을 부하로 정하면 충전 계획이 방전 계획에 매이고
    방전 계획이 다시 충전량(=하루 방전량)에 매인다.
    """

    #: 대표일 가구 부하 합(양수).
    load_total: float
    #: 그중 **방전이 하나도 없던 스텝**에 있던 몫(양수).
    load_outside: float
    #: 그 스텝들의 계통 수전 합 — 창 밖 수요 중 **실제로 사 온** 몫이다.
    #: (창 밖 수요 전부가 구매는 아니다 — 낮에는 태양광이 직접 덮는다.)
    grid_import_outside: float
    #: 방전이 난 스텝 수. 계절 가중 평균이라 정수가 아닐 수 있다.
    steps_discharging: float
    #: 대표일 스텝 수 — 위 값의 분모다.
    steps: float


def _resource_shapes(
    hours: tuple[DispatchHour, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """부호 모양으로 (부하 자원, 저장장치) 이름을 가른다 — 아래 둘이 함께 쓴다."""
    names = tuple(hours[0].per_resource)
    load = tuple(
        name
        for name in names
        if all(hour.per_resource.get(name, 0.0) <= 0.0 for hour in hours)
        and any(hour.per_resource.get(name, 0.0) < 0.0 for hour in hours)
    )
    storage = tuple(
        name
        for name in names
        if any(hour.per_resource.get(name, 0.0) > 0.0 for hour in hours)
        and any(hour.per_resource.get(name, 0.0) < 0.0 for hour in hours)
    )
    return load, storage


def discharge_coverage(
    hours: tuple[DispatchHour, ...],
    *,
    resources: tuple[tuple[str, ...], tuple[str, ...]] | None = None,
) -> DischargeCoverage | None:
    """창 하나에서 위 넷을 잰다. **이름이 아니라 부호 모양으로 자원을 가른다.**

    ## ⚠⚠ `resources` — **「하루 종일 쉰 배터리」와 「배터리가 없다」를 가른다**
    (R65/WP-2c)

    부호 모양은 그 하루 안에서만 본다. 그래서 **한 스텝도 움직이지 않은**
    배터리는 「저장장치가 없는 실행」과 구별되지 않고 이 함수가 `None` 을 낸다.
    20호 단지의 **겨울**이 정확히 그 자리다 — 낮에도 부하가 발전을 넘어 태양광
    잉여가 0 이라 배터리가 통째로 쉰다(실측: `e2e-ess` 가 24스텝 모두 0.0000).

    그때 `None` 을 내면 계절 평균이 통째로 `None` 이 되고, **붙임 8 의 「방전창
    밖 가구 수요」 항목이 산출물에서 사라진다.** 그것은 *「대응했다」* 도
    *「못 했다」* 도 아닌 **침묵**이며, 이 저장소가 반복해 막아 온 형태다.

    ⇒ 호출부가 **연간등가 하루에서 가른 자원 이름**을 넘겨 주면 그것을 쓴다.
    쉰 계절에서는 방전 스텝이 0 이고 창 밖 수요가 그 계절 부하 전량이 되어,
    *「그 계절엔 배터리가 아무것도 덮지 못했다」* 가 **수로** 실린다.
    ⚠ 넘기지 않으면 종전과 **원소 하나까지** 같다.

    부하는 전 스텝이 0 이하이고 한 스텝이라도 음수인 자원, 저장장치는 **양수
    스텝과 음수 스텝을 함께 갖는** 자원이다 — `_measured_quantities` 가 자가소비를
    재려고 쓰는 것과 같은 규칙이며(그쪽은 저장장치를 그래서 **뺀다**), 이름으로
    가르면 자원이 늘 때마다 여기를 고쳐야 하고 고치지 않으면 조용히 0 이 된다.

    ⚠ **「방전창」이 아니라 「방전이 난 스텝」을 잰다.** 창은 자원의 선언이고
    이 파일이 받는 것은 운전 결과다 — 잉여가 없어 배터리가 쉰 계절에서는 창이
    있어도 방전이 없고, 그때 창을 읽으면 **하지 않은 대응을 했다고 세게 된다.**

    부하 자원이나 저장장치가 없으면 `None` 이다 — 잴 것이 없다.
    """
    if not hours:
        return None
    load, storage = resources if resources is not None else _resource_shapes(hours)
    if not load or not storage:
        return None
    outside = [
        hour
        for hour in hours
        if math.fsum(hour.per_resource.get(name, 0.0) for name in storage) <= 0.0
    ]
    return DischargeCoverage(
        load_total=-math.fsum(
            hour.per_resource.get(name, 0.0) for hour in hours for name in load
        ),
        load_outside=-math.fsum(
            hour.per_resource.get(name, 0.0) for hour in outside for name in load
        ),
        grid_import_outside=math.fsum(hour.grid_import for hour in outside),
        steps_discharging=float(len(hours) - len(outside)),
        steps=float(len(hours)),
    )


def discharge_coverage_over_seasons(
    hours: tuple[DispatchHour, ...], seasons: Sequence[SeasonRun] = ()
) -> DischargeCoverage | None:
    """위 넷을 **계절마다 재어 계절일수로 가중 평균**한다.

    `measured_over_seasons` 와 같은 사유다 — 접힌 하루에서 재면 *어느 계절엔가
    방전이 있었던* 시각이 전 계절에서 방전이 있었던 것처럼 세어져 **창 밖
    수요를 과소 계상한다.** 잉여가 없어 배터리가 쉬는 겨울이 정확히 그 자리다.

    ⚠ **잴 운전이 없으면 계절을 보지 않는다** — `measured_over_seasons` 의
    같은 ⚠⚠ 절과 같은 이유다.
    """
    if not hours or not seasons:
        return discharge_coverage(hours)
    # ★ **자원 이름은 연간등가 하루에서 가른다** (R65/WP-2c · 위 함수의 ⚠⚠).
    # 계절마다 다시 가르면 배터리가 쉰 계절이 「배터리가 없는 실행」이 되어
    # `None` 을 내고, 그 하나 때문에 **연간 평균이 통째로 사라진다.**
    resources = _resource_shapes(hours)
    if not resources[0] or not resources[1]:
        return None
    parts = [
        (
            discharge_coverage(
                build_hourly_profile(season.dispatch), resources=resources
            ),
            season.days,
        )
        for season in seasons
    ]
    measured = [(part, days) for part, days in parts if part is not None]
    if len(measured) != len(parts):
        return None

    def blend(pick: str) -> float:
        return math.fsum(
            float(getattr(part, pick)) * days / DAYS_PER_YEAR for part, days in measured
        )

    return DischargeCoverage(
        load_total=blend("load_total"),
        load_outside=blend("load_outside"),
        grid_import_outside=blend("grid_import_outside"),
        steps_discharging=blend("steps_discharging"),
        steps=blend("steps"),
    )
