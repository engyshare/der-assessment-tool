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
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.assumption.provider import AssumptionSet
from core.casegrid.ledger_levels import (
    design_variables,
    ledger_backed_variables,
    required_scalar,
)
from core.contracts.der import DER
from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV
from core.report.capacity import search_range_note
from core.report.case_influences import CONCLUSION_METRIC
from core.report.case_report import CaseReport, build_case_report
from core.report.dispatch_notes import DispatchHour, split_by_direction
from core.report.ess_sizing import shortfall_kwh_by_step
from core.report.ess_sizing_section import (
    ADOPTED_HEAD,
    ADOPTED_TERM,
    ANNUAL_EQUIVALENT_LABEL,
    CAPACITY_KIND_APPLIED,
    CAPACITY_KIND_DIAGNOSTIC,
    CAPACITY_KIND_RUNNING,
    SELF_SUFFICIENT_HEAD,
    ESSSizingReview,
    binding_season,
    build_ess_sizing_review,
    capacity_kind_lines,
    ess_daily_sizing_section,
    usable_capacity_probe,
)
from core.report.narrative import render_markdown
from core.report.sizing import base_level_point

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
    grid_supply_allowance: float = 0.0,
) -> ESSSizingReview:
    """손으로 지은 탐침 하나.

    ⚠ **허용 비율의 기본값을 0 으로 둔 것은 탐침의 편의다** — 배포 경로는
    대장에서 읽어 넘긴다(`core/report/case_report.py`). 완화 자체를 재는 검사는
    아래 「⑤ 완화분」 무리이며 그것들이 비율을 **적어** 넘긴다.
    """
    return build_ess_sizing_review(
        hours=hours,
        seasons=(),
        resources=(_probe_ess(),) if resources is None else resources,
        year=20,
        search_low_kwh=2.0,
        search_high_kwh=search_high_kwh,
        grid_supply_allowance=grid_supply_allowance,
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

    ## ★★ R67/WP-N2 가 여기에 한 줄을 더했다 — **「밖」이 무슨 뜻인가**

    사용자 판정이 *「용량 범위 제한이 없어야 하며」*(판정 R67b §2-2)이므로,
    「구간 밖」 표시가 *「구간을 넘었으니 못 믿는다」* 로 읽히면 반대가 된다.
    그 구간은 **경제성 스윕의 것**이고 이 역산의 답은 그것과 무관하게 그대로
    제시된다 — 값을 구간 안으로 깎는 것이 결함이다. ⚠ 문면을 이 파일에 베끼지
    않는다: 정본은 `core/report/capacity.py::search_range_note` 다.
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
    assert search_range_note(sweep_where="본문 4.4") in body, (
        "「구간 밖」이 무슨 뜻인지 적히지 않았다 — 그 표시가 「넘었으니 못 "
        "믿는다」로 읽히면 사용자 판정(용량 범위 제한을 두지 않는다)과 반대가 된다"
    )
    assert f"{design.high:g}" in body and "깎지 않는다" in body, (
        "역산값을 구간 안으로 깎지 않는다는 진술이 없다"
    )


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


# ── ⑤ 완화분 — 두 값이 서고 역산 채택안이 무엇인지 적힌다 (R67/WP-N3) ──


def _report_with_allowance(allowance: float | None) -> CaseReport:
    """골든 시나리오를 그대로, 또는 **허용 비율만 오버라이드해** 돌린다.

    ⚠ **골든 픽스처를 고치지 않는다.** 읽기만 하고 쓰는 곳은
    `tempfile.TemporaryDirectory()` 안이다 — 관용구의 정본은
    `tests/report/test_load_shift_wired.py::_report` 이며, 그래야 이 검사가
    사용자가 실제로 지나는 통로(**전용 필드가 아니라 대장 오버라이드**)를 잰다.
    """
    fields: dict[str, Any] = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    if allowance is not None:
        fields["assumption_overrides"] = [
            {
                "key": ledger_backed_variables()["grid_supply_allowance"],
                "value": allowance,
                "reason": "이 검사가 축을 흔든다",
            }
        ]
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / _GOLDEN.name
        path.write_text(
            yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return build_case_report(path, assumptions_path=_ASSUMPTIONS)


def _ledger_allowance() -> float:
    """대장이 정한 허용 비율. **여기에 수를 적지 않는다** — 대장이 정본이다.

    키도 손으로 적지 않는다 — `ledger_backed_variables()` 가 케이스 변수와
    대장 키의 짝을 갖는 자리이며, `core/report/case_report.py` 가 같은 자리에서
    같은 짝을 읽어 배선한다.
    """
    key = ledger_backed_variables()["grid_supply_allowance"]
    provider = AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))
    return required_scalar(provider, key, note="이 검사")


