"""실행 이력·케이스 결과·프로포마 — §7.2.

Run 이 시작되면 Run·CaseResult·ProformaLine·ResultMetric·InfluenceRank 가 순서대로
채워진다. 영속성은 이 행렬을 효율적으로 저장·조회하는 역할만 한다.

주의 — `value_krw` 는 `money()` 로 Decimal 원 단위 정수를 담는다 (NFR-103).
`ResultMetric.value` 는 지표값으로 비율·금액·물리량이 섞이므로 float Numeric 으로
둔다 — 화면·단위 라벨이 value 와 함께 가지 않으면 숫자만으로 단위가 드러나지
않는다. ResultMetric.unit 이 그 라벨이다.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from infra.database import Base
from infra.orm.base import PkMixin, TimestampMixin, money


class Run(Base, PkMixin, TimestampMixin):
    """실행 이력 — §7.2. FR-1103 (동일 매니페스트 재실행 = 비트 동일 결과).

    manifest_json 이 재실행의 열쇠다 — 동일 입력을 동일 엔진으로 돌리면 같은
    결과가 나와야 한다. 영속성은 manifest 를 그대로 담고, 정합은 core.engine 이
    검사한다.
    """

    __tablename__ = "runs"
    __table_args__ = (
        # status — started/done/failed/cancelled. core.engine 이 정의하는
        # 상태 기계와 1:1 로 맞춘다. 영속성은 그릇만 제공한다.
    )

    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    case_grid_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_grids.id", ondelete="SET NULL")
    )
    engine: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[str | None] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(16))
    manifest_json: Mapped[str | None] = mapped_column(Text)


class CaseResult(Base, PkMixin):
    """케이스별 결과 — §7.2."""

    __tablename__ = "case_results"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    case_index: Mapped[int] = mapped_column(Integer, nullable=False)
    case_values_json: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[str | None] = mapped_column(Text)


class ProformaLine(Base, PkMixin):
    """프로포마 행 — §7.2. FR-701-AC1.

    value_krw 는 **정수 원(Money)** 이다 (NFR-103). float 로 저장하면 20년 합계와
    항목별 합계가 1~2원 어긋나고, 그 어긋남은 화면상 정상으로 보인다.
    """

    __tablename__ = "proforma_lines"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    case_index: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    der_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("der_instances.id", ondelete="SET NULL")
    )
    value_krw: Mapped[Decimal | None] = mapped_column(money())


class ResultMetric(Base, PkMixin):
    """결과 지표 — §7.2. NPV·IRR·LCOE·회수기간.

    value 가 float 인 이유 — IRR·LCOE 는 비율·단가 혼합 지표다. 단위가
    `unit` 컬럼에 별도로 있어야 숫자만 보고 단위를 추측하지 않는다.
    **금액이 아닌 이유**: NPV 자체는 금액이지만, 동일 컬럼에 IRR(비율)·
    LCOE(단가) 가 섞여 들어오므로 컬럼 타입을 money() Decimal 로 단일화할 수
    없다 — 단위 라벨(unit) 없이 숫자만으로는 단위가 드러나지 않는다.
    금액성 지표는 value 가 아닌 proforma_lines.value_krw (Decimal) 에서
    행 단위로 합산된다.
    """

    __tablename__ = "result_metrics"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    case_index: Mapped[int] = mapped_column(Integer, nullable=False)
    perspective: Mapped[str] = mapped_column(String(32), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float | None] = mapped_column()
    unit: Mapped[str | None] = mapped_column(String(32))


class InfluenceRank(Base, PkMixin):
    """인자별 영향도 — §7.2. FR-1002.

    민감도 분석 결과. `flips_conclusion` 은 이 인자가 결론(NPV 부호 등)을
    뒤집을 수 있는지 — 가장 위험한 가정(FR-1002-AC1) 을 찾는 열쇠.

    delta_low/delta_high 가 float 인 이유 — ResultMetric.value 와 같은 단위를
    가지는 지표값의 변화폭이다. 비율 지표(IRR) 의 델타는 비율이고, 금액
    지표(NPV) 의 델타는 금액이다. 단일 컬럼에 섞이므로 money() Decimal 이
    아니라 float 다. 금액 정합은 proforma_lines 합산 경로에서 보장된다.
    """

    __tablename__ = "influence_ranks"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    assumption_key: Mapped[str] = mapped_column(String(128), nullable=False)
    delta_low: Mapped[float | None] = mapped_column()
    delta_high: Mapped[float | None] = mapped_column()
    rank: Mapped[int | None] = mapped_column(Integer)
    flips_conclusion: Mapped[bool | None] = mapped_column()
