"""등록된 변형 목록 × 지원 계산 — `FR-607-AC1` 의 **합성 자리**.

**왜 이 파일이 `core/incentive/` 가 아니라 여기 있는가.** 조항은 *「지원 0
케이스가 모든 실행에서 자동 포함되어 결과 상단에 표시된다」* 를 요구하고, 그
「모든 실행」의 목록은 `core.casegrid.variants.run_order()` 다. 그런데
`.importlinter` 의 `layers` 가 `core.casegrid` 를 `core.incentive` **위**에
둔다 — 아래가 위를 알면 역방향 import 이고 `lint-imports` 가 막는다
(`NFR-208-AC1`).

R21 에 `core/incentive/calculator.py` 가 `run_order()` 를 직접 import 해서
그 게이트가 실제로 빨간불이 났다. **고칠 곳은 계층 설정이 아니라 합성이 놓인
자리였다** — 계층을 느슨하게 하면 조항 `NFR-208-AC1` 자신이 깨진다.

> **이것이 R20 이 찾은 형태의 세 번째다.** `regulation_axis.py`·
> `dataset_axis.py` 가 각각 「하위가 만든 재료를 상위가 소비한다」의 빈 자리를
> 메웠고, 이 파일은 그 자리가 **편익 계산과 케이스 목록 사이**에도 있었음을
> 말한다. 구획을 옳게 가르면 **구획 사이에 아무도 소유하지 않는 일이 남고**,
> 그것은 워커 브리프로는 잡히지 않는다.

아래가 하는 일은 **판정이 아니라 순회**다. 「기준선이 정확히 하나이고 맨
위인가」는 `ordered_variants()` 가 이미 보증하며, 이 파일은 그 보증에
의존할 뿐 재구현하지 않는다.
"""

from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType
from typing import Any, Literal, NamedTuple

from core.casegrid.variants import run_order
from core.contracts.casevariant import CaseVariant
from core.contracts.schemas import CashFlowRow
from core.contracts.validation import ValidationError
from core.incentive.calculator import (
    build_baseline_capex_cashflows,
    build_capex_cashflows,
)
from core.incentive.schemas import IncentiveScheme

Viewpoint = Literal["OWNER", "PARTICIPANT", "GOV", "SOCIAL"]

#: 변형이 `overrides()` 로 덮어쓰는 키 → `IncentiveScheme` 필드 이름.
#:
#: **두 이름이 다른 것이 요점이다.** 변형은 사용자 입력의 낱말로 말하고
#: (`subsidy_fixed_won` — 단위가 이름에 있다) 스킴은 재무 필드로 말한다
#: (`subsidy_fixed` — `Decimal`). 이 표가 없으면 그 번역이 변형마다 따로
#: 생기고, 오타 하나가 **조용히 무시되어** 그 변형이 기준안과 같은 수를 낸다.
_OVERRIDE_TO_SCHEME_FIELD = MappingProxyType({
    "subsidy_rate": "subsidy_rate",
    "subsidy_fixed_won": "subsidy_fixed",
    "loan_rate": "loan_rate",
})


class CaseCapexCashflows(NamedTuple):
    """등록된 변형 하나의 CAPEX 현금흐름 (`FR-607-AC1`).

    `tag`·`label` 을 함께 나르는 이유: 리포트가 「상단에 표시」할 때 그 행이
    **어느 케이스인가**를 적어야 한다. 행만 돌려주면 표시 쪽이 순서에 의존해
    이름을 붙이게 되고, 순서가 바뀌면 이름이 조용히 어긋난다.
    """

    tag: str
    label: str
    rows: tuple[CashFlowRow, ...]


def build_capex_cashflows_for_all_cases(
    scheme: IncentiveScheme | None,
    capex: float | Decimal,
    viewpoint: Viewpoint,
) -> tuple[CaseCapexCashflows, ...]:
    """`FR-607-AC1`: **모든 실행에서** 지원 0 케이스가 자동 포함되어 상단에 온다.

    `run_order()` 가 등록한 변형 목록을 그대로 따라 돈다 — 호출자가
    「기준선도 계산해 달라」를 따로 기억해서 요청할 필요가 없다. 그것이
    이 조항이 없애려던 것이다: 예전 `build_capex_cashflows(..., is_baseline=)`
    은 **안 넘기면 기준선이 그냥 없었고, 빠졌을 때 나는 증상이 없었다.**
    """
    order = run_order()
    if not order or not order[0].baseline:
        raise ValueError(
            "기준선 변형이 맨 위에 없습니다 (FR-607-AC1). 「지원 0 케이스가 "
            "자동 포함되어 결과 상단에 표시된다」가 성립하지 않습니다"
        )

    results: list[CaseCapexCashflows] = []
    for variant_cls in order:
        variant_scheme = _scheme_for_variant(variant_cls, scheme)
        rows = (
            build_baseline_capex_cashflows(variant_scheme, capex, viewpoint)
            if variant_cls.baseline
            else build_capex_cashflows(variant_scheme, capex, viewpoint)
        )
        results.append(
            CaseCapexCashflows(variant_cls.tag, variant_cls.label, tuple(rows))
        )
    return tuple(results)


