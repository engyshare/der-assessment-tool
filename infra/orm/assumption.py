"""전제 엔티티 — AssumptionSet, AssumptionItem. §7.2.

FR-601 의 본체. v0.5 는 AssumptionItem 에 2 컬럼을 추가했다(applicable_scope,
derivation_method). 7종 부기 항목(FR-601-AC5.*)이 모두 컬럼으로 존재해야 한다 —
이것은 COMMON.md §4(AC 추정 금지)의 확인 대상이다.

스키마가 7종 전부를 컬럼으로 들고 있으면 AC5.* 인용이 비어 있을 때 컬럼 자체가
누락되는 것을 감지할 수 있다. 반대로 단일 value_json 에 전부 묻어두면 빠진 부기
항목이 화면상 정상으로 보인다.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infra.database import Base
from infra.orm.base import PkMixin, TimestampMixin


class AssumptionSet(Base, PkMixin, TimestampMixin):
    """분석 전제 집합 (1급 객체) — §7.2. FR-202 전제 동일성의 단위."""

    __tablename__ = "assumption_sets"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 버전은 문자열이다 — SemVer 를 강제하지 않는다. FR-601-AC8 의 diff 뷰는
    # 두 버전 문자열을 비교하는 것이지 정렬이 아니다.
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    # 자기참조 — 부모 버전. 버전 이력 트리.
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("assumption_sets.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)


class AssumptionItem(Base, PkMixin):
    """전제 개별 항목 — §7.2.

    FR-601-AC5.* 7종 부기 항목 컬럼:
        value_unit           → value_json + unit
        base_year            → base_year
        applicable_scope     → applicable_scope      (v0.5 추가)
        derivation_method    → derivation_method     (v0.5 추가)
        source               → source
        verified_at          → verified_at
        confidence           → confidence

    confidence 는 v0.5 어휘 정정으로 `확정/추정/가정` 세 가지만 허용한다 —
    `미확인` 은 축 1 전용이며 DB 에 들어가면 안 된다. CHECK 제약으로 고정한다.
    """

    __tablename__ = "assumption_items"
    __table_args__ = (
        # value_type — scalar / ref 두 유형 (FR-601-AC6).
        CheckConstraint("value_type IN ('scalar', 'ref')", name="value_type_enum"),
        # v0.5 어휘 정정 — `미확인` 거부. CHECK 가 있으면 잘못된 값이 DB 에
        # 들어가 스키마로는 잡히지 않는 사고를 막는다.
        CheckConstraint(
            "confidence IN ('확정', '추정', '가정')", name="confidence_axis2"
        ),
    )

    assumption_set_id: Mapped[int] = mapped_column(
        ForeignKey("assumption_sets.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # 값은 JSON 문자열로 저장. 단일 값이 아니라 표·벡터일 수 있으므로.
    value_json: Mapped[str | None] = mapped_column(Text)
    # value_type=ref 일 때 가리키는 엔티티.
    ref_entity: Mapped[str | None] = mapped_column(String(64))
    ref_id: Mapped[int | None] = mapped_column(Integer)
    unit: Mapped[str | None] = mapped_column(String(32))

    # ── FR-601-AC5.* 부기 7종 ─────────────────────────────────────
    # 각 컬럼이 어느 AC 에 대응하는지 이름에 드러나게 한다. 스키마 검사
    # (test_assumption_item_metadata_completeness) 가 7종 전부를 컬럼으로
    # 요구한다 — 하나라도 빠지면 FR-601-AC4 의 7종 보유 테스트가 소프트해진다.
    base_year: Mapped[int | None] = mapped_column(Integer)        # AC5.base_year
    # v0.5 추가: 적용 범위·조건. 같은 값이라도 대상이 다르면 다른 항목이다.
    applicable_scope: Mapped[str | None] = mapped_column(Text)    # AC5.applicable_scope
    # v0.5 추가: 산출 방법·표본. 추정치/실측치 구분.
    derivation_method: Mapped[str | None] = mapped_column(Text)   # AC5.derivation_method
    source: Mapped[str | None] = mapped_column(Text)              # AC5.source
    verified_at: Mapped[str | None] = mapped_column(String(32))   # AC5.verified_at
    confidence: Mapped[str | None] = mapped_column(String(16))    # AC5.confidence
