"""FastAPI 의존성 주입 — DB 세션 팩토리."""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import infra.orm  # noqa: F401 — ORM 모델 메타데이터 등록
from infra.database import Base, make_engine, session_factory

#: 환경변수가 없을 때의 DB — 인메모리다. 기존 테스트가 이것을 전제한다.
DEFAULT_DB_URL = "sqlite://"

#: 마이그레이션과 **같은 이름**을 쓴다 (`infra/migrations/env.py`). 이름이
#: 갈리면 마이그레이션과 앱이 서로 다른 DB 를 보고, 그 어긋남은 «테이블이
#: 없다» 가 아니라 «비어 있다» 로 나타나 원인이 드러나지 않는다.
DB_URL_ENV = "DER_DB_URL"


def resolve_db_url() -> str:
    """SC-5 — 앱 런타임 DB 경로는 환경변수에서 온다.

    **함수로 빼 둔 이유.** 모듈 수준에서 `os.environ` 을 직접 읽으면 검사가
    「소스에 그 이름이 있는가」밖에 볼 수 없다. 실제로 R20 에 그런 검사가
    들어왔고, **환경변수를 읽고 그 값을 버리도록 고쳐도 통과했다.**
    순수 함수로 두면 「무엇을 돌려주는가」를 부작용 없이 붙들 수 있다.

    빈 문자열은 «설정하지 않음» 으로 본다 — `DER_DB_URL=` 로 비워 둔 것을
    빈 URL 로 넘기면 엔진 생성이 알 수 없는 자리에서 깨진다.
    """
    return os.environ.get(DB_URL_ENV) or DEFAULT_DB_URL


_engine = make_engine(resolve_db_url())
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
