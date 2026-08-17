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
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar, Final

from core.contracts.der import DispatchResult
from core.contracts.units import Money
from core.contracts.validation import ValidationError

#: spec `FR-205-AC1` 이 나열한 계약·거래 구조 일곱. **저자가 적은 리터럴이며
#: 여기서 파생하거나 줄이지 않는다.**
#:
#: 이 목록을 계약에 두는 이유는 `payer_by_structure` 의 키를 **기동 시점에**
#: 대조하기 위해서다. 오타 난 구조 이름은 영영 매치되지 않고, 그러면 그 편익은
#: 조용히 기본 `payer` 로 떨어진다 — 지불 주체가 틀린 채 계산이 끝나고 결과는
#: 그럴듯하다. 레지스트리가 `tag` 중복을 기동 시점에 터뜨리는 것과 같은 근거다.
#:
#: > **어긋난 것이 하나 있다.** 코드에서 실제로 쓰이는 유일한 구조 리터럴은
#: > `tests/model/test_financial_isolation.py:43` 의 **`"개별 직접계약"`** 인데,
#: > spec 은 **`"개별 세대 직접계약"`** 이라고 적는다. 이 라운드에서 고치지
#: > 않는다 — `FR-205` 정산 조립기가 구조 어휘를 확정할 때 함께 정할 일이고,
#: > 지금 한쪽으로 맞추면 그 판단을 코드가 먼저 해 버린다.
CONTRACT_STRUCTURES: Final[tuple[str, ...]] = (
    "개별 세대 직접계약",
    "단일계약+관리주체 경유",
    "분산특구 직접거래",
    "상계거래",
    "잉여 직거래",
    "집합 PPA",
    "VPP 경유",
)


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


@dataclass(frozen=True)
class ExclusionRule:
    """배타 규칙 1건 — FR-402-AC4.

    **계약에 두는 이유** (R16): 규칙표의 **정본은 데이터 파일**이 됐고
    (`docs/exclusion-rules.yaml`), 그것을 읽는 로더와 그것을 쓰는 판정이 서로
    다른 모듈이다. 타입이 어느 한쪽에 있으면 다른 쪽이 그 모듈을 import 하게
    되어 순환이 생긴다 — `discover()` 를 `core.contracts` 에 둔 것과 같은
    근거다.

    양방향으로 적용한다 — ``(A, B, ...)`` 는 ``(B, A, ...)`` 와 같은 관계다.
    """

    benefit_a: str
    benefit_b: str
    exclusion_type: ExclusionType
    rationale: str
    #: ``None`` 은 «모든 프로파일에 적용». 제도 한정 규칙은 프로파일 이름을 둔다
    applies_to_profile: str | None = None
    #: ``None`` 은 «모든 계약구조에 적용». 구조 한정 규칙은 구조 이름을 둔다
    #: (`CONTRACT_STRUCTURES` 의 리터럴 — 로더가 기동 시점에 대조한다).
    #:
    #: **왜 프로파일과 별도 축인가 (R31 결정 §2-4).** `ContractConfig.structure`
    #: (`FR-205`)와 `RegulationProfile`(`FR-504`)은 **완전히 독립된 두 축**이라,
    #: 사용자가 「상계거래」를 고르고도 다른 규제 프로파일을 선택하면 상계 한정
    #: 규칙이 **조용히 걸리지 않는다** — 설계서가 지적한 REC 이중 계상 위험이 그것이다.
    #:
    #: 구조 선택이 프로파일을 자동 강제하는 안을 택하지 않은 이유: 두 축을 묶으면
    #: **새 구조·새 프로파일 조합마다 매핑 코드를 고치게 된다.** 금지 여부를 이
    #: 규칙표에 두면 코드가 아니라 **데이터가 늘고**, 거부는 이미 실행 경로에
    #: 배선된 `assert_no_exclusions()` 가 그대로 담당한다 (R27).
    applies_to_structure: str | None = None


