"""`RegulationItem` 계약 — 작업 1.4 / spec FR-504.

제도 파라미터는 **코드가 아니라 데이터**다 (NFR-202). 제도 개정 시 코드 배포
없이 항목을 추가·개정할 수 있어야 하고(FR-504), 개정 이력·유효기간·diff를
갖는다.

**규제 프로파일이 값을 소유하고 조항이 그것을 참조한다.** 반대로 하면 —
조항이 값을 들고 있으면 — 제도가 바뀔 때 코드를 고쳐야 하고, 그 순간
"데이터만 교체" 가 성립하지 않는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class RegulationItem:
    """제도 파라미터 1건.

    `value` 가 `Any` 인 이유: 제도 값은 수치(70% 의무비율)일 수도, 목록
    (배타 규칙 집합)일 수도, 참조(요금표 ID)일 수도 있다. 타입을 좁히면
    새 제도 유형이 생길 때 계약을 고쳐야 하고, 그것은 "코드 배포 없이
    항목 추가"(FR-504)와 정면으로 충돌한다.
    """

    key: str
    value: Any
    unit: str | None
    #: 근거 조문·고시 — 출처 없는 제도 값은 검증할 수 없다 (근거 표기 기준)
    source: str | None
    valid_from: date | None = None
    valid_to: date | None = None

    def applies_on(self, when: date) -> bool:
        """유효기간 판정. 경계는 **양끝 포함**이다.

        고시는 "…부터 …까지" 로 쓰이므로 종료일 당일도 유효하다. 반열림
        구간으로 두면 개정 당일의 판정이 조용히 한 칸 어긋난다.
        """
        if self.valid_from and when < self.valid_from:
            return False
        return not (self.valid_to and when > self.valid_to)


class RegulationProfile(ABC):
    """규제 프로파일 계약 (FR-504-AC1).

    프로파일은 버전을 가지며 이전 버전으로 복원 가능하다 (FR-504-AC4).
    """

    name: str
    version: str

    @abstractmethod
    def get(self, key: str, *, when: date) -> RegulationItem:
        """유효한 항목 1건. 없으면 `KeyError`.

        **기본값을 조용히 돌려주지 않는다.** 제도 값이 없는데 0이나 관례값이
        나오면, 제도 근거 없이 계산이 진행되고 결과에는 그 사실이 남지
        않는다. FR-402-AC2.D 는 근거에 도달하지 못한 항목을 **보수적으로
        배타 처리하고 그 사실을 표기**하라고 정한다 — 조용한 기본값은 그
        표기 기회를 없앤다.
        """

    @abstractmethod
    def items(self, *, when: date) -> list[RegulationItem]:
        """해당 시점에 유효한 전 항목. 프로파일 diff·리포트 표시용."""
