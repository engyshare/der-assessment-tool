"""**계절 넷의 대표일을 각각 돌려 합산하는 운전**이 성립하는가 (R64/WP-4 · 착수 36ⓐ).

R60/WP-4 는 계절이 선 자산을 **몫 가중 평균 대표일 한 벌**로 접어 넘겼다. 그
접기를 푼 것이 이 라운드이며, 푸는 순간 R60 이 막았던 결함이 되살아날 수 있다 —
그때 실측된 것이 *「계절을 적는 **차례**만 바꿔도 연간 발전이 +281kWh 생기고
연간 부하가 −315kWh 사라진다」* 였다. 그래서 이 파일이 붙드는 것은 넷이다.

    가  연간 발전량·연간 부하량이 **계절 도입 전과 같다**
    나  Σ(계절일수) == `DAYS_PER_YEAR`  — 달력이 닫힌다
    다  계절을 적는 **차례를 바꿔도 연간 결과가 같다**  ← 36번의 위험이 여기다
    라  계절이 하나(`연중`)뿐인 자산에서는 **종전과 원소 하나까지 같다**

⚠ 「가」는 `tests/report/test_shaped_run_invariants.py` 가 **배포 자산으로**
이미 재고 있다(`test_a_shape_moves_energy_but_does_not_create_it`). 이 파일은
계절이 서로 **다른 하루**를 갖는 시험 자산에서 같은 성질을 다시 잰다 — 배포
자산의 계절 형상이 나중에 평평해지면 저쪽만으로는 「가」가 공허해진다.

⚠⚠ **이 파일이 세우는 계절 일수·몫·형상은 전부 시험용 가정값이며 사업 전망이
아니다. 이 수를 리포트·검토서에 인용하지 마라.**
"""
from __future__ import annotations

import math
from itertools import permutations
from pathlib import Path
from typing import Any

import pytest

from core.casegrid.e2e_runner import (
    DAYS_PER_YEAR,
    HOURS_PER_YEAR,
    PRICE_ESCALATION_RATE,
    PV_CAPACITY_FACTOR,
    PV_SELF_CONSUMPTION_RATIO,
    SECONDS_PER_HOUR,
    STEPS_PER_DAY,
    run_single_case_e2e,
)
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.models import CaseOutcome
from core.casegrid.profiles import (
    GENERATION_SHAPE_KEY,
    LOAD_SHAPE_KEY,
    load_daily_shapes,
)

# ★★★ **모듈을 정면(러너)이 아니라 직접 부른다** (R64/WP-4-fix2 · `NFR-105` 게이트 ②).
# 이 파일이 러너만 import 하는 동안 `core/casegrid/seasonal_dispatch.py` 는
# **동반 시험이 없는 구현**으로 세어졌다 — 러너를 통과시키면 *「4호에서 거부되지
# 않는다」* 는 재이지만 *「그 계절에 배터리가 0 을 싣는다」* 는 재이지 않는다.
from core.casegrid.seasonal_dispatch import build_and_dispatch_case, dispatch_note
from core.contracts.der import DispatchContext
from core.contracts.engine import SystemDispatch
from core.contracts.units import Year
from core.engine.rule_based import RuleBasedEngine
from tests.casegrid.test_seasonal_axis import _asset, _item

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

#: 계절 넷의 일수 — 합이 365 다. 시험용 가정값이다.
_DAYS = {"봄": 92, "여름": 92, "가을": 91, "겨울": 90}


def _bell(peak_hour: int, width: float) -> list[float]:
    """`peak_hour` 를 봉우리로 하는 24스텝 하루. **정규화는 자산 쪽이 한다.**"""
    return [
        round(math.exp(-(((hour - peak_hour) / width) ** 2)), 6) + 0.02
        for hour in range(STEPS_PER_DAY)
    ]


