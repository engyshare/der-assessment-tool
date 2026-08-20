"""VPP 경유 거부 사유가 **spec 이 선언한 선행 조항**을 가리키는가 — `FR-205-AC1.VPP`.

`assemble("VPP 경유", ...)` 는 `NOT_YET_ASSEMBLED["VPP 경유"]` 사유를 들고
거부한다. 그 사유 문면은 `FR-401-AC2.VPPMarket` 을 인용하는데, **그 사전을
읽어 자기 자신과 비교하면 동어반복이다** — 사유 문자열은 코드가 스스로 적은
것이므로 무엇을 적어도 항상 자기 자신과 같다. 그래서 spec 문면을 **따로
파싱해서** `AC1.VPP` 가 선행으로 적은 조항 ID 를 뽑고, 그 ID 가 코드의 사유에
들어 있는지 대조한다 — `tests/contract/test_dv_catalogue_matches_spec.py` ·
`tests/contract/test_exclusion_declaration_matches_table.py` 와 같은 형태다.

★ **`VPP 경유` 는 spec 상 `[Phase 2]` 다.** 그래서 여기서 붙드는 것은 거부
경로와 사유 문면뿐이다 — Phase 2 산출물(VPP 시장참여 편익 구현)을 요구하는
검사는 여기 세우지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.valuestream.settlement import NOT_YET_ASSEMBLED

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = REPO_ROOT / "rslt" / "spec-분산특구-경제성평가.md"

#: spec 의 `AC1.VPP` 줄에서 선행 조항 ID 를 뽑는다 — 예:
#: 「... `FR-401-AC2.VPPMarket` 이 선행이다 [Phase 2]」. `**AC1.VPP**` 표식부터
#: 「이 선행이다」 앞 백틱 인용까지를 **한 줄 안에서** 찾는다 — 줄을 건너가면
#: 다른 AC 의 인용을 집어올 위험이 있다.
_AC1_VPP_PRECURSOR = re.compile(
    r"\*\*AC1\.VPP\*\*.*?`([A-Za-z]+-\d+-AC\d+\.\w+)`\s*이 선행이다"
)


def _spec_declared_precursor() -> str:
    text = SPEC.read_text(encoding="utf-8")
    match = _AC1_VPP_PRECURSOR.search(text)
    assert match is not None, (
        "spec 에서 `AC1.VPP` 가 선행으로 적은 조항 인용을 찾지 못했습니다 — "
        "spec 문면 형식이 바뀌었을 수 있습니다"
    )
    return match.group(1)


@pytest.mark.req("FR-205-AC1.VPP")
def test_the_rejection_reason_cites_the_spec_declared_precursor() -> None:
    """★★★ 사전의 사유 문면이 **spec 이 실제로 적은 선행 조항 ID** 를 인용한다.

    `NOT_YET_ASSEMBLED` 사전을 읽어 자기와 비교하면 참일 수밖에 없으므로,
    spec 을 따로 파싱해 거기 적힌 조항 ID 와 대조한다. spec 이 이 인용을
    지우거나 다른 조항으로 바꾸면(예: `FR-401-AC2.VPPMarket` 이 쪼개지거나
    이름이 바뀌면) 사전이 낡은 조항을 계속 가리킨 채 이 검사가 빨간불이
    되어야 한다.
    """
    precursor = _spec_declared_precursor()
    assert precursor in NOT_YET_ASSEMBLED["VPP 경유"], (
        f"spec 이 `AC1.VPP` 의 선행으로 적은 {precursor!r} 가 코드의 거부 "
        f"사유에 없습니다: {NOT_YET_ASSEMBLED['VPP 경유']!r}"
    )
