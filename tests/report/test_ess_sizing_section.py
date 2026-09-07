"""**ESS 적정용량 역산이 산출물에 선다** — 붙임 10 (R64/WP-8b · 사용자 요구 4).

R64/WP-8a 가 산식(`core/report/ess_sizing.py`)을 세웠으나 **부르는 배포 코드가
0곳**이었다 — 화면·리포트에 한 자도 나오지 않았다. 이 파일이 재는 것은 그
배선이며, 물음 넷이다:

    ① 배포 경로(`build_case_report`)가 그 산식을 **실제로 부르는가**
    ② 붙임 10 이 그 결과를 **인쇄하는가** — PV 역산과 같은 자리에
    ③ 역산이 **결론축을 움직이지 않는가** (되먹이지 않는다)
    ④ 못 하는 것을 **글자로 말하는가** — 절을 지우지 않는가

★ **이 파일은 산식도 「사용 가능 비율」도 베껴 적지 않는다.** 비율은 언제나
실제 `core/der/ess.py::ESS.usable_capacity_kwh` 를 불러 얻고, 결손은 실행이 낸
운전에서 읽는다 — 손으로 적으면 정본이 바뀌는 날 이 검사가 조용히 낡은 수를
지키게 된다.

⚠ **축 불변의 정본은 여기가 아니다** — `tests/golden/test_regression_scenarios.py`
가 세 시나리오의 `npv` 를 통째로 잰다. 여기서는 *「이 소절이 인쇄하는 용량과
실행이 실제로 쓴 용량이 다른데도 결론이 실행의 것 그대로인가」* 만 본다.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.casegrid.ledger_levels import design_variables
from core.contracts.der import DER
from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV
from core.report.case_report import CaseReport, build_case_report
from core.report.dispatch_notes import DispatchHour, split_by_direction
from core.report.ess_sizing import shortfall_kwh_by_step
from core.report.ess_sizing_section import (
    ANNUAL_EQUIVALENT_LABEL,
    ESSSizingReview,
    build_ess_sizing_review,
    ess_daily_sizing_section,
    usable_capacity_probe,
)
from core.report.narrative import render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 소절의 제목 줄. 검사 셋이 이 문면으로 절을 찾는다 — 각자 적으면 제목을
#: 다듬는 날 한쪽만 고쳐진다.
_HEADING = "### 경우 「ESS」"


@pytest.fixture(scope="module")
def report() -> CaseReport:
    """골든 무보조 시나리오 하나 — **배포 경로 그대로** 돌린다."""
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


def _run_capacity_kwh() -> float:
    """그 실행이 **실제로 세운** 배터리 용량(kWh).

    러너는 용량을 수준표의 `base` 에서만 읽고 기본값을 두지 않는다
    (`core/casegrid/ledger_levels.py::design_levels` 독스트링) — 그래서 여기서
    묻는 자리도 그 표 하나다. ⛔ 10.0 을 리터럴로 적지 않는다.
    """
    return next(v for v in design_variables() if v.name == "ess_capacity_kwh").base


# ── ① 배포 경로가 산식을 실제로 부른다 ───────────────────────────────


def test_the_deployment_path_actually_calls_the_inverse(report: CaseReport) -> None:
    """★★ **배선** — `build_case_report` 가 계절마다 역산을 채워 온다.

    R64/WP-8a 뒤 이 값은 아무도 채우지 않았다. 여기서 재는 것은 *「채워져
    있는가」* 이며, 계절이 선 실행이면 계절 수만큼 행이 있어야 한다 — 하나로
    접혀 있으면 그것은 계절을 다시 접은 것이다.
    """
    review = report.ess_sizing
    assert review.unmeasurable_reason is None, review.unmeasurable_reason
    assert len(review.seasons) == len(report.seasons) >= 2
    assert [s.season_name for s in review.seasons] == [
        s.name for s in report.seasons
    ]
    assert [s.days for s in review.seasons] == [s.days for s in report.seasons]
    for season in review.seasons:
        assert season.sizing.required_discharge_kwh > 0.0
        assert season.sizing.required_capacity_kwh > 0.0
        assert season.sizing.required_power_kw > 0.0


def test_the_year_is_the_end_of_the_analysis_period(report: CaseReport) -> None:
    """★ **연차는 분석기간 말이다** — 「가장 덜 내는 해」로 재야 그 용량이
    분석기간 내내 결손을 감당한다. 1년차로 재면 20년차에 미달인 용량을
    「적정」이라 인쇄한다."""
    assert report.ess_sizing.year == report.basis.horizon_years


def test_the_search_range_comes_from_the_design_variable(report: CaseReport) -> None:
    """★ 탐색 구간을 리터럴로 적지 않는다 — `_DESIGN_VARS` **× 단지 규모**다.

    2.0·30.0 을 여기(그리고 배선부)에 적으면 그 표가 바뀌어도 이 소절만 낡는다.

    ⚠ **곱이 붙었다** (R65/WP-2c). `_DESIGN_VARS` 의 수는 「한 호가 갖는 설비」
    이고 본문은 단지 규모를 곱한 설비로 돈다 — 구간을 안 곱하면 20호 실행에서
    이 소절만 한 호를 말한다. **곱한 것이지 띠의 수를 고친 것이 아니며**, 그
    사실을 재는 것이 여기 `* scale` 이다(리터럴 40·600 을 적으면 그 구별이
    사라진다). ⚠ 가구 수를 안 준 실행에서는 배수가 1 이라 종전과 같다.
    """
    design = next(v for v in design_variables() if v.name == "ess_capacity_kwh")
    scale = report.household_count if report.household_count is not None else 1
    assert report.ess_sizing.search_low_kwh == design.low * scale
    assert report.ess_sizing.search_high_kwh == design.high * scale


def test_the_printed_divisor_is_the_divisor_it_actually_divided_by(
    report: CaseReport,
) -> None:
    """★★ 산식 줄의 분모가 **실제로 나눈 그 분모**다.

    `필요 저장용량 = 하루 결손 합 ÷ 비율` 이므로 계절마다 그 몫이 인쇄된 비율과
    같아야 한다. ⚠ 비율을 손으로 적지 않는다 — 「비율이 그 자원에서 왔는가」는
    아래 `test_the_probe_agrees_with_the_resource_it_was_opened_from` 이 잰다.
    """
    review = report.ess_sizing
    assert review.usable_per_capacity_kwh is not None
    for season in review.seasons:
        sizing = season.sizing
        assert sizing.required_discharge_kwh / sizing.required_capacity_kwh == (
            pytest.approx(review.usable_per_capacity_kwh)
        )


# ── ② 붙임 10 이 인쇄한다 ────────────────────────────────────────────


def test_the_appendix_prints_the_inverse_next_to_the_pv_one(report: CaseReport) -> None:
    """★★ **붙임 10 · PV 역산 바로 뒤**에 선다 — 새 붙임을 만들지 않는다.

    양식의 붙임 번호를 늘리지 않았음을 「본문에 없고 붙임 10 안에 있다」로
    잰다: PV 소절(경우 「가」)의 뒤이며, `# 붙임` 머리 뒤다.
    """
    markdown = render_markdown(report)
    assert _HEADING in markdown
    assert markdown.index("# 붙임") < markdown.index("### 경우 「가」")
    assert markdown.index("### 경우 「가」") < markdown.index(_HEADING)


def test_every_season_gets_a_row_with_its_day_count(report: CaseReport) -> None:
    """★ 계절마다 한 행이고, 그 행이 **연 일수**를 함께 적는다.

    *「그 결손이 한 해에 며칠인가」* 가 표를 읽는 사람의 첫 물음이다 — 일수가
    없으면 겨울 하루의 결손을 한 해의 크기로 읽을 수 없다.
    """
    lines = ess_daily_sizing_section(report.ess_sizing)
    for season in report.seasons:
        row = next(
            (line for line in lines if line.startswith(f"| {season.name} |")), None
        )
        assert row is not None, f"{season.name} 행이 없다: {lines}"
        assert f"| {season.days:,} |" in row


def test_the_section_names_the_binding_day(report: CaseReport) -> None:
    """★ **매는 하루를 표에서 눈으로 고르게 두지 않는다.**

    계절이 넷이면 어느 행이 매는 행인지가 표를 훑는 순서에 달리고, 그 순서는
    자산이 계절을 적은 순서다.
    """
    review = report.ess_sizing
    binding = max(review.seasons, key=lambda s: s.sizing.required_capacity_kwh)
    body = "\n".join(ess_daily_sizing_section(review))
    assert f"매는 하루는 **{binding.season_name}**" in body


def test_the_formula_line_carries_the_divisor_it_used(report: CaseReport) -> None:
    """★ 산식 줄이 **분모를 수로** 적는다 — 적지 않으면 검토자가 SOC 창·SOH·
    백업 예비의 곱을 저장소 밖에서 찾아야 한다."""
    review = report.ess_sizing
    assert review.usable_per_capacity_kwh is not None
    body = "\n".join(ess_daily_sizing_section(review))
    assert f"{review.usable_per_capacity_kwh:.6f}kWh" in body
    assert f"{review.year}년차" in body


def test_the_section_says_the_number_is_a_floor_not_a_ceiling(
    report: CaseReport,
) -> None:
    """★★ 결손 **형상**은 1년차 운전에서 읽었다 — 그 사실을 글자로 적는다.

    연차가 가면 태양광도 열화해 결손 자체가 커지므로 말년차의 참 결손은 인쇄된
    것보다 크다. 적지 않으면 검토자가 이 수를 **상한**으로 읽는다.
    """
    body = "\n".join(ess_daily_sizing_section(report.ess_sizing))
    assert "하한이다" in body
    assert "1년차 운전" in body


# ── ③ 되먹이지 않는다 — 결론축이 움직이지 않는다 ─────────────────────


def test_the_inverse_does_not_feed_back_into_the_run(report: CaseReport) -> None:
    """★★★ **판정 — 역산 결과를 실행에 되먹이지 않는다.**

    되먹이면 사업이 스스로 자기 설비를 키우고 결론축이 그 크기를 따라 움직인다
    — 어느 수가 입력이고 어느 수가 결과인지 말할 수 없게 된다. 여기서 재는
    것은 **그 두 수가 실제로 다른데도** 실행이 쓴 용량이 그대로라는 것이다.
    ⚠ 세 시나리오의 `npv` 자체는 `tests/golden/` 이 잰다.
    """
    binding = max(
        report.ess_sizing.seasons, key=lambda s: s.sizing.required_capacity_kwh
    )
    assert binding.sizing.required_capacity_kwh != pytest.approx(
        _run_capacity_kwh()
    ), "역산 용량과 실행 용량이 같아 「되먹였는가」를 가릴 수 없다"
    body = "\n".join(ess_daily_sizing_section(report.ess_sizing))
    assert "진단이다" in body and "채택한 것이 아니다" in body


def test_the_seasons_are_not_folded_before_the_shortfall_is_measured(
    report: CaseReport,
) -> None:
    """★★★ **계절을 접고 재면 결손이 사라진다** — 접지 않았음을 수로 잰다.

    결손은 스텝마다 `max(0, 부하 − PV)` 이고 그 `max` 는 비선형이라, 계절을
    일수로 가중 평균한 하루(`CaseReport.dispatch_hours`)에서 재면 겨울의 부족과
    여름의 잉여가 **같은 시각에서 상쇄돼** 결손이 줄어든다(옌센). 계절마다 재어
    일수로 가중 평균한 값이 그보다 **커야** 한다 — 같으면 어딘가에서 접힌 것이다.
    """
    total_days = sum(s.days for s in report.seasons)
    over_seasons = (
        math.fsum(
            s.sizing.required_discharge_kwh * s.days for s in report.ess_sizing.seasons
        )
        / total_days
    )
    generation, load = split_by_direction(report.dispatch_hours)
    folded = math.fsum(
        shortfall_kwh_by_step(
            load_kwh_by_step=[
                -sum(hour.per_resource.get(n, 0.0) for n in load)
                for hour in report.dispatch_hours
            ],
            pv_kwh_by_step=[
                sum(hour.per_resource.get(n, 0.0) for n in generation)
                for hour in report.dispatch_hours
            ],
        )
    )
    assert over_seasons > folded, (
        f"계절별 결손 가중평균 {over_seasons} 이 접힌 하루 {folded} 보다 크지 "
        "않다 — 결손을 접힌 하루에서 재고 있다"
    )


# ── ④ 못 하는 것을 글자로 말한다 ─────────────────────────────────────


def _hours(*, load: list[float], pv: list[float]) -> tuple[DispatchHour, ...]:
    """손으로 지은 대표일 하나 — 부하 자원 하나와 발전 자원 하나."""
    return tuple(
        DispatchHour(
            step=step,
            per_resource={"탐침-부하": -load[step], "탐침-발전": pv[step]},
            grid_export=0.0,
            grid_import=0.0,
        )
        for step in range(len(load))
    )


def _probe_ess() -> ESS:
    return ESS(name="탐침-ess", capacity_kwh=10.0, power_kw=5.0)


def _review(
    hours: tuple[DispatchHour, ...],
    *,
    resources: tuple[DER, ...] | None = None,
    search_high_kwh: float = 30.0,
) -> ESSSizingReview:
    return build_ess_sizing_review(
        hours=hours,
        seasons=(),
        resources=(_probe_ess(),) if resources is None else resources,
        year=20,
        search_low_kwh=2.0,
        search_high_kwh=search_high_kwh,
    )


def test_a_run_without_a_battery_says_so_instead_of_vanishing() -> None:
    """★ 저장장치가 없는 실행 — **절을 지우지 않고 사유를 적는다.**

    지우면 검토자가 *「역산이 필요 없었다」* 와 *「역산을 싣지 못했다」* 를
    가릴 수 없다.
    """
    review = _review(
        _hours(load=[1.0] * 24, pv=[0.0] * 24),
        resources=(PV(name="탐침-pv", capacity_kw=1.0, capacity_factor=0.15),),
    )
    assert review.unmeasurable_reason is not None
    assert "저장장치가 없습니다" in review.unmeasurable_reason
    body = "\n".join(ess_daily_sizing_section(review))
    assert _HEADING in body
    assert "역산하지 못했다" in body and "저장장치가 없습니다" in body


def test_a_run_without_a_dispatch_says_so() -> None:
    """★ 잴 운전이 없는 실행 — 결손을 읽을 하루가 없다."""
    review = _review(())
    assert review.unmeasurable_reason is not None
    assert "잴 운전이 없습니다" in review.unmeasurable_reason


def test_a_day_without_a_load_resource_says_so() -> None:
    """★ 부하 자원이 없는 하루 — 결손을 잴 분모가 없다.

    ⚠ 0 으로 메워 「결손 0」이라 적지 않는다 — 그러면 필요 용량 0kWh 가 인쇄되고
    검토자는 *「배터리가 필요 없다」* 로 읽는다.
    """
    review = _review(_hours(load=[0.0] * 24, pv=[1.0] * 24))
    assert review.unmeasurable_reason is not None
    assert "부하 자원이 없습니다" in review.unmeasurable_reason
    assert ANNUAL_EQUIVALENT_LABEL in review.unmeasurable_reason


def test_a_capacity_beyond_the_search_range_is_printed_as_outside() -> None:
    """★★★ **판정 ⑤ — 넘는데 넘지 않는 것처럼 적지 않는다.**

    역산 용량이 `ess_capacity_kwh` 탐색 상한을 넘을 수 있다. 그때 구간을 넓히지
    않고 **「밖이다」를 인쇄한다** — 넓히는 것은 결론축(4.4)이 훑는 폭 자체를
    바꾸는 일이고, 넘는 점을 지우지도 않는다.
    """
    design = next(v for v in design_variables() if v.name == "ess_capacity_kwh")
    # 상한을 확실히 넘도록 결손을 크게 잡는다 — 값이 아니라 **넘김**을 위한 탐침이다.
    review = _review(
        _hours(load=[design.high] * 24, pv=[0.0] * 24),
        search_high_kwh=design.high,
    )
    assert review.unmeasurable_reason is None
    (season,) = review.seasons
    assert season.days is None, "계절이 없는 실행인데 일수를 지어냈다"
    assert season.sizing.required_capacity_kwh > design.high
    assert not season.sizing.within_search_range
    body = "\n".join(ess_daily_sizing_section(review))
    assert f"구간 상한 {design.high:g}kWh 초과" in body
    assert f"| {ANNUAL_EQUIVALENT_LABEL} | — |" in body


# ── 탐침 자체 — 「자원에게 되묻는다」가 산식과 같은가 ─────────────────


@pytest.mark.parametrize("year", [1, 7, 20])
@pytest.mark.parametrize(
    "ess_kwargs",
    [
        {},
        {"soc_min_pct": 20.0, "soc_max_pct": 95.0},
        {
            "backup_reserve_pct": 30.0,
            "operating_mode": ESSOperatingMode.BACKUP_RESERVE,
        },
    ],
)
def test_the_probe_agrees_with_the_resource_it_was_opened_from(
    ess_kwargs: dict[str, object], year: int
) -> None:
    """★★ `usable_capacity_probe` 가 그 자원과 **한 자리도 다르지 않다.**

    그 함수는 산식을 옮겨 적지 않고 비율을 되물어 얻는다 — 그러므로 자기가
    열린 그 용량에서는 정본과 정확히 같아야 하고, 다른 용량에서는 새 `ESS` 를
    세워 얻은 값과 같아야 한다. ⚠ 여기서 SOC 창의 곱을 손으로 적지 않는다.
    """
    ess = ESS(name="탐침", capacity_kwh=10.0, power_kw=5.0, **ess_kwargs)
    probe = usable_capacity_probe(ess)
    assert probe(capacity_kwh=10.0, year=year) == pytest.approx(
        ess.usable_capacity_kwh(year=year)
    )
    bigger = ESS(name="탐침", capacity_kwh=25.0, power_kw=5.0, **ess_kwargs)
    assert probe(capacity_kwh=25.0, year=year) == pytest.approx(
        bigger.usable_capacity_kwh(year=year)
    )
