"""영속성 계층의 엔진·세션·베이스 — 작업 3.2 / spec §10.3.

SQLAlchemy 2.0 declarative 를 쓴다. 이 모듈은 영속성 계층에서 **유일한**
`create_engine` 호출 지점이다.

왜 한 곳인가
-----------
백업·복원(NFR-502)·Litestream 복제(NFR-504)는 모두 "DB 파일 경로" 에 의존한다.
`create_engine` 호출이 흩어져 있으면:

    · 백업이 한 엔진의 파일만 복사하고 다른 엔진의 파일을 놓친다.
    · 복제 대상 경로가 호출부마다 다르면 restore 시 어느 파일이 진본인지 갈린다.

`make_engine(url)` 이 그 통로다. `infra` 어디서든 엔진이 필요하면 이 함수를 부른다.

이 모듈은 계산 구획을 전혀 import 하지 않는다 (NFR-208 — `infra-knows-only-contracts`).
ORM 모델조차 여기서 import 하지 않는다 — `Base.metadata` 를 노출하고,
`infra.orm` 패키지가 모델을 등록한다. 순환 import 를 끊기 위해서다.
"""
from __future__ import annotations

from types import MappingProxyType

from sqlalchemy import MetaData
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# 제약·인덱스 명명 규칙. Alembic 이 autogenerate 할 때 diff 가 이름 차이로
# 묻히지 않게 한다. 이 규칙을 바꾸면 마이그레이션 스크립트가 전부 갱신되어야
# 한다 — 이름은 계약이다.
#
# `MappingProxyType` 으로 감싼 이유 (NFR-205): 모듈 수준 가변 dict 는
# DER-VET `Params.py` 가 겪은 함정이다. 읽기 전용으로 쓰고 있어도 다음 사람이
# 런타임에 한 항목을 바꾸면, 케이스 그리드 병렬 실행(FR-805)에서 한 케이스가
# 바꾼 이름 규칙이 다른 케이스의 마이그레이션 diff 에 조용히 묻힌다.
# 읽기 전용 뷰로 두면 변형 자체가 불가능해진다.
NAMING_CONVENTION = MappingProxyType({
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
})


class Base(DeclarativeBase):
    """모든 ORM 모델의 부모. 메타데이터에 명명 규칙을 입힌다."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(url: str, *, echo: bool = False) -> Engine:
    """영속성 계층 유일의 엔진 팩토리.

    SQLite 파일·메모리 URL 을 모두 받는다. SQLite 외의 백엔드는 Phase 1 범위
    밖이다 (§10.3 — SQLite + Litestream). 다른 백엔드가 필요해지면 이 함수가
    아니라 spec §10.3 을 먼저 고쳐야 한다.
    """
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        # FastAPI 등 스레드 기반 런타임에서 SQLite 의 기본 스레드 검사가
        # 작동하지 않게 한다. check_same_thread=False 는 SQLite 전용 인자이므로
        # 다른 백엔드에는 넘기지 않는다.
        connect_args["check_same_thread"] = False
    return create_engine(url, echo=echo, future=True, connect_args=connect_args)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    """세션 팩토리. `expire_on_commit=False` 로 둬 커밋 후에도 객체를 읽을 수
    있게 한다 — 영속성 계층의 객체는 커밋 직후 바로 UI·리포트로 흘러가므로."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
