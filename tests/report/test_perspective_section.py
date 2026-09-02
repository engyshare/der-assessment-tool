"""`core.report.perspective_section` 동반 검사 — R53/WP-1-fix.

`NFR-105` 게이트 ②(`scripts/check_test_accompaniment.py`)가 R53/WP-1 커밋에서
`core/report/perspective_section.py` 를 동반 테스트 없는 구현 변경으로 잡았다
(`tests/casegrid/test_perspective_wiring.py` 는 이 모듈을 `render_markdown()`
을 거쳐서만 부르므로 `core.report.perspective_section` 을 직접 import 하지
않는다 — 경로 ⓐ가 비었고, 이 파일 이름 규약도 없었다). 이 파일이 경로
ⓑ(`tests/report/test_perspective_section.py`)를 만든다.

⚠ 「사회 열의 편익 합계가 0원인 이유」 문면(R53/WP-1)은 *「배선은 서 있다
(`DistributedBenefit` 이 사회 열에 실린다)」* 라는 **사실 주장**이다. 이 파일은
그 주장을 문자열로만 재지 않는다 — 같은 `report` 의 사회 열 편익 행에
`DistributedBenefit` 이 **실제로** 있는지 함께 잰다(오케스트레이터 판정
`.orch/R53/WP-1-fix.md` §3). 둘을 한 검사에서 같이 재야, 누가 배선을
되돌리는 순간 「문면은 남았는데 사실이 아니게 된」 상태를 이 검사가 잡는다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.cba.perspective import Perspective
from core.report.case_report import build_case_report
from core.report.perspective_section import perspective_section

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"


@pytest.fixture(scope="module")
def report():
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


def test_society_zero_reason_claims_wiring_is_up_and_it_actually_is(report) -> None:
    """ⓐ 문면이 「배선은 서 있다」고 적는다 · ⓑ 같은 report 의 사회 열에
    `DistributedBenefit` 행이 실제로 있다 — 배선을 되돌리면 ⓑ가 빨간불이 된다.
    """
    text = "\n".join(perspective_section(report))
    assert "배선은 서 있다" in text and "DistributedBenefit" in text, (
        "「사회 열의 편익 합계가 0원인 이유」 문면이 안 보이거나 문구가 바뀌었다 "
        f"— 이 검사도 함께 갱신해야 한다:\n{text}"
    )

    society = next(
        r for r in report.perspectives.results if r.perspective is Perspective.SOCIETY
    )
    tags = {row.tag for row in society.benefit_rows}
    assert "DistributedBenefit" in tags, (
        f"문면은 「배선은 서 있다」고 적는데 사회 열 편익 행에 DistributedBenefit "
        f"이 없다 — {tags}. 문면이 거짓이다"
    )
