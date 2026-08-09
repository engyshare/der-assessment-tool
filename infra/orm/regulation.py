"""제도 프로파일·편익 배타 규칙 — §7.2.

이 엔티티들은 WP-3(core/regulation) 이 계산에 쓰는 값을 담는 저장소다.
영속성은 스키마와 영속성 계층만 제공한다 — 배타 규칙의 위반 검사(DV-12)·
지불 주체 필수(DV-13) 는 core.regulation 소유.
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from infra.database import Base
from infra.orm.base import PkMixin, TimestampMixin


class RegulationProfile(Base, PkMixin, TimestampMixin):
    """제도 파라미터 묶음(버전) — §7.2.

    제도는 시간에 따라 바뀐다 — RPS 비율·누진 구간이 법개정으로 변한다.
    valid_from·valid_to 로 분석연도와 정합(DV-6) 여부를 검사한다.
    """

    __tablename__ = "regulation_profiles"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulation_profiles.id", ondelete="SET NULL")
    )
    valid_from: Mapped[str | None] = mapped_column(String(32))
    valid_to: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)


class RegulationItem(Base, PkMixin):
    """제도 개별 항목 — §7.2. FR-504 확장성.

    RegulationProfile 의 자식 행. key-value JSON 구조라 새 제도 항목이 생겨도
    스키마 변경 없이 행 추가로 수용한다.
    """

    __tablename__ = "regulation_items"

    regulation_profile_id: Mapped[int] = mapped_column(
        ForeignKey("regulation_profiles.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(32))
    scope: Mapped[str | None] = mapped_column(String(64))
    valid_from: Mapped[str | None] = mapped_column(String(32))
    valid_to: Mapped[str | None] = mapped_column(String(32))
    reference_url: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[str | None] = mapped_column(String(32))


class BenefitExclusionRule(Base, PkMixin, TimestampMixin):
    """편익 배타 규칙 — §7.2. FR-402.

    동일 물리 현상을 두 항목으로 세지 않기 위한 선언적 테이블.
    exclusion_type A/B/C/D 는 core.regulation·core.constraint 가 정의한다 —
    영속성은 질서 있게 저장만 한다.
    """

    __tablename__ = "benefit_exclusion_rules"
    __table_args__ = (
        CheckConstraint(
            "exclusion_type IN ('A', 'B', 'C', 'D')", name="exclusion_type_enum"
        ),
    )

    benefit_a: Mapped[str] = mapped_column(String(64), nullable=False)
    benefit_b: Mapped[str] = mapped_column(String(64), nullable=False)
    exclusion_type: Mapped[str] = mapped_column(String(8), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    regulation_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("regulation_profiles.id", ondelete="SET NULL")
    )


# TimeSeriesDataset 은 Parquet 저장소(3.4) 와 짝을 이룬다. storage_path 가
# Parquet 파일 경로, checksum 이 그 파일의 무결성 지표. 컬럼을 두지 않고
# 별도 datasets 테이블에 두는 이유 — Parquet 파일 자체는 DB 트랜잭션 밖에
# 있고, checksum 일치 여부가 시계열 저장 루틴(tsstore.py) 의 책임이기 때문이다.
class TimeSeriesDataset(Base, PkMixin, TimestampMixin):
    """시계열 데이터 — §7.2. INT-1 (CSV 업로드)."""

    __tablename__ = "time_series_datasets"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('load', 'pv', 'smp', 'temp')", name="ts_kind_enum"
        ),
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    resolution: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
    storage_path: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(128))
    stats_json: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(String(16))
