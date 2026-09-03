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

    ## ★ `GRID_OPERATOR` 와 `POWER_MARKET` 은 **다른 지갑이다** (R50)

    계통 쪽 값이 `GRID_OPERATOR`(「배전사업자」) 하나뿐이었을 때 계통 급전
    편익 둘이 그 값을 **함께** 썼다 — `NWAs`(계통 기여 보상)는 배전망 증설
    회피가 근거이므로 배전사업자에 가깝지만, `CapacityPayment`(용량정산금)는
    **전력시장 정산**이라 배전사업자가 아니다. 값은 리포트의 「지불 주체」
    칸에 **그대로 인쇄되므로**(`core/report/excel.py`) 하나로 두면 검토자가
    시장 정산금을 배전사업자 부담으로 읽고, 관점별 귀속(FR-704)도 같은 곳으로
    잡는다. 지불 주체를 계약이 요구하는 이유(위 모듈 머리말 · FR-402-AC5 ·
    DV-13)가 바로 그 오귀속을 막는 것이므로 **둘을 가른다.**
    """

    RESIDENT = "참여 주민"
    OPERATOR = "사업자"
    GOVERNMENT = "정부"
    GRID_OPERATOR = "배전사업자"
    POWER_MARKET = "전력시장"
    SOCIETY = "사회"
    UNSPECIFIED = "미특정"


class ExclusionType(StrEnum):
    """편익 배타 5유형 (FR-402-AC2.A~.E).

    값은 정본 [[분산자원 경제성 평가 원칙]] 의 절 제목이자 DB enum
    `BenefitExclusionRule.exclusion_type` 이며, spec 조항 ID
    `FR-402-AC2.A` ~ `.E` 의 키와 같은 리터럴이다. **여기서 이름을 바꾸면
    세 곳이 한꺼번에 어긋난다.**

    ## ★ `E` 를 신설한 이유 (R48 판정 §2 · v1.2)

    A~D 넷은 **「계상해도 되는 편익 둘을 동시에 세면 안 된다」** 를 말한다.
    R48 사용자 판정이 세운 축은 그것이 아니다 — **계통 급전(CP·NWAs)과 사용자
    운전(SelfConsumption·PeakShaving)** 은 *「방전 시점을 누가 정하는가」* 가
    갈리므로 **애초에 같은 운전에 함께 존재할 수 없다.**

        A 가 아니다   같은 kWh 를 두 번 파는 것이 **아니다**. 물리량이 겹치지
                      않아도 성립하지 않는다
        D 가 아니다   **제도가 금지하는 것이 아니다.** 제도가 바뀌어도
                      성립하지 않는다 — 제도가 아니라 운전 구조가 막는다

    → 그래서 `E` 의 이름은 **「동시에 성립할 수 없는 운전」**이며, **막는 규칙이
    아니라 「성립하지 않음」을 선언하는 규칙**이다. A~D 를 빌려 쓰면 근거 문장이
    거짓이 되고, 제도 개정 때 *「제도가 바뀌었으니 이 규칙은 풀린다」* 로 잘못
    읽힌다.

    ⚠ **열거값은 A~D 와 같이 키 한 글자 `"E"` 다** — 한국어 이름을 값에 넣지
    않는다. 값은 spec 조항 키·`docs/exclusion-rules.yaml` 의 `type:`·DB enum 이
    함께 쓰는 리터럴이라, 이름을 값으로 두면 그 셋이 한꺼번에 어긋난다.

    ⚠ 유형만 세운다. **규칙 행은 `docs/exclusion-rules.yaml` 이 소유한다** —
    유형과 규칙을 한 곳에서 함께 늘리면 데이터 파일이 정본이라는 FR-402-AC4 가
    무너진다.
    """

    A = "A"  # 동일 물리량 이중 판매 — 차단 100% (음성 검증)
    B = "B"  # 인과 하류 편익이 상류에 이미 포함 — 오탐 0 (양성 검증)
    C = "C"  # 동일 효과의 이중 화폐화 — 오탐 0
    D = "D"  # 제도적 배타 — 오탐 0
    E = "E"  # 동시에 성립할 수 없는 운전 — 오탐 0


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

    #: ★★ **이 편익이 화폐화하는 물리량의 표찰** — 배타 판정의 물리량 축 (R56).
    #:
    #: `FR-402-AC1` 은 *「지불 주체가 다르거나 **물리량이 다르면 정상 계상한다**」*
    #: 를 명시로 요구하고 `FR-402-AC2.A` 는 금지 범위를 *「**같은** 1 kWh」·
    #: 「**같은 시각** ESS 방전」* 으로 좁힌다. 그런데 배타 판정은
    #: `type(s).tag` 의 **집합**으로만 이뤄져서 «같은 물리량인가» 를 물을 수단이
    #: 원리적으로 없었고, 그래서 **물리량이 다른 조합까지 거부**했다 — 거부
    #: 메시지 자신이 *「물리량이 실제로 다른지 확인하고 …」* 라고 처방하면서
    #: 「다르다」를 표현할 자리를 계약이 내주지 않은 상태였다.
    #:
    #: `None` 은 **「말하지 않았다」이지 「없다」가 아니다.** 판정은 **둘 다
    #: 선언하고 서로 다를 때만** 통과시킨다 — 한쪽만 선언한 것을 통과시키면
    #: 한 편익에 표찰을 다는 것만으로 배타 규칙 전체를 무력화할 수 있다
    #: (`core/valuestream/exclusion_table.py::collect_exclusions`).
    #:
    #: ⚠ **`ClassVar` 로 두지 않는다.** 같은 편익 클래스의 두 인스턴스가 서로
    #: 다른 물량을 질 수 있는 것이 이 축의 요점이다 — 한 대의 ESS 를 용량 몫으로
    #: 갈라 몫마다 다른 역할을 주는 구성(사용자 판정 `docs/decisions-2026-09-02-
    #: R52.md` §3 뒷 문장)이 정확히 그 형태다. 바로 위 `payer` 가 `ClassVar`
    #: 하나였다가 *「계약구조에 따름」* 을 표현할 방법이 없어 `payer_by_structure`
    #: 를 얻은 경위와 같다.
    #:
    #: ## ⚠⚠ **`scales_with_dispatch_window` 와 규약이 정반대인 이유**
    #:
    #: 바로 위 그 필드는 **기본값을 일부러 두지 않았다.** 빠뜨렸을 때 가는 쪽이
    #: 「조용히 틀린 수」이기 때문이다 — 여섯이 `False` 라고 그것을 기본으로
    #: 두면 창을 읽는 편익을 새로 만들 때 연간화가 빠진 채 365분의 1로 계상되고
    #: 아무 예외도 나지 않는다(R34 실측: 집합 PPA 502,605원/년 →
    #: 183,450,825원).
    #:
    #: **이 필드는 방향이 반대다.** 빠뜨렸을 때 가는 쪽이 **거부**이므로 실수는
    #: *「막혀서 알게 된다」* 이지 *「조용히 틀린 수가 나온다」* 가 아니다. 그래서
    #: 기본값을 두는 것이 옳다. **두 필드를 같은 규약으로 맞추지 마라** — 어느
    #: 쪽으로 맞추든 하나는 틀린다.
    quantity_id: str | None

    #: ★★ 이 편익이 이전(transfer)일 때 내는 쪽 지갑 (R58 신설).
    #:
    #: - **뜻**: 이 편익이 이전이면(= `effective_payer` 가 받는 만큼 다른 지갑이 정확히
    #:   그만큼 잃는 흐름이면) **내는 쪽 지갑**을 선언한다. `None` 이면 이전이 아니다
    #:   (실물 자원비용 절감·외부효과).
    #: - **`bool` 로 두지 않는 이유**: 관점별 표에서 **부호를 반대로** 세우려면
    #:   **어느 관점에 `-` 를 세울지** 알아야 하고, `bool` 로는 그 자리가 서지 않는다.
    #: - **`ClassVar` 로 두는 이유**: `payer` → `payer_by_structure` 가 걸어온 길처럼
    #:   구조별로 갈릴 수 있으나 **지금 이전인 편익이 하나도 없어 갈래를 지어낼 근거가
    #:   없다.** 필요해지면 그 길을 그대로 간다.
    #: - **기본값을 `None` 으로 두는 이유와 위험성 (세 필드의 규약 차이)**:
    #:   `scales_with_dispatch_window` 는 기본값이 없다(틀리면 금액이 365배 부풀기 때문).
    #:   `quantity_id` 는 기본값이 `None` 이다(빠뜨리면 배타 판정에서 거부되므로).
    #:   이 필드의 `None` 기본값은 **빠뜨리면 사회 편익이 부푸는 위험한 방향**이라
    #:   기본값이 편한 쪽이 아니다. 그러나 지금 이전 편익이 하나도 없어서 당장
    #:   다른 값을 강제할 수 없으므로 기본값을 두고, 대신 **이전 편익이 처음 생길 때를
    #:   감지하는 테스트 래칫**(판정 ④)을 함께 세운다.
    transfer_counterparty: ClassVar[Payer | None] = None

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
        quantity_id: str | None = None,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.structure = structure
        self.quantity_id = quantity_id
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

    @abstractmethod
    def formula(self, dispatch: DispatchResult, *, year: int) -> str:
        """`annual_value()` 의 **대입값 산식** — 수량과 단가를 갈라 적는다.

        ## ★★★ 왜 편익이 이것을 내놓아야 하나 (R36)

        양식 §3 붙임 4 는 *「편익별 산식·**대입값**(발전량·단가)」* 을 요구하는데
        실물은 갈래마다 **`대표일 1,771원 × 365일`** 한 줄이었다 — 곱해서 나온
        금액만 있고 **무엇에 얼마를 곱했는지가 없다.** 비용 쪽은 같은 자리에
        `대표일 수전 6.19kWh × 365일 × 120원/kWh` 로 갈라 적는다.

        그래서 **영향도 1위 인자(잉여 판매단가)의 값이 붙임 4 어디에도 없었다.**
        검토자가 「이 편익이 왜 이 금액인가」를 물으면 붙임 4 가 답하지 못하고,
        수량이 틀렸는지 단가가 틀렸는지도 가릴 수 없다 — **둘은 서로 다른 사람이
        고친다**(단가는 대장, 수량은 운전).

        ## 왜 호출측이 짓지 않는가

        갈래마다 산식의 **모양이 다르다** — 곱(`잉여 × 단가`) · 차(`기준 − 신규`) ·
        합(`하위 항목 다섯`) · 섞임(`(약관 − 거래단가) × 거래량 − 수수료`). 이것을
        호출측에서 지으려면 **태그별 분기**를 들게 되고, 그 목록은 편익이 늘 때
        낡는다 — `scales_with_dispatch_window` 를 선언으로 둔 것과 같은 근거다.
        대입값을 아는 것은 그 값을 생성자에서 받은 편익 자신뿐이다.

        ## 무엇을 적고 무엇을 적지 않는가

            적는다     생성자에서 받은 단가·수량·요율, 창에서 읽은 물리량,
                       각 값의 **이름과 단위**
            적지 않는다 **연간화(`× 365일`)** — 창 비례 여부는
                       `scales_with_dispatch_window` 가 선언하고 곱은 호출측이
                       붙인다. 여기에도 적으면 두 곳이 갈릴 수 있고, 갈린 쪽이
                       365배다
            적지 않는다 **`= 합계`** — 합계는 `annual_value()` 가 낸다. 여기서
                       또 적으면 같은 수의 출처가 둘이 된다

        ⚠ **비활성 여부를 보지 않는다.** `annual_value()` 는 비활성이면 0을
        내지만 산식은 *「이 편익이 무엇을 어떻게 계상하는가」* 이므로 그대로
        적는다 — 0원 옆에 빈 산식이 놓이면 「계상하지 않았다」와 「계상했는데
        0이다」가 같은 모양이 된다.
        """

    def exclusions(self) -> list[tuple[str, ExclusionType, str]]:
        """이 편익과 배타 관계인 편익들 — `(상대 tag, 유형, 근거)`.

        **선언적 규칙 테이블이며 코드가 아니다** (FR-402-AC4). 제도가 바뀌면
        데이터만 교체한다. 기본이 빈 목록인 이유는 대부분의 편익이 배타
        관계를 갖지 않기 때문이며, 관계를 선언할 편익만 덮어쓴다.
        """
        return []
