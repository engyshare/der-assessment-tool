"""**「전환 인자 없음」 옆에 무엇이 서 있는가** — R49 · 판정 §3 ⓒ.

판정의 문면은 한 줄이다 —
*「지금 리포트가 「없음」이라 적는 것 자체는 정직하고 옳다. 지울 대상이 아니다.
바뀌는 것은 **그 옆에 ⓐ·ⓑ 가 서서 「없는 이유」와 「그럼 무엇이 필요한가」를
말하는 것**이다」* (`docs/decisions-2026-08-31-R49.md` §3 ⓒ).

**그 배치를 이 파일이 붙든다.** 다른 파일이 재는 것과 갈라 둔다:

    test_shortfall.py       5.3 의 **수가 실물인가**       (합계 = 결손 · 엔진의 수)
    test_conclusion_gap.py  5.1 의 **줄임 열이 실물인가**  (표를 파싱해 되짚는다)
    ★ 이 파일               그 둘이 **함께 서 있는가**      (없음 · 그 옆 · 가리킴)

★ **왜 배치가 따로 재어져야 하는가.** 5.1 과 5.3 은 각자 자기 검사에서 초록불
이면서도 서로 만나지 않을 수 있다 — 「없음」 줄이 지워지거나, 5.3 이 붙임으로
내려가거나, 요약의 「없음」 칸이 5.3 을 가리키지 않게 되는 변이는 위 두 파일을
**전부 통과한다.** 그때 심의회는 「없음」 한 줄만 읽고 *「이 사업은 무엇을
고쳐도 안 된다」* 로 읽는데, 그 옆의 답은 자료 안에 있으면서 닿지 않는다.

🚫 **「없음」 문면을 지우지 않는다** — 판정이 명시로 남긴다. 그래서 이 파일은
*「없음이 있는가」* 를 재고, *「없음이 없는가」* 를 재지 않는다.

⚠ `req()` 마커는 달지 않았다 — 절의 배치는 양식이 정하는 서식 규정이지 spec
조항이 아니다(`test_shortfall.py`·`test_form_conformance.py` 와 같은 판단).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.report.case_report import CONCLUSION_METRIC, build_case_report
from core.report.narrative import render_markdown
from core.report.shortfall import (
    SECTION_NUMBER as SHORTFALL_SECTION,
)
from core.report.shortfall import (
    SECTION_TITLE as SHORTFALL_TITLE,
)
from core.report.shortfall import (
    SENSITIVITY_SECTION,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"

#: 5.1 이 전환 인자 0건일 때 싣는 줄의 머리. **판정이 남기라고 한 문면**이다.
NO_FLIP_LINE = "- 단독 전환 인자 — 없음"

#: 붙임의 시작. 본문/붙임 경계를 재는 자리 —
#: `test_form_conformance.py` 가 쓰는 것과 같은 꼴이다.
_APPENDIX_HEAD = re.compile(r"^## 붙임 \d+\.", re.MULTILINE)

_SCENARIOS = ("scenario_unsubsidized", "scenario_subsidy_80")


def _report(name: str):
    return build_case_report(_GOLDEN / f"{name}.yaml", assumptions_path=_ASSUMPTIONS)


@pytest.mark.parametrize("name", _SCENARIOS)
def test_no_flip_factor_is_printed_as_none_and_never_left_alone(name: str) -> None:
    """★★ **「없음」과 5.3 이 함께, 본문 안에, 순서대로 서 있다.**

    셋을 잰다 — 판정 §3 ⓒ 가 요구한 배치 그대로다:

        ㉠ 「없음」이 **그대로 있다**            ← 전환 인자가 0건인 갈래
        ㉡ 그 **옆에** 5.3 이 있다              ← 본문 안 · 5.1 뒤 · 합계 = 결론 축
        ㉢ 요약의 그 칸이 5.3 을 **가리킨다**    ← WP-3 이 세운 통로

    ⚠ **갈래를 둘 다 세운다.** 전환 인자가 생기는 날 ㉠ 은 「이름을 적는가」로
    바뀌지만 ㉡ 은 그대로다 — 결손 분해는 전환 인자의 존부와 무관하게 실린다
    (판정 §3 ⓐ 는 그것을 절로 세웠다). 그래서 ㉡·㉢ 은 갈래 밖에 둔다.

    ⚠ **번호를 검사에 박지 않는다** — `SHORTFALL_SECTION`·`SENSITIVITY_SECTION`
    에서 읽으므로 절을 옮기면 검사가 따라간다(WP-4 가 세운 규약).
    """
    report = _report(name)
    text = render_markdown(report)

    appendix = _APPENDIX_HEAD.search(text)
    assert appendix, "붙임이 없다 — 본문/붙임 경계를 잴 수 없다"
    body = text[: appendix.start()]

    # ㉡ 5.3 이 **본문 안에** 있고, 5.1 **뒤에** 온다.
    shortfall_head = f"### {SHORTFALL_SECTION} {SHORTFALL_TITLE}"
    assert shortfall_head in body, (
        f"결손 분해({shortfall_head})가 본문에 없다 — 「없음」 옆에 설 것이 "
        "없거나 붙임으로 내려갔다 (판정 §3 ⓐ·ⓒ)"
    )
    flip_head = f"### {SENSITIVITY_SECTION} "
    assert body.index(flip_head) < body.index(shortfall_head), (
        f"{SHORTFALL_SECTION} 이 {SENSITIVITY_SECTION} 앞에 온다 — "
        "「없는 이유」가 「없음」보다 먼저 나오면 그 답이 무엇에 대한 답인지 "
        "읽는 사람이 알 수 없다"
    )

    # ㉡-2 그 표의 합계가 **결론 축과 같은 수**다. 5.3 이 다른 사업을 가르고
    # 있으면 「없음」 옆에 선 답이 이 사업의 답이 아니다.
    conclusion = float(report.metrics[CONCLUSION_METRIC])
    shortfall_section = body[body.index(shortfall_head) :]
    assert f"**{conclusion:,.0f}원**" in shortfall_section, (
        f"결손 분해의 합계가 결론 축({conclusion:,.0f}원)을 싣지 않는다"
    )

    # ㉢ 요약의 「결론 전환 인자」 칸이 5.3 을 가리킨다.
    summary = text[text.index("## 1. 요약") : text.index("## 2. 평가 개요")]
    flip_cell = next(
        line for line in summary.splitlines() if line.startswith("| 결론 전환 인자")
    )
    if not report.flipping:
        assert "없음" in flip_cell, (
            f"전환 인자가 0건인데 요약이 「없음」이라 적지 않는다: {flip_cell}"
        )
        assert SHORTFALL_SECTION in flip_cell, (
            f"요약의 「없음」 칸이 {SHORTFALL_SECTION} 을 가리키지 않는다 — "
            f"심의회는 「없음」에서 멈춘다: {flip_cell}"
        )
        # ㉠ 5.1 본문의 「없음」 줄도 그대로 있다.
        assert NO_FLIP_LINE in body, (
            f"5.1 에 「{NO_FLIP_LINE}」 줄이 없다 — 판정 §3 ⓒ 는 그 문면을 "
            "**지우지 말라**고 명시한다"
        )
        assert SHORTFALL_SECTION in body[body.index(NO_FLIP_LINE) :].split("\n")[0], (
            f"5.1 의 「없음」 줄이 {SHORTFALL_SECTION} 을 가리키지 않는다"
        )
        return

    names = [f"`{entry.variable}`" for entry in report.flipping]
    assert any(one in flip_cell for one in names), (
        f"전환 인자 {names} 가 있는데 요약이 그 이름을 싣지 않는다: {flip_cell}"
    )
