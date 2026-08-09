"""감사 로그 테이블·저장 계층 — 작업 3.7 / SC-4.

**이 모듈은 테이블과 저장 통로만 제공한다.** *무엇을* 기록할지는
WP-11(app/계층, 14.0 작업) 이 결정한다 — 그 결정을 여기 두면 두 곳이 갈린다.

SC-4 가 요구하는 대상(로그인·시나리오/전제 CRUD·카탈로그 변경) 은 이 테이블의
행으로 표현되지만, **이 모듈은 그 매핑을 모른다.** 호출부(app) 가
`write_audit(session, action="scenario.create", ...)` 라고 넘겨주면 영속성은
그대로 담는다. SC-4 마커도 14.9 가 붙인다 — 여기 테스트에는 req 마커를 달지
않는다.

왜 `before_json`·`after_json` 두 컬럼인가 — 변경 전후 상태를 한 행에 담아 diff
를 재현 가능하게 한다. 어느 한 쪽만 두면 UPDATE 이벤트에서 "무엇이 바뀌었나" 가
사라진다.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from infra.database import Base
from infra.orm.base import PkMixin, TimestampMixin


class AuditLog(Base, PkMixin, TimestampMixin):
    """감사 로그 행 — §9 SC-4.

    `entity_type`·`entity_id` 로 대상을, `action` 으로 행위 유형을 나타낸다.
    행위 유형의 enum 은 영속성이 강제하지 않는다 — app 계층이 14.0 에서
    정의한다. 그래서 CHECK 제약을 두지 않는다 (여기서 제약을 두면 app 의
    새 액션이 영속성 변경을 요구하게 된다).
    """

    __tablename__ = "audit_logs"

    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    # SC-3: 개인정보 최소화. 부하 데이터 자체는 별도 Parquet 에 있고,
    # 감사 로그에는 행위의 메타데이터만 담는다 — 사용자 식별은 actor_user_id
    # 경로로만.
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


def write_audit(
    session: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    before_json: str | None = None,
    after_json: str | None = None,
    note: str | None = None,
) -> AuditLog:
    """감사 로그를 한 행 쓴다. **저장 통로만 — 검사·필터링 없음.**

    이 함수는 **무엇을 기록할지 결정하지 않는다.** 호출부가 모든 판단을 끝낸
    뒤 "이것을 기록하라" 고 넘기는 단순 쓰기 통로다. 그래서 어떤 `action` 이든
    거부 없이 담는다 — 액션의 허용 여부는 14.0(app) 이 정한다.

    `Session` 을 직접 받는 이유: 영속성 계층이 자기 트랜잭션을 열면 호출부의
    트랜잭션과 분리되어, 부모가 rollback 했을 때 감사 로그만 남는 기현상이
    생긴다. 같은 세션에서 쓰고 부모의 commit/rollback 에 따라간다.
    """
    record = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=before_json,
        after_json=after_json,
        note=note,
    )
    session.add(record)
    session.flush()  # id 할당을 위해. commit 은 호출부가.
    return record
