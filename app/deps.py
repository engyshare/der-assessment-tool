"""FastAPI 의존성 주입 — DB 세션 팩토리."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import infra.orm  # noqa: F401 — ORM 모델 메타데이터 등록
from infra.database import Base, make_engine, session_factory

_engine = make_engine("sqlite://")
_engine.pool = StaticPool(_engine.pool._creator)
Base.metadata.create_all(_engine)
_session_factory = session_factory(_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 라우터 요청 세션 주입."""
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()
