"""Alembic 환경 — WP-13.

`infra.orm` 과 `infra.audit` 을 import 하여 `Base.metadata` 에 모든 모델을
등록한다. Alembic 은 이 메타데이터를 target 으로 삼아 diff·DDL 을 낸다.

`render_as_batch=True` — SQLite 는 ALTER TABLE 에 제약이 많다. batch mode 는
새 테이블을 만들고 데이터를 옮긴 뒤 이름을 바꿔, ALTER 가 안 되는 변경도
수용한다. 무료 티어(NFR-504) 운영 환경이 SQLite 이므로 이 설정은 선택이 아니다.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# alembic.ini 가 infra/migrations/ 안에 있으므로, 프로젝트 루트를 sys.path 에
# 추가하지 않으면 `infra.database` 를 import 할 수 없다. alembic 은 스크립트
# 디렉터리(import 에 쓰이는 cwd 후보)를 자동으로 path 에 넣지 않는다.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import infra.audit  # noqa: E402  — 감사로그 테이블도 함께
import infra.orm  # noqa: E402,F401  — 메타데이터 등록 부작용
from infra.database import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 환경변수로 URL 을 덮어쓸 수 있게 한다 — 커밋된 기본 URL(`sqlite:///der.db`)
# 대신 운영·테스트가 각자 경로를 넘긴다.
_env_url = os.environ.get("DER_DB_URL")
if _env_url:
    config.set_main_option("sqlalchemy.url", _env_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """오프라인 모드 — DDL 을 SQL 문자열로 출력 (DB 연결 없음)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_name="sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """온라인 모드 — 실제 DB 연결에서 마이그레이션 실행."""
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(
        section if section is not None else {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
