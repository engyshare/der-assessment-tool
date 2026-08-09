"""17.12 규모 검산 재확인 — NFR-206 파일 규모 500줄 상한 검증."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_file_size

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.req("NFR-206-M1")
def test_17_12_scale_check_reverification() -> None:
    """17.12 규모 검산 재확인 — 소스 코드 라인 수 상한(500줄) 이내 보장 확인."""
    rc = check_file_size.main(["--root", str(REPO_ROOT), "--code-strict"])
    assert rc == 0, "NFR-206 코드 줄 수 상한(500줄) 초과 파일이 있습니다."
