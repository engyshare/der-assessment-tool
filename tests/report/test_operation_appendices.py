"""**엔진 규칙**과 **시간대별 운전**이 리포트에 실리는가 — 「1차 의견」 2·3.

의견 원문 둘:

    「규칙 기반 엔진이 적용되었다는데 규칙이 붙임에 기재되지 않으면
      내용을 이해할 수 없음」                                     ← 의견 2
    「시간대별 디스패치 표」                                       ← 의견 3

재료는 R33 이전에도 있었다 — `build_dispatch_notes()`(`FR-105-AC4`)와 24스텝
운전 결과. **둘 다 배포 호출자가 0곳**이었고, 그래서 `FR-105-AC4`(*「리포트에
표기한다」*)는 매핑표에서 「자동」인데 **표기하는 리포트가 없었다.** 이 검사가
보는 것은 그 배선이다.

    ★ 규칙 순서가 **엔진 선언에서** 온다   ← 리포트가 다시 적으면 순서를 바꾼 날 틀린다
    ★ 자원별 배정이 **실행이 세운 자원**에서 ← 리포트가 자원을 다시 세우면 사본이 된다
    ★ 스텝 합계가 **편익 산식의 수량**과 이어진다
    양식 0절 — 해설을 싣지 않는다
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.engine.rule_based import DEFAULT_RULE_ORDER, DispatchRule
from core.report.case_report import build_case_report
from core.report.dispatch_notes import build_hourly_profile
from core.report.dispatch_sections import (
    RULE_TEXT,
    dispatch_profile_section,
    dispatch_rule_section,
)
from core.report.narrative import render_markdown
from tests.report.conftest import report_shapes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


@pytest.mark.req("FR-105-AC4")
def test_every_rule_of_the_engine_reaches_the_report() -> None:
    """규칙 **전건**이 실린다 — 돌지 않은 것도 그렇게 적는다.

    일곱 중 이 구성에서 실제로 자원이 붙는 것은 둘뿐이다. 붙은 것만 실으면
    검토자는 엔진이 규칙 둘짜리라고 읽고, 그러면 *「부족하면 계통에서 산다」*
    같은 규칙이 있다는 사실 자체가 리포트에서 사라진다.
    """
    lines = dispatch_rule_section(_report())
    text = "\n".join(lines)
    for rule in DEFAULT_RULE_ORDER:
        assert f"`{rule.value}`" in text, f"{rule.value} 규칙이 붙임 6 에 없다"
        assert RULE_TEXT[rule] in text, f"{rule.value}: 규칙 문면이 없다"


@pytest.mark.req("FR-105-AC4")
def test_rule_order_comes_from_the_engine_not_the_report() -> None:
    """★ 순위표가 **실행이 쓴 순서**를 따른다.

    리포트가 `DEFAULT_RULE_ORDER` 를 스스로 읽으면 순서를 바꾼 실행에서
    **기본 순서를 실행 순서로 인쇄**한다 — 조항이 「설정 가능한 순서」
    (`FR-302-AC1`·`AC3`)이므로 이것은 가정할 수 있는 상태가 아니다.

    여기서는 실행이 내놓은 `rule_order` 를 리포트가 그대로 나르는지 본다.
    """
    report = _report()
    # ★ **리포트와 같은 배선으로 돌린다 (R37)** — `conftest.report_shapes`.
    outcome = run_single_case_e2e(
        {},
        level_map=build_level_map(_ASSUMPTIONS),
        horizon_years=report.basis.horizon_years,
        daily_shapes=report_shapes(),
    )
    assert report.rule_order == outcome.rule_order, (
        "리포트의 규칙 순서가 실행이 쓴 순서와 다르다"
    )
    # 순위는 표에서도 그 순서로 서야 한다.
    lines = dispatch_rule_section(report)
    positions = [
        next(i for i, line in enumerate(lines) if f"`{rule.value}`" in line)
        for rule in report.rule_order
    ]
    assert positions == sorted(positions), "표의 순서가 선언 순서와 다르다"


@pytest.mark.req("FR-105-AC4")
def test_each_resource_carries_its_mode_rule_and_priority() -> None:
    """자원마다 운전 방법·규칙·순위·가격 연동이 한 행에 있다.

    `FR-105-AC4` 가 요구하는 것이 정확히 그 **결합**이다 — 운전 방법만 적으면
    그것이 디스패치 순서와 어떻게 만나는지 알 수 없다.
    """
    report = _report()
    lines = dispatch_rule_section(report)
    assert report.dispatch_notes, "자원별 표기가 비어 있다"
    for note in report.dispatch_notes:
        row = next(
            line
            for line in lines
            if line.startswith(f"| `{note.resource_name}` |")
        )
        assert note.operating_mode in row, f"{note.resource_name}: 운전 방법 없음"
        assert note.dispatch_rule.value in row, f"{note.resource_name}: 규칙 없음"
        assert f"| {note.dispatch_priority + 1} |" in row, (
            f"{note.resource_name}: 순위 없음"
        )


@pytest.mark.req("FR-1001-AC2")
def test_hourly_table_carries_every_step_of_the_run() -> None:
    """스텝을 **빠뜨리지 않는다** — 표본이 아니라 전건이다.

    일부만 실으면 검토자는 나머지 시간대를 실린 것과 같다고 읽는다. 이
    구성에서는 심야 여섯 스텝만 다른 모양이므로, 표본을 실었다면 그 여섯이
    사라졌을 것이다.

    ⚠ **표가 둘이다** (2026-08-15) — 파이프라인 운전과 형상 가정 운전. 절
    전체에서 행을 세면 둘이 뭉쳐 *「한 표가 절반만 실려도 합이 맞는」* 상태가
    통과한다. 그래서 **표마다 따로** 센다.
    """
    report = _report()
    lines = dispatch_profile_section(report)
    tables: list[list[str]] = []
    for line in lines:
        if line.startswith("| 스텝 |"):
            tables.append([])
        elif tables and line.startswith("| ") and "시 |" in line:
            tables[-1].append(line)

    expected = [len(report.dispatch_hours)]
    if report.assumed_hours:
        expected.append(len(report.assumed_hours))
    assert len(tables) == len(expected), (
        f"스텝 표가 {len(tables)}개다 — 기대 {len(expected)}개"
    )
    for index, (rows, steps) in enumerate(zip(tables, expected, strict=True)):
        assert len(rows) == steps, (
            f"{index + 1}번째 표: 스텝 {steps}개 중 {len(rows)}개만 실렸다"
        )


@pytest.mark.req("FR-1001-AC2")
def test_hourly_export_total_matches_the_benefit_formula_quantity() -> None:
    """★ **스텝 합계가 편익 산식의 수량과 이어진다.**

    붙임 7 이 실제 운전과 다른 수량 위에 서 있으면, 검토자가 시간대별 표로
    연 편익을 되짚을 때 두 수가 갈린다 — 그때 어느 쪽이 옳은지 리포트만으로는
    말할 수 없다. 여기서는 송전 합계가 실행의 송전 합계와 같은지 본다.
    """
    report = _report()
    levels = build_level_map(_ASSUMPTIONS)
    # ★ **리포트와 같은 배선으로 돌린다 (R37).** 형상 없이 돌리면 송전
    # 합계가 16.10 대 18.80 으로 갈리는데, 그것은 붙임 7 이 틀린 것이 아니라
    # 검사가 **다른 사업**을 돌린 것이다(`conftest.report_shapes`).
    # ★★ 가구 부하도 같은 배선 (R48/WP-B → WP-F) — 본 실행이 부하를 넘겨
    # 계통 수전이 생기고 그만큼 송전이 줄었으므로, 부하 없이 재실행하면
    # 붙임 7 이 실은 수(부하 있는 실행)와 다른 사업이 된다.
    outcome = run_single_case_e2e(
        {},
        level_map=levels,
        horizon_years=report.basis.horizon_years,
        daily_shapes=report_shapes(),
        annual_load_kwh=levels["household_load_annual_kwh"]["base"],
    )
    expected = sum(outcome.dispatch.grid_export)
    reported = sum(hour.grid_export for hour in report.dispatch_hours)
    assert reported == pytest.approx(expected), (
        f"붙임 7 의 송전 합계({reported})가 실행({expected})과 다르다"
    )


def test_hourly_profile_keeps_the_sign_convention() -> None:
    """★ 부호를 **표시 층이 뒤집지 않는다.**

    `DispatchResult` 규약이 *「양수 = 내보냄 · 음수 = 받아들임」* 이다. 표시
    층이 뒤집으면 ESS 의 충·방전이 두 열로 갈리고, 그때 「스텝 합계가 계통
    송·수전과 맞는가」를 눈으로 셀 수 없게 된다.

    ⚠ `req()` 마커는 달지 않았다 — 부호 규약은 `core/contracts/der.py` 의
    자료형 규약이며 이 검사가 보는 것은 **표시 층이 그것을 건드리지 않는가**다.
    """
    report = _report()
    outcome = run_single_case_e2e(
        {},
        level_map=build_level_map(_ASSUMPTIONS),
        horizon_years=report.basis.horizon_years,
    )
    hours = build_hourly_profile(outcome.dispatch)
    for hour in hours:
        for name, value in hour.per_resource.items():
            assert value == outcome.dispatch.per_resource[name].electric[hour.step], (
                f"{name} step {hour.step}: 표시 층이 값을 바꿨다"
            )
    charging = [h for h in hours if any(v < 0 for v in h.per_resource.values())]
    assert charging, (
        "충전(음수) 스텝이 하나도 없다 — 부호가 뒤집혔거나 운전이 바뀌었다"
    )


def test_appendices_six_and_seven_stand_in_the_report_in_order() -> None:
    """양식이 정한 자리에 선다 (붙임 6 → 7).

    ⚠ `req()` 마커는 달지 않았다 — 붙임의 번호와 순서는 양식
    (`docs/report-form-심의보고서.md`)이 정하는 서식 규정이지 spec 조항이
    아니다.
    """
    text = render_markdown(_report())
    rules = text.index("## 붙임 6. 디스패치 규칙과 우선순위")
    profile = text.index("## 붙임 7. 시간대별 운전")
    unreflected = text.index("## 붙임 8. 미반영 항목")
    assert rules < profile < unreflected


def test_appendices_carry_no_reading_instructions() -> None:
    """★ **해설을 싣지 않는다** (양식 0절).

    정형 출력이므로 산출물에는 계산 결과와 정의만 있어야 한다. 인용문(`>`)
    형태의 주의·독법 지시는 프로그램이 참임을 보증할 수 없는 진술이며, 그것이
    계산 결과와 같은 무게로 읽히는 것이 이 규정이 막으려는 것이다.
    """
    report = _report()
    for section in (dispatch_rule_section(report), dispatch_profile_section(report)):
        quoted = [line for line in section if line.startswith(">")]
        assert not quoted, f"해설 인용문이 남았다: {quoted[:2]}"
        for banned in ("읽지 말", "읽힌다", "해야 한다", "주의"):
            offenders = [line for line in section if banned in line]
            assert not offenders, f"독법 지시가 남았다({banned}): {offenders[:2]}"


def test_unknown_rule_is_named_not_blanked() -> None:
    """문면이 없는 규칙은 **빈칸이 아니라 그렇게** 적힌다.

    엔진에 규칙이 하나 늘고 이름표가 없으면 표에 빈칸이 생기고, 빈칸은
    「규칙이 없다」로 읽힌다.
    """
    from core.report.dispatch_sections import _rule_text

    known = DispatchRule.GRID_IMPORT
    assert _rule_text(known) == RULE_TEXT[known]
    assert set(RULE_TEXT) == set(DEFAULT_RULE_ORDER), (
        "규칙 문면표가 엔진 선언과 어긋났다 — 새 규칙에 문면을 붙일 것"
    )


def test_appendix_seven_and_the_unreflected_row_use_the_same_two_differences() -> None:
    """★★ **붙임 7 의 차이와 붙임 8 의 방향이 같은 수인가** (R43-H · 나-5).

    붙임 8 의 자가소비 행은 이제 방향을 적는데, 그 계산의 재료는 **붙임 7 이
    싣는 두 차이**(계통 송전·수전의 파이프라인 → 형상 가정 변화)다. 두 자리가
    서로 다른 수를 쓰면 검토자는 *어느 쪽이 틀렸는지 물을 자리가 없다* — 표
    하나를 보고 다른 표의 방향을 되짚을 수 없다.

    ⚠ **여기서 방향을 다시 계산하지 않는다.** 계산을 베끼면 오라클이 구현의
    사본이 된다. 재는 것은 **붙임 7 이 인쇄한 연간화 수전 차이가 붙임 8 의
    크기 칸에도 같은 문면으로 있는가** 다.
    """
    report = _report()
    assert report.assumed_hours, "이 시나리오는 형상 가정 운전을 가져야 한다"
    text = render_markdown(report)

    seven = text[text.index("### 부하·일사 형상을 가정한 운전") : text.index("## 붙임 8.")]
    eight = text[text.index("## 붙임 8.") : text.index("## 붙임 9.")]

    rows = [line for line in seven.splitlines() if line.startswith("| 계통 수전 (연간화")]
    assert len(rows) == 1, f"붙임 7 에 연간화 수전 차이 행이 {len(rows)}개다"
    delta = rows[0].split("|")[-2].strip()
    assert delta.startswith(("+", "-")), f"차이가 부호를 갖지 않는다 — {delta}"

    assert f"{delta}kWh/년" in eight, (
        f"붙임 7 의 수전 차이 {delta} 가 붙임 8 의 자가소비 행에 없다 — 두 붙임이 "
        "서로 다른 수로 같은 사실을 말하고 있다"
    )
