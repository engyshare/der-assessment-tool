"""**부하·일사 형상을 가정한 운전** — 붙임 7 둘째 표 (2026-08-15).

파이프라인이 실제로 도는 운전에는 **가구 부하가 없고 태양광이 24시간 평탄**
하다(붙임 8 두 항목). 그 표만 실으면 검토자는 *야간 태양광 발전*과 *부하 없는
단지*를 실물로 읽는다.

    ★ 형상은 **배분**이지 값이 아니다      ← 연간 총량이 바뀌면 안 된다
    ★ 자원을 **리포트가 다시 세우지 않는다** ← 같은 진입점을 한 번 더 부른다
    ★ 프로포마·결론은 **건드리지 않는다**   ← 한쪽만 반영하면 한 방향으로 틀린다
    ★ 자산이 없으면 **메우지 않는다**       ← 지어낸 운전을 실물처럼 싣지 않는다
"""
from __future__ import annotations

import math
from pathlib import Path

from core.casegrid.e2e_runner import (
    DAYS_PER_YEAR,
    HOURS_PER_YEAR,
    PV_CAPACITY_FACTOR,
    run_single_case_e2e,
)
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.profiles import load_daily_shapes
from core.report.case_report import build_case_report
from core.report.narrative import render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"
_LOAD_KWH = 3_600.0


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def _levels():
    return build_level_map(_ASSUMPTIONS)


def test_a_shape_moves_energy_but_does_not_create_it() -> None:
    """★★ **형상은 배분이지 값이 아니다.**

    형상이 총량까지 정하면 대장을 고쳐도 그 값이 따라오지 않는다 — 그리고
    그때 붙임 7 은 *「부하를 반영했다」* 를 말하면서 **다른 사업**을 그린다.
    여기서는 연간 발전량이 형상 유무와 무관하게 같은지 본다.
    """
    levels = _levels()
    plain = run_single_case_e2e({}, level_map=levels, horizon_years=20)
    shaped = run_single_case_e2e(
        {},
        level_map=levels,
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=_LOAD_KWH,
    )
    expected = levels["pv_capacity_kw"]["base"] * PV_CAPACITY_FACTOR * HOURS_PER_YEAR

    for tag, outcome in (("평탄", plain), ("형상", shaped)):
        daily = sum(outcome.dispatch.per_resource["e2e-pv"].electric)
        assert math.isclose(daily * DAYS_PER_YEAR, expected, rel_tol=1e-6), (
            f"{tag}: 연간 발전량이 {daily * DAYS_PER_YEAR:,.0f}kWh 다 "
            f"(기대 {expected:,.0f}) — 형상이 총량을 바꿨다"
        )


def test_the_shaped_run_has_no_generation_at_night() -> None:
    """★ 형상을 주면 **야간 발전이 0** 이다 — 그것이 이 표를 만든 이유다."""
    hours = _report().assumed_hours
    assert hours, "가정 운전이 비어 있다"
    night = [0, 1, 2, 3, 4, 23]
    for step in night:
        assert hours[step].per_resource["e2e-pv"] == 0.0, (
            f"{step}시에 태양광이 {hours[step].per_resource['e2e-pv']}kWh 발전한다"
        )


def test_the_load_shows_up_as_grid_import() -> None:
    """★★ **부하를 넣으면 계통 수전이 실제 수량으로 나온다.**

    이것이 검토 의견 *「계통에서 전력을 구매한다면 구매 비용이 얼마인지」* 가
    물은 자리다. 지금 파이프라인의 수전은 ESS 충전분뿐이다.
    """
    report = _report()
    plain = sum(hour.grid_import for hour in report.dispatch_hours)
    assumed = sum(hour.grid_import for hour in report.assumed_hours)
    assert assumed > plain, (
        f"부하 {_LOAD_KWH:,.0f}kWh/년 을 넣었는데 수전이 늘지 않았다 "
        f"(파이프라인 {plain:,.2f} · 가정 {assumed:,.2f})"
    )
    total_load = sum(
        -hour.per_resource.get("e2e-load", 0.0) for hour in report.assumed_hours
    )
    assert math.isclose(total_load * DAYS_PER_YEAR, _LOAD_KWH, rel_tol=1e-6), (
        f"대표일 부하 {total_load:,.3f}kWh 의 연간화가 대장값과 다르다"
    )


def test_the_assumed_run_does_not_move_the_conclusion() -> None:
    """★★★ **한쪽만 반영한 수를 결론으로 올리지 않는다** (양식 4절).

    부하를 편익 계산에 태우면 잉여판매가 줄어드는데, 그 대가인 자가소비 절감은
    소매 단가가 없어 계상할 수 없다. 그 상태의 NPV 는 **사업에 불리한 쪽으로**
    틀린다 — 그래서 붙임 7 둘째 표는 수량만 싣는다.
    """
    report = _report()
    text = render_markdown(report)
    plain_export = sum(hour.grid_export for hour in report.dispatch_hours)
    assumed_export = sum(hour.grid_export for hour in report.assumed_hours)
    assert assumed_export != plain_export, "가정 운전이 송전을 바꾸지 않았다"

    # 결론은 파이프라인 운전 위에 서 있어야 한다.
    conclusion = float(report.metrics["npv"])
    unshaped = run_single_case_e2e({}, level_map=_levels(), horizon_years=20)
    assert conclusion == float(unshaped.variants["as_planned"]["npv"]), (
        "결론이 형상 가정 운전 위에 서 있다 — 자가소비 절감이 빠진 채로 "
        "잉여판매만 줄어든 값이다"
    )
    body = text[: text.index("# 붙임")]
    assert "형상 가정" not in body, "가정 운전의 수가 본문에 올라갔다"


def test_a_missing_profile_asset_leaves_the_table_out() -> None:
    """★ 자산이 없으면 **메우지 않는다.**

    기본 형상으로 메우면 「자산이 비었다」와 「이 형상을 골랐다」가 구별되지
    않고, 붙임 7 이 **지어낸 운전을 실물처럼** 싣는다.
    """
    import core.report.case_report as module

    original = module.load_daily_shapes
    module.load_daily_shapes = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
        OSError("자산 없음")
    )
    try:
        report = build_case_report(
            _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
        )
        assert report.assumed_hours == (), "자산이 없는데 운전이 나왔다"
        assert report.assumed_basis is None
        text = render_markdown(report)
        assert "미산출 (형상 자산 또는 대장 항목 부재)" in text, (
            "자산 부재를 리포트가 밝히지 않는다"
        )
    finally:
        module.load_daily_shapes = original  # type: ignore[assignment]
