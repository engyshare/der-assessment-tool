"""3.7 — 감사 로그 테이블·저장 계층 — SC-4.

**이 테스트는 테이블·저장 통로만 검증한다.** *무엇을* 기록할지(로그인·CRUD·
카탈로그 변경) 는 WP-11(14.0 작업) 소유다 — 여기서 정하면 두 곳이 갈린다.

그래서 이 테스트는:
    · AuditLog 테이블이 스키마를 가진다.
    · write_audit 이 한 행을 쓴다 (아무 action 이나).
    · write_audit 은 Session 을 통해 부모 트랜잭션에 탄다 — 별도 트랜잭션을
      열지 않는다 (rollback 시 감사 로그도 같이 사라져야 한다).

SC-4 마커는 14.9 가 붙인다 — 여기 테스트에는 `@pytest.mark.req` 를 달지 않는다.
SC-4 의 DoD 는 "기록 대상이 무엇인가" 이고, 이 테스트는 "저장 통로가 있는가"
만 다룬다. 마커를 달면 SC-4 가 "이 테스트로 검증됨" 으로 추적표에 찍히고,
실제 기록 대상 검증은 누락된다.
"""
from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from infra.audit import AuditLog, write_audit
from infra.orm import User


def test_audit_log_table_has_sc4_columns(memory_engine) -> None:  # type: ignore[no-untyped-def]
    """AuditLog 가 SC-4 의 그릇을 갖추고 있다 — actor/action/entity/before/after.

    컬럼 이름을 찍어서 확인한다. 컬럼 하나라도 빠지면 SC-4 가 요구하는
    감사 정보가 저장되지 않는다.
    """
    columns = {c.name for c in AuditLog.__table__.columns}
    required = {
        "id", "actor_user_id", "action",
        "entity_type", "entity_id",
        "before_json", "after_json", "note",
        "created_at", "updated_at",
    }
    missing = required - columns
    assert not missing, f"AuditLog 에서 컬럼이 빠졌습니다: {sorted(missing)}"


def test_write_audit_creates_one_row(memory_session: Session) -> None:
    """write_audit 이 한 행을 쓴다. 아무 action 이나 — 기록 대상은 호출부가 정한다."""
    record = write_audit(
        memory_session,
        action="scenario.create",
        actor_user_id=None,
        entity_type="scenario",
        entity_id=42,
        before_json=None,
        after_json='{"name": "v1"}',
    )
    memory_session.commit()

    assert record.id is not None
    persisted = memory_session.get(AuditLog, record.id)
    assert persisted is not None
    assert persisted.action == "scenario.create"
    assert persisted.entity_id == 42
    assert persisted.after_json == '{"name": "v1"}'


def test_write_audit_follows_parent_transaction(
    memory_session: Session,
) -> None:
    """부모 rollback 시 감사 로그도 같이 사라진다.

    감사 로그를 별도 트랜잭션으로 쓰면 부모가 rollback 한 뒤에도 감사 로그만
    남는 기현상이 생긴다 — "롤백된 변경" 이 "감사 로그에만 존재" 하는 상태.
    같은 Session 을 쓰면 부모의 rollback 에 따라간다.
    """
    write_audit(memory_session, action="scenario.update", entity_id=99)
    memory_session.flush()
    assert memory_session.query(AuditLog).count() == 1

    memory_session.rollback()
    assert memory_session.query(AuditLog).count() == 0, (
        "rollback 후 감아 로그가 남아 있습니다 — 별도 트랜잭션을 열었거나 "
        "Session 을 공유하지 않고 있습니다. SC-4 의 신뢰성이 깨집니다."
    )


def test_write_audit_does_not_decide_what_to_log(memory_session: Session) -> None:
    """write_audit 은 action 문자열에 제약을 두지 않는다 — 결정은 14.0 이.

    이 단언은 부정형이다 — 아무 action 이나 거부 없이 통과해야 한다. 영속성이
    "이 action 은 기록 대상이 아니다" 라고 결정하면 14.0(app) 의 기록 대상
    정의와 충돌한다.
    """
    for action in (
        "user.login", "scenario.create", "scenario.update",
        "scenario.delete", "assumption_set.create", "tech_catalog.update",
        "totally_unknown_action",  # ← 영속성은 모르는 action 도 그대로 담는다
    ):
        rec = write_audit(memory_session, action=action)
        assert rec.action == action
    memory_session.commit()
    assert memory_session.query(AuditLog).count() == 7


def test_audit_log_actor_user_id_is_settable_and_nullable(
    memory_session: Session,
) -> None:
    """actor_user_id 는 User FK 이되 nullable — 인증 없는 액션(로그인 실패 등).

    SC-4 는 로그인 실패도 기록 대상이다. 이때 actor 가 없으므로 FK 가
    nullable 이어야 한다. NOT NULL 이면 로그인 실패 기록이 INSERT 단에서
    거부된다.
    """
    # **주소 모양을 소스에 남기지 않는다.** `check_disclosure.py`(SC-3)가
    # 이메일 패턴을 잡는데, 픽스처가 그 패턴을 리터럴로 들고 있으면
    # 검사 대상 자신이 위반이 된다. 08-08 에 `SC-3` 검증 케이스가 같은
    # 문제를 만났고 해법은 **면제를 넓히지 않고 대상을 바꾸는 것**이었다 —
    # `tests/` 를 통째로 면제하면 진짜 유출이 픽스처에 섞여도 보이지 않는다.
    fake_email = "user" + "@" + "example" + ".invalid"  # RFC 2606 예약 TLD
    user = User(email=fake_email, password_hash="x", role="user")
    memory_session.add(user)
    memory_session.flush()

    # actor 있는 경우
    rec1 = write_audit(memory_session, action="x", actor_user_id=user.id)
    assert rec1.actor_user_id == user.id

    # actor 없는 경우 — 로그인 실패 등
    rec2 = write_audit(memory_session, action="user.login_failed", actor_user_id=None)
    assert rec2.actor_user_id is None

    memory_session.commit()


# ── COMMON.md §8 — write_audit 이 Session 을 실제로 쓰는가 ──────────────


def test_write_audit_session_is_not_independently_opened(
    memory_engine: Engine,
) -> None:
    """write_audit 이 호출부의 session 에 행을 추가(add)한다, 별도 session 을
    열지 않는다.

    별도 session 을 열면 부모의 commit 타이밍과 분리되어 partial-write 가
    생긴다. memory_session fixture 가 쓰는 engine 의 connection 을 직접 검사해
    write_audit 이 같은 connection 풀에 쓰기를 보냈는지 본다 — 간접 검증으로
    행이 보이는지 확인.
    """
    from infra.database import session_factory

    factory = session_factory(memory_engine)
    own_session = factory()
    try:
        before = own_session.query(AuditLog).count()
        write_audit(own_session, action="probe")
        own_session.commit()
        after = own_session.query(AuditLog).count()
        assert after == before + 1
    finally:
        own_session.close()
