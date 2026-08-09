"""17.8 DoD 8 — 자원 6종 + 공통설비 케이스 전건 통과 검증."""
from __future__ import annotations

from pathlib import Path

import pytest

import core.der
from core.contracts.der import DER
from core.contracts.registry import discover

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DER_DIR = REPO_ROOT / "tests" / "der"


@pytest.mark.req("NFR-106-M1")
def test_dod8_all_discovered_resources_have_cases() -> None:
    """DoD 8 — 등록된 자원 클래스 전건에 독립 테스트 케이스 세트 존재 확인."""
    registry = discover(core.der, DER)
    assert len(registry) >= 6, f"자원 클래스가 최소 6종 이상 등록되어야 합니다: {len(registry)}종"

    missing: list[str] = []
    for tag, cls in sorted(registry.items()):
        module_path = REPO_ROOT / f"{cls.__module__.replace('.', '/')}.py"
        if not module_path.is_file():
            continue  # 임시/테스트 클래스 제외
        module_name = cls.__module__.rsplit(".", maxsplit=1)[-1]
        test_file = TESTS_DER_DIR / f"test_{module_name}.py"
        if not test_file.is_file():
            missing.append(f"{tag} ({test_file.name})")

    assert not missing, "독립 테스트 파일이 누락된 자원 클래스가 있습니다: " + ", ".join(missing)
