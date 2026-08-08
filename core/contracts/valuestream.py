"""`ValueStream` 계약 — 작업 1.4 / spec FR-401 · FR-402.

편익 1종 = 독립 클래스 1개 = 파일 1개 (`core/valuestream/`, §16.3 WP-4).
편익을 추가하거나 비활성화해도 코어 엔진 수정이 발생하지 않는다 (FR-401-AC1).

**지불 주체를 계약이 요구하는 이유** (FR-402-AC5 · DV-13):
    편익은 누군가의 지갑에서 나온다. 주체를 특정하지 않으면 같은 화폐 흐름이
    두 관점에서 각각 계상되어 이중 계상이 된다 — FR-402-AC2.C 가 막으려는
    것이 정확히 이것이다. 그래서 주체 미특정 편익은 **활성화를 거부**한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import ClassVar

from core.contracts.der import DispatchResult
from core.contracts.units import Money


class Payer(StrEnum):
    """지불 주체 (FR-402 공통 기준 · DV-13).

    `UNSPECIFIED` 를 열거에 두는 이유: 미특정 상태를 `None` 으로 표현하면
    "아직 안 정함"과 "정할 필요 없음"이 구분되지 않는다. 명시적 값으로 두고
    활성화 시점에 거부한다.
    """

    RESIDENT = "참여 주민"
    OPERATOR = "사업자"
    GOVERNMENT = "정부"
    GRID_OPERATOR = "배전사업자"
    SOCIETY = "사회"
    UNSPECIFIED = "미특정"


class ExclusionType(StrEnum):
    """편익 배타 4유형 (FR-402-AC2.A~.D).

    값은 정본 [[분산자원 경제성 평가 원칙]] 의 절 제목이자 DB enum
    `BenefitExclusionRule.exclusion_type` 이며, spec 조항 ID
    `FR-402-AC2.A` ~ `.D` 의 키와 같은 리터럴이다. **여기서 이름을 바꾸면
    세 곳이 한꺼번에 어긋난다.**
    """

    A = "A"  # 동일 물리량 이중 판매 — 차단 100% (음성 검증)
    B = "B"  # 인과 하류 편익이 상류에 이미 포함 — 오탐 0 (양성 검증)
    C = "C"  # 동일 효과의 이중 화폐화 — 오탐 0
    D = "D"  # 제도적 배타 — 오탐 0


class ValueStream(ABC):
    """편익 흐름 공통 계약 (FR-401-AC1)."""

    #: spec FR-401-AC2.<tag> 의 키와 같은 리터럴. 슬러그화·대소문자 변환 금지
    tag: ClassVar[str]

    #: 이 편익을 누가 지불하는가. 미특정이면 활성화가 거부된다
    payer: ClassVar[Payer] = Payer.UNSPECIFIED

    name: str
    enabled: bool

    def __init__(self, *, name: str, enabled: bool = True) -> None:
        if enabled and self.payer is Payer.UNSPECIFIED:
            raise ValueError(
                f"{name}: 지불 주체가 특정되지 않은 편익은 활성화할 수 없습니다 "
                "(FR-402-AC5 · DV-13). 주체가 없으면 같은 화폐 흐름이 두 관점에서 "
                "각각 계상되어 이중 계상이 됩니다"
            )
        self.name = name
        self.enabled = enabled

    @abstractmethod
    def annual_value(self, dispatch: DispatchResult, *, year: int) -> Money:
        """해당 연도 편익 (원). 비활성이면 0.

        **정수 원을 돌려준다** — 시계열(float)에서 연 집계로 넘어오는 경계가
        여기이며, 반올림은 `units.to_won()` 한 곳에서만 일어난다 (NFR-103).
        """

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        """이 편익과 배타 관계인 편익들 — `(상대 tag, 유형, 근거)`.

        **선언적 규칙 테이블이며 코드가 아니다** (FR-402-AC4). 제도가 바뀌면
        데이터만 교체한다. 기본이 빈 목록인 이유는 대부분의 편익이 배타
        관계를 갖지 않기 때문이며, 관계를 선언할 편익만 덮어쓴다.
        """
        return []
