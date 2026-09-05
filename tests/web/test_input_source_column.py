"""화면이 **「그 수가 어디서 왔나」에 답하는가** — 출처 칸 (착수 목록 53 · `D12`).

판정 정본: `.orch/R63/WP-NEXT.md` §B · 실측 정본: `.orch/R63/result_V2.md` §2 `D12`.

## ★ 무엇이 어긋나 있었나

R63/S1 이 `web/render.py` 의 입력값 출처 문면을 「전제 대장」 → **「분석 설정
대장」**으로 옮겼는데, 브라우저 실측에서 **전 화면 일곱에 두 낱말이 0건**이었다.
옛 낱말도 안 보였다 ⇒ **바꾼 자리가 죽은 데이터였다.** 대시보드의 입력값 부록
`dl` 이 `item.source` 를 아예 그리지 않았기 때문이다.

S1 은 그 사실을 스스로 적고 **문맥에서** 쟀다(`test_dashboard.py::
test_the_ledger_source_word_moved_in_the_context` — *「화면에 없는 것을 「화면에
서라」로 재면 그 검사는 없는 자리를 세우라고 요구한다」*). ⇒ **이 파일은 그 자리가
선 뒤의 검사**이며, 같은 값을 이제 **화면에서** 잰다.

## ⚠⚠ 기준을 화면에서 되읽지 않는다

「화면에 있는 출처가 화면에 있다」는 항진이다. 모집단은 언제나 **자료 쪽**이다 —
대시보드는 `demo_context()["inputs"]`, 결과 화면은 `CaseReport.assumptions` 와
`CaseReport.influences`. 화면이 한 줄을 빠뜨리면 그 차이가 여기서 드러난다.

## ⚠ 「하나 이상 있다」로 두지 않는다

한 줄만 그리고 나머지 넷을 빠뜨린 상태가 「하나 이상」에서는 초록불이다. 그것이
R63 착수 시점에 이 저장소가 반복해 밟은 형태다(`test_dashboard.py::
test_no_parameter_variable_name_is_printed_where_people_read` 머리말).

## ⚠ `@pytest.mark.req(...)` 를 **하나도 달지 않았다**

가장 가까워 보이는 것은 `FR-1002-AC3`(*「각 인자마다 함께 표시: 사용값 / 단위 /
기준연도 / 출처 / 신뢰도 / 최종확인일 / 지표 변동폭 / 결론이 뒤집히는 임계값 존재
여부」*)이나 그 조항이 요구하는 것은 **여덟 가지**이고 이 축이 세운 것은 **출처
하나**다. 마커를 달면 `docs/traceability.md` 에 *「화면이 `FR-1002-AC3` 을
자동으로 판정한다」* 가 실리고 그것은 **거짓 인용**이다. `FR-1002-AC6`(*「전 가정
목록을 부록 시트로」*)도 아니다 — 여기서 그리는 것은 목록 전건이 아니라 영향도
인자마다의 출처다.
⇒ **달지 않고 사유를 적는다.** `tests/app/test_screen_words.py` 와
`tests/app/test_ui_verify.py` 가 같은 자리에서 같은 판정을 적었다.
"""
from __future__ import annotations

import re

import pytest

from app.services.ui_run import run_ui_case
from tests.web.test_dashboard import human_text, machine_attribute_text, parse
from web.render import demo_context, render_dashboard, render_run_result
from web.render_run import NO_LEDGER_SOURCE, run_result_context

#: 기본값 실행의 무보조 결론축. **표시층은 이 수를 움직이지 않는다.**
#: ⚠ 옛 수를 인용하지 마라(`−11,537,129`·`−12,591,162`·`−924,900`).
_DEFAULT_NPV = -11_552_270.0

#: 대조에 쓰는 골든 시나리오 — 결론축의 정의가 이것이다.
_SCENARIO = "scenario_unsubsidized"