#: 계절마다 **서로 다른 하루**. 이것이 평평하면 「다」가 무엇을 재는지 알 수 없다
#: (차례를 바꿔도 값에 흔적이 남지 않으므로 공허하게 통과한다) — WP-3 이
#: `test_seasonal_representative_days.py` 에서 같은 이유로 같은 대비를 세웠다.
_GENERATION_SEASONS: list[dict[str, Any]] = [
    {"name": "봄", "days": _DAYS["봄"], "share": 0.27, "weights": _bell(12, 3.5)},
    {"name": "여름", "days": _DAYS["여름"], "share": 0.34, "weights": _bell(13, 4.5)},
    {"name": "가을", "days": _DAYS["가을"], "share": 0.24, "weights": _bell(12, 3.0)},
    {"name": "겨울", "days": _DAYS["겨울"], "share": 0.15, "weights": _bell(12, 2.0)},
]

#: 부하는 발전과 **같은 달력**을 쓰되 봉우리가 저녁이다 — 겨울에 크게 둔다.
_LOAD_SEASONS: list[dict[str, Any]] = [
    {"name": "봄", "days": _DAYS["봄"], "share": 0.23, "weights": _bell(19, 4.0)},
    {"name": "여름", "days": _DAYS["여름"], "share": 0.26, "weights": _bell(20, 4.5)},
    {"name": "가을", "days": _DAYS["가을"], "share": 0.22, "weights": _bell(19, 4.0)},
    {"name": "겨울", "days": _DAYS["겨울"], "share": 0.29, "weights": _bell(18, 5.0)},
]


def _levels() -> dict[str, dict[str, float]]:
    return build_level_map(_ASSUMPTIONS)


def _load_kwh() -> float:
    """대장이 정한 가구 부하 총량. **여기에 수를 적지 않는다** — 대장이 정본이다."""
    return float(_levels()["household_load_annual_kwh"]["base"])


def _seasonal_path(
    tmp_path: Path,
    *,
    generation: list[dict[str, Any]],
    load: list[dict[str, Any]],
    name: str = "seasonal-24.yaml",
) -> Path:
    path = _asset(
        tmp_path,
        _item(LOAD_SHAPE_KEY, seasons=load),
        _item(GENERATION_SHAPE_KEY, seasons=generation),
    )
    return path.rename(path.with_name(name))


def _run(path: Path) -> CaseOutcome:
    """시험 자산 하나로 **배포 러너를 그대로** 돌린다.

    자원을 손으로 세우지 않는 이유는 그러면 러너의 사본이 되기 때문이다 —
    이 파일이 재려는 것은 *러너가 계절을 어떻게 다루는가* 다.
    """
    return run_single_case_e2e(
        {},
        level_map=_levels(),
        horizon_years=20,
        daily_shapes=load_daily_shapes(path),
        annual_load_kwh=_load_kwh(),
    )


def _daily(dispatch: SystemDispatch, resource: str) -> float:
    return math.fsum(dispatch.per_resource[resource].electric)


# ── 「나」 달력이 닫힌다 ────────────────────────────────────────────────────


def test_the_season_days_close_the_calendar(tmp_path: Path) -> None:
    """★ **Σ(계절일수) == `DAYS_PER_YEAR`.**

    닫히지 않으면 연간 결과가 한 해가 아닌 무언가의 결과가 되고, 그 어긋남은
    총량 보존(「가」)이 **깨져야만** 드러난다 — 곧 늦게 드러난다.
    ⚠ 여기서 일수를 다시 세지 않는다. 정본은 자산이며 그것을 읽는 것은
    `DailyShape._calendar_days()` 하나다.
    """
    outcome = _run(
        _seasonal_path(tmp_path, generation=_GENERATION_SEASONS, load=_LOAD_SEASONS)
    )
    assert [s.name for s in outcome.seasons] == list(_DAYS), (
        f"계절 이름·차례가 자산과 다르다: {[s.name for s in outcome.seasons]}"
    )
    assert sum(s.days for s in outcome.seasons) == DAYS_PER_YEAR, (
        f"계절일수 합이 {sum(s.days for s in outcome.seasons)} 다 "
        f"(기대 {DAYS_PER_YEAR}) — 달력이 닫히지 않았다"
    )


