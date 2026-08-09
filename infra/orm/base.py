"""ORM 공통 믹스인 — 작업 3.2 / §7.2.

`id`·`created_at`·`updated_at` 같은 공통 컬럼을 모델마다 반복하면 컬럼 누락이
조용히 일어난다 — `id` 를 깜빡한 모델이 `__table__` 생성 시에만 에러로 드러나므로.

믹스인으로 올리는 대신, 금액 컬럼의 공통 타입을 여기서 정의한다 (NFR-103):
`money()` 가 항상 `Numeric(asdecimal=True)` 를 돌려주게 하여 `float` 가
금액 자리에 끼어드는 것을 막는다.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column


def money() -> Numeric[Decimal]:
    """금액 컬럼의 표준 타입. Decimal 원 단위 정수 (NFR-103).

    `Numeric(precision=None, scale=0, asdecimal=True)` — 정밀도 무한, 소수점
    자리 0, 파이썬 Decimal 로 읽는다.

    `scale=0` 이지만 입력은 Decimal 이면 그대로 들어간다. SQLite 는 동적 타입이라
    INTEGER 로 저장하고 Decimal 로 읽어온다 — 경계에서 `core.contracts.units.to_won`
    이 원 단위 정수를 보장하므로 영속성 계층은 그 값을 그대로 담는다.

    `Integer` 로 쓰지 않는 이유: SQLAlchemy `Integer` 는 Python int 로 읽고,
    Decimal 과 호환되지 않는다. CBA 계층(Money) 과의 변환 비용이 매 컬럼마다
    발생하며, 그 변환 지점이 바로 미세 오차가 새는 곳이다.
    """
    return Numeric(precision=None, scale=0, asdecimal=True)


class PkMixin:
    """정수 기본키. 모든 테이블이 단일 정수 PK 를 쓴다 (§7.2)."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TimestampMixin:
    """생성·수정 시각. 감사·추적용. nullable 하게 둬 마이그레이션 부담을 줄인다."""

    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
