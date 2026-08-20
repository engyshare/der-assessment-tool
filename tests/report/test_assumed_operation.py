"""**부하·일사 형상을 가정한 운전** — 붙임 7 둘째 표 (2026-08-15).

파이프라인이 실제로 도는 운전에는 **가구 부하가 없다**(붙임 8). 그 표만 실으면
검토자는 *부하 없는 단지*를 실물로 읽는다.

⚠ **「태양광이 24시간 평탄하다」는 R37 에 거짓이 됐다.** 일사 곡선이 결론에
배선되어 본 실행의 발전도 곡선이며, 붙임 8 의 「일중 발전 프로파일 (평탄)」 행은
사라졌다. 남은 차이는 **부하 하나**다 — 그래서 이 파일의 대조도 「형상 유무」가
아니라 「부하 유무」로 바뀌었다.

    ★ 형상은 **배분**이지 값이 아니다      ← 연간 총량이 바뀌면 안 된다
    ★ 자원을 **리포트가 다시 세우지 않는다** ← 같은 진입점을 한 번 더 부른다
    ★ 프로포마·결론은 **건드리지 않는다**   ← 한쪽만 반영하면 한 방향으로 틀린다
    ★ 자산이 없으면 **메우지 않는다**       ← 지어낸 운전을 실물처럼 싣지 않는다
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

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
    배타 규칙 유형 A 라 같은 프로포마에 함께 실을 수 없다. 그 상태의 NPV 는
    **사업에 불리한 쪽으로** 틀린다 — 그래서 붙임 7 둘째 표는 수량만 싣는다.

    ## ⚠ 기준선이 R37 에 바뀌었다 — **부하만** 배제한다

    종전 이 검사는 결론이 *「형상을 전혀 주지 않은 실행」* 과 같은지 보았고,
    그것으로 두 가지를 한꺼번에 붙들고 있었다: **부하가 결론에 들어가지 않는가**
    와 (뜻하지 않게) **발전 형상도 들어가지 않는가**. R37 이 일사 곡선을 결론에
    배선했으므로 뒤쪽은 이제 붙들 것이 아니다.

    그래서 대조 실행을 *「형상은 주고 부하 총량은 주지 않은 실행」* 으로 바꾼다 —
    이 검사가 실제로 막으려던 것(부하가 결론에 스며드는 것)만 남는다. 두 갈래를
    한 대조로 묶어 두면 배선이 옳아진 날 이 검사가 **옳은 리포트를 빨간불로
    만든다**, 그리고 실제로 그렇게 됐다.
    """
    report = _report()
    text = render_markdown(report)
    plain_export = sum(hour.grid_export for hour in report.dispatch_hours)
    assumed_export = sum(hour.grid_export for hour in report.assumed_hours)
    assert assumed_export != plain_export, "가정 운전이 송전을 바꾸지 않았다"

    # 결론은 **부하 없는** 파이프라인 운전 위에 서 있어야 한다.
    conclusion = float(report.metrics["npv"])
    loadless = run_single_case_e2e(
        {},
        level_map=_levels(),
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
    )
    assert conclusion == float(loadless.variants["as_planned"]["npv"]), (
        "결론이 부하를 실은 가정 운전 위에 서 있다 — 자가소비 절감이 빠진 "
        "채로 잉여판매만 줄어든 값이다"
    )
    body = text[: text.index("# 붙임")]
    assert "형상 가정" not in body, "가정 운전의 수가 본문에 올라갔다"


def test_a_missing_profile_asset_stops_the_report() -> None:
    """★★ 형상 자산이 없으면 **리포트가 서지 않는다** (R37).

    R37 이 일사 곡선을 결론에 배선한 뒤로 이 자산은 **장식이 아니라 결론의
    입력**이다. 없을 때 조용히 이용률 하나로 되돌아가면 리포트는 *심야에도
    태양광이 발전하는* 사업의 순현재가치를 **그렇다고 말하지 않고** 싣는다 —
    그것이 붙임 8 이 R34 부터 「미반영 항목」으로 들고 있던 바로 그 상태다.

    ⚠ **비우는 것으로 고치지 않는다.** 「자산이 비었다」를 표만 빼는 것으로
    처리하면 본문 2절의 수는 그대로 나오고, 무엇 위에 선 수인지가 사라진다.
    """
    import core.report.case_report as module

    original = module.load_daily_shapes
    module.load_daily_shapes = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
        OSError("자산 없음")
    )
    try:
        with pytest.raises(OSError):
            build_case_report(
                _GOLDEN / "scenario_unsubsidized.yaml",
                assumptions_path=_ASSUMPTIONS,
            )
    finally:
        module.load_daily_shapes = original  # type: ignore[assignment]