def test_the_deployment_path_carries_the_ledger_allowance(report: CaseReport) -> None:
    """★★★ **배선** — 소절의 허용 비율이 **대장에서** 왔다.

    소절이 그 비율을 스스로 고르면 대장을 고쳐도 채택값이 안 움직이고, 그
    어긋남은 아무 예외도 내지 않는다 — 이 저장소가 형상(R37)·기준선
    갈래(R60)·이용률(R67/WP-N2)에서 세 번 밟은 형태다.
    """
    assert report.ess_sizing.grid_supply_allowance == pytest.approx(
        _ledger_allowance()
    )
    assert report.ess_sizing.grid_supply_allowance > 0.0, (
        "대장 비율이 0 이다 — 채택값이 완전 자립분과 같아져 「완화분이 채택값」이 "
        "사실상 꺼진다"
    )


def test_the_adopted_value_is_the_relaxed_one_and_is_exactly_the_kept_share(
    report: CaseReport,
) -> None:
    """★★★ **계절마다 채택값이 완전 자립분의 정확히 `1 - 비율` 배다.**

    ⚠ **기대값을 리터럴(0.7)로 적지 않는다** — 대장에서 읽은 비율로 짓는다.
    산식 자체의 성질은 `tests/report/test_ess_sizing.py` 가 탐침 하루로 재고,
    여기서 재는 것은 **배포 실행이 그 성질을 그대로 낸다**는 것이다.
    """
    kept = 1.0 - _ledger_allowance()
    assert report.ess_sizing.seasons, "계절이 서지 않아 잴 것이 없다"
    for season in report.ess_sizing.seasons:
        assert season.sizing.grid_supply_allowance == 0.0
        assert season.relaxed.grid_supply_allowance == pytest.approx(
            _ledger_allowance()
        )
        assert season.relaxed.required_capacity_kwh == pytest.approx(
            season.sizing.required_capacity_kwh * kept
        )
        assert season.relaxed.required_power_kw == pytest.approx(
            season.sizing.required_power_kw * kept
        )


def test_the_section_prints_both_values_and_says_which_one_is_adopted(
    report: CaseReport,
) -> None:
    """★★ **두 값을 나란히 싣고 채택값이 완화분임을 적는다** (판정 §4).

    한 값만 실으면 검토자가 *「917kWh 가 필요하다」* 와 *「642kWh 가 필요하다」*
    중 어느 것이 이 평가의 답인지 고르게 된다.
    """
    review = report.ess_sizing
    body = "\n".join(ess_daily_sizing_section(review))
    # ⚠ **낱말을 리터럴로 적지 않는다**(R68/WP-1) — 열 이름의 정본은
    #   `ADOPTED_HEAD` · `SELF_SUFFICIENT_HEAD` 이고 렌더러가 같은 상수를 쓴다.
    #   박아 두면 낱말을 고치는 날 **시험이 옛 낱말을 지킨다.**
    assert f"{SELF_SUFFICIENT_HEAD} 저장용량" in body
    assert f"{ADOPTED_HEAD} 저장용량" in body
    assert f"{SELF_SUFFICIENT_HEAD} 정격출력" in body
    assert f"{ADOPTED_HEAD} 정격출력" in body
    assert f"{ADOPTED_TERM}은 「계통 허용」 완화분" in body
    assert "`policy.grid_supply_allowance`" in body, (
        "비율의 출처(대장 키)가 적히지 않았다"
    )
    assert "근거 법령·고시는 **확인되지 않았다**" in body, (
        "없는 근거를 있는 것처럼 두었다 — 「30%」의 출처는 사용자 문면 하나다"
    )
    for season in review.seasons:
        row = next(
            line for line in ess_daily_sizing_section(review)
            if line.startswith(f"| {season.season_name} |")
        )
        assert f"| {season.sizing.required_capacity_kwh:,.2f} |" in row
        assert f"| {season.relaxed.required_capacity_kwh:,.2f} |" in row


def test_the_section_says_the_relaxation_hits_power_too(report: CaseReport) -> None:
    """★★ **완화가 용량에만 걸리는가 출력에도 걸리는가** — 표가 답한다.

    다음 사람이 반드시 묻는 물음이고, 적지 않으면 표의 두 열(용량·출력)이 같은
    비율로 준 것을 보고 *「출력까지 깎은 것은 실수」* 로 읽을 수 있다.
    """
    body = "\n".join(ess_daily_sizing_section(report.ess_sizing))
    assert "완화는 용량과 출력에 «둘 다» 걸린다" in body


