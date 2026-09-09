"""검증 1단계 ⓐ — **수요 입력의 여섯 속성** 표와 그 아래 세 절 (R68/WP-7).

동반 대상은 `core/report/verification_demand.py` 다(NFR-105 · 파일명 규약).

## ⚠ 무엇을 재고 무엇을 재지 않는가

이 검사가 붙드는 것은 넷이다.

1. **여섯 열이 서 있고 다섯이 대장에서 온다** — 값·단위·출처·계측 경계는
   지어낸 문면이 아니라 실행과 대장의 것과 **글자로 같아야** 한다.
2. **「÷ 충전효율」이 보이되 곱해지지 않는다** — 인쇄된 총계가 대장 값 그대로다.
3. ★★ **대장이 여전히 「배터리 투입 기준」이라 적고 있다** — 이 모듈은 그 문면을
   파싱하지 않고 **글자로 못 박아** 인쇄하므로, 대장이 그 말을 거두면 산출물이
   거짓말이 된다. 파싱 대신 **이 검사가 어긋나는 날 사람을 부른다.**
4. **멈춘 자리 둘이 「없다」를 적는다** — 히트펌프 분해와 검증 상태. ⛔ 그 둘이
   표로 인쇄되기 시작하면(= 등급 승격·산문 파싱) 이 검사가 빨간불이어야 한다.

⛔ **엔진도 대장 검사기도 재지 않는다.** 값이 실제로 러너에 걸리는지는
`tests/casegrid/` 가, 대장 부기가 채워졌는지는 `scripts/check_assumptions.py` 가
잰다. 문서 전체가 이 절을 싣는지는 `tests/report/test_verification.py` 가 잰다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.assumption.provider import AssumptionSet
from core.casegrid.appliance_load import (
    APPLIANCE_LOAD_UNIT,
    EV_LOAD_LEDGER_KEY,
    EV_LOAD_TITLE,
    HEATPUMP_LOAD_LEDGER_KEY,
    HEATPUMP_LOAD_TITLE,
)
from core.report.case_report import CaseReport, build_case_report
from core.report.verification_demand import (
    EV_BOUNDARY_LEDGER_PHRASE,
    HOUSEHOLD_LOAD_TITLE,
    demand_attribute_lines,
)
from core.report.verification_scaleup import HOUSEHOLD_LOAD_LEDGER_KEY, household_base_kwh

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 검토서 §3.1 이 요구한 여섯 — **순서까지** 그 문면이다.
_SIX_ATTRIBUTES = ("값", "단위", "출처", "계측 경계", "산출식", "변경 경로")


@pytest.fixture(scope="module")
def report() -> CaseReport:
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


@pytest.fixture(scope="module")
def ledger() -> AssumptionSet:
    return AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))


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


def _folded(text: str) -> str:
    """대장 산문을 표 칸과 **같은 꼴**로 접는다 — 비교의 양쪽을 맞춘다."""
    return " ".join(text.split())


def test_the_head_carries_the_six_attributes_in_order(report: CaseReport) -> None:
    """★ 검토서 §3.1 의 여섯이 **열 제목으로** 서 있다 — 그리고 단위가 둘 다에 있다.

    ⚠ 「전제」가 열 제목에 없어야 한다 — 이 머리는 `/ui/verify` 에서 `th` 가 되고
    사람이 읽는 자리의 그 낱말은 0건이 규약이다(판정 R63b §1).
    """
    lines = demand_attribute_lines(report)
    head = next(line for line in lines if line.startswith("| 수요 입력"))
    columns = [cell.strip() for cell in head.strip().strip("|").split("|")][1:]
    assert len(columns) == len(_SIX_ATTRIBUTES)
    for column, attribute in zip(columns, _SIX_ATTRIBUTES, strict=True):
        assert column.startswith(attribute), (column, attribute)
    # 검토서 §4.2 — 단위가 **표 제목과 열 제목 둘 다**에 있다.
    title = next(line for line in lines if line.startswith("**수요 입력의 여섯 속성"))
    assert APPLIANCE_LOAD_UNIT in title
    assert APPLIANCE_LOAD_UNIT in columns[0]
    assert "전제" not in head


def test_unit_source_and_scope_are_read_from_the_ledger_verbatim(
    report: CaseReport, ledger: AssumptionSet
) -> None:
    """★★ 단위·출처·계측 경계는 **대장 문면 그대로**다 — 요약도 발췌도 아니다.

    한 글자라도 지어내면 그 문면이 「대장이 그렇게 적었다」로 읽힌다. 접기
    (`_cell`)만 허용되므로, 공백을 같은 꼴로 맞춘 뒤 **같아야** 한다.
    """
    lines = demand_attribute_lines(report)
    pairs = (
        (HOUSEHOLD_LOAD_TITLE, HOUSEHOLD_LOAD_LEDGER_KEY),
        (HEATPUMP_LOAD_TITLE, HEATPUMP_LOAD_LEDGER_KEY),
        (EV_LOAD_TITLE, EV_LOAD_LEDGER_KEY),
    )
    for title, key in pairs:
        item = ledger.items()[key]
        _name, _value, unit, source, scope, _derivation, route = _row(lines, title)
        assert unit == _folded(item.value_unit)
        assert source == _folded(item.source or "출처 미기재")
        assert scope == _folded(item.applicable_scope)
        assert f"`{key}`" in route  # 변경 경로 = 대장 키 자체


def test_the_printed_values_are_the_ones_this_run_used(report: CaseReport) -> None:
    """값 칸은 **이 실행이 쓴 값**이다 — 대장의 기준값이 아니라."""
    lines = demand_attribute_lines(report)
    loads = report.appliance_loads
    expected = (
        (HOUSEHOLD_LOAD_TITLE, household_base_kwh(report)),
        (HEATPUMP_LOAD_TITLE, loads.heatpump_kwh),
        (EV_LOAD_TITLE, loads.ev_kwh),
    )
    for title, value in expected:
        assert value is not None  # 이 골든이 셋 다 값을 갖는다는 것 자체
        assert _row(lines, title)[1] == f"{value:,.0f}"


def test_the_ev_formula_shows_the_charging_loss_term_without_multiplying_it(
    report: CaseReport,
) -> None:
    """⚠⚠ **「÷ 충전효율」이 보이되 어떤 수도 곱해지지 않는다.**

    검토서 §3.1 이 그 항을 산식에 요구하고 대장은 *「손실 계수를 지어내 곱하지
    않았다」* 고 적는다 — 둘 다 참이 되는 유일한 꼴이 **미반영으로 보이는 것**이다.
    그래서 인쇄된 총계는 **실행값 그대로**여야 한다(0.9 로 나눈 흔적이 없다).
    """
    lines = demand_attribute_lines(report)
    ev_kwh = report.appliance_loads.ev_kwh
    assert ev_kwh is not None
    formula = _row(lines, EV_LOAD_TITLE)[5]
    assert formula.startswith(f"{ev_kwh:,.0f} =")
    for term in ("대수", "연간 주행거리", "전비", "충전효율"):
        assert term in formula
    assert "미반영" in formula
    # ⛔ 항의 수를 리터럴로 박지 않았다 — 꼴만 세우고 수는 대장을 가리킨다.
    assert "45.99" not in formula
    assert "6.03" not in formula


def test_ledger_still_says_the_ev_value_is_battery_side(ledger: AssumptionSet) -> None:
    """★★★ **드리프트 붙잡이** — 대장이 그 말을 거두면 산출물이 거짓말이 된다.

    `verification_demand.py` 는 *「배터리 투입 기준이다」* 를 **글자로 못 박아**
    인쇄한다(산문을 파싱하지 않기 위해서다). 그 대가로 **대장이 바뀌면 조용히
    틀린다** — 그 침묵을 이 검사가 깬다. ⚠ 빨간불이 뜨면 고칠 곳은 이 검사가
    아니라 **인쇄되는 문면**이다.
    """
    item = ledger.items()[EV_LOAD_LEDGER_KEY]
    haystack = f"{item.derivation_method} {item.applicable_scope}"
    assert EV_BOUNDARY_LEDGER_PHRASE in haystack


def test_the_boundary_section_says_the_value_is_smaller_than_metered_purchase(
    report: CaseReport,
) -> None:
    """계측 경계 절 — **어느 방향으로 틀렸는지**까지 적는다.

    「배터리 기준이다」만으로는 검토자가 그 값이 실제 수전량보다 큰지 작은지 모른다.
    대장이 그 방향을 적었으므로(*「약 10% 낮게 잡혀 있다」*) 산출물도 적어야 한다.
    """
    text = "\n".join(demand_attribute_lines(report))
    assert "배터리 투입 기준" in text
    assert "충전 손실이 빠져 있다" in text
    assert "작다" in text


def test_the_heatpump_breakdown_is_pointed_at_not_tabulated(
    report: CaseReport, ledger: AssumptionSet
) -> None:
    """★ ⓒ — 난방·냉방·급탕은 **대장 항목이 아니므로** 표가 되지 않는다.

    ⚠ 앞머리에서 **그 사실 자체를 실물로 다시 잰다** — 대장에 하위 셋이 서는 날
    이 검사가 빨간불이 되어야 하고, 그때 할 일은 「인쇄하기」다.
    """
    heatpump_keys = [key for key in ledger.items() if key.startswith("load.heatpump")]
    assert heatpump_keys == [HEATPUMP_LOAD_LEDGER_KEY], heatpump_keys
    lines = demand_attribute_lines(report)
    text = "\n".join(lines)
    assert "난방·냉방·급탕 분해는 이 표에 없다" in text
    assert "대장 항목이 아니다" in text
    assert "사람의 판정 대기" in text
    # ⛔ 산문에서 뽑아 온 세 수가 표 행이 되지 않았다.
    assert not any(cells[0].startswith(("난방", "냉방", "급탕")) for cells in _cells(lines))


def test_the_verification_state_is_declared_absent_not_promoted(
    report: CaseReport,
) -> None:
    """★★ ⓓ — 넷의 검증 상태를 `confidence` 셋에서 **승격해 짓지 않았다.**

    ⛔ 이 저장소가 실물로 밟은 결함이다 — 없는 확인을 「출처 확인」으로 적으면
    검토자가 그 값을 확인된 사실로 읽는다. 그래서 넷은 **「없다」의 설명으로만**
    나타나야 하고, 값 칸이나 표 행이 되어서는 안 된다.
    """
    lines = demand_attribute_lines(report)
    text = "\n".join(lines)
    assert "검증 상태(계산됨 · 출처 확인 · 조사 인용 · 가정)는 대장이 갖고 있지 않다" in text
    assert "근거 등급의 승격" in text
    for cells in _cells(lines):
        for cell in cells:
            assert cell not in ("계산됨", "출처 확인", "조사 인용")


def test_the_unit_note_is_measured_rather_than_asserted(
    report: CaseReport, ledger: AssumptionSet
) -> None:
    """ⓔ — 단위가 갈렸는지 **세어서** 적는다. 갈리면 맞추지 않고 그 사실을 적는다.

    지금 실물은 셋 다 러너 상수와 같다. 갈리는 날 문면이 「같다」에서 「갈렸다」로
    바뀌어야 하므로, 여기서는 **세어 본 결과와 인쇄된 문면이 일치하는가**를 잰다.
    """
    keys = (HOUSEHOLD_LOAD_LEDGER_KEY, HEATPUMP_LOAD_LEDGER_KEY, EV_LOAD_LEDGER_KEY)
    mismatched = [k for k in keys if ledger.items()[k].value_unit != APPLIANCE_LOAD_UNIT]
    note = next(
        line for line in demand_attribute_lines(report) if line.startswith("- 단위")
        or line.startswith("- ⚠⚠ **단위가 갈렸다")
    )
    if mismatched:
        assert "갈렸다" in note
        assert all(f"`{key}`" in note for key in mismatched)
    else:
        assert "같다" in note
        assert APPLIANCE_LOAD_UNIT in note
