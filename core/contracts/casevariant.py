"""케이스 변형 계약 — spec FR-607-AC1 · FR-611 · FR-801.

FR-607-AC1 은 *「**모든 실행에서** `지원 0` 케이스가 **자동 포함**되어 결과
**상단에 표시**된다」* 이다. 저장소가 가진 것은 이것이었다.

    build_capex_cashflows(scheme, net_capex, "OWNER", is_baseline=True)
                                                      ^^^^^^^^^^^^^^^^
    호출자가 **손으로 넘기는 깃발.** 안 넘기면 기준선은 그냥 없다.

**「자동 포함」을 호출자의 기억에 맡기면 그것은 자동이 아니다.** 그리고
빠졌을 때 나는 증상이 없다 — 기준선 없는 결과도 완전한 결과처럼 보인다.

**그래서 변형을 선언으로 바꾼다.** 등록된 변형 목록이 곧 실행 목록이고,
`ordered_variants()` 가 **기준선이 정확히 하나 있고 맨 위에 온다**는 것을
기계로 보증한다. 기준선을 빠뜨리려면 파일을 지워야 하고, 그러면 검사가
빨간불이 된다.

**확장 방향.** 지금 필요한 변형은 「무지원」과 「입력된 지원안」 둘이지만,
`FR-608`(최소 지원 수준 역산)·`FR-609`(등가 지원 조합)·민감도 변형이 같은
자리에 온다. 그때 필요한 것은 **파일 하나**이며 이 계약도 파이프라인도
바뀌지 않는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar


class CaseVariant(ABC):
    """한 번의 평가 실행에서 함께 산출되는 케이스 하나.

    구현은 `core/casegrid/variants/<tag>.py` 파일 하나이며 등록은
    `discover()` 가 한다 — 자원·차트와 같은 형태다.
    """

    #: 레지스트리 키
    tag: ClassVar[str]

    #: 리포트에 찍히는 이름
    label: ClassVar[str]

    #: **표시 순서. 작을수록 위.** FR-607-AC1 의 「결과 상단에 표시」가
    #: 이 값으로 표현된다 — 리포트가 자기 나름대로 정렬하면 조항이
    #: 리포트마다 다르게 지켜진다
    order: ClassVar[int] = 100

    #: 이 변형이 충족시키는 spec 수용기준
    clauses: ClassVar[tuple[str, ...]] = ()

    #: **기준선인가.** 정확히 하나만 참이어야 한다 (`ordered_variants`)
    baseline: ClassVar[bool] = False

    @abstractmethod
    def overrides(self, base: Mapping[str, Any]) -> dict[str, Any]:
        """기준 입력에 이 변형이 덮어쓰는 값만 돌려준다.

        **전체 입력을 다시 만들지 않는다.** 변형이 전체를 돌려주면 기준
        입력에 항목이 하나 늘 때 모든 변형이 그것을 따라 늘려야 하고,
        빠뜨린 변형은 그 항목이 조용히 사라진 채로 계산된다.
        """


def ordered_variants(
    variants: Mapping[str, type[CaseVariant]],
) -> Sequence[type[CaseVariant]]:
    """표시 순서대로 정렬하고 **기준선이 정확히 하나인지** 확인한다.

    이 함수가 FR-607-AC1 을 기계로 만든다.

      · 기준선이 없다  → 「지원 0 케이스가 자동 포함」이 성립하지 않는다
      · 기준선이 둘    → 어느 것이 상단인지 결과만 보고는 알 수 없다

    둘 다 **조용한 실패**이므로 오류로 막는다. 빠진 기준선은 결과에 아무
    흔적을 남기지 않고, 읽는 사람은 지원안 케이스를 기준선으로 읽는다.
    """
    baselines = sorted(tag for tag, cls in variants.items() if cls.baseline)
    if not baselines:
        raise ValueError(
            "기준선 변형이 없습니다 (FR-607-AC1). 「무지원 기준 경제성을 항상 "
            "먼저 산출한다」가 성립하지 않으며, 기준선 없는 결과는 완전한 "
            "결과처럼 보입니다"
        )
    if len(baselines) > 1:
        raise ValueError(
            f"기준선 변형이 둘 이상입니다: {', '.join(baselines)}. "
            "어느 것이 결과 상단인지 결과만 보고는 알 수 없습니다 (FR-607-AC1)"
        )

    ordered = sorted(variants.values(), key=lambda cls: (cls.order, cls.tag))
    if not ordered[0].baseline:
        raise ValueError(
            f"기준선({baselines[0]})이 맨 위가 아닙니다. `order` 를 가장 작게 "
            "두십시오 — FR-607-AC1 은 「결과 상단에 표시」를 요구합니다"
        )
    return tuple(ordered)
