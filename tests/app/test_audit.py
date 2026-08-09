"""14.9 — 감사 로그 기록 대상 (SC-4).

``infra.audit.write_audit`` 통로를 쓴다. **저장 계층은 WP-13 소유** — 다시 만들지
않는다. 여기서는 «무엇을 기록할지» 와 «개인정보가 안 들어가는지» 를 검증한다.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.audit import AuditAction, record
from app.audit.recorder import _PII_PATTERNS


def _mock_session() -> MagicMock:
    """``Session`` 목 — ``write_audit`` 이 ``session.add`` + ``flush`` 를 쓴다."""
    session = MagicMock()
    return session


@pytest.mark.req("SC-4")
def test_record_login_success_calls_write_audit() -> None:
    """로그인 성공 기록 — ``write_audit`` 이 호출되는지."""
    session = _mock_session()
    record(
        session,
        action=AuditAction.LOGIN_SUCCESS,
        actor_user_id=1,
        entity_type="user",
        entity_id=1,
    )
    # write_audit 이 session.add + flush 를 호출 — 목이 add 를 잡는다
    session.add.assert_called_once()
    session.flush.assert_called_once()


def test_record_scenario_crud_actions() -> None:
    """시나리오 CRUD 전건이 기록 대상 — enum 으로 강제."""
    session = _mock_session()
    for action in (
        AuditAction.SCENARIO_CREATE,
        AuditAction.SCENARIO_UPDATE,
        AuditAction.SCENARIO_DELETE,
    ):
        record(session, action=action, actor_user_id=1, entity_type="scenario", entity_id=1)
    assert session.add.call_count == 3


def test_record_assumption_crud_actions() -> None:
    """전제 CRUD — SC-4 기록 대상."""
    session = _mock_session()
    record(session, action=AuditAction.ASSUMPTION_CREATE, actor_user_id=1)
    record(session, action=AuditAction.ASSUMPTION_UPDATE, actor_user_id=1)
    record(session, action=AuditAction.ASSUMPTION_DELETE, actor_user_id=1)
    assert session.add.call_count == 3


def test_record_catalog_change() -> None:
    """카탈로그 변경(관리자) — SC-4 기록 대상."""
    session = _mock_session()
    record(session, action=AuditAction.CATALOG_UPDATE, actor_user_id=1, entity_type="catalog")
    session.add.assert_called_once()


def test_pii_in_payload_rejected() -> None:
    """SC-3 — 감사 로그 before/after_json 에 가구 식별정보 키가 있으면 예외.

    감사 로그이 SC-3 의 우회로가 되는 것을 막는다.
    """
    session = _mock_session()
    with pytest.raises(ValueError, match="가구 식별정보"):
        record(
            session,
            action=AuditAction.SCENARIO_UPDATE,
            before_json='{"resident_name": "홍길동"}',
        )


def test_pii_in_after_payload_rejected() -> None:
    """after_json 도 검사 — 어느 쪽이든 PII 면 예외."""
    session = _mock_session()
    with pytest.raises(ValueError, match="가구 식별정보"):
        record(
            session,
            action=AuditAction.SCENARIO_UPDATE,
            after_json='{"household_address": "서울시 강남구"}',
        )


def test_action_enum_covers_sc4_targets() -> None:
    """SC-4 기록 대상 4종(로그인·시나리오 CRUD·전제 CRUD·카탈로그) 이 enum 에 있다."""
    actions = {a.value for a in AuditAction}
    assert "auth.login.success" in actions
    assert "auth.login.failure" in actions
    assert "scenario.create" in actions
    assert "assumption.create" in actions
    assert "catalog.update" in actions


def test_pii_patterns_cover_identifying_keys() -> None:
    """PII 패턴이 가구 식별 키를 충분히 덮는지."""
    # SC-3 이 «가구 개별 식별정보» 를 요구 — 이름·주소·전화·계량기 번호
    for key in ("resident_name", "household_address", "resident_phone", "meter_serial"):
        assert key in _PII_PATTERNS, f"PII 패턴이 {key!r} 를 안 잡는다"