def test_the_section_still_says_it_is_a_diagnosis_not_an_applied_result(
    report: CaseReport,
) -> None:
    """★★★ **「채택값」이 실행 구성이 되지 않는다** (사용자 판정 R67 §4-4).

    *「적용 전이면 결과를 만들어 낸 것처럼 표시하지 않는다」* — ★ 열이 붙었으니
    그 표시가 더 필요해졌다. 지우면 검토자가 ★ 를 *「이 용량으로 돌렸다」* 로
    읽는다. ⚠ 실행이 실제로 쓴 용량은 `_run_capacity_kwh()` 가 답한다.
    """
    body = "\n".join(ess_daily_sizing_section(report.ess_sizing))
    assert "진단이다" in body and "적용 전이다" in body
    assert "채택한 것이 아니다" in body
    binding = max(
        report.ess_sizing.seasons, key=lambda s: s.relaxed.required_capacity_kwh
    )
    assert binding.relaxed.required_capacity_kwh != pytest.approx(
        _run_capacity_kwh()
    ), "채택값과 실행 용량이 같아 「되먹였는가」를 가릴 수 없다"


def test_shaking_the_ledger_allowance_moves_the_adopted_value() -> None:
    """★★★ **대장을 흔들면 채택값이 따라 움직인다** — 값이 소스에 없다.

    ⚠ **골든 픽스처를 고치지 않는다.** 대장 오버라이드(`assumption_overrides`)로
    흔든다 — 사용자가 실제로 지나는 통로이며 관용구는
    `tests/report/test_load_shift_wired.py::_report` 의 것이다.

    ★ **완전 자립분은 움직이지 않아야 한다** — 그것은 허용 비율 0 의 역산이고,
    함께 움직이면 완화가 「두 값」이 아니라 한 값을 옮긴 것이 된다.
    """
    shaken = _report_with_allowance(0.10)
    kept = 0.90
    assert shaken.ess_sizing.grid_supply_allowance == pytest.approx(0.10)
    for season in shaken.ess_sizing.seasons:
        assert season.relaxed.required_capacity_kwh == pytest.approx(
            season.sizing.required_capacity_kwh * kept
        )
    base = _report_with_allowance(None)
    for shook, plain in zip(
        shaken.ess_sizing.seasons, base.ess_sizing.seasons, strict=True
    ):
        assert shook.sizing.required_capacity_kwh == pytest.approx(
            plain.sizing.required_capacity_kwh
        ), "허용 비율을 흔들었는데 완전 자립분이 함께 움직였다"
        assert shook.relaxed.required_capacity_kwh != pytest.approx(
            plain.relaxed.required_capacity_kwh
        ), "허용 비율을 흔들었는데 채택값이 그대로다 — 배선이 닿지 않았다"


def test_the_relaxation_does_not_move_the_conclusion_axis() -> None:
    """★★★ **결론축은 한 원도 움직이지 않는다** — 이 절은 진단이다.

    허용 비율을 끝에서 끝까지 흔들어도 순현재가치가 그대로여야 한다. 움직이면
    역산이 실행에 되먹여진 것이고, 그때 *어느 수가 입력이고 어느 수가 결과인지*
    말할 수 없게 된다(`core/report/ess_sizing_section.py` 머리말 ★★★).
    ⚠ 세 시나리오의 `npv` 자체는 `tests/golden/` 이 잰다 — 여기서는 **이 축을
    흔들어도** 그 수가 같다는 것만 본다.
    """
    plain = _report_with_allowance(None)
    for allowance in (0.0, 0.10, 0.50):
        shaken = _report_with_allowance(allowance)
        assert shaken.metrics[CONCLUSION_METRIC] == pytest.approx(
            plain.metrics[CONCLUSION_METRIC]
        ), (
            f"허용 비율 {allowance} 에서 결론축이 움직였다 — 역산이 실행에 "
            "되먹여졌다"
        )


