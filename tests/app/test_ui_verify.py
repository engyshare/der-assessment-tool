"""검증 모드 화면 — **순차적으로 중간값을 보이는가** (사용자 판정 `docs/
decisions-2026-09-05-R63.md` §1 「결과」 · §3 ⓓ).

사용자 문면: *「분석결과는 순차적으로 분석 과정 상의 중간값을 사용자가 확인할
수 있는 형태로 제시하는 검증 모드를 제공해야 함」* — 예시로 네 걸음을 들었다
(① 사용자 정보·소비패턴·요금 · ② 공급설비·공급패턴·공급비용 · ③ 전력순수요 ·
④ 연차별 비용·편익).

## ★★★ 이 검사가 실제로 붙드는 것 — **화면이 값을 지어내지 않는가**

중간값 렌더러(`core/report/verification.py::render_verification_markdown`)는
**이미 있었고 CLI 하나만 불렀다**. 그래서 이 화면이 하는 일은 새로 계산하는
것이 아니라 **붙이는 것**이며, 이 파일의 중심 검사는
`test_stage_bodies_are_the_renderers_own_text` 다 — 화면에 인쇄된 단계 본문이
**렌더러가 낸 문자열의 부분집합**임을 문자 단위로 확인한다. 화면이 한 글자라도
스스로 지어내면 그 검사가 빨간불이 된다.

그 위에 **재료가 없는 다섯**(`.orch/R63/result_P4.md` §7)이 「빈 칸 + 사유」로
서 있는지를 따로 센다. 단계를 조용히 빼면 사용자가 요구한 것이 화면에서
사라지고, 사라진 것은 아무도 못 본다.

## `web.render_verify` 를 직접 부르지 않는다

전부 `TestClient(create_app())` 를 지난다. 문맥 함수를 직접 부르면 「배포
코드가 부르지 않는 함수가 초록불을 만든다」를 그대로 다시 밟는다 —
`tests/app/test_ui_router.py`·`test_ui_run.py` 머리말이 그 형태를 적어 두었다.

## 기댓값을 소스에 박지 않는다

수는 하나도 리터럴로 적지 않는다. 단계 본문은 렌더러 출력에서, 연차 금액은
`CaseReport.cashflows` 에서, 순수요는 `CaseReport.dispatch_hours` 에서 읽어
대조한다. 박으면 대장 판이 오르는 날 이 검사가 조용히 낡는다.

## ⚠⚠ `@pytest.mark.req(...)` 를 달지 않았다 — **조항을 대조하고 내린 판정이다**

브리프(`.orch/R63/WP-S3.md` §3 ①)가 `FR-1002`·`FR-1005` 를 가리켰으나, spec
(`rslt/spec-분산특구-경제성평가.md`)의 문면을 열어 대조한 결과 **이 화면이
충족하는 수용기준이 없다**:

- `FR-1002-AC3` 은 *「각 인자마다 함께 표시: 사용값 / 단위 / 기준연도 / 출처 /
  신뢰도 / 최종확인일 / **지표 변동폭** / **결론이 뒤집히는 임계값 존재
  여부**」* 다. 이 화면의 1단계 대장 표는 앞 여섯만 싣고 **뒤 둘을 싣지
  않는다** — 그것은 영향도 순위 절(`run_result.html#impact-ranking`)의 몫이다.
- `FR-1002-AC6` 은 *「전 가정 목록을 **부록 시트**로 제공한다」* 이며 이미
  심의용 리포트 붙임이 충족한다(`tests/report/test_overview_sections.py`).
  이 화면은 부록 시트가 아니다.
- `FR-1005-AC1` 은 *「실행마다 {실행ID, 시각, 코드 커밋 해시, …} 기록. 동일
  매니페스트 재실행 시 **비트 단위 동일 결과** 보장」* 이다. 이 화면은
  매니페스트 해시를 **보일 뿐** 기록하지도 재현성을 재지도 않는다.
- spec 전문에 `검증 모드`·`중간값`·`순차적` 이 **한 건도 없다**(grep 0건) —
  「단계별 검증 보고서」라는 산출물을 요구하는 조항 자체가 아직 없다.

`tests/report/test_verification.py` 가 **같은 자리에서 같은 판정**을 적어
두었고(그 머리말), `tests/app/test_report_cli.py::test_cli_writes_a_report_file`
가 같은 사유로 마커를 달지 않은 전례다. 맞지 않는 조항을 달면
`docs/traceability.md` 에 *「이 조항이 검증됐다」* 는 **거짓 인용**이 실린다.
⇒ spec 개정 여부는 오케스트레이터에게 넘긴다(`.orch/R63/result_S3.md` §7).
"""
from __future__ import annotations

