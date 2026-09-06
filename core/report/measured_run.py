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
from core.report.dispatch_notes import DispatchHour, build_hourly_profile

__all__ = (
    "MeasuredQuantities",
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

    **자가소비 = 스텝마다 min(발전, 부하)** 다. 발전 자원은 전 스텝이 0 이상,
    부하 자원은 전 스텝이 0 이하인 것으로 가른다 — 이름으로 가르면 자원이
    늘 때마다 여기를 고쳐야 하고, 고치지 않으면 조용히 0 이 된다. 충·방전을
    함께 하는 자원(ESS)은 어느 쪽도 아니므로 빠진다.

    ⚠ **이 함수는 「창 하나」를 잰다.** 계절이 선 실행에서 배포 경로가 부르는
    것은 아래 `measured_over_seasons` 이며, 그 이유는 그쪽 독스트링에 있다.
    """
    if not hours:
        return None
    names = tuple(hours[0].per_resource)
    generation = [
        name
        for name in names
        if all(hour.per_resource.get(name, 0.0) >= 0.0 for hour in hours)
        and any(hour.per_resource.get(name, 0.0) > 0.0 for hour in hours)
    ]
    load = [
        name
        for name in names
        if all(hour.per_resource.get(name, 0.0) <= 0.0 for hour in hours)
        and any(hour.per_resource.get(name, 0.0) < 0.0 for hour in hours)
    ]
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
