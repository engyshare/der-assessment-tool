"""**부하·일사 형상을 세운 본 실행** — 붙임 7 (2026-08-15 · R49/★A 개편).

## ⚠ 이 파일이 재던 「둘째 표」는 사라졌다

이 파일은 붙임 7 의 **둘째 표**(부하·일사 형상을 가정해 다시 그린 운전)를 재는
자리였다. R48 이 본 실행에 가구 부하를 세우면서 두 표가 완전히 같아졌고,
사용자 판정(`docs/decisions-2026-08-31-R49.md` §1)이 둘째 표를 지웠다.

**표가 없어졌다고 성질까지 버리지 않았다.** 아래 셋은 둘째 표와 무관하게 여전히
참이어야 하는 성질이며, 재는 **대상**만 본 실행(`dispatch_hours`)으로 옮겼다:

    ★ 형상은 **배분**이지 값이 아니다      ← 연간 총량이 바뀌면 안 된다
    ★ 부하가 **계통 수전**으로 나타난다     ← 「구매 비용이 얼마인가」가 물은 자리
    ★ 자산·대장이 없으면 **리포트가 서지 않는다**

지운 것과 그 근거는 `.orch/R49/result_1.md` 3절에 있다.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from core.casegrid.e2e_runner import (
    DAYS_PER_YEAR,
    HOURS_PER_YEAR,
    PV_CAPACITY_FACTOR,
    run_single_case_e2e,
)
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.profiles import load_daily_shapes
from core.report.case_report import build_case_report

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"
_LOAD = "e2e-load"
#: 부하 총량이 오는 대장 키. **여기에 수를 적지 않는다** — 대장이 정본이고,
#: 이 파일이 값을 베끼면 대장을 고쳐도 검사가 따라오지 않는다.
_LOAD_LEDGER_KEY = "load.household.annual"


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def _levels():
    return build_level_map(_ASSUMPTIONS)


def _load_kwh() -> float:
    """대장이 정한 가구 부하 총량 (kWh/년)."""
    return float(_levels()["household_load_annual_kwh"]["base"])


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
        annual_load_kwh=_load_kwh(),
    )
    expected = levels["pv_capacity_kw"]["base"] * PV_CAPACITY_FACTOR * HOURS_PER_YEAR

    for tag, outcome in (("평탄", plain), ("형상", shaped)):
        daily = sum(outcome.dispatch.per_resource["e2e-pv"].electric)
        assert math.isclose(daily * DAYS_PER_YEAR, expected, rel_tol=1e-6), (
            f"{tag}: 연간 발전량이 {daily * DAYS_PER_YEAR:,.0f}kWh 다 "
            f"(기대 {expected:,.0f}) — 형상이 총량을 바꿨다"
        )


def test_the_load_shows_up_as_grid_import() -> None:
    """★★ **부하를 넣으면 계통 수전이 실제 수량으로 나온다.**

    이것이 검토 의견 *「계통에서 전력을 구매한다면 구매 비용이 얼마인지」* 가
    물은 자리다. 부하가 없으면 수전은 ESS 충전분뿐이다.

    ## ⚠ 대조 대상이 바뀌었다 — 「둘째 표」가 아니라 **부하 없는 실행**이다

    종전 이 검사는 `report.dispatch_hours`(부하 없던 본 실행)와
    `report.assumed_hours`(부하를 가정한 둘째 표)를 견주었다. R48 이 본 실행에
    부하를 세운 뒤 그 둘이 같아져 *「수전이 늘지 않았다」* 로 빨간불이 됐다 —
    **성질이 깨진 것이 아니라 대조군이 사라진 것**이다.

    그래서 대조군을 *「형상은 주고 부하 총량은 주지 않은 실행」* 으로 세운다.
    붙임 7 이 싣는 본 실행은 여전히 그보다 수전이 많아야 한다.
    """
    report = _report()
    loadless = run_single_case_e2e(
        {}, level_map=_levels(), horizon_years=20, daily_shapes=load_daily_shapes()
    )
    reported = sum(hour.grid_import for hour in report.dispatch_hours)
    baseline = sum(float(v) for v in loadless.dispatch.grid_import)
    assert reported > baseline, (
        f"부하 {_load_kwh():,.0f}kWh/년 을 세운 실행의 수전이 늘지 않았다 "
        f"(부하 없음 {baseline:,.2f} · 붙임 7 {reported:,.2f})"
    )

    # ★ 부하 자원의 대표일 소비가 **대장 총량의 하루치**인가 — 형상은 배분이다.
    total_load = sum(
        -hour.per_resource.get(_LOAD, 0.0) for hour in report.dispatch_hours
    )
    assert math.isclose(total_load * DAYS_PER_YEAR, _load_kwh(), rel_tol=1e-6), (
        f"대표일 부하 {total_load:,.3f}kWh 의 연간화가 대장값과 다르다"
    )


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


def test_a_missing_load_total_stops_the_report(tmp_path: Path) -> None:
    """★★ 대장에 부하 총량이 없으면 **리포트가 서지 않는다** (R49/★A 전제 교체).

    ## ⚠ 이 검사의 전제가 R48 에 뒤집혔다 — 「표만 빠진다」에서 「서지 않는다」로

    종전 문면은 *「붙임 7 둘째 표만 빠지고 리포트 자체는 선다」* 였다. 부하가
    **둘째 표에만** 쓰이던 시절의 참이며, 그때는 `case_report` 가 이 값을
    `provider.get(LOAD_LEDGER_KEY)` 로 직접 읽어 없으면 비웠다.

    **R48 이 부하를 본 실행에 세우면서 이 값은 결론의 입력이 됐다.** 이제
    `build_level_map()` 이 `household_load_annual_kwh` 축을 세우다 `ValueError`
    를 내고, 리포트는 **형상 자산이 없을 때와 같은 자리에서** 선다 —
    기본값으로 메우면 「대장이 비었다」와 「이 값을 골랐다」가 구별되지 않고,
    리포트가 **지어낸 부하 위에 선 순현재가치**를 그렇다고 말하지 않고 싣는다.

    ⚠ **오라클은 그대로다** — *「없는 값을 메우지 않는다」*. 재는 대상만
    「둘째 표가 빠지는가」에서 「리포트가 서지 않는가」로 옮겼다.
    """
    data = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    kept = [
        item for item in data["assumptions"] if item["key"] != _LOAD_LEDGER_KEY
    ]
    assert len(kept) == len(data["assumptions"]) - 1, (
        f"대장에 `{_LOAD_LEDGER_KEY}` 항목이 없다 — 이 검사가 겨누는 자리가 "
        "이미 사라졌다"
    )
    data["assumptions"] = kept
    stripped = tmp_path / "assumptions.yaml"
    stripped.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match=_LOAD_LEDGER_KEY):
        build_case_report(
            _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=stripped
        )
