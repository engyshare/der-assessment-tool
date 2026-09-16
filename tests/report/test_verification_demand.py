"""검증 1단계 ⓐ — **수요 입력의 여섯 속성** 표와 그 아래 세 절 (R68/WP-7).

동반 대상은 `core/report/verification_demand.py` 다(NFR-105 · 파일명 규약).

## ⚠ 무엇을 재고 무엇을 재지 않는가

이 검사가 붙드는 것은 넷이다.

1. **여섯 열이 서 있고 다섯이 대장에서 온다** — 값·단위·출처·계측 경계는
   지어낸 문면이 아니라 실행과 대장의 것과 **글자로 같아야** 한다.
2. ★ **「÷ (1 − 충전 손실률)」이 곱해졌고, 그래서 «보인다»** (R71/WP-1). 종전에는
   그 항이 `미반영` 으로 서 있었다 — 그때 붙들 것은 *「보이되 곱해지지 않는다」*
   였고 지금 붙들 것은 그 **반대**다: 인쇄된 총계가 대장 값을 나눈 수이고, 나눈
   사실과 나눈 수가 표와 그 아래 절에 **글자로** 선다. ⛔ **계산에는 들어가는데
   표에는 안 보이는 것**이 이 자리의 새 결함이며 그것을 이 검사가 막는다.
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
    EV_CHARGING_LOSS_LEDGER_KEY,
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
from core.report.verification_scaleup import (
    ESTATE_LOAD_UNIT,
    HOUSEHOLD_LOAD_LEDGER_KEY,
    household_base_kwh,
)

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


def test_the_ev_formula_prints_the_charging_loss_it_actually_divided_by(
    report: CaseReport, ledger: AssumptionSet
) -> None:
    """★★★ **곱해지는 수는 «보여야» 한다** (R71/WP-1).

    R67 이 지적한 결함이 *「항이 보이되 곱해지지 않는다」* 였다. 그것을 닫으면서
    **그 반대의 결함**이 열린다 — *「곱해지는데 안 보인다」*. 안 보이면 이 표의
    값(3,093)과 대장 행의 값(2,784)이 나란히 선 채로 읽는 사람에게 **어느 쪽이
    오타인가**로 읽힌다.

    ⇒ 산식 칸이 ⓐ **이 실행이 쓴 총계**로 시작하고 ⓑ **손실률 항**을 싣고
    ⓒ **대장에서 읽은 그 수**를 인쇄해야 한다.

    ⚠ 수를 리터럴로 적지 않는다 — 셋 다 대장·실행에서 읽어 맞댄다.
    """
    lines = demand_attribute_lines(report)
    ev_kwh = report.appliance_loads.ev_kwh
    assert ev_kwh is not None
    formula = _row(lines, EV_LOAD_TITLE)[5]
    assert formula.startswith(f"{ev_kwh:,.0f} =")
    for term in ("대수", "연간 주행거리", "전비", "충전 손실률"):
        assert term in formula
    # ⓒ 인쇄된 손실률이 **대장이 가진 그 수**다 — 지어낸 수가 아니다.
    loss = ledger.items()[EV_CHARGING_LOSS_LEDGER_KEY]
    assert f"{float(loss.value):g}" in formula
    assert EV_CHARGING_LOSS_LEDGER_KEY in formula
    # ⛔ 「미반영」은 이제 거짓이다 — 남아 있으면 산출물이 거짓말을 한다.
    assert "미반영" not in formula
    # ⛔ 항의 수를 리터럴로 박지 않았다 — 꼴만 세우고 수는 대장을 가리킨다.
    assert "45.99" not in formula
    assert "6.03" not in formula


def test_the_printed_ev_value_is_the_ledger_value_divided_by_one_minus_the_loss(
    report: CaseReport, ledger: AssumptionSet
) -> None:
    """★★★ **표의 값과 대장 행의 값이 «다르고», 그 차이가 산식이 말한 그것이다.**

    ⚠ **방향까지 잰다.** 곱하면 수전량이 줄어 결론축이 좋아지는데, 그 갈래는
    산출물을 훑는 눈으로는 안 잡힌다 — `tests/casegrid/test_appliance_load.py::
    test_the_ledger_ev_value_comes_out_converted_to_the_grid_side` 가 엔진 쪽에서
    같은 부등호를 잰다. 여기서 재는 것은 **인쇄된 수**다.
    """
    ev_kwh = report.appliance_loads.ev_kwh
    assert ev_kwh is not None
    battery = float(ledger.items()[EV_LOAD_LEDGER_KEY].value)
    loss = float(ledger.items()[EV_CHARGING_LOSS_LEDGER_KEY].value)
    assert ev_kwh == pytest.approx(battery / (1.0 - loss))
    lines = demand_attribute_lines(report)
    assert _row(lines, EV_LOAD_TITLE)[1] == f"{ev_kwh:,.0f}"
    assert ev_kwh > battery


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


def test_the_boundary_section_names_both_boundaries_and_which_way_it_moved(
    report: CaseReport,
) -> None:
    """계측 경계 절 — **두 경계와 옮긴 방향**을 글자로 적는다 (R71/WP-1).

    종전에는 *「배터리 투입 기준이고 실제 수전량보다 작다」* 였다. 이제 표의 값은
    **환산된 뒤**이므로 그 문장이 그대로면 거짓이 된다 — 적어야 할 것이 셋으로
    늘었다: ⓐ 대장의 조사값이 무슨 기준인가 ⓑ 표의 값이 무슨 기준인가
    ⓒ 어느 쪽이 큰가.
    """
    text = "\n".join(demand_attribute_lines(report))
    assert "배터리 투입 기준" in text  # ⓐ
    assert "계통 수전 기준" in text  # ⓑ
    assert "크다" in text  # ⓒ
    # ⚠ **방향을 말로도 못 박는다** — 부등호만 맞고 말이 「곱한다」면 다음 사람이
    #   소스를 그 말대로 고친다.
    assert "곱하기가 아니라 나누기다" in text


def test_the_boundary_section_says_the_loss_rate_is_an_assumption_not_a_survey(
    report: CaseReport, ledger: AssumptionSet
) -> None:
    """★★★ **곱했다고 해서 「조사했다」가 되지 않는다.**

    이 WP 가 한 일은 *「곱하되 그것이 가정임을 감추지 않는 것」* 이다. 값을
    조사값에 섞지 않고 **자기 이름을 단 항목**으로 세운 것이 그 실물이고,
    산출물은 그 사실을 **두 가지로** 적어야 한다: ⓐ 신뢰도가 `가정` 이라는 것
    ⓑ 민감도 폭이 없고 그것이 「민감하지 않다」가 아니라는 것.

    ⛔ 이 절이 사라지면 검토자는 3,093 을 **조사로 얻은 수**로 읽는다.
    """
    text = "\n".join(demand_attribute_lines(report))
    loss = ledger.items()[EV_CHARGING_LOSS_LEDGER_KEY]
    assert EV_CHARGING_LOSS_LEDGER_KEY in text
    assert loss.confidence.value in text  # ⓐ 「가정」
    assert "관례치 가정" in text
    assert "폭을 주장할 근거가 없다" in text  # ⓑ
    # ⚠ **이 단지로 좁힌 문면**은 그대로 남아야 한다 — 아래 검사와 같은 사실이다.
    assert "**이 단지의** 충전 손실을 잰 값이 없다" in text

def test_the_charging_efficiency_gap_names_the_number_it_refuses_to_borrow(
    report: CaseReport,
) -> None:
    """★ **문면을 좁혔다** — 「재료가 없다」가 저장소의 같은 이름을 가리지 않는다.

    독립 검증(`.orch/R68/result_V.md` 결함 #5)이 짚은 자리다. R68 은
    *「이 단지의 완속·급속 비율과 충전기 효율을 아무도 모른다」* 로 「닫을 수
    없다」를 세웠고 **그 판단 자체는 옳다** — `core/der/ev_v2g.py` 의
    `charge_efficiency` 는 V2G 자원의 **배터리 왕복** 파라미터이지 이 단지
    충전기 실측이 아니고 대장 항목도 아니다. 다만 *「재료가 없다」* 라는 넓은
    문면이 **저장소에 같은 이름의 수가 있다는 사실을 가렸다.**

    ⇒ 산출물이 그 사실을 적되 **경계가 다르므로 끌어다 쓰지 않는다**고 함께
    적어야 한다. ⛔ 그 수(0.92)를 산식에 곱하기 시작하면 이 검사가 아니라
    바로 위 `test_the_ev_formula_shows_the_charging_loss_term_without_
    multiplying_it` 이 빨간불이 된다 — 둘은 다른 자리를 붙든다.
    """
    text = "\n".join(demand_attribute_lines(report))
    # ⓐ 「없다」를 **이 단지로** 좁혔다 — 저장소 전체를 말하지 않는다.
    assert "**이 단지의** 충전 손실을 잰 값이 없다" in text, text
    # ⓑ 같은 이름의 수가 어디 있는지 **짚는다** — 가리지 않는다.
    assert "core/der/ev_v2g.py" in text
    assert "charge_efficiency" in text
    # ⓒ 그러나 **왜 못 쓰는지**를 함께 적는다. 짚기만 하고 사유가 없으면
    #    다음 사람이 그것을 「쓰면 되는 수」로 읽는다.
    assert "왕복" in text and "계측 경계가 아니" in text, text


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


def test_the_estate_unit_line_states_the_word_instead_of_deferring_it(
    report: CaseReport,
) -> None:
    """★★ **단지 합계의 단위를 「사람이 정할 일」로 미루지 않는다** (R68/WP-8).

    R68/WP-7 은 저장소의 낱말(`kWh/년`)과 검토서의 낱말(`kWh/단지·년`)이 갈린
    것을 **드러내고 멈췄다** — 그 줄은 *「맞추지 않았다 … 어느 낱말을 정본으로
    삼을지는 사람이 정한다」* 였고, 그것이 그 자리에서는 옳은 이행이었다.
    판정(`.orch/R68/JUDGMENT-wp7.md` ⓔ-1)이 검토서 쪽으로 정했으므로 그 줄은
    이제 **정해진 사실**을 적어야 한다.

    ⚠ 값도 곱하는 자리도 움직이지 않았다 — 낱말만이다. 그래서 이 검사도
    낱말만 본다.
    """
    note = next(
        line for line in demand_attribute_lines(report) if ESTATE_LOAD_UNIT in line
    )
    assert "맞추지 않았다" not in note, (
        "판정이 난 뒤에도 「맞추지 않았다」가 남아 있다 — 산출물이 해결된 일을 "
        "미해결로 인쇄한다"
    )
    assert APPLIANCE_LOAD_UNIT in note, (
        "단지 단위를 호당 단위와 나란히 놓지 않았다 — 그 대비가 이 줄의 요점이다"
    )
