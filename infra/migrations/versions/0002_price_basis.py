"""assumption_sets.price_basis 신설 — DV-7 / R31.

`DV-7` 은 실질/명목 구분을 **`AssumptionSet` 수준에서 1회 선언**하라고 요구하는데
그 자리가 스키마에 없었다. 계약(`core/contracts/assumptions.py::PriceBasis`)에
기본값을 두지 않았으므로 저장 층도 두지 않는다 — 두면 계약의 강제가 왕복
(save→load)에서 사라지고, 「선언하지 않았다」가 「명목이라고 선언했다」와
구별되지 않는다.

**기존 행에는 `명목` 을 채운다.** `docs/assumptions.yaml` 이 R31 에 `명목` 을
선언했고 그 대장이 지금까지 유일한 전제 원본이므로, 이미 저장된 집합의 금액도
명목이다 — 추측이 아니라 실제 원본을 읽은 결과다.

`render_as_batch` 는 `env.py` 가 이미 켜 둔다 (SQLite ALTER 제약).

Revision ID: 0002_price_basis
Revises: 0001_initial
Create Date: 2026-08-14
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_price_basis"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 기존 행을 채우는 값. **컬럼 기본값이 아니다** — 이 마이그레이션 안에서만
#: 쓰이고, 이후에 삽입되는 행은 선언을 반드시 실어야 한다.
_BACKFILL = "명목"


def upgrade() -> None:
    # ① nullable 로 더한다 — 기존 행이 있으면 NOT NULL 이 바로 붙지 않는다
    with op.batch_alter_table("assumption_sets") as batch:
        batch.add_column(sa.Column("price_basis", sa.String(8), nullable=True))

    # ② 기존 행을 채운다
    op.execute(
        sa.text(
            "UPDATE assumption_sets SET price_basis = :basis "
            "WHERE price_basis IS NULL"
        ).bindparams(basis=_BACKFILL)
    )

    # ③ NOT NULL + CHECK 로 조인다. **여기서 조이지 않으면 이 마이그레이션은
    #    「컬럼을 만들었다」로 끝나고 선언은 여전히 생략 가능하다.**
    with op.batch_alter_table("assumption_sets") as batch:
        batch.alter_column("price_basis", existing_type=sa.String(8), nullable=False)
        batch.create_check_constraint(
            "price_basis_enum", "price_basis IN ('실질', '명목')"
        )


def downgrade() -> None:
    with op.batch_alter_table("assumption_sets") as batch:
        batch.drop_constraint("price_basis_enum", type_="check")
        batch.drop_column("price_basis")
