"""식별 엔티티 — User, Project. §7.2.

Phase 1 영속성은 모델을 정의할 뿐, 인증 로직을 구현하지 않는다. password_hash
는 평문이 아니라 해시를 저장하는 자리표시자다 — 실제 해시 알고리즘 선택은
WP-11(app/계층) 소유다.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infra.database import Base
from infra.orm.base import PkMixin, TimestampMixin


class User(Base, PkMixin, TimestampMixin):
    """사용자 — §7.2."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    # SC-1: 평문 비밀번호 저장 금지. 영속성 계층은 자리만 만든다.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="user")


class Project(Base, PkMixin, TimestampMixin):
    """분석 프로젝트 — §7.2."""

    __tablename__ = "projects"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # tags 를 별도 테이블로 정규화하지 않는다 — 단순 string 집합이므로 CSV 로.
    tags: Mapped[str | None] = mapped_column(Text)