@pytest.fixture(scope="module")
def report():
    """기본 갈래로 한 번만 돈다 — 실행 하나에 1초대가 든다."""
    return run_ui_case(_SCENARIO).report


# ── 대시보드 「입력값 부록」 ────────────────────────────────────────────────


def test_the_input_appendix_prints_the_source_of_every_input() -> None:
    """★★ **부록의 입력 전건이 자기 출처를 화면에 싣는다** — `D12` 의 본체.

    ⚠ **모집단을 화면에서 얻지 않는다.** `demo_context()["inputs"]` 가 기준이며
    화면이 한 줄을 빠뜨리면 그 이름이 아래 목록에 남는다.
    """
    inputs = demo_context()["inputs"]
    assert inputs, "부록에 입력이 하나도 없다 — 검사가 성립하지 않는다"

    corpus = human_text(render_dashboard())
    missing = [
        f"{item['label']}({item['source']})"
        for item in inputs
        if str(item["source"]) not in corpus
    ]
    assert not missing, (
        f"부록이 출처를 안 그리는 입력 {len(missing)}건: {missing} — "
        "출처 칸이 없으면 심의에서 「그 수가 어디서 왔나」에 답할 수 없다"
    )


def test_each_source_sits_in_the_row_of_its_own_input() -> None:
    """★ **출처가 자기 줄에 붙어 있다** — 한 덩이로 쏟아 놓은 것과 가른다.

    ⚠ 위 검사만 두면 가장 싼 통과 방법이 **출처 다섯을 한 문단에 이어 적는
    것**이고, 그때 사람은 어느 수의 출처인지 알 수 없다. ⇒ 칸마다
    `data-input-source` 로 **어느 입력의 것인지**를 싣고, 그 칸의 글자가 자료의
    출처와 **같은가**를 본다(부분 문자열이 아니다).
    """
    inputs = demo_context()["inputs"]
    cells = {
        element.attrs["data-input-source"]: element.text.strip()
        for element in parse(render_dashboard()).elements
        if "data-input-source" in element.attrs
    }

    assert len(cells) == len(inputs), (
        f"출처 칸이 {len(cells)}개 — 입력은 {len(inputs)}개다"
    )
    for item in inputs:
        assert cells.get(str(item["id"])) == str(item["source"]), (
            f"{item['id']} 의 출처 칸이 자료와 다르다: "
            f"{cells.get(str(item['id']))!r} ≠ {item['source']!r}"
        )


def test_the_input_id_stays_in_the_places_a_machine_reads() -> None:
    """★ **기계가 읽는 자리에는 입력 식별자가 남아 있다** — 양방향.

    ⚠ 위 검사만 두고 두면 사람이 읽는 칸을 세우면서 식별자를 지우는 구현이
    통과한다. 그때 「어느 입력의 출처인가」를 기계가 되짚을 길이 없어지고,
    `tests/web/test_dashboard.py` 가 파라미터 이름에 대해 세운 짝
    (`test_the_variable_name_is_still_in_the_places_the_form_reads`)이
    여기서만 빠진다.
    """
    machine = machine_attribute_text(render_dashboard())

    missing = [
        str(item["id"])
        for item in demo_context()["inputs"]
        if str(item["id"]) not in machine
    ]
    assert not missing, f"기계가 읽는 자리에서 사라진 입력 식별자: {missing}"


