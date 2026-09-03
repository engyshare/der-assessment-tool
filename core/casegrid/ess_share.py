"""ESS 용량 **몫** — 한 대를 갈라 몫마다 다른 역할을 준다 (★분할 선행 ②).

## 무엇이 어긋나 있었는가 — **몫이 「선언」이었고 「수」가 아니었다**

한 대의 `ESS` 를 몫으로 갈라 몫마다 다른 역할을 주려면 **몫마다 `ESS`
인스턴스를 세워야 한다.** 그런데 `ESS` 의 제원 중 셋은 **인스턴스마다 통째로
붙는다** — `capacity_kwh` 만 갈라 두 인스턴스를 세우면 `power_kw` 가 **2배** 가
되고 `fixed_om_won_per_year` 도 **2배** 가 된다. 용량만 갈랐는데 정격출력과
고정 운영비가 늘어나고, 그 늘어남은 **아무 예외도 내지 않는다** — 두 몫이 각각
자기 정격출력 안에서 계획을 세우므로 `ESS._check_power()` 도 통과한다.
(`capex_unit_won_per_kwh` 는 **단위당** 값이라 용량이 갈리면 저절로 옳게 갈린다.)

⚠ **`mode_weights` 로는 못 푼다.** `ESS.dominant_mode` 가 *「가중치대로 시간대를
쪼개 섞는 것은 디스패치 엔진의 몫이다. 자원이 임의 배분을 하면 결과가 두 벌이
되어 어느 쪽이 실렸는지 구분할 수 없다」* 라고 못 박고, 그 규약대로 오늘
`mode_weights` 는 **대표 모드 하나로만 디스패치하고** 편익 태그만 여럿 낸다 —
즉 몫이 **편익 규모에 반영되지 않는다.** 몫을 수로 만들려면 자원 쪽에서
갈라야 한다.

## 왜 여기인가 — **거부한 갈래 셋과 그 사유**

- **`ESS` 자체에 몫 개념을 넣는다** → 거부. `core/der/ess.py` 는 `NFR-206` 코드
  줄 상한에 붙어 있어 넣을 자리가 없고, 무엇보다 **자원이 스스로 배분하면**
  `dominant_mode` 가 금지한 *「결과가 두 벌」* 이 된다.
- **편익 쪽에서만 몫을 표현한다** → 거부. `power_kw` 는 **물리 제약**이라 자원
  쪽에서 갈라야 몫마다 옳게 걸린다. 편익 금액에 비율만 곱하면 **몫이 정격출력을
  넘는 계획을 세워도 아무도 거부하지 않는다** — 그것이 이 모듈이 막으려는
  바로 그 형태다(위 「어긋나 있었는가」).
- **`mode_weights` 를 디스패치까지 확장한다** → 거부. 그것은 **디스패치 엔진의
  몫**이며 이 모듈의 범위가 아니다.

## 잔차 규약 — **합계가 원래 값과 같다**

비율 곱셈은 부동소수 잔차를 낳는다. 잔차는 **마지막 몫**(`RESIDUAL_HOLDER_INDEX`)
이 받는다 — `core/asset/common_asset.py` 가 공통설비 안분에서 정한 규약과
**같고 대상만 다르다**(받는 쪽이 가구가 아니라 몫이다). `core/casegrid/
attribution.py` 가 자원 귀속에서 같은 자리를 이미 한 번 지났고, 그 파일이
상수를 import 하지 않은 이유도 같다 — **같은 값을 공유할 대상이 아니고,
규약이 같다는 사실은 이 문단이 갖는다.**

## ★ 배포 경로가 이 모듈을 쓴다 — **다만 몫을 주는 케이스가 없다** (R57/WP-6)

`core/casegrid/e2e_runner.py` 가 `ESSShare` 를 import 하고
`run_single_case_e2e(ess_shares=…)` 로 몫 선언을 받는다. 몫을 세우고 그 몫의
편익을 짓는 몸통은 `core/casegrid/ess_build.py::build_case_ess_fleet`·
`build_fleet_streams` 다. `tests/casegrid/test_ess_share.py` 가 그 import 를
`ast` 로 재므로 **배선이 조용히 끊기면 빨간불**이다.

⚠⚠ **그런데 어느 케이스도 몫을 주지 않는다** — `ess_shares` 의 기본값이
`None`(*「가르지 않는다」*)이고 케이스 축에도 올리지 않았다. **그래서 결론축은
한 원도 움직이지 않았다**(골든 3건이 그 증인이다). 몫 비율·역할 배분은 아직
아무도 정하지 않았고 지어내지 않는다 — **값이 오면 그때가 사용자 판정 자리**다.

몫마다 **어느 편익이 서는지**는 이 모듈이 정하지 않는다
(`core/casegrid/ess_share_benefits.py` 가 정한다). 여기까지가
*「몫을 수로 만드는 자리」* 다.

> ⚠ **R57/WP-6 앞까지 이 자리에는** *「배포 경로가 쓰지 않는다 · 러너가 이
> 모듈을 import 하지 않는다」* 라고 적혀 있었고, 「결론축 불변」의 증인도
> 그 검사였다. 지금 그 증인은 **골든 3건**이다 — 배선이 섰으므로 *「의존이
> 없다」* 로는 더 이상 그것을 잴 수 없다.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, NoReturn

from core.contracts.validation import ValidationError
from core.der.ess import ESS, ESSOperatingMode

#: 나눗셈 잔차를 받는 몫의 인덱스. **-1(마지막 몫)로 고정한다** — 상수로 두는
#: 이유는 검사와 설명이 같은 값을 참조하게 하기 위해서다
#: (`common_asset.RESIDUAL_HOLDER_INDEX` 와 같은 규약이며 대상만 다르다).
RESIDUAL_HOLDER_INDEX: Final[int] = -1

#: **몫 비율로 나누는** 제원 — 자원 하나에 통째로 붙는 값들이다. 여기 없는
#: 제원은 그대로 준다(아래 `split_ess` 독스트링의 표).
#:
#: ⚠ **`capex_unit_won_per_kwh` 를 여기 넣지 마라.** 단위당 값이므로 갈린
#: 용량에 곱해지면 저절로 갈리고, 여기 넣으면 **몫의 제곱만큼 작아진다.**
PRORATED_FIELDS: Final[tuple[str, ...]] = (
    "capacity_kwh",
    "power_kw",
    "fixed_om_won_per_year",
    "capex_extra_won",
)

#: 몫 선언이 **이기는** 제원 — 물리 제원에 있어도 몫이 준 것으로 덮는다.
#: `mode_weights` 는 아예 주지 않는다(모듈 머리말의 `dominant_mode` 인용).
_SHARE_OWNED_FIELDS: Final[tuple[str, ...]] = ("name", "operating_mode", "mode_weights")

#: 비율 합계 비교 여유. `ESS._normalize_weights` 가 가중치 합에 쓰는 값과 같다 —
#: 둘 다 「사람이 적은 비율의 합이 1인가」를 재므로 문턱이 달라야 할 이유가 없다.
_FRACTION_TOLERANCE: Final[float] = 1e-9


@dataclass(frozen=True)
class ESSShare:
    """용량 몫 하나의 **선언** — 이름 · 비율 · 역할 하나 · 물량 표찰.

    **역할이 하나다.** 둘이면 그것은 몫 둘이며, 그렇게 세어야 몫마다 정격출력이
    옳게 걸린다. `mode_weights` 가 여기 없는 것이 그 뜻이다.

    `quantity_id` 는 이 몫이 화폐화하는 **물량의 이름**이다. 몫마다 달라야
    하며(`split_ess` 가 거부한다), 그 이름이 그대로 편익의
    `ValueStream.quantity_id` 가 되어 배타 판정의 물리량 축에 실린다
    (`core/valuestream/exclusion_table.py` 의 `_same_quantity_is_possible`).
    ★ **같은 표찰을 두 몫에 주면 배타 규칙이 몫을 구별하지 못한다** — 그것이
    이 자료형이 표찰을 필수로 받는 이유다.
    """

    name: str
    fraction: float
    operating_mode: ESSOperatingMode
    quantity_id: str


@dataclass(frozen=True)
class ESSSharePlan:
    """몫 선언과 그 몫으로 세운 `ESS` 를 **묶어서** 돌려준다.

    `ESS` 만 돌려주면 `quantity_id` 가 결과에서 사라지고, 호출측이 선언 목록과
    **순서로** 다시 짝지어야 한다 — 순서가 어긋나도 아무 예외가 나지 않는
    형태이며, 그 짝짓기가 곧 배타 판정의 표찰을 정하므로 조용히 틀리면
    **몫 둘이 서로의 물량을 주장한다.**
    """

    share: ESSShare
    resource: ESS


def _reject(field: str, reason: str, action: str) -> NoReturn:
    """몫 선언을 거부한다 — **원인과 조치를 함께 적는다** (`NFR-303`).

    `core/der/ess.py::_normalize_weights` 의 `reject` 와 같은 모양이다. `rule` 은
    비운다 — `§7.3` 대장에 몫 선언을 다루는 규칙이 아직 없고, 없는 ID 를 달면
    추적표가 그 규칙을 검증된 것으로 센다(`ValidationError` 독스트링).
    """
    raise ValidationError(field=field, reason=reason, action=action)


def _validate(shares: Sequence[ESSShare]) -> None:
    """몫 목록이 성립하는가 — 넷을 본다.

    넷째(**같은 `quantity_id`**)가 이 검사의 요점이다. 앞 셋은 수가 틀린 것을
    막지만, 넷째는 **배타 판정을 무력화하는 우회로**를 막는다 — 두 몫이 같은
    표찰을 달면 `collect_exclusions` 가 *「같은 물량일 수 있다」* 로 읽어 둘을
    한 물량으로 세거나, 반대로 표찰이 같다는 이유로 규칙이 몫을 구별하지
    못한다. 몫을 가르는 목적 자체가 **다른 물량을 다른 몫에 싣는 것**이므로,
    표찰이 같은 몫 둘은 애초에 몫 둘이 아니다.
    """
    if not shares:
        _reject(
            "ess_share.shares",
            "몫이 하나도 없습니다",
            "몫을 하나 이상 선언하십시오 — 몫이 없으면 무엇을 얼마로 가를지 정할 수 "
            "없습니다. 가르지 않을 것이라면 `ESS` 를 그대로 쓰십시오",
        )

    negative = [s.name for s in shares if s.fraction < 0.0]
    if negative:
        _reject(
            "ess_share.fraction",
            f"몫 비율이 음수입니다: {', '.join(negative)}",
            "모든 몫 비율을 0 이상으로 지정하십시오 — 음수 몫은 다른 몫의 정격출력을 "
            "원래 값보다 크게 만들고, 그렇게 커진 출력은 아무 검사에도 걸리지 않습니다",
        )

    total = math.fsum(s.fraction for s in shares)
    if abs(total - 1.0) > _FRACTION_TOLERANCE:
        _reject(
            "ess_share.fraction",
            f"몫 비율의 합이 1이 아닙니다 (합 {total})",
            "몫 비율의 합이 1이 되도록 지정하십시오 — 합이 1이 아니면 몫을 다 더한 "
            "용량·정격출력·고정 운영비가 실물과 달라집니다",
        )

    labels = [s.quantity_id for s in shares]
    duplicated = sorted({label for label in labels if labels.count(label) > 1})
    if duplicated:
        _reject(
            "ess_share.quantity_id",
            f"두 몫 이상이 같은 물량 표찰을 갖습니다: {', '.join(duplicated)}",
            "몫마다 서로 다른 `quantity_id` 를 지정하십시오 — 표찰이 같으면 배타 판정이 "
            "두 몫을 같은 물량으로 읽어 몫을 구별하지 못합니다. 같은 물량을 두 몫이 "
            "나눠 진다면 그것은 몫 둘이 아니라 하나입니다",
        )


def _prorate(total: float, fractions: Sequence[float]) -> tuple[float, ...]:
    """비율대로 나누고 **잔차를 마지막 몫에 가산**한다.

    마지막 몫은 곱셈이 아니라 **뺄셈**으로 얻는다 — 그래서 결과 합계는 정의상
    원래 값과 같다(부동소수에서 `0.1 + 0.2 != 0.3` 인 것과 같은 어긋남이
    용량·정격출력에 남지 않는다). 모듈 머리말의 잔차 규약이 여기서 수행된다.
    """
    head = [total * f for f in fractions[:RESIDUAL_HOLDER_INDEX]]
    return (*head, total - math.fsum(head))


def split_ess(
    spec: Mapping[str, Any],
    shares: Sequence[ESSShare],
) -> tuple[ESSSharePlan, ...]:
    """물리 `ESS` 의 **제원**과 몫 목록을 받아 **몫마다 `ESS` 하나**를 세운다.

    `spec` 은 `ESS(...)` 생성자에 그대로 넘길 수 있는 인자 묶음이다 — 인스턴스가
    아니라 제원을 받는 이유는, 이미 세워진 `ESS` 에서 비용 제원을 되읽으려면
    그 클래스의 **비공개 속성**(`_capex_unit`·`_fixed_om` 등)을 밖에서 열어야
    하고 그러면 이 모듈이 `core/der/ess.py` 의 내부 표현에 묶이기 때문이다.

    나누는 규약:

    | 제원 | 어떻게 |
    |---|---|
    | `PRORATED_FIELDS` 의 넷 | **몫 비율로 나눈다** — 자원 하나에 통째로 붙는 값이다 |
    | `capex_unit_won_per_kwh` · `rte_pct` · `soc_*` · 수명 제원 | **그대로 준다** |
    | `operating_mode` | 몫이 선언한 것 하나. `mode_weights` 는 **주지 않는다** |

    둘째 줄이 그대로인 이유는 **단위당·비율 값이기 때문**이다 — 몫으로 나누면
    단위당 단가가 몫만큼 싸지고 왕복효율이 몫만큼 떨어진다.

    ⚠ **`operating_mode`·`mode_weights`·`name` 은 몫 선언이 이긴다**
    (`_SHARE_OWNED_FIELDS`). 물리 제원에 그것들이 있어도 몫이 준 것으로 덮는다 —
    남겨 두면 `ESS._normalize_weights` 가 「단일 모드에 가중치를 줬다」로 거부하거나,
    더 나쁘게는 **몫 둘이 같은 이름**으로 서서 리포트에서 구별되지 않는다.

    몫 이름은 `«물리 자원 이름»/«몫 이름»` 이 된다. 물리 자원 이름을 지우지 않는
    이유는 리포트에서 **어느 배터리의 몫인지** 를 되짚을 수 있어야 하기 때문이다.

    ⚠ 비율 0 인 몫은 여기서 거부하지 않는다 — 갈린 용량이 0 이 되어
    `ESS` 생성자(`_positive`)가 *자기 필드 이름으로* 거부한다. 같은 거부를 두 곳에
    두면 어느 쪽이 판정했는지에 따라 필드 이름이 달라진다.
    """
    _validate(shares)

    # ⚠ 나뉜 제원도 여기서 빼 둔다 — 남기면 아래에서 같은 키를 두 번 넘겨
    # `TypeError` 가 나고, 그것은 검증 오류가 아니라 이 함수의 결함이다.
    replaced = (*_SHARE_OWNED_FIELDS, *PRORATED_FIELDS)
    base = {k: v for k, v in spec.items() if k not in replaced}
    physical_name = str(spec.get("name", "ESS"))
    fractions = [s.fraction for s in shares]
    prorated = {
        field: _prorate(float(spec[field]), fractions)
        for field in PRORATED_FIELDS
        if field in spec
    }

    plans = []
    for index, share in enumerate(shares):
        # 인자를 **한 묶음으로 모아** 넘긴다 — `**` 를 둘로 나눠 넘기면 두 묶음의
        # 값 타입이 서로 다르다는 이유로 `mypy` 가 자리마다 오류를 낸다(실측 7건).
        kwargs: dict[str, Any] = {
            **base,
            "name": f"{physical_name}/{share.name}",
            "operating_mode": share.operating_mode,
            **{field: values[index] for field, values in prorated.items()},
        }
        plans.append(ESSSharePlan(share=share, resource=ESS(**kwargs)))
    return tuple(plans)
