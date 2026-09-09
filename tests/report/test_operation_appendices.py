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

import dataclasses
import re
from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.engine.rule_based import DEFAULT_RULE_ORDER, DispatchRule
from core.report.case_report import build_case_report
from core.report.dispatch_notes import (
    NO_OPERATING_MODE,
    DispatchHour,
    build_hourly_profile,
    split_three_ways,
)
from core.report.dispatch_sections import (
    GENERATION_HEAD,
    GRID_EXPORT_HEAD,
    GRID_IMPORT_HEAD,
    LOAD_HEAD,
    RULE_TEXT,
    STORAGE_CHARGE_HEAD,
    STORAGE_DISCHARGE_HEAD,
    dispatch_profile_section,
    dispatch_rule_section,
    human_step_columns,
    step_table,
)
from core.report.narrative import render_markdown
from tests.report.conftest import (
    report_household_wiring,
    report_shapes,
    report_shift_share,
)

# ★ **오버라이드 실행을 짓는 관용구를 새로 만들지 않는다** (R67/WP-N1d).
# `test_load_shift_wired.py::_report` 가 골든을 **임시 디렉터리로 복사해**
# `assumption_overrides` 를 얹는다 — 사용자가 실제로 지나는 통로(전용 필드가
# 아니라 대장 오버라이드)이며 골든 픽스처를 고치지 않는다.
from tests.report.test_load_shift_wired import _report as _report_with_shift_share

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

    ⚠ **표마다 따로 센다.** 2026-08-15~R48 사이에도 표가 둘이었고 이 검사가
    표마다 세었다 — 절 전체에서 행을 세면 표들이 뭉쳐 *「한 표가 절반만 실려도
    합이 맞는」* 상태가 통과하기 때문이다.

    ★★ **R64/WP-5 뒤로 표는 `1 + 계절 수` 개다** (사용자 요구 6). 연간등가 하루
    하나와 계절마다 하나이며, 전부 `_hour_table()` 이 그린다. ⚠ 기대 개수를
    리터럴로 박지 않는다 — `report.seasons` 에서 얻는다. 박으면 자산이 계절을
    다섯으로 늘리는 날 이 검사가 「표가 틀렸다」로 빨간불이 된다.
    """
    report = _report()
    lines = dispatch_profile_section(report)
    tables: list[list[str]] = []
    for line in lines:
        if line.startswith("| 스텝 |"):
            tables.append([])
        elif tables and line.startswith("| ") and "시 |" in line:
            tables[-1].append(line)

    expected = [len(report.dispatch_hours)] + [
        len(season.dispatch.grid_export) for season in report.seasons
    ]
    assert len(tables) == len(expected), (
        f"스텝 표가 {len(tables)}개다 — 기대 {len(expected)}개"
        f"(연간등가 하루 1 + 계절 {len(report.seasons)})"
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
        # ★ **부하 이동도 같은 배선** (R64/WP-7 · 사용자 요구 2) — 안 넘기면
        # 붙임 7 이 실은 하루(옮긴 하루)를 **다른 사업**의 송전 합계에 대고
        # 재게 되고, 그때 옳은 리포트가 빨간불이 된다. 바로 위 두 배선
        # (형상 · 가구 부하)이 적어 둔 것과 같은 함정이다.
        dr_shiftable_share_pct=report_shift_share(),
        # ★★ **단지 규모·기기 부하·계절 몫도 같은 배선** (R65/WP-2c) — 안 넘기면
        # 리포트(20호 단지)의 수를 **한 호짜리** 재실행과 맞대게 된다.
        **report_household_wiring(),
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


def test_appendix_eight_self_consumption_stands_on_the_run_in_appendix_seven() -> None:
    """★★ **붙임 8 의 자가소비량이 붙임 7 의 운전 안에 있는 수인가** (나-5).

    ## ⚠ 재던 것이 사라졌다 — 성질은 남았다 (R49/★A)

    종전 이 검사는 **붙임 7 이 싣는 두 차이**(첫 표 → 둘째 표의 송전 차·수전
    차)가 붙임 8 의 크기 칸에 **같은 문면으로** 있는지 보았다. R48 이 본
    실행에 부하를 세워 두 표가 같아졌고 그 차이가 전부 0 이 됐다. 판정 §1 이
    둘째 표를 지웠으므로 **잴 차이가 없다.**

    남는 성질은 *「두 붙임이 같은 운전 위에 선다」* 다. 붙임 8 의 자가소비량은
    붙임 7 이 싣는 운전에서 잰 것이므로, 그 운전의 **발전 합계·부하 합계를
    넘을 수 없다** — 자가소비는 스텝마다 그 둘의 작은 쪽을 넘지 못한다.

    ⚠ **여기서 자가소비를 다시 계산하지 않는다**(스텝별 min 을 베끼면 오라클이
    구현의 사본이 된다). 재는 것은 **붙임 7 의 합계가 세우는 상한 안에 붙임 8
    의 수가 있는가** 이며, 그 상한은 표의 합계 행만으로 지어진다.
    """
    report = _report()
    assert report.dispatch_hours, "이 시나리오는 붙임 7 운전을 가져야 한다"
    text = render_markdown(report)
    eight = text[text.index("## 붙임 8.") : text.index("## 붙임 9.")]

    printed = re.findall(r"자가소비 ([\d,.]+)kWh/일", eight)
    assert len(printed) == 1, f"붙임 8 에 자가소비량이 {len(printed)}개다"
    self_consumption = float(printed[0].replace(",", ""))

    generation = sum(
        value
        for hour in report.dispatch_hours
        for value in hour.per_resource.values()
        if value > 0.0
    )
    load = -sum(
        value
        for hour in report.dispatch_hours
        for value in hour.per_resource.values()
        if value < 0.0
    )
    assert 0.0 < self_consumption <= min(generation, load) + 5e-3, (
        f"붙임 8 의 자가소비 {self_consumption:,.2f}kWh/일 이 붙임 7 의 운전 "
        f"밖에 있다 (발전 합계 {generation:,.2f} · 부하 합계 {load:,.2f}) — "
        "두 붙임이 서로 다른 운전 위에 서 있다"
    )


# ── ★ 붙임 7 이 **자기가 인쇄한 하루의 성질**을 말하는가 (R64/WP-4) ─────────
#
# 러너가 계절 넷의 대표일을 각각 돌려 계절일수로 가중 합산하게 되면서, 이 절이
# 싣는 24행은 **계절별 하루를 일수로 가중 평균한 「연간등가 하루」**가 됐다.
# 그 사실을 절이 말하지 않으면 검토자는 이 표를 *「어느 하루의 운전」* 으로 읽고,
# 한 스텝에 송전과 수전이 함께 선 것을 **표의 결함**으로 읽는다.


def _profile_bullets(report) -> list[str]:
    """붙임 7 의 「항목 — 값」 줄 중 **이 절이 스스로 쓴 것**만.

    ⚠ 「시간 해상도」 줄은 이 절이 쓴 것이 아니라 **러너가 낸 문면**
    (`CaseBasis.dispatch_note` · `core/casegrid/seasonal_dispatch.py::dispatch_note`)
    을 그대로 나르는 자리다. 그것을 함께 세면 이 검사가 `dispatch_sections` 를
    재는 것이 아니라 **다른 모듈의 문면을 재게 된다** — 그쪽은
    `tests/casegrid/test_seasonal_dispatch_run.py` 가 따로 붙든다.
    """
    return [
        line
        for line in dispatch_profile_section(report)
        if line.startswith("- ") and report.basis.dispatch_note not in line
    ]


def test_the_profile_section_says_the_printed_day_is_the_annual_equivalent_one() -> None:
    """★★★ 붙임 7 이 **이 표의 하루가 무엇인지** 말한다 (R64/WP-4 · 판정 ⑤ 후단).

    ⚠ **문면을 통째로 리터럴로 박지 않는다** — 오탈자 하나에 깨지는 시험이 되면
    다음 사람이 문장을 다듬을 수 없다. 걸리는 것은 **그 줄이 주장하는 사실**이다:
    이 하루가 계절별 하루를 **일수로 가중 평균**한 것이라는 진술.

    ★ 그리고 그 진술이 **참인 상태에서만** 재도록 두 사실을 함께 건다 —
    이 실행이 실제로 계절 여럿을 돌았고(`report.seasons`), 인쇄된 하루가 계절
    하나의 하루와 **같은 스텝 수**다(이어 붙이지 않았다).
    """
    report = _report()
    assert len(report.seasons) >= 2, (
        f"이 시나리오가 계절을 {len(report.seasons)}개만 돌았다 — 「연간등가 하루」"
        "라는 진술을 잴 자리가 없다"
    )
    for season in report.seasons:
        assert len(season.dispatch.grid_export) == len(report.dispatch_hours), (
            f"계절 `{season.name}` 의 하루가 인쇄된 하루와 스텝 수가 다르다 — "
            "계절을 이어 붙였다면 이 절의 진술이 거짓이다"
        )

    bullets = _profile_bullets(report)
    said = [line for line in bullets if "연간등가" in line and "가중 평균" in line]
    assert len(said) == 1, (
        "붙임 7 이 **이 표의 하루가 계절을 일수로 가중 평균한 연간등가 하루라는 "
        f"것**을 스스로 말하는 줄이 {len(said)}개다 — 정확히 1개여야 한다: {bullets}"
    )


def test_the_profile_section_warns_that_one_step_can_hold_both_directions() -> None:
    """★★★ 붙임 7 이 **한 스텝에 송전과 수전이 함께 설 수 있다**를 미리 말한다.

    연간등가 하루는 평균이므로 *「어떤 계절은 그 시각에 내보내고 어떤 계절은
    받아들인다」* 가 한 행에 둘 다 남는다. 적어 두지 않으면 검토자는 그것을
    **수지가 깨진 표**로 읽는다 — 실제로는 깨지지 않는다(스텝별 수지는 그대로다).

    ★ **경고만 재지 않는다** — 이 실행에 그런 스텝이 **실제로 있는지**를 먼저
    본다. 없는데 경고만 있으면 그 문장이 무엇을 가리키는지 아무도 확인할 수 없고,
    있는데 경고가 없으면 검토자가 표를 결함으로 읽는다.

    ## ⚠⚠ **배포 실행이 아니라 «오버라이드 실행»에서 잰다** (R67/WP-N1d)

    R67/WP-N1·N1b 가 부하의 계절 축과 하루 축을 가른 뒤 **배포 실행의 계통
    송전이 0 kWh** 가 됐다 — 잉여가 없어서가 아니라 **DR 이동과 ESS 충전이
    먼저 다 먹기 때문**이다(디스패치 차례가 `pv_self_consumption →
    ess_charge → v2g_charge → grid_export` 로 **송전이 맨 끝**이다). 송전이
    0 이면 **한 스텝에 송전과 수전이 함께 서는 일이 없고**, 그러면 이 검사가
    붙들 상태 자체가 사라진다.

    ⇒ `load.dr_shiftable_share` 를 **0** 으로 두면 DR 이 잉여를 먹지 않아
    송전이 돌아온다(실측: 스텝 **18** 에 송전과 수전이 함께 선다).
    ⚠ **단언을 「없어도 된다」로 완화하지 않았다** — 완화하면 붙임 7 의 경고가
    무엇을 가리키는지 아무도 확인할 수 없게 된다.

    ★★ **그러므로 이 경고가 가리키는 상태는 배포 실행에 없다** — 「이 사업에는
    잉여 판매가 없다」가 참인 동안 그 상태를 지키는 것은 **이 오버라이드 검사
    하나뿐**이다. *「배포 실행이 이것을 지난다」* 고 믿지 마라.
    """
    report = _report_with_shift_share(share=0)
    both = [
        hour.step
        for hour in report.dispatch_hours
        if hour.grid_export > 0.0 and hour.grid_import > 0.0
    ]
    assert both, (
        "송전과 수전이 함께 선 스텝이 하나도 없다 — 이 경고가 가리키는 상태가 "
        "이 실행에 없으므로 검사가 무엇을 확인하는지 말할 수 없다"
    )

    bullets = _profile_bullets(report)
    warned = [
        line for line in bullets if "송전" in line and "수전" in line and "함께" in line
    ]
    assert len(warned) == 1, (
        f"스텝 {both} 에 송전과 수전이 함께 서 있는데 붙임 7 이 그 사실을 미리 "
        f"말하는 줄이 {len(warned)}개다 — 정확히 1개여야 한다: {bullets}"
    )


# ── ★ 붙임 7 의 **계절별 표** (R64/WP-5 · 사용자 요구 6) ────────────────────
#
# 사용자 문면: *「계절별로 가구의 전력 수요, 발전, ESS 운전 등을 시간대별로 수치와
# 도표를 확인할 수 있어야 함」*. WP-4 가 계절 넷을 각각 돌려 `CaseReport.seasons`
# 에 실었고 **인쇄하는 자리가 하나도 없었다.** 아래 넷이 그 자리를 붙든다.


def _season_tables(report) -> list[list[str]]:
    """계절별 스텝 표만 — 첫 표(연간등가 하루)를 뗀 나머지."""
    tables: list[list[str]] = []
    for line in dispatch_profile_section(report):
        if line.startswith("| 스텝 |"):
            tables.append([])
        elif tables and line.startswith("| ") and "시 |" in line:
            tables[-1].append(line)
    return tables[1:]


def _annual_row(report, label: str) -> list[str]:
    """계절별 연간 기여 표에서 한 행을 꺼낸다 — 칸을 문자열로."""
    lines = dispatch_profile_section(report)
    start = lines.index("#### 계절별 연간 기여 (kWh/년)")
    for line in lines[start:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0].replace("*", "") == label:
            return cells
    raise AssertionError(f"계절별 연간 기여 표에 {label!r} 행이 없다: {lines[start:]}")


def test_the_seasonal_tables_use_the_same_columns_as_the_folded_one() -> None:
    """★★★ **계절별 표가 접힌 하루 표와 같은 기계로 그려진다** (판정 ②).

    갈라 두면 한쪽만 열이 바뀌고 검토자가 둘을 견줄 수 없다 —
    `core/report/dispatch_sections.py::_hour_table` 독스트링이 그 사유를 진다.
    여기서 재는 것은 **머리글이 글자까지 같은가**이며, 사본을 만들면 (자원
    차례든 열 이름이든) 언젠가 여기서 갈린다.

    ⚠ 표 개수를 리터럴로 박지 않는다 — `report.seasons` 가 정본이다.
    """
    report = _report()
    assert len(report.seasons) >= 2, "이 시나리오가 계절을 갈라 돌지 않았다"

    headers = [
        line
        for line in dispatch_profile_section(report)
        if line.startswith("| 스텝 |")
    ]
    assert len(headers) == 1 + len(report.seasons), (
        f"스텝 표 머리글이 {len(headers)}개다 — 접힌 하루 1 + 계절 "
        f"{len(report.seasons)} 이어야 한다"
    )
    assert len(set(headers)) == 1, (
        f"스텝 표의 머리글이 서로 다르다 — 표를 두 벌로 그리고 있다: {set(headers)}"
    )


def test_the_seasonal_annual_totals_close_on_the_folded_day() -> None:
    """★★★ **계절별 연간 기여의 합이 접힌 하루의 연간 총량과 같다** (성질 나).

    접힌 하루는 계절별 하루를 일수로 가중 평균한 것이므로
    `Σ(계절 하루 합 · 그 계절 일수)` 와 `접힌 하루 합 · Σ일수` 는 **같은 수**다.
    다르면 두 표가 서로 다른 실행을 보고 있다는 뜻이고, 그때 어느 쪽이 옳은지
    산출물만으로는 말할 수 없다.

    ⚠ **인쇄된 표에서 읽는다.** 자료형끼리 견주면 인쇄가 다른 수를 실어도 이
    검사는 초록불이다 — 붙임은 인쇄물이므로 인쇄된 것을 재야 한다.
    """
    report = _report()
    days = sum(season.days for season in report.seasons)
    assert days > 0, "계절 일수 합이 0 이다"

    printed = _annual_row(report, "합계")
    folded_export = sum(hour.grid_export for hour in report.dispatch_hours)
    folded_import = sum(hour.grid_import for hour in report.dispatch_hours)

    for column, folded in ((-2, folded_export), (-1, folded_import)):
        got = float(printed[column].replace("*", "").replace(",", ""))
        assert got == pytest.approx(folded * days, abs=0.01), (
            f"계절별 연간 합계 {got:,.2f} 가 접힌 하루의 {days}배 "
            f"({folded * days:,.2f}) 와 다르다 — 두 표가 다른 실행을 보고 있다"
        )


def test_the_seasonal_calendar_is_printed_as_the_asset_wrote_it() -> None:
    """★★ **계절 이름과 일수가 자산이 적은 그대로 인쇄된다** (성질 라 · 판정 ⑤).

    이름·일수를 인쇄 층이 지어내면 그것은 대장 밖의 값이 되고, 자산이 계절을
    다섯으로 늘리거나 이름을 바꾸는 날 붙임만 옛 달력을 계속 인쇄한다.

    ⚠ 「봄 92일」 같은 수를 여기 박지 않는다 — `report.seasons` 에서 읽는다.
    """
    report = _report()
    lines = dispatch_profile_section(report)
    text = "\n".join(lines)

    for season in report.seasons:
        assert f"#### {season.name} — 대표일 (연 {season.days}일)" in lines, (
            f"계절 `{season.name}` 의 표 머리가 자산이 적은 이름·일수로 서지 않았다"
        )
        assert _annual_row(report, season.name)[1] == str(season.days)

    total = sum(season.days for season in report.seasons)
    assert f"일수 합계 {total}일" in text, f"일수 합계 {total}일 이 인쇄되지 않았다"
    assert _annual_row(report, "합계")[1].replace("*", "") == str(total)


def test_the_seasonal_shape_is_printed_as_an_assumption_not_a_measurement() -> None:
    """★★ **계절 몫·형상이 「가정값」이라고 적힌다** (판정 ⑤ · 사용자 판정 §2).

    사용자 문면: *「해당 자료도 참값은 아님. 가정한 값임을 유의해줘」*. 표만
    세우면 계절 넷의 24행이 **실측 소비패턴**으로 읽히고, 그 오독이 심의 자료에
    실린다.

    ⚠ 문면을 통째로 박지 않는다 — 그 줄이 **주장하는 사실**(자산이 정한 값이며
    실측이 아니다)을 건다.
    """
    report = _report()
    said = [
        line
        for line in dispatch_profile_section(report)
        if line.startswith("- ") and "가정값" in line and "실측이 아니다" in line
    ]
    assert len(said) == 1, (
        f"계절 몫·형상이 가정값이라는 것을 말하는 줄이 {len(said)}개다 — "
        f"정확히 1개여야 한다: {said}"
    )


@pytest.mark.parametrize("kept", [0, 1])
def test_a_run_without_seasons_still_prints_and_says_why(kept: int) -> None:
    """★★★ **계절이 없거나 하나뿐인 실행에서도 인쇄가 서고 깨지지 않는다** (성질 다).

    계절 축이 서기 전 자산(형상 없는 실행 · `연중` 하나짜리 자산)과의 연속성을
    잰다. 그때 계절별 표는 접힌 하루 표를 한 번 더 인쇄한 것이 되므로 세우지
    않되, **조용히 건너뛰지 않는다** — 건너뛰면 「계절이 없다」와 「계절 절이
    빠졌다」가 산출물에서 같아진다(`app/services/ui_charts.py` 머리말이 차트
    쪽에서 같은 판단을 적었다).
    """
    report = dataclasses.replace(_report(), seasons=_report().seasons[:kept])

    lines = dispatch_profile_section(report)
    assert "### 계절별 시간대별 운전" in lines, "계절 절 자체가 사라졌다"
    assert [line for line in lines if line.startswith("| 스텝 |")] != [], (
        "접힌 하루 표까지 사라졌다"
    )
    assert len([line for line in lines if line.startswith("| 스텝 |")]) == 1, (
        "계절이 하나 이하인데 계절별 표가 섰다 — 같은 표를 두 번 인쇄한 것이다"
    )
    said = [line for line in lines if line.startswith("- ") and "계절 갈래 없음" in line]
    assert len(said) == 1, f"계절이 없는 사유가 글자로 서지 않았다: {lines}"


@pytest.mark.req("FR-105-AC4")
def test_the_assignment_table_says_what_this_run_actually_preferred() -> None:
    """「선택한 운전 방법」 칸이 **선언 라벨이 아니라 이 실행의 배분**까지 싣는다.

    R64 에서 다른 에이전트가 산출물을 대조해 찾은 결함이다(결함 2). 이 표는
    `DispatchNote.operating_mode` — 자원이 **선언한** 짧은 라벨 — 만 실었고,
    이 실행이 실제로 무엇을 우선했는지는 `CaseBasis.resources` 의 긴 문면에만
    있었다. 그래서 **사용자 요구 5**(ESS 가 가구 부하를 보고 방전한다)를 이
    표에서 가릴 수 없었다.

    ⚠ **낱말을 여기 박지 않는다** — 「부하 추종」·「집 우선」은 실행마다
    달라지므로 `basis` 가 적은 것을 그대로 읽어 견준다.
    """
    report = _report()
    modes = {line.name: line.operating_mode for line in report.basis.resources}
    lines = dispatch_rule_section(report)
    assert modes, "자원 목록이 비어 있다"
    for note in report.dispatch_notes:
        row = next(
            line for line in lines if line.startswith(f"| `{note.resource_name}` |")
        )
        long = modes.get(note.resource_name)
        if long:
            assert long in row, (
                f"{note.resource_name}: 「선택한 운전 방법」 칸이 이 실행의 배분을 "
                f"싣지 않는다 — 실물은 {long!r} 인데 행은 {row!r} 다"
            )


@pytest.mark.req("FR-105-AC4")
def test_a_resource_without_an_operating_mode_gets_a_sentence_not_a_blank() -> None:
    """운전 방법이 없는 자원의 칸은 **빈칸이 아니라 문장**이다.

    `DER._check_operating_mode` 는 `OPERATING_MODES` 가 빈 자원(부하)에 `""` 를
    돌려준다. 그 빈 문자열을 그대로 인쇄하면 표에서 **「아직 안 적었다」와
    구별되지 않는다** — 이 저장소의 ★★ 규약(「`None` 은 빈칸이 아니라 «진술»
    이다」)이 금지하는 자리다.
    """
    report = _report()
    modes = {line.name: line.operating_mode for line in report.basis.resources}
    blank = [
        n
        for n in report.dispatch_notes
        if not (modes.get(n.resource_name) or n.operating_mode)
    ]
    assert blank, "운전 방법 없는 자원이 없어 이 시험이 재는 것이 없다"
    lines = dispatch_rule_section(report)
    for note in blank:
        row = next(
            line for line in lines if line.startswith(f"| `{note.resource_name}` |")
        )
        assert NO_OPERATING_MODE in row, (
            f"{note.resource_name}: 운전 방법 칸이 비어 있다 — {row!r}"
        )


@pytest.mark.req("FR-105-AC4")
def test_the_appendix_and_the_body_do_not_disagree_about_the_operating_mode() -> None:
    """붙임의 「선택한 운전 방법」과 본문의 「운전 방식」이 **같은 말을 한다.**

    한 문서가 같은 물음에 두 답을 적으면 검토자는 어느 쪽이 정본인지 물어야
    한다. R64 전에는 본문(`core/report/method_sections.py`)이 긴 문면을 싣고
    붙임이 짧은 라벨을 실어 **그 상태였다.**
    """
    report = _report()
    body = render_markdown(report)
    appendix = "\n".join(dispatch_rule_section(report))
    for line in report.basis.resources:
        if not line.operating_mode:
            continue
        assert line.operating_mode in body, (
            f"{line.name}: 본문이 운전 방식을 싣지 않는다"
        )
        assert line.operating_mode in appendix, (
            f"{line.name}: 붙임이 본문과 다른 말을 한다 — 본문은 "
            f"{line.operating_mode!r} 를 싣는데 붙임에는 없다"
        )


# ── ★★ R68/WP-3: 스텝 표를 그리는 기계는 **하나**, 열 구성은 인자 ─────────────
#
# 검증 3단계가 같은 하루를 **사람용 양수 표**로도 실어야 했다(검토서 §3.4·§4.3).
# 붙임 7 은 자원별 **부호** 표라 열이 다르다 — 그렇다고 표를 두 벌로 그리면
# `_hour_table()` 의 ⚠(*「계절 쪽에 사본을 만들지 마라」*)가 금한 상태가 정확히
# 돌아온다. ⇒ 기계 하나(`step_table`) + 열 구성만 갈라 두었고, 아래가 그 성질을
# 붙든다.


def _synthetic_day() -> tuple[DispatchHour, ...]:
    """자원 셋(발전·저장장치·부하)이 다 있는 하루 둘 — **실행을 돌리지 않는다.**

    이 검사가 재는 것은 **열을 짜는 규칙**이고, 그것은 실행과 무관하다. 실물로
    재는 자리는 `tests/report/test_verification_dispatch.py` 다.
    """
    return (
        DispatchHour(
            step=0,
            per_resource={"pv": 0.0, "ess": -2.0, "load": -5.0},
            grid_export=0.0,
            grid_import=7.0,
        ),
        DispatchHour(
            step=1,
            per_resource={"pv": 9.0, "ess": 1.5, "load": -4.0},
            grid_export=6.5,
            grid_import=0.0,
        ),
    )


def test_the_human_columns_carry_positive_quantities_in_separate_columns() -> None:
    """★★★ **부호를 읽지 않고 읽는 표다** (검토서 §4.3).

    검토서 문면: *「사람용 표에서는 «한전 수전»·«한전 역송»을 양의 수량으로
    별도 열에 두고, 내부 부호는 수식 설명에만 남기는 편이 안전하다」*. 그래서 이
    표에서는 부하가 **양수**로 서고 저장장치의 충전·방전이 **두 열**로 갈린다.

    ⚠ 붙임 7 은 그 반대 요구를 진다(자원 수지는 부호가 뜻이다) — **두 요구가
    둘 다 참이므로 표가 둘**이고, 갈리는 것은 열 구성뿐이다.
    """
    hours = _synthetic_day()
    generation, storage, load = split_three_ways(hours)
    columns = human_step_columns(generation, storage, load)
    heads = [head for head, _ in columns]

    assert heads == [
        LOAD_HEAD,
        GENERATION_HEAD,
        STORAGE_CHARGE_HEAD,
        STORAGE_DISCHARGE_HEAD,
        GRID_IMPORT_HEAD,
        GRID_EXPORT_HEAD,
    ], f"열 구성이나 차례가 다르다 — {heads}"

    by_head = dict(columns)
    first, second = hours
    assert by_head[LOAD_HEAD](first) == 5.0, "부하가 양수로 서지 않았다"
    assert by_head[STORAGE_CHARGE_HEAD](first) == 2.0, "충전이 양수로 서지 않았다"
    assert by_head[STORAGE_DISCHARGE_HEAD](first) == 0.0, (
        "충전만 한 스텝에 방전이 실렸다 — 두 열이 순액을 두 번 인쇄하고 있다"
    )
    assert by_head[STORAGE_CHARGE_HEAD](second) == 0.0, (
        "방전만 한 스텝에 충전이 실렸다"
    )
    assert by_head[STORAGE_DISCHARGE_HEAD](second) == 1.5, "방전이 실리지 않았다"
    assert by_head[GENERATION_HEAD](second) == 9.0, "발전이 실리지 않았다"
    # ⚠ 스텝 수지가 닫힌다 — 부호를 걷었어도 물리가 바뀌지 않았다는 증거다.
    for hour in hours:
        supplied = (
            by_head[GENERATION_HEAD](hour)
            + by_head[STORAGE_DISCHARGE_HEAD](hour)
            + by_head[GRID_IMPORT_HEAD](hour)
        )
        used = (
            by_head[LOAD_HEAD](hour)
            + by_head[STORAGE_CHARGE_HEAD](hour)
            + by_head[GRID_EXPORT_HEAD](hour)
        )
        assert supplied == pytest.approx(used, abs=1e-9), (
            f"{hour.step}번 스텝의 수지가 닫히지 않는다 — 공급 {supplied} · "
            f"사용 {used}"
        )


def test_an_absent_role_loses_its_column_but_never_the_grid_ones() -> None:
    """★★★ **없는 설비의 열을 0 으로 세우지 않는다** — 계통 두 열은 언제나 선다.

    「저장장치 충전 0.00」 열을 스물넷 인쇄하면 *「저장장치가 있는데 하루 종일 안
    움직였다」* 로 읽힌다. 반면 계통 두 열은 자원이 하나도 없는 실행에서도 서야
    한다 — `DispatchHour` 가 그 둘을 직접 나르고, 자원 없는 실행도 계통에서 받아
    온다.
    """
    heads = [head for head, _ in human_step_columns((), (), ("load",))]
    assert LOAD_HEAD in heads, "부하 열이 사라졌다"
    assert GENERATION_HEAD not in heads, "발전 자원이 없는데 발전 열을 세웠다"
    assert STORAGE_CHARGE_HEAD not in heads, "저장장치가 없는데 그 열을 세웠다"
    assert STORAGE_DISCHARGE_HEAD not in heads, "저장장치가 없는데 그 열을 세웠다"

    bare = [head for head, _ in human_step_columns((), (), ())]
    assert bare == [GRID_IMPORT_HEAD, GRID_EXPORT_HEAD], (
        f"자원이 하나도 없는 실행에서 계통 두 열이 사라졌다 — {bare}"
    )


def test_the_step_table_always_closes_with_a_total_row() -> None:
    """★★ **합계 행을 뺄 수 없다** — 이 저장소의 스텝 표는 전부 합계로 검증된다.

    붙임 7 의 합계는 붙임 4 산식의 대입값과, 검증 3단계의 합계는 그 계절의
    연간값과 맞댄다. 선택 인자로 두면 합계 없는 표가 생기고 그 표는 대조할 수
    없다.

    ⚠ 첫 칸의 머리글은 **인자로 갈린다** — 붙임 7 은 「스텝」, 사람용 표는
    「시각」이다. 스텝 수가 24가 아닌 실행에서 「시각」은 없는 해상도를 주장하는
    것이 되므로 `_hour_label()` 과 짝이 맞아야 한다.
    """
    hours = _synthetic_day()
    columns = human_step_columns(*split_three_ways(hours))
    lines = step_table(hours, columns, step_head="시각")

    assert lines[0].startswith("| 시각 |"), f"첫 칸 머리글이 인자를 따르지 않았다 — {lines[0]}"
    assert step_table(hours, columns)[0].startswith("| 스텝 |"), (
        "머리글 기본값이 붙임 7 의 「스텝」이 아니다"
    )
    total = next((line for line in lines if line.startswith("| **합계** |")), None)
    assert total is not None, f"합계 행이 없다 — {lines}"
    cells = [cell.strip() for cell in total.strip("|").split("|")]
    assert len(cells) == 1 + len(columns), (
        f"합계 행의 칸 수가 머리글과 다르다 — {cells}"
    )
    load_total = sum(-hour.per_resource["load"] for hour in hours)
    assert cells[1] == f"**{load_total:,.2f}**", (
        f"합계가 그 열의 합이 아니다 — {cells[1]} ≠ {load_total:,.2f}"
    )
    # 스텝이 2개뿐이므로 시각으로 적으면 없는 해상도를 주장한다 — 번호로 남는다.
    assert lines[2].startswith("| 0 |"), (
        f"24스텝이 아닌 하루를 시각으로 적었다 — {lines[2]}"
    )