import html
import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ui_run import run_ui_case
from app.services.verify_steps import (
    GAP_TAGS,
    STAGE_COUNT,
    VerificationStageError,
    split_stages,
)
from core.report._format import _num, _won
from core.report.case_report import CaseReport
from core.report.verification import render_verification_markdown

#: 대조에 쓰는 골든 시나리오 — `/ui/run` 쪽 검사와 **같은 것**을 써야 두 화면의
#: 수를 맞댈 수 있다.
_SCENARIO = "scenario_unsubsidized"

_VERIFY_PATH = "/ui/verify"

#: 사용자 문면의 네 걸음. **번호와 순서로 서야 한다** — 「하나 이상」이 아니다.
_USER_STEPS = 4

_GROUP = re.compile(r'data-group="(\d+)"')
_STAGE = re.compile(r'data-stage="(\d+)"')
_STAGE_BODY = re.compile(r'<pre class="stage-body">(.*?)</pre>', re.DOTALL)
_GAP_BLOCK = re.compile(r'<section class="verify-gap"(.*?)</section>', re.DOTALL)
_GAP_TAG = re.compile(r'data-gap="([^"]+)"')
_GAP_REASON = re.compile(r'<p class="gap-reason">(.*?)</p>', re.DOTALL)
_GAP_FILLED = re.compile(r'data-filled="([^"]+)"')
_CARRY = re.compile(r'<p class="group-carry">(.*?)</p>', re.DOTALL)
_NET_ROW = re.compile(r'<tr data-step="(\d+)">(.*?)</tr>', re.DOTALL)

#: 각 단계가 실어야 하는 네 칸 — `core/report/verification.py::_stage` 가 정본.
_CELLS = ("ⓐ 전제한 수치", "ⓑ 계산된 수치", "ⓒ 다음 단계로 넘긴 값", "ⓓ 계산 수식")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="module")
def body(client: TestClient) -> str:
    response = client.get(_VERIFY_PATH, params={"scenario": _SCENARIO})
    assert response.status_code == 200, response.text[:400]
    return response.text


@pytest.fixture(scope="module")
def report() -> CaseReport:
    """화면과 **같은 경로**로 돈 리포트 — 대조의 정본."""
    return run_ui_case(_SCENARIO).report


def _text(fragment: str) -> str:
    """화면 조각에서 태그를 걷어 낸 글자."""
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).strip()


def _group_slice(body: str, number: int) -> str:
    """묶음 하나의 HTML 조각 — 다음 묶음이 시작하기 전까지."""
    start = body.index(f'data-group="{number}"')
    tail = body[start:]
    following = _GROUP.search(tail, pos=1)
    return tail[: following.start()] if following else tail


def test_verification_mode_has_a_screen(client: TestClient) -> None:
    """검증 모드 경로가 **200** 이고 앱의 경로 목록에 서 있다.

    ⚠ `app.routes` 같은 앱 내부 자료구조를 훑지 않는다 — CI(3.11/FastAPI
    0.141)와 로컬(3.13/0.136)의 모양이 다르다. **응답**과 `openapi()` 만 본다.
    """
    assert _VERIFY_PATH in client.app.openapi()["paths"]
    assert client.get(_VERIFY_PATH, params={"scenario": _SCENARIO}).status_code == 200


