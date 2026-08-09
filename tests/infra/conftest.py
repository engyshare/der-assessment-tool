"""tests/infra 공용 픽스처 — WP-13.

영속성 검증은 실제 파일 I/O·트랜잭션을 돌려야 하므로 in-memory SQLite 만으로는
부족하다. 두 종류의 엔진을 제공한다:

- `memory_engine`  — 스키마·모델 형상 검사. 빠르고 상태를 남기지 않는다.
- `tmp_db_url`     — 파일 기반 SQLite 경로. 백업·복원·마이그레이션처럼 파일을
                     직접 건드려야 하는 검증에 쓴다.

어느 쪽도 `core.engine`·`core.cba` 같은 계산 구획을 import 하지 않는다 (NFR-208).
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from infra.audit import AuditLog  # noqa: F401  — 감사로그 테이블도 함께 생성
from infra.database import Base, make_engine, session_factory

# 모든 ORM 모델을 메타데이터에 등록한다. import 자체가 부작용이다 —
# declarative Base 의 metadata 에 클래스가 등록되어 create_all 이 보게 된다.
# 사용하는 모델을 한 곳에서 다시 나열하면 누락을 눈으로 잡을 수 있다.
from infra.orm import (  # noqa: F401  — 메타데이터 등록이 목적
    AssumptionItem,
    AssumptionSet,
    BenefitExclusionRule,
    CaseGrid,
    CaseResult,
    CommonAsset,
    DERDatasetBinding,
    DERInstance,
    IncentiveScheme,
    InfluenceRank,
    ProformaLine,
    Project,
    RegulationItem,
    RegulationProfile,
    ResultMetric,
    Run,
    Scenario,
    ScenarioOverride,
    TariffTable,
    TechCatalog,
    TimeSeriesDataset,
    User,
)


@pytest.fixture
def memory_engine() -> Iterator[Engine]:
    """in-memory SQLite 엔진. 모든 테이블을 만든 채로 반환한다.

    in-memory SQLite 는 연결이 닫히면 사라진다. `yield` 후 dispose 하여
    다른 테스트로 누수되지 않게 한다.
    """
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def memory_session(memory_engine: Engine) -> Iterator[Session]:
    """in-memory 세션. 만료 시 커밋-보존(expire_on_commit=False)."""
    factory = session_factory(memory_engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """파일 기반 SQLite URL. 백업·복원·마이그레이션 검증에 쓴다.

    `sqlite:///:memory:` 로는 백업 대상 파일이 없다. 백업 명령이 파일을
    복사하는 경로를 검증하려면 진짜 파일이어야 한다.
    """
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def tmp_db_engine(tmp_db_url: str) -> Iterator[Engine]:
    engine = make_engine(tmp_db_url)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def tmp_session(tmp_db_engine: Engine) -> Iterator[Session]:
    factory: sessionmaker[Session] = session_factory(tmp_db_engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
