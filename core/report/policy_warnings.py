"""리포트 **상단**의 정책 가정 경고 절 — `FR-404-AC1` · R48 판정 §7.

## 무엇이 없었나

조항은 *「활성화 시 『정책 가정 편익 — 현행 제도 미반영』 경고를 **리포트
상단에** 표시」* 를 요구하는데, `core/report/` 안에 `policy_warnings()` 를 부르는
곳이 **한 곳도 없었다.** 즉 제도 근거 없는 가정 위에서 편익이 켜져 있어도
리포트는 아무 말도 하지 않았다 — 그리고 아무 예외도 나지 않았다.

## ★ 이 절이 **분류하지 않는 이유**

R48 판정 §6 은 두 문면을 갈라 놓았다 — `NWAs` 는 **제도 필요**(제도 자체가
설계 중), `CP` 는 **제도 보완 필요**(제도는 현행이나 분산특구 내 ESS 에 적용할
산정 기준이 없다). *「둘은 심의회에서 다른 답을 요구한다」* 이므로 뭉뚱그릴 수
없다.

그런데 그 구분을 **여기서** 지으면 안 된다. 표시 층이 문자열을 보고
`"보완" in warning` 같은 갈래를 치는 순간, 자원이 문면을 한 글자 다듬을 때마다
분류가 조용히 틀려지고 **아무 검사도 걸리지 않는다.** 그래서 구분은 **문면
자체가** 나르고(자원이 문면을 소유한다 — `DER.policy_warnings()` 독스트링),
이 절은 **누구의 경고인지만 붙여 그대로 인쇄한다.**

## ★ 비면 절을 만들지 않는다

*「해당 없음」* 한 줄을 세우지 않는다. 이 저장소의 규약은 *「값 0인 행은
『없음』과 『미구현』을 구분하지 못한다」* 이며, 경고 절에서는 그것이 더 나쁘다 —
상시로 뜨는 경고는 읽히지 않고, 읽히지 않는 경고는 경고가 아니다
(`narrative._provisional_cell` 이 같은 이유를 적어 두었다).
"""
from __future__ import annotations

from collections.abc import Sequence

from core.casegrid.models import ResourceLine

#: 절 제목. **번호를 달지 않는다** — 본문 절 번호는 양식
#: (`docs/report-form-심의보고서.md` §2)이 소유하고
#: `tests/report/test_form_conformance.py` 가 양방향으로 대조한다. 여기서
#: 번호를 달면 양식에 없는 절이 본문 번호를 차지한 것이 되어 그 검사가 빨간불이
#: 되고, 통과시키려면 남의 WP 인 양식 문서를 고치게 된다.
SECTION_HEADING = "## ⚠ 정책 가정 경고 — 제도 근거 미확인"


def policy_warning_section(resources: Sequence[ResourceLine]) -> list[str]:
    """경고가 있는 자원마다 **한 줄씩**. 하나도 없으면 **빈 목록**이다.

    구분자(`---`)까지 함께 낸다 — 절이 없을 때 호출부가 구분자만 남기지
    않게 하기 위해서다(비어 있으면 호출부는 아무것도 더하지 않는다).
    """
    entries = [
        f"- **`{line.name}`** ({line.kind}) — {warning}"
        for line in resources
        for warning in line.policy_warnings
    ]
    if not entries:
        return []
    return [SECTION_HEADING, "", *entries, "", "---", ""]