# ── 「가」 총량은 자산이 정한다 ─────────────────────────────────────────────


def test_the_annual_energy_is_what_the_asset_says_not_what_the_seasons_make(
    tmp_path: Path,
) -> None:
    """★★★ **연간 발전량·연간 부하량이 계절 도입 전과 같다** (성질 「가」).

    에너지 총량은 자산·대장이 정하고 **운전만** 달라져야 한다. 여기가 빨간불이면
    R60 이 실측한 *「차례만 바꿔도 발전이 +281kWh 생긴다」* 가 되살아난 것이다.

    ⚠ **두 갈래로 잰다** — ⓐ 접힌 하루(`CaseOutcome.dispatch`)의 365배와
    ⓑ 계절별 기여의 합(`SeasonRun.per_resource_annual_kwh`). 둘이 같아야
    「연간등가 하루 × 365 == Σ(계절 하루 × 계절일수)」가 성립한다 — 한쪽만
    재면 그 항등식이 깨져도 초록불이다.
    """
    outcome = _run(
        _seasonal_path(tmp_path, generation=_GENERATION_SEASONS, load=_LOAD_SEASONS)
    )
    expected = {
        "e2e-pv": _levels()["pv_capacity_kw"]["base"] * PV_CAPACITY_FACTOR * HOURS_PER_YEAR,
        "e2e-load": -_load_kwh(),
    }
    for resource, want in expected.items():
        folded = _daily(outcome.dispatch, resource) * DAYS_PER_YEAR
        by_season = math.fsum(
            s.per_resource_annual_kwh[resource] for s in outcome.seasons
        )
        assert math.isclose(folded, want, rel_tol=1e-9), (
            f"{resource}: 연간등가 하루의 365배가 {folded:,.4f} 다 "
            f"(기대 {want:,.4f}) — 계절이 총량을 바꿨다"
        )
        assert math.isclose(by_season, want, rel_tol=1e-9), (
            f"{resource}: 계절별 기여의 합이 {by_season:,.4f} 다 "
            f"(기대 {want:,.4f}) — 계절일수 가중이 어긋났다"
        )


def test_the_seasons_really_are_different_days(tmp_path: Path) -> None:
    """★★ **대조군** — 계절 넷의 하루가 서로 다른가.

    다르지 않으면 위 「가」도 아래 「다」도 **공허하게** 통과한다: 차례를 바꿔도
    값에 흔적이 남지 않고, 총량 보존은 하루가 하나뿐인 것과 구별되지 않는다.
    """
    outcome = _run(
        _seasonal_path(tmp_path, generation=_GENERATION_SEASONS, load=_LOAD_SEASONS)
    )
    generation = {s.name: _daily(s.dispatch, "e2e-pv") for s in outcome.seasons}
    load = {s.name: _daily(s.dispatch, "e2e-load") for s in outcome.seasons}
    assert len(set(generation.values())) == len(outcome.seasons), (
        f"계절별 하루 발전이 서로 다르지 않다: {generation}"
    )
    assert len(set(load.values())) == len(outcome.seasons), (
        f"계절별 하루 부하가 서로 다르지 않다: {load}"
    )
    assert generation["여름"] > generation["겨울"], (
        f"여름 하루 발전({generation['여름']:.4f})이 겨울({generation['겨울']:.4f})보다 "
        "크지 않다 — 계절 몫이 운전에 서지 않았다"
    )


# ── 「다」 차례를 바꿔도 결과가 같다 — **36번의 위험이 여기다** ─────────────


