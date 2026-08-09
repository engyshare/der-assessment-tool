from pathlib import Path

import pytest


@pytest.mark.req("SC-3")
def test_privacy_procedure_document_exists_and_valid() -> None:
    """
    SC-3 개인정보 처리 절차 수립 검증.
    절차 문서(docs/privacy-procedure.md)가 존재하고,
    반입 전 차단 절차와 필수 요건(식별 정보 제거 규칙, 익명 집계 단위,
    반입 시점 검증 절차)을 포함하는지 확인한다.
    """
    doc_path = Path(__file__).parent.parent.parent / "docs" / "privacy-procedure.md"
    assert doc_path.exists(), "개인정보 처리 절차 문서가 존재해야 한다."

    content = doc_path.read_text(encoding="utf-8")

    # 필수 절 확인
    assert "식별 정보 제거 규칙" in content
    assert "익명 집계 단위" in content
    assert "데이터 반입 시점 검증 절차" in content

    # 반입 전 차단 여부 명시 확인
    assert "반입 전 차단" in content or "저장소 외부 격리 환경" in content or "원천 차단" in content
