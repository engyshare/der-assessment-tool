"""**양식과 실물을 대조한다** — `docs/report-form-심의보고서.md` ↔ 렌더러.

양식 머리말은 *「양식을 고치면 `narrative.py` 의 절 순서가 함께 움직인다」* 고
선언한다. 그런데 **그 선언을 강제하는 기계가 없었다.** 그동안 개별 절을 보는
검사만 있었고, 그래서 양식이 조용히 낡았다 — 2026-08-15 에 실측하니 넷이
어긋나 있었다(표제 · 5.1 출처 열 · 붙임 2 열 구성 · 산식의 자리).

    ★ 양식을 **파싱해서** 기대 목록을 만든다   ← 손으로 베끼면 그 사본이 낡는다
    ★ **양방향**으로 본다                      ← 한쪽에만 있는 절이 빨간불이다
    ★ 이름은 **앞부분 일치**로 본다            ← 실물은 「— 무엇」 을 덧붙인다

⚠ `req()` 마커는 달지 않았다 — 절의 구성은 양식이 정하는 서식 규정이지 spec
조항이 아니다. 조항이 정하는 것(`FR-1002-AC1` 절 순서)은
`tests/report/test_narrative.py` 가 따로 본다.

⚠ **이 검사는 「양식이 옳은가」를 묻지 않는다.** 둘이 같은 것을 말하는가만
본다. 어느 쪽이 맞는지는 사람이 정하고, 정한 뒤에는 **양쪽이 함께 움직인다.**
"""
from __future__ import annotations

import re
from pathlib import Path

from core.report.case_report import build_case_report
from core.report.narrative import render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORM = _REPO_ROOT / "docs" / "report-form-심의보고서.md"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"

# 양식 §2 의 본문 절 — `### 【1】 요약 *(약 0.5쪽)*`
_FORM_SECTION = re.compile(r"^### 【(\d)】\s+(.+?)(?:\s+\*\(.*)?$")
# 양식 §2 의 소절 — `- **2.1 평가 대상** — …`
_FORM_SUBSECTION = re.compile(r"^- \*\*(\d\.\d)\s+(.+?)\*\*")
# 양식 §3 의 붙임 표 — `| **1** | **전제 대장 전건** — … |`
# ⚠ `\d+` 이다. 한 자리로 두었더니 **붙임 10 이 파싱되지 않아** 검사가
# 조용히 통과했다 — 붙임을 지우는 변이가 초록불이었다(2026-08-15 실측).
_FORM_APPENDIX = re.compile(r"^\| \*\*(\d+)\*\* \| \*\*(.+?)\*\*")

# 실물 — `## 1. 요약` / `### 2.1 평가 대상` / `## 붙임 6. 디스패치 규칙과 …`
_RENDERED_SECTION = re.compile(r"^## (\d)\.\s+(.+)$")
_RENDERED_SUBSECTION = re.compile(r"^### (\d\.\d)\s+(.+)$")
_RENDERED_APPENDIX = re.compile(r"^## 붙임 (\d+)\.\s+(.+)$")


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def _collect(pattern: re.Pattern[str], lines: list[str]) -> list[tuple[str, str]]:
    found = [pattern.match(line) for line in lines]
    return [(m.group(1), m.group(2).strip()) for m in found if m]


def _form_lines() -> list[str]:
    return _FORM.read_text(encoding="utf-8").splitlines()


def _rendered_lines() -> list[str]:
    return render_markdown(_report()).splitlines()


def _assert_same_order(
    declared: list[tuple[str, str]],
    rendered: list[tuple[str, str]],
    what: str,
) -> None:
    """번호는 **순서까지** 같아야 하고, 이름은 **앞부분**이 같아야 한다.

    실물은 제목에 「— 무엇에 답하는 절인가」를 덧붙인다(`5.1 불확실 인자 —
    값이 틀릴 수 있는 것`). 그것까지 양식에 베끼면 문장 하나 다듬을 때마다 두
    파일이 함께 움직여야 해서, 결국 **검사를 통과시키려고 양식을 고치게** 된다.
    """
    assert [n for n, _ in declared] == [n for n, _ in rendered], (
        f"{what} 번호가 양식과 실물에서 다르다 — "
        f"양식 {[n for n, _ in declared]} · 실물 {[n for n, _ in rendered]}. "
        "한쪽에만 있는 것은 양식을 먼저 고쳐서 맞춘다"
    )
    pairs = zip(declared, rendered, strict=True)  # 길이는 위에서 이미 같다
    for (number, declared_name), (_, rendered_name) in pairs:
        assert rendered_name.startswith(declared_name), (
            f"{what} {number} 의 이름이 갈렸다 — "
            f"양식 「{declared_name}」 · 실물 「{rendered_name}」"
        )