def test_reordering_the_seasons_changes_nothing_in_the_result(tmp_path: Path) -> None:
    """★★★★ **계절을 적는 차례를 바꿔도 연간 결과가 같다** (성질 「다」).

    R60/WP-4 가 실측한 결함이 정확히 이것이었다 — `spread()` 로 계절을 **이어
    붙이면** 러너가 잡는 앞 하루가 「첫 계절의 하루」가 되어, 자산에 적힌 차례가
    결론을 정했다(연간 발전 +281kWh · 연간 부하 −315kWh). 그래서 R60 은 평균
    하루로 막았고 이 라운드가 그 막은 것을 열었다. **여는 쪽이 이 성질을 지고
    있다.**

    ## 왜 차례 하나가 아니라 **스물넷 전부**를 도는가

    하나만 바꿔 보면 *「그 한 자리만 우연히 무감했다」* 와 구별되지 않는다.
    계절 넷의 순열은 24개이고 전부 돈다.

    ## 무엇을 견주는가 — **결론축과 운전 전건**

    ⓐ 지표(`npv`) ⓑ 연간등가 하루의 **모든 스텝**(자원별·송전·수전) ⓒ 계절
    이름 → (일수 · 그 계절 연간 기여). ⓐ 만 보면 두 오차가 상쇄된 경우를
    놓치고, ⓑ 만 보면 지표 쪽 경로가 따로 차례를 타는 것을 놓친다.
    """
    base = _run(
        _seasonal_path(tmp_path, generation=_GENERATION_SEASONS, load=_LOAD_SEASONS)
    )
    base_by_name = {
        s.name: (s.days, dict(s.per_resource_annual_kwh), s.grid_export_annual_kwh,
                 s.grid_import_annual_kwh)
        for s in base.seasons
    }
    for index, order in enumerate(permutations(range(len(_GENERATION_SEASONS)))):
        if list(order) == sorted(order):
            continue
        moved = _run(
            _seasonal_path(
                tmp_path,
                generation=[_GENERATION_SEASONS[i] for i in order],
                load=[_LOAD_SEASONS[i] for i in order],
                name=f"reordered-{index}.yaml",
            )
        )
        assert moved.metrics["npv"] == base.metrics["npv"], (
            f"차례 {order} 에서 순현재가치가 {moved.metrics['npv']:,.0f} 로 "
            f"기준({base.metrics['npv']:,.0f})과 다르다 — 계절을 적는 차례가 "
            "결론을 정하고 있다(36번의 위험)"
        )
        assert moved.dispatch.grid_export == base.dispatch.grid_export, (
            f"차례 {order} 에서 계통 송전 하루가 달라졌다"
        )
        assert moved.dispatch.grid_import == base.dispatch.grid_import, (
            f"차례 {order} 에서 계통 수전 하루가 달라졌다"
        )
        for resource, result in base.dispatch.per_resource.items():
            assert moved.dispatch.per_resource[resource].electric == result.electric, (
                f"차례 {order} 에서 `{resource}` 의 연간등가 하루가 달라졌다"
            )
        moved_by_name = {
            s.name: (s.days, dict(s.per_resource_annual_kwh), s.grid_export_annual_kwh,
                     s.grid_import_annual_kwh)
            for s in moved.seasons
        }
        assert moved_by_name == base_by_name, (
            f"차례 {order} 에서 계절별 기여가 달라졌다"
        )


# ── 「라」 계절이 하나면 종전과 원소 하나까지 같다 ──────────────────────────


