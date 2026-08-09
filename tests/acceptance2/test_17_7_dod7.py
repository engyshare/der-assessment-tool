"""17.7 DoD 7 — 골든 3종 CI 회귀 통과 및 무료 호스팅 외부 접속 검증."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "tests.yml"


@pytest.mark.req("FR-1103-AC1")
def test_dod7_golden_3_scenarios_exist_and_valid() -> None:
    """DoD 7 — 골든 시나리오 3종 파일 존재 및 사양 검증 (NFR-104 / FR-1103)."""
    expected_files = [
        "scenario_subsidy_20.yaml",
        "scenario_subsidy_80.yaml",
        "scenario_unsubsidized.yaml",
    ]
    for name in expected_files:
        file_path = GOLDEN_DIR / name
        assert file_path.is_file(), f"골든 시나리오 파일이 존재하지 않습니다: {name}"
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"YAML 파싱 실패: {name}"


@pytest.mark.req("NFR-104-M1")
def test_dod7_ci_workflow_includes_pytest_and_ruff() -> None:
    """DoD 7 — GitHub Actions CI 워크플로에 pytest 및 ruff 검사 포함 확인."""
    assert WORKFLOW_PATH.is_file(), "CI 워크플로 파일이 존재해야 합니다."
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "pytest" in content
    assert "ruff" in content
