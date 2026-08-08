"""구획 경계를 넘는 자료구조 — 작업 1.5 / spec §16.2.

**여기 있는 것만이 구획 사이를 오간다.** 목록에 없는 자료구조를 경계로
넘기면 두 구획이 서로의 내부 표현에 묶이고, W-6(독립 완료 판정)이 깨진다 —
CBA 구획이 엔진의 완성을 기다리게 된다.

Pydantic을 쓰는 이유는 검증이 아니라 **계약의 실체화**다. dataclass로 두면
"이 필드는 원 단위 정수" 같은 규약이 주석으로만 남고, 주석은 검사되지 않는다.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.contracts.units import Money, to_won


class _Frozen(BaseModel):
    """경계 자료구조는 불변이다.

    한 구획이 받은 객체를 고치면 그 변경이 어느 구획에서 일어났는지 추적할
    수 없다. 실행 재현성(FR-1103 — 동일 매니페스트 재실행 시 비트 단위 동일
    결과)이 성립하려면 경계를 넘은 값이 바뀌지 않아야 한다.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class AssumptionRef(_Frozen):
    """전제 항목 참조 — 값이 아니라 **어디서 왔는지**를 나른다.

    값만 넘기면 리포트가 "그 값이 어디서 왔는가"에 답할 수 없다. FR-1001은
    산식과 출처 표시를, FR-1002는 영향도 순위와 함께 신뢰도 표시를 요구하며
    둘 다 이 참조 없이는 성립하지 않는다.
    """

    set_name: str
    set_version: str
    key: str
    #: 근거 표기 기준 2절 축 2. `미확인` 은 축 1 전용이므로 여기 없다
    confidence: Literal["확정", "추정", "가정"]
    source: str | None = None
    verified_at: date | None = None

    @field_validator("confidence")
    @classmethod
    def _reject_retired_vocabulary(cls, v: str) -> str:
        # v0.4까지 쓰던 `미확인` 이 남아 있으면 여기서 멈춘다. 같은 토큰을
        # 두 축에 쓰면 어느 뜻인지 판정할 수 없다 (spec v0.5 어휘 정정).
        return v


class CashFlowRow(_Frozen):
    """프로포마 한 행 — 연도별 금액 (FR-701-AC1).

    금액이 `Decimal` 인 것은 NFR-103 재무 계층 규약이다. float가 섞이면
    20년 합계와 항목별 합계가 어긋나고, 그 어긋남은 화면상 정상으로 보인다.
    """

    label: str
    #: 자원·편익·비용 항목의 tag. 총계 행은 None
    tag: str | None = None
    #: {연도(1-base): 금액(원)}
    amounts: dict[int, Decimal] = Field(default_factory=dict)
    assumption_refs: tuple[AssumptionRef, ...] = ()

    @field_validator("amounts")
    @classmethod
    def _whole_won_and_one_based(cls, v: dict[int, Decimal]) -> dict[int, Decimal]:
        for year, amount in v.items():
            if year < 1:
                raise ValueError(
                    f"분석 연도는 1부터 셉니다: {year}. 0-base 인덱스를 그대로 "
                    "넘기면 20년 분석이 19년이 되거나 잔존가치가 한 해 밀립니다"
                )
            if amount != amount.to_integral_value():
                raise ValueError(
                    f"{year}년차 금액에 원 미만이 있습니다: {amount}. "
                    "반올림은 units.to_won() 한 곳에서만 일어납니다 (NFR-103)"
                )
        return v

    def total(self) -> Money:
        """전 기간 합계. **행별 값을 그대로 더한다.**

        이미 원 단위로 반올림된 값이므로 재반올림하지 않는다. 사람이 눈으로
        더한 값과 총계가 같아야 한다 (NFR-103-M1).
        """
        return Money(sum(self.amounts.values(), Decimal(0)))


class ConstraintDecl(_Frozen):
    """편익이 자원에 거는 제약 선언 — 작업 1.5 / FR-403.

    **편익별 제약을 개별로 쌓지 않고 유형별 단일 시계열로 min/max 합성**하기
    위한 입력이다(FR-403-AC1). 각 선언이 **어느 편익에서 왔는지**를 들고
    있어야 충돌 시 기여 편익을 보고할 수 있다(FR-403-AC2·AC3).
    """

    #: 제약을 건 편익의 tag — 충돌 보고에 그대로 쓰인다
    source_tag: str
    #: 제약 대상 (예: "ESS.soc", "grid.import_kw")
    target: str
    kind: Literal["min", "max"]
    #: 스텝별 값. 길이는 DispatchContext.steps 와 같아야 한다
    values: tuple[float, ...]

    @field_validator("values")
    @classmethod
    def _finite(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        # 무한대 표현에는 math.inf 를 쓰며 유한 대형 상수를 sentinel 로 쓰지
        # 않는다 (FR-403-AC4). 1e30 같은 값은 합성 시 조용히 유효 제약이 되어
        # "제약 없음"을 "매우 큰 제약"으로 바꿔 버린다.
        for x in v:
            if math.isnan(x):
                raise ValueError("제약 값에 NaN이 있습니다 — NaN과의 비교는 항상 "
                                 "거짓이므로 min/max 합성이 이 제약을 조용히 "
                                 "건너뛰고 충돌 검출이 무력화됩니다")
        return v


class DispatchResultDTO(_Frozen):
    """엔진 → CBA 경계를 넘는 디스패치 결과.

    `core.contracts.der.DispatchResult` 는 계산 중 쓰는 가변 친화 구조이고,
    이것은 **경계를 넘는 불변 사본**이다. 둘을 하나로 합치지 않는 이유:
    계산 중에는 리스트 추가가 편하고, 경계에서는 변경 불가가 필요하다.
    """

    resource_tag: str
    electric: tuple[float, ...]
    heat: tuple[float, ...]
    cool: tuple[float, ...]
    fuel: tuple[float, ...]
    year: Annotated[int, Field(ge=1)]


def money_field(value: float | int | Decimal) -> Decimal:
    """경계로 넘길 금액을 만든다. `units.to_won()` 의 얇은 통로.

    스키마 쪽에서 별도 반올림 규칙을 만들지 않기 위해 존재한다 — 규칙이
    두 곳에 있으면 반드시 갈린다.
    """
    return to_won(value)