def test_the_four_user_steps_stand_in_order(body: str) -> None:
    """사용자가 든 네 걸음이 **번호와 순서로** 선다 — 하나라도 빠지면 빨간불."""
    numbers = [int(n) for n in _GROUP.findall(body)]
    assert numbers == list(range(1, _USER_STEPS + 1)), (
        f"네 걸음이 순서대로 서지 않았다: {numbers}"
    )


def test_all_nine_renderer_stages_are_on_screen(body: str) -> None:
    """렌더러의 9단계가 **하나도 빠짐없이** 화면에 실린다.

    조용히 빠뜨리면 사용자는 없는 단계를 찾을 때까지 모른다.
    """
    stages = [int(n) for n in _STAGE.findall(body)]
    assert sorted(stages) == list(range(1, STAGE_COUNT + 1)), stages
    assert len(stages) == STAGE_COUNT, f"단계가 중복 또는 누락됐다: {stages}"


def test_stage_bodies_are_the_renderers_own_text(body: str, report: CaseReport) -> None:
    """★★★ **화면이 지어낸 글자가 없다** — 단계 본문이 렌더러 출력의 부분집합.

    화면이 수를 하나라도 스스로 지어내면 그 문자열이 렌더러 출력에 없고, 이
    검사가 그 자리에서 빨간불이 된다.
    """
    markdown = render_verification_markdown(report)
    bodies = _STAGE_BODY.findall(body)
    assert len(bodies) == STAGE_COUNT
    for index, raw in enumerate(bodies, start=1):
        printed = html.unescape(raw).strip()
        assert printed, f"{index}단계 본문이 비었다"
        assert printed in markdown, (
            f"{index}단계 본문에 렌더러가 내지 않은 글자가 있다:\n"
            f"{printed[:300]}"
        )


def test_every_stage_shows_where_its_values_came_from(body: str) -> None:
    """각 단계가 ⓐ 전제 → ⓑ 계산 → ⓒ 인계 → ⓓ 수식 **넷을 다** 싣는다.

    ⓓ 가 `CaseReport.formulas`·`BenefitLine.formula` 등 저장소가 이미 가진
    산식 문면이며, 그것이 「이 수가 어디서 왔나」의 답이다.
    """
    for index, raw in enumerate(_STAGE_BODY.findall(body), start=1):
        printed = html.unescape(raw)
        for cell in _CELLS:
            assert cell in printed, f"{index}단계에 「{cell}」 칸이 없다"


def test_every_missing_material_is_a_blank_cell_with_a_reason(body: str) -> None:
    """★★★ 못 그리는 칸이 **말없이 비어 있지 않다** — 사유가 글자로 있다."""
    blocks = _GAP_BLOCK.findall(body)
    tags = [_GAP_TAG.search(block).group(1) for block in blocks if _GAP_TAG.search(block)]
    assert sorted(tags) == sorted(GAP_TAGS), f"빈 칸 목록이 다르다: {tags}"
    for block in blocks:
        tag = _GAP_TAG.search(block).group(1)
        reason = _GAP_REASON.search(block)
        assert reason is not None, f"빈 칸 {tag!r} 에 사유 문단이 없다"
        assert len(_text(reason.group(1))) >= 20, (
            f"빈 칸 {tag!r} 의 사유가 글자로 서지 않았다: {reason.group(1)!r}"
        )


def test_blank_cells_print_no_number(body: str) -> None:
    """★★★ **재료가 없다고 판정된 항목에 수가 인쇄돼 있지 않다.**

    `.orch/R63/result_P4.md` §7 이 이름으로 못 박은 다섯이다. 표도 그림도
    값 칸도 그 자리에 서지 않는다 — 서면 그것이 지어낸 값이다.
    """
    for block in _GAP_BLOCK.findall(body):
        tag = _GAP_TAG.search(block).group(1)
        filled = _GAP_FILLED.search(block)
        assert filled is not None and filled.group(1) == "false", (
            f"빈 칸 {tag!r} 이 「값이 선 칸」으로 표시됐다"
        )
        for forbidden in ("<table", "<pre", "<img", "<figure"):
            assert forbidden not in block, (
                f"빈 칸 {tag!r} 에 {forbidden} 이 서 있다 — 값을 지어낸 자리다"
            )