def _scheme_for_variant(
    variant_cls: type[CaseVariant], scheme: IncentiveScheme | None
) -> IncentiveScheme | None:
    """변형이 덮어쓰는 값을 스킴에 적용한다 — **`overrides()` 의 소비자** (R32).

    ## 왜 이것이 필요한가 — `overrides()` 를 읽는 배포 코드가 0곳이었다

    `CaseVariant.overrides()` 는 **추상 메서드**라 변형 전부가 구현하고 계약
    테스트가 그 반환값을 붙들고 있었다. 그런데 **그것을 읽는 배포 코드가 한 줄도
    없었다** — 이 함수 이전의 순회는 `variant_cls.baseline` 하나만 보고 기준선이면
    「무지원」, 아니면 「입력 스킴 그대로」로 갈랐다.

    변형이 둘일 때는 두 기계가 같은 답을 낸다(`Unsupported` 는 지원을 0으로,
    `AsPlanned` 는 아무것도 덮어쓰지 않으므로). **셋째 변형에서 갈린다** —
    `FR-608`(최소 지원 수준 역산)처럼 「보조율 30%」를 덮어쓰는 변형을 파일 하나로
    더하면, `baseline` 만 보는 순회는 그것을 **입력 지원안과 똑같이** 계산하고
    **아무 예외도 내지 않는다.** 확장점 문서(`casevariant.py`)가 *「필요한 것은
    파일 하나이며 파이프라인은 바뀌지 않는다」* 고 약속하는데, 그 약속이 숫자
    수준에서는 지켜지지 않는 상태였다.

    ## 모르는 키는 거부한다

    통과시키면 오타(`subsidy_ratio`)가 **조용히 무시되고** 그 변형은 기준안과 같은
    수를 낸다 — 표에는 행이 둘 있고 값이 같으니 「효과 없는 지원안」처럼 보인다.

    ## 기준선은 그 뒤에 `FR-607-AC3` 이 다시 판정한다

    적용 순서가 뒤가 아니라 **앞**이다. `build_baseline_capex_cashflows()` 가
    「타 사업 **확정** 지원분은 기준선에 포함된 소여, **예정**분은 제외」를 판정하며
    (`FR-607-AC3`·`AC4`), 그 판정이 나중에 오므로 변형의 덮어쓰기가 그것을
    뒤집을 수 없다.
    """
    overrides = variant_cls().overrides(_base_params(scheme))
    if not overrides:
        return scheme

    unknown = sorted(set(overrides) - set(_OVERRIDE_TO_SCHEME_FIELD))
    if unknown:
        raise ValidationError(
            field="casegrid.variant_overrides",
            reason=(
                f"변형 {variant_cls.tag!r} 이 지원 조건에 없는 키를 덮어씁니다: "
                f"{', '.join(unknown)}"
            ),
            action=(
                "`IncentiveScheme` 에 대응하는 키로 고치거나, 그 값이 지원 조건이 "
                "아니라면 변형에서 빼십시오. 모르는 키를 조용히 무시하면 그 변형이 "
                "입력 지원안과 같은 수를 내면서 표에는 별개 행으로 남습니다"
            ),
        )

    update: dict[str, Any] = {}
    for key, value in overrides.items():
        field = _OVERRIDE_TO_SCHEME_FIELD[key]
        if field == "subsidy_fixed":
            update[field] = None if value is None else Decimal(str(value))
        else:
            update[field] = value

    base = scheme if scheme is not None else IncentiveScheme.create_baseline()
    # `model_copy(update=…)` 는 **검증기를 다시 돌리지 않는다** — 정액·정률 동시
    # 지정 금지(`_validate_subsidy`)를 지나쳐 버린다. 그래서 다시 짓는다.
    return base.model_validate({**base.model_dump(), **update})


def _base_params(scheme: IncentiveScheme | None) -> dict[str, Any]:
    """`overrides(base)` 에 넘기는 기준 입력 — **변형이 쓰는 낱말로** 짓는다.

    변형은 「기준 입력에 있는 키만 덮어쓴다」는 계약을 지고 있고
    (`test_variants_return_only_what_they_change`), 그 계약을 확인할 수 있으려면
    기준 입력이 실물이어야 한다. 빈 사전을 넘기면 계약이 무의미해진다.
    """
    base = scheme if scheme is not None else IncentiveScheme.create_baseline()
    return {
        "subsidy_rate": base.subsidy_rate,
        "subsidy_fixed_won": (
            None if base.subsidy_fixed is None else int(base.subsidy_fixed)
        ),
        "loan_rate": base.loan_rate,
    }