def test_a_single_season_asset_runs_exactly_as_one_folded_day_did(
    tmp_path: Path,
) -> None:
    """★★★ **계절이 하나(`연중`)면 접힌 하루를 한 번 돌린 것과 원소 하나까지 같다**
    (성질 「라」 · 계절 축이 서기 전과의 연속성).

    ## 오라클을 어떻게 세웠는가 — 옛 코드가 없으므로 **옛 계산**을 세운다

    종전 배포 경로는 *「연간등가 자원을 한 번 돌린다」* 였다. 그 자원은 지금도
    `CaseOutcome.resources` 로 나오므로, 그것을 엔진에 **한 번** 먹인 결과가
    옛 계산 그 자체다. 계절이 하나면 계절별 자원과 그 자원이 같으므로 두
    결과가 **부동소수 마지막 자리까지** 같아야 한다.

    ⚠ 허용오차를 두지 않는다(`==`). 일수 가중치가 `365/365 == 1.0` 이라
    `fsum([x * 1.0]) == x` 이고, 그것이 이 성질의 근거다 — 허용오차로 덮으면
    가중치가 1 이 아니게 되는 날 아무것도 말하지 않는다.
    """
    one_season = [
        {"name": "연중", "days": DAYS_PER_YEAR, "share": 1.0, "weights": _bell(12, 3.5)}
    ]
    one_load = [
        {"name": "연중", "days": DAYS_PER_YEAR, "share": 1.0, "weights": _bell(19, 4.0)}
    ]
    outcome = _run(
        _seasonal_path(
            tmp_path, generation=one_season, load=one_load, name="one-season.yaml"
        )
    )
    assert [s.name for s in outcome.seasons] == ["연중"], (
        f"계절이 하나가 아니다: {[s.name for s in outcome.seasons]}"
    )
    folded = RuleBasedEngine().run(
        list(outcome.resources),
        DispatchContext(steps=STEPS_PER_DAY, dt=SECONDS_PER_HOUR, year=Year(1)),
    )
    assert outcome.dispatch.grid_export == folded.grid_export, "계통 송전이 다르다"
    assert outcome.dispatch.grid_import == folded.grid_import, "계통 수전이 다르다"
    for resource, result in folded.per_resource.items():
        assert outcome.dispatch.per_resource[resource].electric == result.electric, (
            f"`{resource}` 의 하루가 접힌 하루와 다르다"
        )


# ── 판정 ③ — **월 단위로 이미 연간값인 것은 계절 수만큼 곱하지 않는다** ────


def test_the_monthly_peak_benefit_is_not_multiplied_by_the_number_of_seasons(
    tmp_path: Path,
) -> None:
    """★★★★ **첨두 절감은 계절 수만큼 중복 계상되지 않는다** (판정 ③).

    `PeakShaving` 은 `scales_with_dispatch_window = False` 이며 생성자에서
    **월별 감축 12개월치**를 받는다 — 이미 연간값이다. 계절 합산을 **금액에서**
    하면 그런 편익이 계절 수(넷)만큼 곱해지는데, **합계만 보면 드러나지 않는다.**

    ## 오라클 — 계절을 접은 자산과 **정확히 같은 금액**이어야 한다

    첨두 저감은 사업장 부하의 최대 시각과 그 값이 정하고
    (`ESS.reducible_peak_kw`), 그 부하 계열은 연간등가 하루의 것이다. 계절 넷의
    일수 가중 평균이 곧 `representative_day()` 이므로(WP-3 이 시험으로 붙든
    항등식), **계절 넷 자산과 「그 평균 하루를 연중 한 계절로 적은 자산」의
    첨두 절감은 같은 수여야 한다.** 넷이 곱해졌다면 여기가 곧바로 빨간불이다.
    """
    seasonal = _run(
        _seasonal_path(tmp_path, generation=_GENERATION_SEASONS, load=_LOAD_SEASONS)
    )
    shapes = load_daily_shapes(
        _seasonal_path(
            tmp_path,
            generation=_GENERATION_SEASONS,
            load=_LOAD_SEASONS,
            name="for-folding.yaml",
        )
    )
    folded_asset = _run(
        _seasonal_path(
            tmp_path,
            generation=[
                {
                    "name": "연중", "days": DAYS_PER_YEAR, "share": 1.0,
                    "weights": list(shapes.generation.representative_day(1.0, days=1)),
                }
            ],
            load=[
                {
                    "name": "연중", "days": DAYS_PER_YEAR, "share": 1.0,
                    "weights": list(shapes.load.representative_day(1.0, days=1)),
                }
            ],
            name="folded-one-season.yaml",
        )
    )
    peak = {
        outcome_name: next(
            line.annual_won
            for line in outcome.basis.benefits
            if line.tag == "PeakShaving"
        )
        for outcome_name, outcome in (("계절 넷", seasonal), ("접은 하루", folded_asset))
    }
    assert peak["계절 넷"] == peak["접은 하루"], (
        f"첨두 절감이 계절 넷에서 {peak['계절 넷']:,}원, 접은 하루에서 "
        f"{peak['접은 하루']:,}원이다 — 월 단위로 이미 연간값인 편익이 계절 "
        "수만큼 중복 계상됐을 수 있다(판정 ③)"
    )