def test_the_new_ledger_word_now_stands_on_the_screen() -> None:
    """★★★ **「분석 설정 대장」이 화면 본문에 선다** — `D12` 가 막으려던 것.

    ⚠ **옛 낱말도 함께 잰다.** 새 낱말만 세면 옛 낱말이 다른 줄에 남은 상태가
    초록불이고, 그것이 R63/S1 이 고친 뒤에도 화면이 「전제 대장」을 인쇄할 수
    있었던 이유다.

    ## ⚠⚠ 「시나리오 기본값」은 여기서 재지 않는다 — **재료에 없다**

    판정 정본 `docs/decisions-2026-09-05-R63b.md` §1 이 부록의 셋째 출처
    문면(「사업 기본 설정」)을 **「시나리오 기본값」**으로 옮기라고 적으면서
    *「S1 은 그 자리가 정말로 시나리오 값인지 확인하라. 아니면 적고 멈춰라 —
    **그러면 이 판정이 틀린 것이다**」* 를 함께 적었다. S1 이 확인했고 **틀렸다**:
    분석기간의 소유자는 시나리오가 아니라 대장이며(`docs/assumptions.yaml` 의
    `analysis.period_years`), `infra/orm/scenario.py` 는 `analysis_years` 를
    Scenario **금지 필드**로 열거한다(`DV-11`).
    ⇒ 그 낱말을 화면에 세우려면 **손으로 적어야** 하고, 손으로 적으면 이 항목이
    막으려는 「죽은 데이터」가 그대로 다시 생긴다. **적고 멈췄다**
    (`.orch/R63/result_N2.md` §6).
    """
    corpus = human_text(render_dashboard())

    assert "분석 설정 대장" in corpus, (
        "「분석 설정 대장」이 화면에 없다 — 출처 칸이 죽은 데이터로 돌아갔다"
    )
    assert "전제 대장" not in corpus, "옛 낱말이 화면에 되살아났다"


# ── 결과 화면 `/ui/run` ────────────────────────────────────────────────────


def test_every_influence_carries_the_source_the_ledger_recorded(report) -> None:
    """★★ **영향도 인자 전건이 자기 출처를 갖는다** — 화면이 아니라 자료에서 잰다.

    ★ **문면을 화면에 손으로 적지 않는다.** 출처는 `CaseReport.assumptions` 의
    `source` 이며 인자의 `ledger_key` 로 잇는다 — 손으로 적으면 대장이 출처를
    갱신하는 날 화면만 옛 글자를 인쇄하고, 그 상태는 아무 검사도 빨간불을 내지
    않는다(그것이 `D12` 의 경위다).

    ⚠ **대장 키가 없는 인자를 빈칸으로 두지 않는다.** 빈칸은 「출처가 없다」와
    「싣지 못했다」를 화면에서 같게 만든다(§13.0.1 ④). 글자로 인쇄한다.
    """
    sources = {row.key: row.source for row in report.assumptions}
    context = run_result_context(report, scenario_text="")

    assert context["influences"], "영향도 인자가 없다 — 검사가 성립하지 않는다"
    for entry, drawn in zip(report.influences, context["influences"], strict=True):
        expected = sources.get(entry.ledger_key or "", NO_LEDGER_SOURCE)
        assert drawn["source"] == expected, (
            f"{entry.variable} 의 출처가 대장과 다르다: "
            f"{drawn['source']!r} ≠ {expected!r}"
        )
        assert str(drawn["source"]).strip(), (
            f"{entry.variable} 의 출처 칸이 비어 있다 — 빈칸은 진술이 아니다"
        )


def test_the_result_screen_draws_every_one_of_those_sources(report) -> None:
    """★★ **문맥에 실린 출처 전건이 화면에 그려진다** — 문맥만 맞는 상태와 가른다.

    ⚠ **개수를 박지 않는다.** 모집단은 이 실행의 인자 수이며 그것은 리포트가
    정한다.
    """
    context = run_result_context(report, scenario_text="")
    html = render_run_result(context)

    cells = {
        element.attrs["data-influence-source"]: element.text.strip()
        for element in parse(html).elements
        if "data-influence-source" in element.attrs
    }
    assert len(cells) == len(context["influences"]), (
        f"화면의 출처 칸이 {len(cells)}개 — 인자는 {len(context['influences'])}개다"
    )
    for item in context["influences"]:
        assert cells.get(str(item["rank"])) == str(item["source"]), (
            f"{item['rank']}위 인자의 출처 칸이 문맥과 다르다: "
            f"{cells.get(str(item['rank']))!r} ≠ {item['source']!r}"
        )