class ValueStream(ABC):
    """편익 흐름 공통 계약 (FR-401-AC1)."""

    #: spec FR-401-AC2.<tag> 의 키와 같은 리터럴. 슬러그화·대소문자 변환 금지
    tag: ClassVar[str]

    #: 이 편익을 누가 지불하는가 — **계약구조와 무관한 경우의 답**.
    #: 미특정이면 활성화가 거부된다 (DV-13)
    payer: ClassVar[Payer] = Payer.UNSPECIFIED

    #: **계약구조에 따라 지불 주체가 갈리는 편익만** 채운다 (도메인 원칙 2-3).
    #:
    #: v0.1~R15 동안 `payer` 는 `ClassVar` 하나뿐이었고, 그래서 *「계약구조에
    #: 따름」* 을 **표현할 방법이 아예 없었다** — 같은 잉여 판매라도 상계거래
    #: 에서는 주민 지갑이고 집합 PPA 에서는 사업자 지갑인데, 클래스에 하나로
    #: 고정돼 있으니 둘 중 하나는 반드시 틀린 값이었다.
    #:
    #: **`if structure == ...` 로 짜지 않는다.** 선언표로 두면 여덟 번째
    #: 구조가 생겨도 이 계약과 엔진은 바뀌지 않고 그 편익의 표에 한 줄이
    #: 늘 뿐이다 — `FR-402-AC4`(배타 규칙)가 이미 같은 이유로 표다.
    payer_by_structure: ClassVar[Mapping[str, Payer]] = MappingProxyType({})

    #: ★★★ **`annual_value()` 의 값이 주어진 디스패치 창에 비례하는가** (R34).
    #:
    #:     True   창에서 읽은 물리량으로 계산한다 → 대표일을 주면 **대표일치**가
    #:            나오고, 호출측이 한 해로 환산해야 한다 (`SurplusSale`·`REC`)
    #:     False  생성자에서 받은 **연간** 수량으로 계산하며 디스패치를 보지
    #:            않는다 → 이미 연간값이고, 곱하면 365배가 된다
    #:
    #: **왜 계약에 자리를 만들었나.** 메서드 이름이 `annual_value` 인데 창에
    #: 비례하는 갈래가 섞여 있었고, 그 차이가 **어디에도 선언되어 있지 않았다.**
    #: 호출측(`e2e_runner`)은 정산 편익 전건에 365를 곱하고 첨두 절감에는
    #: 곱하지 않는 식으로 **암묵 규약**을 들고 있었다 — 그래서 「분산특구
    #: 직접거래」와 「집합 PPA」가 실행 경로에서 **365배**로 계상됐다(R34 실측:
    #: 집합 PPA 502,605원/년 → 183,450,825원). 금액이 크게 틀렸는데 **아무
    #: 예외도 나지 않고** 표는 그럴듯했다.
    #:
    #: ⚠ **기본값을 두지 않는다.** 여덟 중 여섯이 `False` 이므로 그것을 기본으로
    #: 두고 싶어지는데, 그러면 창을 읽는 편익을 새로 만들 때 **연간화가 빠진 채
    #: 365분의 1로** 조용히 계상된다. 선언을 빠뜨리면 아래 `__init_subclass__`
    #: 가 **기동 시점에** 막는다 — 계산이 끝난 뒤가 아니라.
    scales_with_dispatch_window: ClassVar[bool]

    name: str
    enabled: bool
    #: 이 인스턴스가 놓인 계약·거래 구조. `None` 이면 구조 무관으로 본다
    structure: str | None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """선언표의 키가 spec 의 구조 이름인지 **기동 시점에** 본다.

        오타는 영영 매치되지 않으므로 그 편익이 조용히 기본 `payer` 로
        떨어진다. 지불 주체가 틀린 채 계산이 끝나고 결과는 그럴듯하다 —
        `discover()` 가 `tag` 중복을 늦게 발견하면 안 되는 것과 같은 이유다.

        **연간화 규약의 선언 여부도 여기서 본다** (`scales_with_dispatch_window`).
        빠뜨리면 호출측이 곱해야 할지 말지를 짐작하게 되고, 짐작이 틀리면
        금액이 365배 또는 365분의 1이 되면서 아무 예외도 나지 않는다.
        """
        super().__init_subclass__(**kwargs)
        unknown = sorted(set(cls.payer_by_structure) - set(CONTRACT_STRUCTURES))
        if unknown:
            raise ValueError(
                f"{cls.__qualname__}.payer_by_structure 에 spec FR-205-AC1 이 "
                f"열거하지 않은 구조가 있습니다: {', '.join(unknown)}\n"
                f"허용: {', '.join(CONTRACT_STRUCTURES)}\n"
                "오타는 영영 매치되지 않고 기본 payer 로 조용히 떨어집니다"
            )
        # ⚠ **상속으로 물려받은 선언은 세지 않는다** (`vars(cls)` 를 본다).
        # 물려받은 것을 통과시키면 창을 읽는 편익을 창과 무관한 편익에서
        # 상속했을 때 규약이 조용히 따라오고, 그것이 곧 365배다.
        #
        # ⚠ 중간 추상 클래스도 면제하지 않는다. 처음에 `__abstractmethods__` 로
        # 면제하려 했는데 그 속성은 `__init_subclass__` 시점에 아직 채워지지
        # 않아 **조건 자체가 죽은 코드**였다(실측). 조건을 살리는 대신 없앴다 —
        # 규약을 물려주려는 중간 클래스라면 그것이 어느 쪽인지 적을 수 있다.
        #
        # ⚠ **구조 선언표 검사보다 뒤에 둔다.** 앞에 두면 오타를 보는 검사가
        # 이 메시지를 먼저 받아 **잡으려던 결함이 아닌 것으로** 빨간불이 난다 —
        # 한 자리에서 둘을 던지면 먼저 던지는 쪽이 다른 쪽을 가린다.
        if "scales_with_dispatch_window" not in vars(cls):
            raise ValueError(
                f"{cls.__qualname__} 이 `scales_with_dispatch_window` 를 선언하지 "
                "않았습니다.\n"
                "`annual_value()` 가 디스패치 창에서 읽은 양으로 계산하면 True "
                "(호출측이 연간화한다), 생성자에서 받은 연간 수량으로 계산하면 "
                "False 입니다.\n"
                "기본값을 두지 않은 이유는 짐작이 틀렸을 때 금액이 365배로 "
                "어긋나면서도 아무 예외가 나지 않기 때문입니다"
            )

    def __init__(
        self,
        *,
        name: str,
        enabled: bool = True,
        structure: str | None = None,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.structure = structure
        if enabled and self.effective_payer is Payer.UNSPECIFIED:
            raise ValidationError(
                field=f"valuestream.{type(self).tag}.payer",
                reason=(
                    f"{name}: 지불 주체가 특정되지 않았습니다"
                    + (f" (계약구조 «{structure}»)" if structure else "")
                ),
                action=(
                    "편익 클래스에 `payer` 를 선언하거나, 구조에 따라 갈리면 "
                    "`payer_by_structure` 에 해당 구조의 주체를 넣으십시오. "
                    "주체가 없으면 같은 화폐 흐름이 두 관점에서 각각 계상되어 "
                    "이중 계상이 됩니다"
                ),
                rule="DV-13",
            )

    @property
    def effective_payer(self) -> Payer:
        """이 인스턴스에 실제로 적용되는 지불 주체.

        **`payer` 를 직접 읽는 코드가 남으면 구조별 선언이 무시된다.** 그래서
        판정·리포트가 전부 이 통로를 지난다 — R16 에 `payer_gate.assess()` 와
        `report.py` 를 여기로 옮겼다.
        """
        if self.structure is not None:
            by_structure = self.payer_by_structure.get(self.structure)
            if by_structure is not None:
                return by_structure
        return self.payer

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