def test_the_seasonal_run_still_reports_one_day_not_four(tmp_path: Path) -> None:
    """★★ **계절을 이어 붙이지 않는다** — 연간등가 하루는 여전히 24스텝이다.

    이어 붙이면(96스텝) 러너의 연간화 규약(`× DAYS_PER_YEAR`)이 그대로 곱해져
    **연간 총량이 계절 수만큼 커진다.** 「가」가 그것을 잡지만, 그때 원인이
    「가중이 틀렸다」인지 「창이 길어졌다」인지 이 검사가 갈라 준다.
    """
    outcome = _run(
        _seasonal_path(tmp_path, generation=_GENERATION_SEASONS, load=_LOAD_SEASONS)
    )
    assert len(outcome.dispatch.grid_export) == STEPS_PER_DAY, (
        f"연간등가 하루가 {len(outcome.dispatch.grid_export)}스텝이다 "
        f"(기대 {STEPS_PER_DAY}) — 계절을 이어 붙였다"
    )
    for season in outcome.seasons:
        assert len(season.dispatch.grid_export) == STEPS_PER_DAY, (
            f"계절 `{season.name}` 의 하루가 {len(season.dispatch.grid_export)}스텝이다"
        )


# ── ★ 모듈을 **직접** 부르는 자리 (R64/WP-4-fix2 · `NFR-105` 게이트 ②) ──────
#
# 위 일곱은 전부 러너(`run_single_case_e2e`)를 통과시켜 잰다 — 그것이 *「결론이
# 그 위에 선다」* 를 재는 옳은 방법이지만, **모듈이 정면 뒤에서 약속하는 것**은
# 그 통로로 재이지 않는다. 아래 둘이 그 자리를 직접 잰다.


def _deployed_case(**overrides: object) -> object:
    """배포 경로와 **같은 값으로** `build_and_dispatch_case` 를 직접 부른다.

    ⚠ **수를 지어내지 않는다** — 제원은 `core/casegrid/e2e_runner.py` 의 모듈
    상수에서, 금액·용량은 **대장 수준표**에서 그대로 가져온다. 리터럴을 적으면
    대장 판이 올라갈 때 이 시험만 옛 사업을 돌리게 된다.

    ⚠ 러너가 이 함수를 부르는 자리(`run_single_case_e2e`)와 **같은 인자**를
    넘긴다 — 다르면 여기서 재는 것이 배포 경로가 아니게 된다.
    """
    levels = _levels()
    kwargs: dict[str, object] = {
        "engine": RuleBasedEngine(),
        "daily_shapes": load_daily_shapes(),
        "case_values": {},
        "horizon_years": 20,
        "steps_per_day": STEPS_PER_DAY,
        "seconds_per_hour": SECONDS_PER_HOUR,
        "pv_capacity_kw": levels["pv_capacity_kw"]["base"],
        "pv_capacity_factor": PV_CAPACITY_FACTOR,
        "pv_capex": levels["pv_unit_cost"]["base"],
        "pv_inverter_share": levels["pv_inverter_share"]["base"],
        "pv_fixed_om": levels["pv_fixed_om"]["base"],
        "pv_self_consumption_ratio": PV_SELF_CONSUMPTION_RATIO,
        "price_escalation_rate": PRICE_ESCALATION_RATE,
        "replacement_escalation_rate": (
            PRICE_ESCALATION_RATE + levels["replacement_real_trend"]["base"]
        ),
        "annual_load_kwh": _load_kwh(),
        "extra_appliance_load_kwh": 0.0,
        "household_count": None,
        "ess_shares": None,
        "ess_capacity_kwh": levels["ess_capacity_kwh"]["base"],
        "ess_capex": levels["ess_unit_cost"]["base"],
        "ess_fixed_om": levels["ess_fixed_om"]["base"],
        "ess_replacement_price": levels["ess_replacement"]["base"],
        "ess_operating_mode": None,
        "ess_charge_source": None,
        # `None` 이 「고르지 않았다」이며 모듈 상수
        # (`ESS_DISCHARGE_ALLOCATION_DEFAULT` = 「부하 추종」)가 이긴다
        # (R64/WP-6b · 사용자 요구 5).
        "ess_discharge_allocation": None,
        "pv_allocation_priority": None,
        "baseline_arrangement": None,
        "pool_metering": None,
    }
    kwargs.update(overrides)
    return build_and_dispatch_case(**kwargs)  # type: ignore[arg-type]