# ── ⑥ R68/WP-1 — 「채택」이 **두 가지를 가리켰다.** 셋으로 갈라 세운다 ──────
#
# ③ 표의 열 이름이 「★ 채택 정격용량」이고 겨울 값이 642.07kWh 였는데, 이 실행이
# 실제로 돌린 저장장치는 200kWh / 100kW 다(검토서 §3.2 · §6 의 1번). 한 낱말이
# ⓐ 「역산 갈래 둘 중 답으로 고른 쪽」과 ⓑ 「진단값 중 실행에 반영하기로 결정한
# 값」을 함께 가리켰다. ⛔ **사용자 판정(완화분이 역산의 답)은 뒤집지 않는다** —
# 아래 검사들이 재는 것은 **낱말이 갈라져 있는가**와 **구분 표가 서는가**다.


def test_the_adopted_column_says_what_kind_of_adoption_it_is() -> None:
    """★★★ 열 이름이 **무엇의 채택인지** 말한다 — 「채택」 하나로 두지 않는다.

    ⚠ 이 검사가 없으면 낱말이 「★ 채택」으로 되돌아가도 초록불이다. 그 낱말이
    실제로 *「이 용량으로 돌렸다」* 로 읽혔다.
    """
    assert ADOPTED_TERM == "역산 채택안", (
        "역산의 답을 부르는 낱말이 「무엇의 채택인지」를 말하지 않는다"
    )
    assert ADOPTED_TERM in ADOPTED_HEAD, "열 이름이 그 낱말을 쓰지 않는다"
    assert CAPACITY_KIND_APPLIED != ADOPTED_TERM, (
        "역산의 답과 실행 반영 결정이 같은 낱말이다 — 갈라 세운 것이 아니다"
    )


def test_the_appendix_table_no_longer_says_bare_adopted(report: CaseReport) -> None:
    """★★ 붙임 10 의 표에 **맨 「★ 채택」이 한 자리도 없다.**

    ⚠ 「채택」이 통째로 사라져야 하는 것은 아니다 — 표 아래 마지막 주의
    *「채택한 것이 아니다」* 는 **실행 반영**의 뜻으로 옳게 쓴 자리다(지시문
    §2-ⓐ). 재는 것은 **열 이름 쪽 낱말** 하나다.
    """
    body = "\n".join(ess_daily_sizing_section(report.ess_sizing))
    assert "★ 채택 " not in body, (
        "열 이름이 여전히 맨 「★ 채택」이다 — 무엇의 채택인지가 없다"
    )
    assert "채택한 것이 아니다" in body, (
        "실행 반영을 부정하는 줄까지 지웠다 — 그 자리의 「채택」은 옳은 쓰임이다"
    )


def test_the_binding_season_is_chosen_by_the_code_not_by_a_literal(
    report: CaseReport,
) -> None:
    """★★ **매는 하루를 코드가 고른다** — 계절 이름을 박지 않는다.

    ⚠ 실측에서 그것은 「겨울」이지만 그 사실은 자산과 형상이 정한 것이다. 박으면
    형상이 바뀌는 날 **틀린 계절이 매는 하루로 인쇄된다.**
    """
    review = report.ess_sizing
    binding = binding_season(review)
    assert binding.sizing.required_capacity_kwh == max(
        season.sizing.required_capacity_kwh for season in review.seasons
    ), "매는 하루가 가장 큰 용량을 요구하는 하루가 아니다"
    # ★ 완화가 스텝마다 같은 상수를 곱하므로 두 값에서 같은 하루가 매야 한다.
    assert binding.season_name == max(
        review.seasons, key=lambda s: s.relaxed.required_capacity_kwh
    ).season_name


def test_the_capacity_kind_table_separates_the_three_meanings(
    report: CaseReport,
) -> None:
    """★★★ **구분 표가 셋을 갈라 세운다** — 진단 · 실행 · 채택 (검토서 §3.2).

    ⚠ **수를 리터럴로 적지 않는다** — 태양광은 `report.self_sufficiency`, 저장
    장치는 매는 하루, 실행 용량은 준 조각에서 온다.
    """
    review = report.ess_sizing
    binding = binding_season(review)
    body = "\n".join(
        capacity_kind_lines(
            review=review,
            pv=report.self_sufficiency,
            run_used=["저장장치 용량 **200 kWh**"],
        )
    )
    for kind in (
        CAPACITY_KIND_DIAGNOSTIC,
        CAPACITY_KIND_RUNNING,
        CAPACITY_KIND_APPLIED,
    ):
        assert f"| **{kind}** |" in body, f"구분 표에 「{kind}」 행이 없다"
    assert f"{binding.sizing.required_capacity_kwh:,.2f}kWh" in body, (
        "진단 용량 칸에 완전 자립분이 없다"
    )
    assert f"{binding.relaxed.required_capacity_kwh:,.2f}kWh" in body, (
        "진단 용량 칸에 역산 채택안이 없다"
    )
    assert binding.season_name in body, "어느 하루 기준인지가 없다"
    assert SELF_SUFFICIENT_HEAD in body and ADOPTED_TERM in body
    assert "저장장치 용량 **200 kWh**" in body, "실행 용량 칸이 준 값을 안 쓴다"


