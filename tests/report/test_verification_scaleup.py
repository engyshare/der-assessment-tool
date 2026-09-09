"""검증 2단계 ⓐ — **1가구 → 단지 확대 규칙 표**와 동시율 제외 표 (R68/WP-4).

동반 대상은 `core/report/verification_scaleup.py` 다(NFR-105 · 파일명 규약).

## ⚠ 무엇을 재고 무엇을 재지 않는가

이 검사가 붙드는 것은 **표의 축**(같은 배수를 어디서 곱하는가) · **곱하지
않는 둘**(단가·동시율) · **제외와 누락의 구별** · **수가 실행에서 온다는
사실**이다. 문서 전체가 그 표를 실제로 싣는지는
`tests/report/test_verification.py` 가 렌더러 산출물로 재고, 1단계의 부하
칸들은 `tests/report/test_verification_inputs.py` 가 잰다 — 같은 것을 세 곳에서
재지 않는다.

⛔ **엔진을 재지 않는다.** 배수가 실제로 걸리는지는
`tests/casegrid/` 의 결선 시험들이 재고(`test_household_count_wired.py` ·
`test_coincidence_factor_wiring.py`), 이 파일은 **인쇄된 규칙이 그 실행값과
어긋나지 않는가**만 잰다.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from core.casegrid.appliance_load import APPLIANCE_LOAD_UNIT
from core.casegrid.household_scale import HOUSEHOLD_COUNT_UNSPECIFIED
from core.report.case_report import CaseReport, build_case_report
from core.report.verification_scaleup import (
    COINCIDENCE_EXCLUDED,
    COINCIDENCE_FACTOR_LEDGER_KEY,
    ESTATE_LOAD_UNIT,
    EXCLUDED_BY_DECISION,
    NO_CHANGE_PATH_NOTE,
    NOT_MULTIPLIED,
    SAME_AS_HOUSEHOLD,
    estate_load_kwh,
    household_base_kwh,
    household_total_load_kwh,
    scaleup_lines,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 설비 셋의 행 이름 — 「같은 배수를 타는 것」이 무엇인지 이 검사가 아는 자리.
_EQUIPMENT_ROWS = ("태양광 용량", "저장장치 용량", "저장장치 정격출력")


@pytest.fixture(scope="module")
def report() -> CaseReport:
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


def _cells(lines: list[str]) -> list[list[str]]:
    """표 행들만 골라 칸으로 가른다 — 구분선(`|---|`)과 글머리 줄은 뺀다."""
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in lines
        if line.startswith("|") and "---" not in line
    ]


def _row(lines: list[str], head: str) -> list[str]:
    for cells in _cells(lines):
        if cells[0].startswith(head):
            return cells
    raise AssertionError(f"그 행이 없다: {head}")


def test_every_equipment_row_multiplies_the_same_scale_and_says_where(
    report: CaseReport,
) -> None:
    """★★★ **표의 축은 「20배인가」가 아니라 「어디서 곱하는가」다.**

    설비 셋의 「단지 값 ÷ 한 호 기준값」이 **모두 가구 수와 같아야** 한다 —
    하나만 배수를 안 타면 같은 실행 안에서 설비가 서로 다른 규모의 사업을
    그린다(R65/WP-2b 실측: 그때 실행이 `ess.power_kw` 로 거부됐다).

    ⚠ 그리고 셋의 **곱하는 자리가 같지 않다** — 용량 둘은 러너, 정격출력은
    `core/casegrid/ess_build.py` 다. 자리를 한 칸으로 뭉개면 그 사실이 사라진다.
    """
    count = report.household_count
    assert count is not None and count > 1  # 이 골든이 단지 실행이라는 것 자체
    lines = scaleup_lines(report)
    sites: set[str] = set()
    for head in _EQUIPMENT_ROWS:
        name, per_household, site, estate = _row(lines, head)
        assert name == head
        household_value = float(per_household.split()[0])
        estate_value = float(estate.split()[0])
        assert estate_value == pytest.approx(household_value * count)
        sites.add(site)
    assert len(sites) == 2, sites
    assert any("e2e_runner.py::run_single_case_e2e" in site for site in sites)
    assert any("ess_build.py::_case_ess_spec" in site for site in sites)


def test_the_load_row_adds_before_multiplying(report: CaseReport) -> None:
    """부하 행 — **더한 뒤에 곱한다.**

    곱한 뒤에 더하면 추가 기기가 단지에 딱 한 대 있는 사업이 된다. 러너의
    순서(`core/casegrid/seasonal_dispatch.py::_load_total_kwh`)와 같아야 한다.
    """
    loads = report.appliance_loads
    per_household = household_total_load_kwh(report)
    assert per_household == pytest.approx(
        (household_base_kwh(report) or 0.0) + (loads.heatpump_kwh or 0.0) + (loads.ev_kwh or 0.0)
    )
    count = report.household_count
    assert count is not None
    assert estate_load_kwh(report) == pytest.approx(per_household * count)
    _name, household_cell, site, estate_cell = _row(scaleup_lines(report), "가구 부하")
    assert f"{per_household:,.0f}" in household_cell
    assert f"{per_household * count:,.0f}" in estate_cell
    assert "seasonal_dispatch.py::_load_total_kwh" in site
    assert "더한 뒤에 곱한다" in site


def test_unit_costs_are_printed_as_not_multiplied(report: CaseReport) -> None:
    """⚠ **단가는 곱하지 않는다** — 총액은 자원 안에서 `용량 × 단가` 로 나온다.

    여기서 함께 곱하면 두 번 곱해진다. 그래서 단가 행의 단지 값 칸은 「같다」
    이고, 그 칸이 수로 채워지면 **그 오독을 산출물이 권한다.**
    """
    lines = scaleup_lines(report)
    assert report.basis.resources  # 자원이 없으면 이 검사가 성립하지 않는다
    for line in report.basis.resources:
        _name, unit_capex, site, estate = _row(lines, f"{line.kind} 단가")
        assert unit_capex == line.unit_capex  # 자원이 든 문면 그대로다
        assert site.startswith(NOT_MULTIPLIED)
        assert estate == SAME_AS_HOUSEHOLD


def test_coincidence_row_names_the_single_site_and_the_ledger_key(
    report: CaseReport,
) -> None:
    """동시율 — **걸리는 자리가 하나**이고 **배수를 타지 않는다.**

    ⚠ 대장 항목 이름을 함께 싣는다 — *「사용자가 바꿀 통로가 어디인가」* 가
    검토서 §4.5 가 묻는 것이고, 값만 적으면 그 통로가 산출물에 없다.
    """
    lines = scaleup_lines(report)
    name, value, site, estate = _row(lines, "설비 동시율")
    assert COINCIDENCE_FACTOR_LEDGER_KEY in name
    assert "_site_load_kw" in site
    assert "최대수요" in site
    assert NOT_MULTIPLIED in estate
    ledger = [row for row in report.assumptions if row.key == COINCIDENCE_FACTOR_LEDGER_KEY]
    assert ledger, "이 실행이 동시율을 대장에서 읽지 않았다 — 검사가 성립하지 않는다"
    assert f"{float(ledger[0].value):,.1f}" in value
    assert ledger[0].value_unit in value
    # ★ 바꾸는 통로가 글자로 서 있다 (검토서 §4.5).
    body = "\n".join(lines)
    assert "assumption_overrides" in body
    assert "설정 화면의 대장 항목 칸" in body


def test_the_three_excluded_places_are_decided_not_missing(report: CaseReport) -> None:
    """⚠⚠ **「제외」와 「누락」을 가른다.**

    `core/casegrid/e2e_runner.py::_site_load_kw` 독스트링이 못 박은 것이다 —
    *「곱하지 않은 것이 「빠뜨린 것」이 아니다」*. 누락으로 인쇄하면 다음 사람이
    넣고, 그 순간 결론축이 **좋아지는 쪽으로** 조용히 틀린다.
    """
    lines = scaleup_lines(report)
    body = "\n".join(lines)
    assert len(COINCIDENCE_EXCLUDED) == 3
    for where, _why in COINCIDENCE_EXCLUDED:
        cells = _row(lines, where)
        assert cells[1] == EXCLUDED_BY_DECISION
        assert cells[2]  # 사유 칸이 비어 있지 않다
    assert body.count(EXCLUDED_BY_DECISION) == len(COINCIDENCE_EXCLUDED)
    assert "판정이 **명시로 제외**한 자리다" in body
    assert "decisions-2026-09-07-R66.md" in body


def test_the_numbers_are_read_from_the_run_not_written_in_the_source(
    report: CaseReport,
) -> None:
    """★ **수를 리터럴로 박지 않았다** — 실행이 다른 용량으로 돌면 표가 따라온다.

    설계 변수의 사용값과 정격출력을 바꿔 넣고, 표의 두 칸이 **그 수로** 바뀌는
    것을 본다. 값을 소스에 적어 두면 이 검사가 그때 빨간불이 된다.
    """
    count = report.household_count
    assert count is not None
    findings = tuple(
        dataclasses.replace(finding, used_value=finding.used_value * 3)
        for finding in report.capacity_review
    )
    review = dataclasses.replace(report.ess_sizing, run_power_kw=1_234.0)
    moved = dataclasses.replace(report, capacity_review=findings, ess_sizing=review)
    lines = scaleup_lines(moved)
    for finding in findings:
        _name, per_household, _site, estate = _row(lines, finding.label)
        assert float(estate.split()[0]) == pytest.approx(finding.used_value)
        assert float(per_household.split()[0]) == pytest.approx(finding.used_value / count)
    _name, per_household, _site, estate = _row(lines, "저장장치 정격출력")
    assert float(estate.split()[0]) == pytest.approx(1_234.0)
    assert float(per_household.split()[0]) == pytest.approx(1_234.0 / count)


def test_no_storage_row_when_the_run_built_no_storage(report: CaseReport) -> None:
    """⚠ 저장장치가 없는 실행은 **정격출력 행을 짓지 않는다.**

    없는 설비의 확대 규칙을 인쇄하면 그 설비가 있다는 뜻이 된다 — 이 저장소가
    「빈칸으로 두지 않는다」와 함께 지키는 짝이다.
    """
    review = dataclasses.replace(report.ess_sizing, run_power_kw=None)
    lines = scaleup_lines(dataclasses.replace(report, ess_sizing=review))
    assert not any(cells[0].startswith("저장장치 정격출력") for cells in _cells(lines))


def test_unspecified_household_count_prints_the_statement_and_scale_one(
    report: CaseReport,
) -> None:
    """★★ **미지정은 빈칸이 아니라 진술이다** — 배수가 `1` 이다.

    미지정에 곱할 수를 지으면 «모든 가구가 같다»는 뜻이 되고, 이 보고서의 모든
    수량이 한 호의 것이라는 사실이 그 칸에서 사라진다.
    """
    alone = dataclasses.replace(report, household_count=None)
    assert estate_load_kwh(alone) is None
    lines = scaleup_lines(alone)
    body = "\n".join(lines)
    assert HOUSEHOLD_COUNT_UNSPECIFIED in body
    assert "배수가 **1**" in body
    assert "| 무엇 | 한 호 기준값 | 배수를 곱하는 자리 | 단지 값 |" in lines
    # 설비 셋은 나눌 것이 없으므로 두 칸이 같은 수다 — 지어낸 배수가 없다.
    for head in _EQUIPMENT_ROWS:
        _name, per_household, _site, estate = _row(lines, head)
        assert per_household.split()[0] == estate.split()[0]
    _name, household_cell, _site, estate_cell = _row(lines, "가구 부하")
    assert estate_cell == HOUSEHOLD_COUNT_UNSPECIFIED
    assert f"{household_total_load_kwh(alone):,.0f}" in household_cell


def test_the_section_says_the_storage_is_a_sum_of_household_storage(
    report: CaseReport,
) -> None:
    """검토서 §3.5 의 넷째 물음 — **가구별 합산인가 공용 하나인가.**

    모형에 서는 저장장치는 자원 «하나»이지만 그 용량이 「한 호분 × 가구 수」다
    — 별도로 설계한 공용 설비가 아니다. 그 사실이 표 아래 글자로 서야 한다.
    """
    body = "\n".join(scaleup_lines(report))
    assert "합산" in body
    assert "공용 설비가 아니다" in body
    # 다섯째·여섯째 물음도 같은 자리가 답한다.
    assert "ESS.reducible_peak_kw" in body
    assert "household_scale.py::household_scale" in body


def test_the_section_stands_no_new_premise_word_and_no_new_stage(
    report: CaseReport,
) -> None:
    """⚠⚠ 사람이 읽는 자리에 **「전제」를 새로 세우지 않는다**(판정 R63b §1).

    그리고 **단계를 늘리지 않는다** — `## N단계 — ` 로 시작하는 줄을 내면
    `app/services/verify_steps.py::split_stages` 가 그것을 열째 단계로 읽고
    `app/services/verify_steps.py::STAGE_COUNT`(9)와 어긋나 CLI 가 멈춘다.
    """
    lines = scaleup_lines(report)
    assert "전제" not in "\n".join(lines)
    assert not any(line.startswith("## ") for line in lines)


def test_the_estate_unit_says_it_is_the_estate_not_one_household() -> None:
    """★★ **단지 합계의 단위가 「호당」과 낱말로 갈린다** (R68/WP-8 · 검토서 §4.2).

    이 표는 한 호 값과 단지 값을 **나란히** 싣는다. 그때 단지 칸이 맨 `kWh/년`
    이면 그 수가 호당인지 단지인지 **낱말이 말하지 않는다** — 20호 단지에서
    그 오독은 20배다. 판정(`.orch/R68/JUDGMENT-wp7.md` ⓔ-1)이 검토서의 낱말
    (`kWh/단지·년`)로 맞추기로 했다.

    ⚠ **분모가 바뀐 것이 아니라 이름이 바뀐 것**이다 — 그래서 이 검사는 낱말만
    보고 수는 보지 않는다(수는 위 검사들이 이미 잰다).
    """
    assert "단지" in ESTATE_LOAD_UNIT, (
        f"단지 합계의 단위 「{ESTATE_LOAD_UNIT}」가 «단지»라고 말하지 않는다"
    )
    assert ESTATE_LOAD_UNIT != APPLIANCE_LOAD_UNIT, (
        "단지 합계와 호당 값의 단위 낱말이 같다 — 두 열이 나란히 서면 구별되지 않는다"
    )


def test_the_axes_with_no_change_path_are_reported_in_words(
    report: CaseReport,
) -> None:
    """★★★ **바꾸는 통로가 「없다」를 산출물이 글자로 신고한다** (R68/WP-8).

    ## 왜 이 줄이 필요한가 — **「미반영 항목」 표가 이 둘을 못 센다**

    그 표(`core/report/unreflected.py::_unread_items`)는 *대장 스윕 축인데
    파이프라인이 안 읽는 것*만 센다. 저장장치 용량·정격출력은 **대장에 아예
    없어서** 그 판정에 들지 않는다 — 감시의 사각지대다. 검토서 §4.5 는 그 둘을
    *「하나씩 바꿨을 때 움직이는지 테스트해야 한다」* 의 목록에 넣었으므로,
    적지 않으면 산출물이 *「모든 수치는 변경 가능」* 을 **말없이 참으로 만든다.**

    ⛔ **통로를 세우는 것은 이 검사의 몫이 아니다** — 대장에 올리면 `sensitivity`
    삼수를 지어야 하고 그 근거가 없다. 여기서 붙드는 것은 **없다는 사실이 인쇄되는가**다.
    """
    lines = scaleup_lines(report)
    assert NO_CHANGE_PATH_NOTE in lines, (
        "「바꾸는 통로가 없다」 줄이 2단계에 없다 — 그러면 산출물이 「모든 수치는 "
        f"변경 가능」을 말없이 참으로 만든다. 실린 줄: {lines}"
    )
    assert "ESS_POWER_KW" in NO_CHANGE_PATH_NOTE, (
        "신고가 **어디에 있는 값인지**를 가리키지 않는다 — 가리키지 않으면 "
        "읽는 사람이 그것을 찾을 수 없다"
    )