def test_a_season_with_no_pv_surplus_lets_the_battery_rest() -> None:
    """★★★★ **잉여가 하루 종일 0 인 계절에서 배터리가 쉰다** — 그리고 **한 해는 산다**.

    ## 이 성질이 없으면 무엇이 되돌아오나

    가구 수가 늘면 겨울·여름처럼 `max(0, 발전 − 부하)` 가 **스물넷 전부 0** 인
    계절이 생긴다. 그런데 `ESS` 는 *「충전원이 태양광 잉여인데 잉여 시계열이
    없거나 전부 0입니다」* 로 거부한다
    (`core/der/ess_schedule.py::check_pv_surplus_profile`). 계절마다 배터리를
    세우면서 그 판정을 **계절에** 걸면 **한 계절이 비었다고 한 해 전체가 평가
    불가**가 된다 — R64/WP-4 가 실제로 한 번 그 상태를 만들었고, 가구 수를 준
    실행 여덟이 거기서 죽었다(`.orch/R64/result_4.md` ⑩ 의 (나) 하나).

    ## 재는 것 넷 — **하나만 재면 빈 구현이 통과한다**

        ⓐ 한 해가 산다        거부가 나지 않는다
        ⓑ 쉬는 계절이 있다     그 계절의 배터리 전력이 **원소 하나까지 0** 이다
        ⓒ 쉬지 않는 계절도 있다 ← 대조군. 없으면 ⓑ 는 「배터리가 늘 0」과 같다
        ⓓ 배터리가 사라지지 않는다 **모든 계절**의 자원 목록에 그 이름이 있고,
                              연간등가 자원 한 벌에도 서 있다(값을 무는 배터리다)

    ⚠ **3호를 쓰는 이유** — 이 자산·대장에서 잉여가 0 인 계절이 처음 생기는
    가구 수이고(1·2호에서는 네 계절 다 돈다), 4호부터는 **한 해 전체**의 잉여가
    0 이라 거부가 옳다. 곧 3호가 ⓑ 와 ⓒ 를 **동시에** 갖는 유일한 자리다.
    """
    built = _deployed_case(household_count=3)
    seasons = built.seasons  # type: ignore[attr-defined]
    fleet = built.ess_fleet  # type: ignore[attr-defined]
    assert fleet, "연간등가 저장장치가 서지 않았다 — ⓓ 의 재료가 없다"
    battery = fleet[0].name

    resting = [
        season.name
        for season in seasons
        if all(v == 0.0 for v in season.dispatch.per_resource[battery].electric)
    ]
    working = [season.name for season in seasons if season.name not in resting]
    moved = {
        season.name: math.fsum(
            abs(v) for v in season.dispatch.per_resource[battery].electric
        )
        for season in seasons
    }
    assert resting, (
        "잉여가 0 인 계절이 하나도 없다 — 이 시험이 겨누는 자리가 사라졌다 "
        f"(계절별 배터리 절대합 {moved})"
    )
    assert working, (
        f"모든 계절에서 배터리가 쉰다({resting}) — 그러면 「쉰다」가 「늘 0이다」와 "
        "구별되지 않는다(대조군 ⓒ)"
    )
    for season in seasons:
        assert battery in season.dispatch.per_resource, (
            f"계절 `{season.name}` 의 자원 목록에서 배터리가 사라졌다 — 쉬는 것과 "
            "없는 것은 다른 말이다"
        )
        assert season.per_resource_annual_kwh[battery] == pytest.approx(
            math.fsum(season.dispatch.per_resource[battery].electric) * season.days
        # RUF001: 「×」는 사람이 읽는 산식 문면이다 — `x` 로 바꾸면 곱셈이 변수
        # 이름으로 읽힌다(`core/casegrid/operating_lines.py` 가 세운 규약).
        ), f"계절 `{season.name}` 의 배터리 연간 기여가 그 하루 × 일수 가 아니다"  # noqa: RUF001


