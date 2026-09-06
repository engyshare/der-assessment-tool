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
#: ⚠⚠ **속성을 더 붙일 수 있게 열어 둔다.** 종전에 이 정규식이
#: `<pre class="stage-body">` 를 **글자까지 고정**하고 있었고, 접근성 위반
#: (`scrollable-region-focusable`)을 고치려고 그 태그에 `tabindex="0"` 을 더한
#: 순간 **찾은 본문이 0개가 되어** `assert 0 == 9` 로 빨간불이 됐다 —
#: 화면은 멀쩡했고 깨진 것은 **재는 쪽**이다. 태그의 속성은 접근성·스타일 때문에
#: 늘어나는 것이 정상이므로, 재는 것을 **클래스 이름 하나**로 좁힌다.
_STAGE_BODY = re.compile(
    r'<pre class="stage-body"[^>]*>(.*?)</pre>', re.DOTALL
)
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


#: ★★ 가구 수를 **준** 실행의 화면 — 아래 갈래 검사 넷이 함께 쓴다.
#: 값은 「잉여가 남는 규모」이며 사유는
#: `tests/casegrid/test_household_count.py::_COUNT` 가 갖는다.
_HOUSEHOLD_COUNT = 2

_FILL_BLOCK = re.compile(r'<section class="verify-fill"(.*?)</section>', re.DOTALL)
_FILL_TAG = re.compile(r'data-fill="([^"]+)"')
_FILL_VALUE = re.compile(r'<p class="fill-value">(.*?)</p>', re.DOTALL)


@pytest.fixture(scope="module")
def sized_body(client: TestClient) -> str:
    """가구 수를 **준** 실행의 화면 — 위 `body` 와 같은 시나리오·다른 갈래."""
    response = client.get(
        _VERIFY_PATH,
        params={"scenario": _SCENARIO, "household_count": _HOUSEHOLD_COUNT},
    )
    assert response.status_code == 200, response.text[:400]
    return response.text


def test_without_a_household_count_the_screen_stands_no_number(body: str) -> None:
    """★★★ **가구 수를 안 준 실행에는 값 칸이 하나도 없다** — 지금까지와 같다.

    이것이 기본 갈래이며 골든 셋이 도는 갈래다. 여기에 값이 서면 그것은
    저장소가 지어낸 세대 수이고, 그 수가 단지 총부하를 통째로 정한다.
    """
    assert not _FILL_BLOCK.findall(body), (
        "가구 수를 주지 않았는데 값이 선 칸이 있다 — 지어낸 수다"
    )


def test_giving_a_household_count_turns_the_blank_into_a_number(
    sized_body: str,
) -> None:
    """★★★ **47ⓐ — 값이 지정된 실행에서는 칸이 아니라 수를 보인다** (판정 ④).

    ⚠ 수를 리터럴로 대조하지 않는다 — 질의로 보낸 값을 그대로 되찾는다.
    """
    blocks = _FILL_BLOCK.findall(sized_body)
    tags = [_FILL_TAG.search(block).group(1) for block in blocks]
    assert tags == ["households"], f"값이 선 칸 목록이 다르다: {tags}"
    value = _FILL_VALUE.search(blocks[0])
    assert value is not None, "값이 선 칸에 값 문단이 없다"
    assert f"{_HOUSEHOLD_COUNT:,}호" in _text(value.group(1)), (
        f"화면이 {_HOUSEHOLD_COUNT}호를 보이지 않는다: {value.group(1)!r}"
    )
    assert 'data-filled="true"' in blocks[0], (
        "값이 선 칸이 「빈 칸」으로 표시됐다"
    )


def test_the_household_type_stays_a_blank_cell_even_with_a_count(
    sized_body: str,
) -> None:
    """★★ **칸이 사라지지 않고 좁아진다** — 가구 유형은 여전히 재료가 없다.

    수가 왔다고 칸을 통째로 지우면 사용자가 요구한 「가구 유형」이 화면에서
    사라지고, 사라진 것은 아무도 못 본다. 대장의 `load.household.type_mix` 는
    아직 `track: blocked` 이며 **표현할 자료형조차 정해지지 않았다.**
    """
    blocks = _GAP_BLOCK.findall(sized_body)
    tags = [_GAP_TAG.search(b).group(1) for b in blocks if _GAP_TAG.search(b)]
    assert sorted(tags) == sorted(GAP_TAGS), (
        f"가구 수를 준 실행에서 빈 칸 목록이 달라졌다: {tags}"
    )
    households = next(
        b for b in blocks if _GAP_TAG.search(b).group(1) == "households"
    )
    assert "가구 유형" in _text(households), (
        "가구 수를 주었는데 남은 빈 칸이 가구 유형을 가리키지 않는다"
    )
    filled = _GAP_FILLED.search(households)
    assert filled is not None and filled.group(1) == "false"