def test_the_capacity_kind_table_says_the_applied_capacity_is_none(
    report: CaseReport,
) -> None:
    """★★★ **「채택 용량」 칸이 「없음」이라고 말한다** — 그리고 사유가 없다고도.

    이 저장소는 역산 결과를 실행에 되먹이지 않는다(모듈 머리말 ★★★). ⇒ 반영된
    진단값은 **있을 수 없고**, 실행 용량이 진단 용량과 다른 사유는 이 리포트가
    갖고 있지 않다 — **그 둘을 글자로 적는 것**이 이 표의 값이다.
    """
    body = "\n".join(
        capacity_kind_lines(
            review=report.ess_sizing,
            pv=report.self_sufficiency,
            run_used=["태양광 용량 **60 kW**"],
        )
    )
    assert "**없음 — 이 실행은 진단값을 반영하지 않았다**" in body
    assert "사람 판단 자리다" in body, (
        "실행 용량이 진단 용량과 다른 사유가 「없다」는 진술이 빠졌다 — 빠지면 "
        "독자가 그 사유를 리포트 안에서 찾는다"
    )


def test_the_capacity_kind_table_states_it_when_the_inverse_could_not_run(
    report: CaseReport,
) -> None:
    """★★ 역산이 못 돈 실행에서도 **칸을 비우지 않는다**(모듈 머리말 마지막 절).

    ⚠ 빈칸은 *「역산이 필요 없었다」* 와 *「역산을 싣지 못했다」* 를 가리지 않는다.
    """
    reason = "이 실행에는 저장장치가 없습니다 — 역산할 대상이 없습니다"
    body = "\n".join(
        capacity_kind_lines(
            review=ESSSizingReview(
                year=report.ess_sizing.year,
                step_hours=0.0,
                usable_per_capacity_kwh=None,
                seasons=(),
                unmeasurable_reason=reason,
                search_low_kwh=report.ess_sizing.search_low_kwh,
                search_high_kwh=report.ess_sizing.search_high_kwh,
                grid_supply_allowance=report.ess_sizing.grid_supply_allowance,
            ),
            pv=report.self_sufficiency,
            run_used=[],
        )
    )
    assert f"역산하지 못했다({reason})" in body
    assert "이 실행에는 설계 변수가 서지 않았다" in body, (
        "실행 용량이 없는 실행에서 칸이 비었다"
    )


def test_the_diagnostic_pv_cell_reads_the_base_point_from_one_rule(
    report: CaseReport,
) -> None:
    """★★★ **기준 수준 점을 고르는 규칙의 사본을 닫았다** (R68/WP-2 부수 정리).

    R68/WP-1 이 이 칸을 세울 때 `core/casegrid/ledger_levels.py::LEVEL_NAMES` 에서
    `index("base")` 로 규칙을 다시 썼는데, 같은 규칙이 `core/report/sizing.py::
    _mismatch_lines` 에도 있었다 — **사본이 하나 생겼다.** 규칙이 둘이면 한쪽만
    고쳐지는 날 두 표가 서로 다른 점을 「기준」이라 부르고 둘 다 그럴듯해 보인다.

    ⚠ **고른 값이 바뀌면 안 된다** — 이 검사가 그 불변을 잰다: 구분 표가 인쇄한
    태양광 수가 `base_level_point()` 가 고른 점의 수와 같아야 한다.
    """
    pv = report.self_sufficiency
    point = base_level_point(pv)
    assert point is not None, "픽스처 전제가 깨졌다 — 대장 기준 수준 점이 없다"
    body = "\n".join(
        capacity_kind_lines(
            review=report.ess_sizing, pv=pv, run_used=["태양광 용량 **60 kW**"]
        )
    )
    expected = (
        f"{point.required_capacity_kw:,.2f}kW"
        if pv.scales_to_estate
        else f"{point.household_capacity_kw:,.2f}kW"
    )
    assert expected in body, (
        f"구분 표의 태양광 진단 값이 기준 수준 점의 수가 아니다 — 「{expected}」 를 "
        f"찾지 못했다"
    )
    assert point.source_label in body, (
        f"어느 부하 수준의 점인지가 없다 — 「{point.source_label}」"
    )