def test_the_source_text_is_the_ledgers_own_and_never_written_by_hand(report) -> None:
    """★ **화면에 선 출처가 전부 자료 쪽 글자다** — 손으로 적은 것이 섞이지 않았다.

    ⚠ 위 두 검사는 「자료가 화면에 있다」를 재고, 이것은 그 **반대 방향**이다:
    화면에 있는 출처 중 자료에도 상수에도 없는 글자가 있으면 누군가 손으로 적은
    것이다. 그 글자는 대장이 갱신되는 날 조용히 낡는다.
    """
    allowed = {row.source for row in report.assumptions} | {NO_LEDGER_SOURCE}
    context = run_result_context(report, scenario_text="")

    invented = sorted(
        str(item["source"])
        for item in context["influences"]
        if str(item["source"]) not in allowed
    )
    assert not invented, f"자료에 없는 출처 문면이 화면에 있다: {invented}"


# ── 가로 스크롤 · 결론축 ───────────────────────────────────────────────────

#: 템플릿이 자기 `<style>` 안에서 가로 스크롤을 켠 선택자.
_SCROLLABLE = re.compile(r"\.([A-Za-z0-9_-]+)\s*\{[^}]*overflow-x:\s*(?:auto|scroll)")


@pytest.mark.parametrize("html_factory", ["dashboard", "run_result"])
def test_a_sideways_scrolling_region_can_be_reached_by_keyboard(
    html_factory: str, report
) -> None:
    """★ **가로로 스크롤하는 영역에는 `tabindex="0"` 이 있다.**

    ⚠ 안 붙이면 키보드만 쓰는 사람이 그 영역을 스크롤할 수 없고, axe 가
    `scrollable-region-focusable`(serious) 위반을 낸다 — R63 이 실물로 밟았다
    (`web/templates/verify.html` 의 ⚠ 주석이 그 경위를 적는다).

    ⚠ **클래스 이름을 이 파일에 베껴 적지 않는다.** 템플릿의 `<style>` 에서
    `overflow-x` 를 켠 선택자를 읽어 온다 — 베껴 적으면 템플릿이 칸을 하나 더
    감쌀 때 이 검사가 그것을 못 본다.
    """
    if html_factory == "dashboard":
        html = render_dashboard()
    else:
        html = render_run_result(run_result_context(report, scenario_text=""))

    scrolling = set(_SCROLLABLE.findall(html))
    if not scrolling:
        pytest.skip(f"{html_factory} 에 가로 스크롤을 켠 선택자가 없다")

    naked = [
        f"{element.tag}.{element.attrs.get('class')}"
        for element in parse(html).elements
        if scrolling & set(element.attrs.get("class", "").split())
        and element.attrs.get("tabindex") != "0"
    ]
    assert not naked, (
        f"가로 스크롤 영역에 `tabindex=\"0\"` 이 없다: {naked} — "
        "키보드만 쓰는 사람이 그 안을 스크롤할 수 없다"
    )


def test_the_source_column_does_not_move_the_conclusion(report) -> None:
    """★★★ **결론축 불변** — 이 축은 표시층이고 계산 경로를 한 줄도 만지지 않았다.

    기본값 실행의 무보조 `npv` 는 **−11,552,270원**이며 화면이 인쇄하는 날값이
    리포트의 값과 **같은 객체에서** 온다. 움직였으면 그것이 새 결함이다.
    """
    context = run_result_context(report, scenario_text="")

    assert report.metrics["npv"] == pytest.approx(_DEFAULT_NPV)
    assert context["npv_raw"] == pytest.approx(_DEFAULT_NPV)
    assert len(report.overrides) == 0, "기본값 실행에 변경 항목이 생겼다"
