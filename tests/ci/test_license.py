from pathlib import Path

import pytest


@pytest.mark.req("FR-1101-AC1")
def test_public_repository_includes_basic_contribution_documents() -> None:
    root_dir = Path(__file__).parent.parent.parent
    required = [
        "README.md",
        "CONTRIBUTING.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/pull_request_template.md",
        "docs/domain-rules.md",
    ]

    missing = [name for name in required if not (root_dir / name).is_file()]

    assert missing == []


@pytest.mark.req("SC-6")
def test_license_and_der_vet_attribution():
    """
    FR-1101, SC-6: 라이선스는 MIT 또는 BSD 3-Clause를 따르며,
    DER-VET 코드를 사용하지 않았다는 사실을 명기해야 합니다.
    """
    root_dir = Path(__file__).parent.parent.parent

    readme_path = root_dir / "README.md"
    assert readme_path.exists(), "README.md 파일이 존재해야 합니다."
    readme_content = readme_path.read_text(encoding="utf-8")

    assert "DER-VET 코드" in readme_content, (
        "README에 DER-VET 설계 참조 및 미사용 사실이 명기되어야 합니다.")
    assert "MIT" in readme_content or "BSD" in readme_content, "라이선스 명칭이 명기되어야 합니다."

    license_path = root_dir / "LICENSE"
    assert license_path.exists(), "LICENSE 파일이 존재해야 합니다."
    license_content = license_path.read_text(encoding="utf-8")
    assert ("MIT License" in license_content
            or "BSD 3-Clause" in license_content), (
        "MIT 또는 BSD 3-Clause 라이선스여야 합니다.")
