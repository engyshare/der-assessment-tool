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


@pytest.mark.req("NFR-206-M1")
def test_17_12_scale_total_line_ceiling_is_enforced_by_clause_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-206 조항 문면은 "500줄을 초과하지 않아야 한다" — **총** 줄 수이지
    코드 줄 수가 아니다. 위 테스트는 `--code-strict`(코드 줄만)만 부르므로,
    설명이 많아 총 줄만 넘고 코드는 500줄 이내인 파일이 있어도 조용히
    통과로 보인다.

    손으로 만든 오라클: 주석 480줄 + 코드 21줄 = 총 501줄인 파일을 만든다.
    코드는 21줄로 상한 이내이므로 `--code-strict` 는 통과(rc=0)해야 하고,
    조항 문면 그대로인 `--strict`(총 줄 수 기준)는 위반을 잡아야 한다(rc=1).
    """
    core_dir = tmp_path / "core"
    core_dir.mkdir()
    body = "\n".join(["# 근거 설명 줄"] * 480 + ["x = 1"] * 21)
    (core_dir / "synthetic.py").write_text(body + "\n", encoding="utf-8")
    monkeypatch.setattr(check_file_size, "TARGETS", ("core",))

    rc_code = check_file_size.main(["--root", str(tmp_path), "--code-strict"])
    assert rc_code == 0, "코드 줄은 21줄로 상한 이내인데 --code-strict 가 위반으로 잡았습니다"

    rc_total = check_file_size.main(["--root", str(tmp_path), "--strict"])
    assert rc_total == 1, (
        "조항 문면(총 줄 수 500줄 상한)을 501줄로 위반했는데 --strict 가 "
        "잡지 못했습니다 — 코드 줄 수만 보고 총 줄 수를 보지 않으면 "
        "조항 문면에 미달합니다"
    )
