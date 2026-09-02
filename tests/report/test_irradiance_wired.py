"""**일사 곡선이 결론에 닿는가** — 기본 경로를 진입점에서 붙든다 (R37).

## 왜 이 파일이 새로 필요했는가

배선은 통로가 없어서 빠진 것이 아니라 **쓰지 않아서** 빠져 있었다. 그 상태를
붙임 8 이 「일중 발전 프로파일 (평탄)」으로 정직하게 싣고 있었는데도 결함이
살아 있었던 이유는 검사 쪽에 있다 —

    tests/report/test_shaped_run_invariants.py
        ::test_the_shaped_run_has_no_generation_at_night   ← **형상을 명시적으로
                                                             준 실행**을 본다
                                                (R49/★A 에 지웠다 — 아래 참조)

즉 *「형상을 주면 야간이 0 이다」* 는 붙들려 있었고 *「기본 경로가 형상을
준다」* 는 아무도 붙들지 않았다. 그 자리를 메우는 것이 이 파일이다.

⚠ **저쪽 검사는 R49/★A 에 지웠다.** 붙임 7 둘째 표(형상을 가정한 운전)가
사라지면서 *「형상을 명시적으로 준 실행」* 과 *「기본 경로가 준 실행」* 이 같은
것이 됐고, 두 검사가 같은 성질을 두 번 재게 됐다. 남긴 쪽은 **더 엄한 이
파일**이다 — 야간 스텝을 손으로 적지 않고 형상 자산에서 읽어 온다.

## 무엇을 어느 층에 대고 재는가 (동어반복 회피)

이 파일의 단언에 나오는 수는 **셋 다 다른 층**에서 온다.

    ① 야간이 0 이라는 사실   ← 형상 **자산** (`fixtures/profiles/…`)
    ② 곡선이 결론에 닿았다   ← **진입점** 재실행과의 일치
    ③ 스윕도 같은 사업이다   ← 리포트 **4절** 과 **2절** 의 교차

①만 쓰면 자산의 야간 가중치를 0 이 아닌 값으로 바꾸는 변이가 검사를 따라와
공허해진다(status.md 「검사가 자기 검사 대상에서 정본을 읽어 오면」). 그래서
①에는 **자산 자신이 어떤 형상인가**를 함께 물어, 「해가 없는 시간이 있는가」를
자산에 대고 잰다 — 그 수는 fixture 의 값을 옮겨 적은 사본이 아니다.

## ⚠ `req()` 마커를 달지 않았다

이 파일이 붙드는 것은 spec 조항이 아니라 **배포 경로가 자산을 쓰는가**다.
가까워 보이는 ID(`FR-1001-AC2` 등)를 짐작해서 붙이면 status.md 「수용기준 ID를
추정해서 쓰면 안 된다」가 막으려던 상태가 된다 — ID 가 실재하므로 매핑 검사는
통과하고, **엉뚱한 조항이 초록불**이 된다. 조항을 확인한 사람이 붙일 자리로
남긴다.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.profiles import load_daily_shapes
from core.report.case_report import (
    CONCLUSION_METRIC,
    PLAN_VARIANT,
    build_case_report,
)
from core.report.unreflected import build_unreflected
from tests.report.conftest import report_rec_terms, report_shapes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"
_PV = "e2e-pv"


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def test_the_shape_asset_actually_has_hours_without_sun() -> None:
    """★★ **자산이 「해가 없는 시간」을 갖고 있는가** — ①의 근거를 먼저 세운다.

    아래 검사들은 *「기본 실행의 야간 발전이 0 이다」* 를 자산에 대고 잰다.
    그러면 자산의 야간 가중치가 0 이 아닌 값으로 바뀌는 변이는 **양쪽을 함께**
    움직여 검사를 통과시킨다 — 그 구멍을 여기서 막는다.

    ⚠ **몇 시부터 몇 시까지인지는 적지 않는다.** 적으면 자산의 사본이 되고,
    일출·일몰을 옮기는 정당한 갱신이 이 검사를 빨간불로 만든다. 여기서 붙드는
    것은 *「0 인 스텝이 있고, 곡선이 평탄하지 않다」* — 태양광의 성질이며
    자산이 그것을 그리고 있는가를 묻는다.
    """
    weights = load_daily_shapes().generation.weights
    dark = [i for i, w in enumerate(weights) if w == 0.0]
    assert dark, (
        f"발전 형상 {len(weights)}스텝에 0 인 스텝이 하나도 없다 — "
        "해가 없는 시간이 없는 형상이며, 그러면 「야간 발전 0」을 이 자산에 "
        "대고 잴 수 없다"
    )
    assert max(weights) > min(weights), "발전 형상이 평탄하다 — 곡선이 아니다"


def test_the_default_report_run_has_no_generation_at_night() -> None:
    """★★★ **기본 경로**의 야간 발전이 0 이다 — 이 라운드가 메운 자리.

    `build_case_report` 를 인자 없이 부른 결과를 본다. 형상을 여기서 주지
    않는다 — **리포트가 스스로 주는가**가 물음이기 때문이다.
    """
    hours = _report().dispatch_hours
    assert hours, "붙임 7 운전이 비어 있다"
    dark = [i for i, w in enumerate(load_daily_shapes().generation.weights) if w == 0.0]
    for step in dark:
        assert hours[step].per_resource[_PV] == 0.0, (
            f"{step}시에 태양광이 {hours[step].per_resource[_PV]}kWh 발전한다 — "
            "기본 경로가 형상을 넘기지 않아 이용률 하나로 24스텝을 균등 "
            "배분하고 있다"
        )
    series = [hour.per_resource[_PV] for hour in hours]
    assert max(series) > min(series), (
        f"기본 경로의 발전이 전 스텝 {series[0]}kWh 로 평탄하다"
    )


def test_the_conclusion_stands_on_the_shaped_run() -> None:
    """★★★ **결론이 곡선 위에 서 있다** — 표시만 곡선인 구현을 막는다.

    붙임 7 만 곡선이고 프로포마·NPV 는 평탄이던 것이 이 라운드 전의 상태다.
    그때 붙임 7 을 보는 검사는 전건 초록불이었다(R33 이 임계값에서 만난 형태와
    같다: **표시만 하는 구현은 표시를 보는 검사를 전부 통과한다**).
    """
    report = _report()
    levels = build_level_map(_ASSUMPTIONS)
    rec_price, rec_weight = report_rec_terms()
    shaped = run_single_case_e2e(
        {},
        level_map=levels,
        horizon_years=report.basis.horizon_years,
        daily_shapes=report_shapes(),
        # ★★ 가구 부하도 같은 배선 (R48/WP-B → WP-F) — 본 실행이 부하를
        # 넘기므로, 이 재실행도 넘기지 않으면 「곡선 대 평탄」이 아니라
        # 「곡선+부하 대 곡선」을 재는 것이 된다.
        annual_load_kwh=levels["household_load_annual_kwh"]["base"],
        # ★ REC 도 같은 배선 (R52/WP-6) — 안 넘기면 리포트(REC 있음)와
        # 재실행(REC 없음)이 서로 다른 사업을 그린다.
        rec_price_won_per_unit=rec_price, rec_weight_pv=rec_weight,
    )
    flat = run_single_case_e2e(
        {},
        level_map=levels,
        horizon_years=report.basis.horizon_years,
    )
    reported = float(report.metrics[CONCLUSION_METRIC])
    assert reported == pytest.approx(
        float(shaped.variants[PLAN_VARIANT][CONCLUSION_METRIC]), abs=1.0
    ), "리포트의 결론이 곡선 실행의 결론과 다르다"
    # ★ 두 실행이 **실제로 다른 수**를 낸다는 것도 함께 붙든다. 같으면 위
    # 단언은 무엇을 넘겨도 성립하고, 그때 이 검사는 공허하다.
    assert float(flat.variants[PLAN_VARIANT][CONCLUSION_METRIC]) != pytest.approx(
        reported, abs=1.0
    ), "평탄 실행과 곡선 실행의 결론이 같다 — 이 검사가 배선을 붙들지 못한다"


def test_the_shape_moves_energy_without_creating_it() -> None:
    """★ 형상이 **총량을 옮기지 않는다** — 형상은 배분이지 값이 아니다.

    총량이 함께 움직였다면 이 라운드의 전/후 비교는 *「곡선의 효과」* 가 아니라
    *「발전량이 바뀐 효과」* 를 잰 것이 된다.

    ## ⚠ 이 검사는 **기본 경로를 보지 않는다**

    이름에 `…_on_the_default_path` 가 붙어 있었는데 **거짓이었다** — 여기서는
    러너를 평탄·곡선으로 두 번 직접 부르고 총량을 견주며, 리포트는
    `horizon_years` 를 얻는 데만 쓴다. 그래서 배선을 되돌리는 변이에 **이
    검사는 초록불로 남는다**(그 변이는 위 세 검사가 잡는다).

    이름이 거짓이면 다음 사람이 *그 자리가 붙들려 있다*고 읽으므로 이름에서
    떼었다. 붙드는 것(형상은 총량을 만들지 않는다)은 그대로 옳고 필요하다 —
    러너 층의 성질이며, 기본 경로가 그것을 쓰는지는 위 검사들이 본다.
    """
    levels = build_level_map(_ASSUMPTIONS)
    horizon = _report().basis.horizon_years
    flat = run_single_case_e2e({}, level_map=levels, horizon_years=horizon)
    shaped = run_single_case_e2e(
        {}, level_map=levels, horizon_years=horizon, daily_shapes=report_shapes()
    )
    totals = [
        sum(outcome.dispatch.per_resource[_PV].electric)
        for outcome in (flat, shaped)
    ]
    assert math.isclose(totals[0], totals[1], rel_tol=1e-9), (
        f"대표일 발전량이 평탄 {totals[0]:,.4f}kWh · 곡선 {totals[1]:,.4f}kWh 로 "
        "다르다 — 형상이 총량을 바꿨다"
    )


def test_the_flat_generation_row_is_gone_from_appendix_eight() -> None:
    """★★ 붙임 8 의 「일중 발전 프로파일 (평탄)」 행이 **사라졌다.**

    그 행은 판정이지 문장이므로(`_flat_generation_item`) 곡선이 들어오면 스스로
    빠진다. 빠지지 않으면 판정이 아니라 문장인 것이고, 그때 리포트는 **없는
    결함을 계속 인쇄한다.**
    """
    labels = [item.label for item in build_unreflected(_report())]
    assert not [x for x in labels if x.startswith("일중 발전 프로파일")], (
        f"곡선이 결론에 닿았는데 평탄 항목이 남아 있다 — 미반영 {labels}"
    )


def test_the_sensitivity_and_capacity_sections_run_the_same_business() -> None:
    """★★★ **스윕에만 배선을 빠뜨리면 두 절이 다른 사업을 그린다.**

    본 실행은 곡선, 민감도·용량 검토는 평탄 — 그러면 각 절은 자기 기준에서
    매끈하고 **아무 검사도 걸리지 않는다.** 여기서는 4절(용량 검토)이 *실제로
    쓴 용량*에서 낸 결론이 2절의 결론과 같은지 본다. 스윕이 다른 배선으로
    돌면 그 두 수가 갈린다.

    ⚠ 이 단언의 두 수는 **리포트의 서로 다른 두 절**에서 온다 — 어느 쪽도
    검사가 정하지 않는다.
    """
    report = _report()
    conclusion = float(report.metrics[CONCLUSION_METRIC])
    levels = build_level_map(_ASSUMPTIONS)
    horizon = report.basis.horizon_years

    # ── ⓐ 4절 ↔ 2절: 실제로 쓴 용량에서 두 절이 같은 수를 내는가 ──────────
    # 용량 격자가 사용값을 지나는 인자만 대상이다(저장장치 격자 2·9·16·23·30 은
    # 사용값 10 을 지나지 않는다). **그래서 이 갈래만으로는 부족하고** 아래 ⓑ 가
    # 남은 점 전부를 진입점으로 되짚는다.
    at_used = [
        (finding, point)
        for finding in report.capacity_review
        for point in finding.points
        if point.value == finding.used_value and point.conclusion is not None
    ]
    assert at_used, (
        "용량 격자가 사용값을 지나는 인자가 0건이다 — 이 갈래가 0회 순회한다"
    )
    for finding, point in at_used:
        assert point.conclusion == pytest.approx(conclusion, abs=1.0), (
            f"{finding.variable}: 용량 검토가 실제 용량 {finding.used_value}"
            f"{finding.unit} 에서 {point.conclusion:,.0f}원을 내는데 2절의 "
            f"결론은 {conclusion:,.0f}원이다 — 스윕이 본 실행과 다른 "
            "배선으로 돌고 있다"
        )

    # ── ⓑ 4절의 모든 점을 **진입점으로 되짚는다** (R33·R35 가 세운 형태) ───
    # 여기서 형상을 검사가 직접 주므로, 스윕에만 배선을 빠뜨리는 변이는 사용값을
    # 지나지 않는 격자에서도 걸린다.
    probed = 0
    rec_price, rec_weight = report_rec_terms()
    for finding in report.capacity_review:
        for point in finding.points:
            if point.conclusion is None:
                continue  # 제약에 막힌 점은 결론이 없다
            probe = {name: dict(v) for name, v in levels.items()}
            probe[finding.variable] = {
                **probe[finding.variable], "base": point.value
            }
            outcome = run_single_case_e2e(
                {},
                level_map=probe,
                horizon_years=horizon,
                daily_shapes=report_shapes(),
                # ★★ 가구 부하도 같은 배선 (R48/WP-B → WP-F) — 4절 용량 검토는
                # `_Sweeper.conclusion_at_many()` 를 거치므로 부하를 이미 본다.
                annual_load_kwh=probe["household_load_annual_kwh"]["base"],
                # ★ REC 도 같은 배선 (R52/WP-6).
                rec_price_won_per_unit=rec_price, rec_weight_pv=rec_weight,
            )
            measured = float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])
            assert point.conclusion == pytest.approx(measured, abs=1.0), (
                f"{finding.variable}={point.value}{finding.unit}: 리포트 4절은 "
                f"{point.conclusion:,.0f}원인데 그 값으로 곡선 배선으로 다시 "
                f"돌리면 {measured:,.0f}원이다"
            )
            probed += 1
    assert probed >= 5, f"되짚은 용량 점이 {probed}개뿐이다 — 순회가 너무 얕다"


def test_the_influence_endpoints_move_with_the_shaped_run() -> None:
    """★★ **3절(민감도)도 곡선 위에 서 있다.**

    파이프라인이 읽지 않는 인자(`unread_by_pipeline`)는 양 끝이 기준 결론과
    같아야 한다 — 그 항목이 스윕의 **기준선**을 드러낸다. 스윕만 평탄으로 돌면
    그 기준선이 2절의 결론과 갈린다.
    """
    report = _report()
    conclusion = float(report.metrics[CONCLUSION_METRIC])
    unread = [e for e in report.influences if e.unread_by_pipeline]
    assert unread, (
        "파이프라인이 읽지 않는 인자가 0건이다 — 이 검사가 0회 순회로 통과한다"
    )
    for entry in unread:
        for label, value in (("low", entry.npv_low), ("high", entry.npv_high)):
            assert value == pytest.approx(conclusion, abs=1.0), (
                f"{entry.variable}: 파이프라인이 읽지 않는 인자인데 `{label}` "
                f"끝이 {value:,.0f}원이고 2절 결론은 {conclusion:,.0f}원이다 — "
                "스윕이 본 실행과 다른 배선으로 돈다"
            )


def test_the_grid_columns_carry_no_negative_zero() -> None:
    """★ 계통 송·수전에 **음의 0** 이 없다 (R37 실측).

    `max(-net, 0.0)` 은 `net` 이 정확히 `+0.0` 인 스텝에서 `-0.0` 을 돌려준다.
    수치로는 0 과 같아 잔차 검사도 합계 검사도 걸리지 않는데 **붙임 7 은
    「-0.00」 을 인쇄하고**, 검토자는 계통 수전에 붙은 음수 부호를 읽는다.
    일사 곡선이 배선되어 야간 발전이 0 이 되자 net 이 정확히 0 인 스텝이 처음
    생겨 드러났다 — 그러므로 이 검사는 이 라운드가 만든 자리다.
    """
    hours = _report().dispatch_hours
    offenders = [
        (hour.step, hour.grid_import, hour.grid_export)
        for hour in hours
        if math.copysign(1.0, hour.grid_import) < 0.0
        or math.copysign(1.0, hour.grid_export) < 0.0
    ]
    assert not offenders, f"음의 0 이 계통 열에 남았다: {offenders[:3]}"