def test_a_household_count_below_one_is_refused_as_a_readable_screen(
    client: TestClient,
) -> None:
    """★★ **0호는 거부고, 그 거부가 사람이 읽는 화면이다** (`NFR-303`).

    ⚠ JSON 으로 내지 않는다 — 이 라우트는 화면이고, JSON 을 받은 브라우저는
    3요소를 사람이 읽을 모양으로 그리지 못한다.
    """
    response = client.get(
        _VERIFY_PATH, params={"scenario": _SCENARIO, "household_count": 0}
    )
    assert response.status_code == 400, response.text[:200]
    printed = _text(response.text)
    assert "가구 수" in printed and "조치" in printed, (
        f"거부 화면이 3요소를 사람이 읽을 모양으로 그리지 않았다: {printed[:300]}"
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


# ── ★★★ R64/WP-5: ① 걸음의 **계절별 표** (사용자 요구 6) ──────────────────
#
# 사용자 문면: *「계절별로 가구의 전력 수요, 발전, ESS 운전 등을 시간대별로
# 수치와 도표를 확인할 수 있어야 함」*. WP-4 가 계산을 세우고
# `seasonal_operation` 빈 칸의 사유를 *「아직 없는 것은 화면이다」* 로 갈아
# 끼웠다. 아래가 그 화면이며, 그 사유가 **거짓이 됐는지**를 함께 잰다.

_SEASON_TABLE = re.compile(
    r'<table data-season="([^"]+)" data-season-days="(\d+)">(.*?)</table>', re.DOTALL
)
_SEASON_ROW = re.compile(r'<tr data-season-step="(\d+)">(.*?)</tr>', re.DOTALL)
_SEASON_CAPTION = re.compile(r'<figcaption>(.*?)</figcaption>', re.DOTALL)

_SEASONAL_GAP = "seasonal_operation"


def test_the_screen_splits_the_run_by_season(body: str, report: CaseReport) -> None:
    """★★★ **화면이 계절을 갈라 보인다** — 이름·일수·스텝이 리포트 그대로다.

    ⚠ 「봄 92일」 같은 수를 소스에 박지 않는다. 계절 달력은 자산
    (`fixtures/profiles/representative-day.yaml`)이 정하고 `CaseReport.seasons`
    가 나른다 — 박으면 자산이 달력을 바꾸는 날 이 검사가 「화면이 틀렸다」로
    빨간불이 된다.

    ⚠⚠ **화면이 계절을 다시 나누지 않는가**를 함께 잰다. 값 한 칸까지
    `SeasonRun.dispatch` 와 맞대므로, 화면이 연간등가 하루를 계절 몫으로 되짚어
    지으면 여기서 갈린다.
    """
    assert report.seasons, "이 시나리오가 계절을 하나도 돌지 않았다"

    section = _group_slice(body, 1)
    tables = _SEASON_TABLE.findall(section)
    assert [name for name, _, _ in tables] == [s.name for s in report.seasons], (
        f"화면의 계절 목록이 실행과 다르다: {[n for n, _, _ in tables]}"
    )
    assert [int(days) for _, days, _ in tables] == [s.days for s in report.seasons]

    for (name, _, table), season in zip(tables, report.seasons, strict=True):
        rows = _SEASON_ROW.findall(table)
        assert len(rows) == len(season.dispatch.grid_export), (
            f"계절 {name}: 스텝 {len(season.dispatch.grid_export)}개 중 "
            f"{len(rows)}개만 실렸다"
        )
        for step, cells in rows:
            index = int(step)
            assert _num(season.dispatch.grid_import[index]) in cells, (
                f"계절 {name} {index}스텝의 계통 수전이 실행 값과 다르다"
            )
            assert _num(season.dispatch.grid_export[index]) in cells, (
                f"계절 {name} {index}스텝의 계통 송전이 실행 값과 다르다"
            )


def test_the_seasonal_tables_carry_the_same_columns_as_the_net_demand_one(
    body: str,
) -> None:
    """★★ **계절 표와 순수요 표의 자원 열이 같다** — 두 표를 맞대 볼 수 있어야 한다.

    갈라 두면 한쪽만 자원이 늘거나 이름이 바뀌고, 그때 화면은 멀쩡해 보인다
    (`app/services/verify_steps.py::net_demand_columns` 의 ⚠).

    ⚠ **머리글 전체를 맞대지 않는다.** ③ 순수요 표의 마지막 열은 「순수요 =
    계통 수전」이고 그것이 그 표의 요지다(*「화면이 부하에서 자가공급을 다시
    빼지 않는다」*). 같아야 하는 것은 **자원 열**이며, 첫 칸(스텝)과 뒤 두
    칸(계통 송·수전)을 걷어 낸 나머지다.
    """
    heads = re.findall(r"<thead>(.*?)</thead>", body, re.DOTALL)
    columns = [
        tuple(re.findall(r'<th scope="col">([^<]*)</th>', head))[1:-2]
        for head in heads
    ]
    assert len(columns) >= 2, f"화면에 표가 {len(columns)}개뿐이다"
    assert all(columns), "자원 열이 없는 표가 있다"
    assert len(set(columns)) == 1, (
        f"표마다 자원 열이 다르다 — 표를 두 벌로 그리고 있다: {set(columns)}"
    )


def test_the_seasonal_caption_says_the_calendar_is_an_assumption(body: str) -> None:
    """★★★ **계절 몫·형상이 「가정값」이라고 화면이 말한다** (사용자 판정 §2).

    사용자 문면: *「해당 자료도 참값은 아님. 가정한 값임을 유의해줘」*. 24행짜리
    표 넷만 세우면 그것이 **실측 소비패턴**으로 읽히고, 그 오독이 심의 자료에
    실린다 — 이 화면에서 가장 비싼 오독이다.
    """
    section = _group_slice(body, 1)
    captions = [_text(found) for found in _SEASON_CAPTION.findall(section)]
    assert captions, "계절 표에 캡션이 없다"
    said = [
        caption
        for caption in captions
        if "가정값" in caption and "실측이 아니다" in caption
    ]
    assert len(said) == 1, (
        f"계절 달력이 가정값이라고 말하는 캡션이 {len(said)}개다: {captions}"
    )


def test_the_seasonal_blank_cell_narrowed_instead_of_disappearing(
    body: str,
) -> None:
    """★★★ **`seasonal_operation` 칸이 좁아졌다 — 사라지지 않았다** (판정 ④).

    ## 무엇이 닫혔나

    WP-4 가 남긴 사유는 *「아직 없는 것은 화면이다 — 이 검증 절차가 계절별
    소비·발전·수전을 갈라 그리지 않는다」* 였고, 위 검사가 그 화면이 섰음을
    잰다. 그러므로 **그 문면은 거짓이 됐고 남아 있으면 안 된다.**

    ## 무엇이 남았나

    계절 몫·형상은 여전히 자산의 **가정값**이고 「가구별」 분해는 재료가 없다.
    칸을 통째로 지우면 화면이 *「계절별 소비패턴을 실측으로 안다」* 를 주장하게
    되므로 지우지 않는다 — `_HOUSEHOLD_TYPE_ONLY` 가 이미 밟은 형태다.

    ⚠ 「화면에 무언가 있다」가 아니라 **그 태그의 상태**를 잰다.
    """
    assert _SEASONAL_GAP in GAP_TAGS, "칸이 목록에서 사라졌다"

    block = next(
        found
        for found in _GAP_BLOCK.findall(body)
        if _GAP_TAG.search(found).group(1) == _SEASONAL_GAP
    )
    reason = _text(_GAP_REASON.search(block).group(1))

    assert "아직 없는 것은 화면이다" not in reason, (
        "화면이 계절을 갈라 보이는데도 「아직 없는 것은 화면이다」가 남아 있다"
    )
    assert "가정값" in reason, (
        f"남은 결손이 「계절 몫·형상이 가정값」임을 말하지 않는다: {reason}"
    )
    assert "가구별" in reason, (
        f"남은 결손이 「가구별 분해가 없다」임을 말하지 않는다: {reason}"
    )