def test_the_steps_are_linked_to_each_other_in_words(body: str) -> None:
    """★★ 「순차적」이 조항이다 — **한 걸음의 산출이 다음의 입력임이 글자로** 선다.

    첫 걸음에는 앞이 없으므로 ②③④ 셋을 센다.
    """
    for number in range(2, _USER_STEPS + 1):
        carry = _CARRY.search(_group_slice(body, number))
        assert carry is not None, f"{number}번째 걸음에 이어짐 문단이 없다"
        text = _text(carry.group(1))
        assert len(text) >= 20, f"{number}번째 걸음의 이어짐이 글자로 서지 않았다"
        assert "←" in carry.group(1), (
            f"{number}번째 걸음이 앞 걸음을 가리키지 않는다: {text!r}"
        )


def test_net_demand_stands_step_by_step_from_the_report(
    body: str, report: CaseReport
) -> None:
    """③ 전력순수요가 `dispatch_hours` 24행 그대로 선다 — **읽은 것뿐이다**.

    ⚠ 「대표일 하루」임이 캡션에 글자로 있어야 한다. 없으면 그 표가
    「계절 변동이 없다」를 결과로 주장한다(착수 순서 41번이 만난 함정).
    """
    section = _group_slice(body, 3)
    rows = _NET_ROW.findall(section)
    assert len(rows) == len(report.dispatch_hours)
    for (step, cells), hour in zip(rows, report.dispatch_hours, strict=True):
        assert int(step) == hour.step
        assert _num(hour.grid_import) in cells, (
            f"{hour.step}스텝의 순수요가 리포트 값과 다르다"
        )
    assert "대표일" in _text(section)


def test_year_by_year_rows_agree_with_the_proforma(
    body: str, report: CaseReport
) -> None:
    """★ ④ 연차별 비용·편익이 **프로포마와 원 단위로 같다**.

    수를 리터럴로 박지 않고 `CaseReport.cashflows` 에서 읽어 대조한다.
    생애주기 행은 1년차가 아니라 **실제 발생 연차**의 금액을 본다
    (`core/report/verification.py::_lifecycle_year_amounts` 가 그 사유를 적는다).
    """
    section = _text(_group_slice(body, 4))
    cf = report.cashflows
    for row in (*cf.benefit, *cf.operating_cost):
        assert _won(int(row.amounts[1])) in section, (
            f"{row.label} 의 1년차 금액이 화면에 없다"
        )
    for line in report.basis.one_off_flows:
        assert _won(line.amount_won) in section, (
            f"{line.label} 의 {line.year}년차 금액이 화면에 없다"
        )


def test_split_refuses_when_the_stage_count_changes() -> None:
    """⚠⚠ 단계가 9로 갈리지 않으면 **멈춘다** — 조용히 빠뜨리지 않는다.

    렌더러가 단계를 늘리는 날 화면이 말없이 여덟만 그리면 사용자는 없는 단계를
    찾을 때까지 모른다. `ParameterCatalogueError` 가 같은 판단을 적어 두었다.
    """
    short = "\n".join(f"## {n}단계 — 제목 {n}\n\n본문\n" for n in range(1, 9))
    with pytest.raises(VerificationStageError):
        split_stages(short)


def test_split_keeps_the_renderer_titles(report: CaseReport) -> None:
    """가른 단계가 렌더러의 번호·제목을 그대로 나른다."""
    stages = split_stages(render_verification_markdown(report))
    assert [s.number for s in stages] == list(range(1, STAGE_COUNT + 1))
    assert all(s.title and s.body.strip() for s in stages)