def test_an_asset_that_vanishes_between_the_two_reads_is_not_swallowed() -> None:
    """★★ 자산이 **읽는 사이에** 사라지면 조용히 비우지 않는다 (R37 후속).

    ## 왜 이 자리가 있는가 — 변이가 초록불로 남았다

    `build_case_report` 는 형상을 **두 번** 읽는다: 결론에 넘기려고 한 번,
    붙임 7 둘째 표를 그리려고 `_assumed_operation` 에서 한 번. 그래서
    *「자산이 없으면 리포트가 서지 않는다」* 는 **첫 읽기에만** 걸려 있고, 둘째
    읽기가 실패하는 갈래는 위 검사가 보지 못한다.

    그 갈래를 `except OSError` 로 삼키면 **결론은 이미 읽은 형상 위에 서 있는데
    붙임 7 은 「미산출」로 비는** 상태가 된다 — 리포트가 무엇 위에 섰는지
    스스로 부정하는 꼴이고, 아무 예외도 나지 않는다. `OSError` 를 `except` 에서
    뺀 것이 그 처리이며, 이 검사가 그것을 붙든다(빼지 않으면 초록불이다).

    ⚠ **읽기를 한 번으로 줄이면 이 갈래는 아예 없어진다** — 그것이 더 나은
    구조이나 이 라운드의 담당 밖이다. 구조가 바뀌면 이 검사는 「없어진 갈래를
    지키는 검사」가 되므로 그때 함께 지울 자리다.
    """
    import core.report.case_report as module

    original = module.load_daily_shapes
    calls = {"n": 0}

    def vanishing(*args: object, **kwargs: object):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("둘째 읽기에서 자산이 사라졌다")
        return original(*args, **kwargs)

    module.load_daily_shapes = vanishing  # type: ignore[assignment]
    try:
        with pytest.raises(OSError):
            build_case_report(
                _GOLDEN / "scenario_unsubsidized.yaml",
                assumptions_path=_ASSUMPTIONS,
            )
        assert calls["n"] >= 2, (
            f"형상을 {calls['n']}회만 읽었다 — 이 검사가 겨누는 둘째 읽기에 "
            "닿지 않았다(읽기가 한 번으로 줄었다면 이 검사를 지울 자리다)"
        )
    finally:
        module.load_daily_shapes = original  # type: ignore[assignment]


def test_a_missing_load_total_leaves_the_table_out() -> None:
    """★★ 대장에 부하 총량이 없으면 **붙임 7 둘째 표만** 빠지고, 사유는 **대장뿐**이다.

    기본값으로 메우면 「대장이 비었다」와 「이 값을 골랐다」가 구별되지 않고,
    붙임 7 이 **지어낸 부하를 실물처럼** 싣는다. 자산 부재와 달리 이쪽은 결론의
    입력이 아니므로(부하는 운전만 그린다) 리포트 자체는 선다.

    ## ⚠ **사유에 「형상 자산 부재」가 없어야 한다** (R37 후속)

    이 자리가 비어 있어서 부작용이 났다. 종전 검사는 사유 문면이 **있는가**만
    보았고, 그래서 문면이 *「형상 자산 또는 대장 항목 부재」* 로 남아 있는 것을
    아무도 잡지 못했다 — 그 괄호의 앞쪽 절은 **인쇄될 수 없는 사유**다(자산이
    없으면 위 검사대로 리포트가 서지 않는다).

    그래서 여기서는 **적힌 것과 적히지 않은 것을 함께** 본다. 「무엇이 있는가」만
    보는 검사는 사유가 넓어지는 방향의 잘못을 구조적으로 보지 못한다.
    """
    import core.report.case_report as module

    original = module.LOAD_LEDGER_KEY
    module.LOAD_LEDGER_KEY = "load.household.annual.대장에없는키"  # type: ignore[assignment]
    try:
        report = build_case_report(
            _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
        )
        assert report.assumed_hours == (), "대장 항목이 없는데 운전이 나왔다"
        assert report.assumed_basis is None
        text = render_markdown(report)
        assert "미산출 (대장 항목 부재)" in text, (
            "대장 항목 부재를 리포트가 밝히지 않는다"
        )
        # ★ 사유가 **넓어지지 않았는가.** 자산은 결론의 입력이므로 여기까지 온
        # 실행에서는 사유가 될 수 없다 — 그 절이 문면에 있으면 리포트가 스스로
        # 세운 규칙과 어긋나는 안내를 싣는 것이다.
        for impossible in ("형상 자산 또는", "형상 자산 부재"):
            assert impossible not in text, (
                f"인쇄될 수 없는 사유가 문면에 남았다: {impossible!r} — "
                "자산이 없으면 리포트 자체가 서지 않는다"
            )
    finally:
        module.LOAD_LEDGER_KEY = original  # type: ignore[assignment]