def test_body_sections_match_the_form() -> None:
    """본문 6절의 **번호·순서·이름**이 양식 §2 와 같다."""
    declared = _collect(_FORM_SECTION, _form_lines())
    assert len(declared) >= 6, f"양식에서 본문 절을 못 읽었다: {declared}"
    rendered = _collect(_RENDERED_SECTION, _rendered_lines())
    _assert_same_order(declared, rendered, "본문 절")


def test_subsections_match_the_form() -> None:
    """소절(N.M)이 **양쪽에 같은 집합으로** 있다.

    ★ 실물에만 있는 소절이 곧 *「양식에 없는 절을 인쇄하고 있다」* 이고,
    양식에만 있는 소절이 곧 *「규정해 놓고 내지 않는다」* 다. 둘 다 「양식대로
    썼다」를 무너뜨리므로 한 검사가 양쪽을 본다.
    """
    declared = _collect(_FORM_SUBSECTION, _form_lines())
    assert len(declared) >= 10, f"양식에서 소절을 못 읽었다: {declared}"
    rendered = _collect(_RENDERED_SUBSECTION, _rendered_lines())
    _assert_same_order(declared, rendered, "소절")


def test_appendices_match_the_form() -> None:
    """붙임의 **번호·순서·이름**이 양식 §3 표와 같다."""
    declared = _collect(_FORM_APPENDIX, _form_lines())
    assert len(declared) >= 9, f"양식에서 붙임 표를 못 읽었다: {declared}"
    rendered = _collect(_RENDERED_APPENDIX, _rendered_lines())
    _assert_same_order(declared, rendered, "붙임")


def test_title_block_rows_match_the_form() -> None:
    """표제의 **행 이름과 순서**가 양식 【표제】 표와 같다.

    표제는 절이 아니라 **표**라서 위 셋과 같은 방식으로 잡히지 않는다. 그런데
    2026-08-15 에 실제로 어긋나 있던 넷 중 하나가 여기였다(양식은 작성일·작성
    주체를 요구하는데 실물에 없었다). 그래서 따로 본다.
    """
    lines = _form_lines()
    start = lines.index("### 【표제】")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("### 【1】"))
    declared = [
        line.split("|")[1].strip()
        for line in lines[start:end]
        if line.startswith("| ") and not line.startswith("|---")
    ][1:]  # 첫 행은 표 머리(`행 | 내용`)다
    assert declared, "양식에서 표제 표를 못 읽었다"

    rendered_all = _rendered_lines()
    body_start = next(
        i for i, line in enumerate(rendered_all) if line.startswith("## 1. ")
    )
    rendered = [
        line.split("|")[1].strip()
        for line in rendered_all[:body_start]
        if line.startswith("| ") and not line.startswith("|---")
    ][1:]

    assert declared == rendered, (
        f"표제 행이 양식과 실물에서 다르다 — 양식 {declared} · 실물 {rendered}"
    )


def test_the_report_carries_no_authoring_date() -> None:
    """★ **작성일을 싣지 않는다** (양식 【표제】 · 2026-08-15 개정).

    생성 시점을 찍으면 같은 입력이 같은 바이트를 내지 못해 `FR-1001-AC5`
    (비트 단위 동일 재실행)가 깨진다. 「언제의 수인가」는 **전제 대장 판**과
    **매니페스트 해시**가 답한다.

    ⚠ 날짜 **모양**을 금지하는 것이 아니다 — 대장의 기준연도처럼 계산에서 온
    날짜는 실린다. 금지되는 것은 **표제의 작성일 행**이다.
    """
    rendered_all = _rendered_lines()
    body_start = next(
        i for i, line in enumerate(rendered_all) if line.startswith("## 1. ")
    )
    head = "\n".join(rendered_all[:body_start])
    assert "작성일" not in head, "표제에 작성일이 실렸다 — 재실행 동일성이 깨진다"
    assert "작성 주체" in head, "표제에 작성 주체가 없다"