def test_the_dispatch_note_says_what_the_run_actually_did(tmp_path: Path) -> None:
    """★★★ **문면이 계절을 실제로 읽는다** — 박아 두지 않는다 (판정 ④).

    붙임 7 머리의 「시간 해상도」 한 줄이 이 함수에서 나온다. 문장을 상수로 박아
    두면 계절이 하나인 자산에서도 *「계절 넷을 각각 돌렸다」* 가 인쇄되고, 그것은
    **하지 않은 일을 적는 것**이다 — 이 저장소가 R60/WP-4-fix 에서 반대 방향으로
    한 번 고친 자리다(*「접었다」* 로 적어 계절이 결론을 가른다고 읽히게 했다).

    ⚠ **문면 전체를 리터럴로 대조하지 않는다** — 그러면 오탈자 하나에 깨지고
    다음 사람이 문장을 다듬을 수 없다. **문면이 주장하는 사실**을 건다.
    """
    seasonal = _run(
        _seasonal_path(tmp_path, generation=_GENERATION_SEASONS, load=_LOAD_SEASONS)
    )
    note = dispatch_note(seasonal.seasons, steps_per_day=STEPS_PER_DAY)

    assert f"계절 {len(seasonal.seasons)}개" in note, (
        f"문면이 계절 수를 자산에서 읽지 않는다: {note!r}"
    )
    for season in seasonal.seasons:
        assert season.name in note, f"계절 `{season.name}` 이 문면에 없다: {note!r}"
        assert f"{season.days}일" in note, (
            f"계절 `{season.name}` 의 일수({season.days})가 문면에 없다: {note!r}"
        )
    assert f"합 {DAYS_PER_YEAR}일" in note, (
        f"문면이 달력이 닫힌다는 것을 말하지 않는다: {note!r}"
    )
    assert "요일" in note, (
        f"**요일 변동이 그대로 미반영**임을 말하지 않는다 — 하지 않은 일을 한 "
        f"것으로 읽힌다: {note!r}"
    )

    # ★ 갈래 — 계절이 하나면 **다른 문면**이 나간다.
    one = _run(
        _seasonal_path(
            tmp_path,
            generation=[
                {"name": "연중", "days": DAYS_PER_YEAR, "share": 1.0,
                 "weights": _bell(12, 3.5)}
            ],
            load=[
                {"name": "연중", "days": DAYS_PER_YEAR, "share": 1.0,
                 "weights": _bell(19, 4.0)}
            ],
            name="one-season-note.yaml",
        )
    )
    plain = dispatch_note(one.seasons, steps_per_day=STEPS_PER_DAY)
    assert plain != note, "계절 하나짜리 실행이 계절 넷과 같은 문면을 인쇄한다"
    for season in seasonal.seasons:
        assert season.name not in plain, (
            f"계절 하나짜리 실행의 문면이 계절 `{season.name}` 을 말한다 — "
            f"하지 않은 일을 적는다: {plain!r}"
        )
    assert "요일" in plain, f"그 갈래에서도 요일 미반영을 말해야 한다: {plain!r}"

    # ★ 형상 자산이 없는 실행(`seasons` 가 비어 있다)도 **같은 갈래**다 —
    #   계절이 가를 것이 없다는 점에서 계절 하나와 같은 상태이기 때문이다.
    assert dispatch_note((), steps_per_day=STEPS_PER_DAY) == plain, (
        "형상 자산이 없는 실행이 계절 하나짜리와 다른 문면을 인쇄한다"
    )
