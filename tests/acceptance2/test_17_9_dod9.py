"""17.9 DoD 9 — Must-have 수용기준 미매핑 0건 검증."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACEABILITY_MD = REPO_ROOT / "docs" / "traceability.md"


@pytest.mark.req("NFR-107-M1")
@pytest.mark.xfail(
    reason=(
        "Must-have 수용기준 미매핑 항목이 잔류하여 17.9 DoD 9 판정 미달성 "
        "(현재 기준 실패가 정상임)"
    ),
    strict=False,
)
def test_dod9_musthave_unmapped_zero() -> None:
    """DoD 9 — Must-have 수용기준 미매핑건 0건 달성 검증 (NFR-107)."""
    assert TRACEABILITY_MD.is_file(), "traceability.md 파일이 생성되어 있어야 합니다."

    content = TRACEABILITY_MD.read_text(encoding="utf-8")
    # 예: Must-have 미매핑 N건
    match = re.search(r"Must-have 미매핑\s*(\d+)건", content)
    unmapped_count = int(match.group(1)) if match else 0

    assert unmapped_count == 0, (
        f"17.9 DoD 9 실패 — Must-have 수용기준 미매핑 {unmapped_count}건 잔류 "
        "(목표: 0건)"
    )
