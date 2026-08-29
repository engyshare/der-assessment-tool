"""편익 금액을 **자원별 몫으로 가른다** — 4.3 의 귀속 (R43-E2).

## 왜 이 모듈이 생겼는가 — 표가 **자기가 적어 둔 성립 조건을 어기고 있었다**

4.3「자원별 수지」는 편익을 `line.tag in resource.produces` 로 자원에 실었고,
표 아래에 **스스로** 그 조건을 적었다 — *「이 표의 성립 조건 — 편익이 자원에
1:1 로 귀속될 때 (이 구성: PV→잉여판매 · ESS→첨두절감)」*.

그 조건이 기준 구성에서 **거짓이다.** 잉여 판매 754,820원의 근거 수량은 계통
송전 **18.80kWh** 인데, 붙임 7 대표일 13~16시를 보면 그중 **8.00kWh 는 저장장치
방전분**이다. 4.3 은 전액을 태양광 몫으로 적어 단순 회수를 태양광 **7.3년** ·
저장장치 **50.2년** 으로 인쇄했다 — 심의회에서 *「그럼 태양광만 하면 7년에
회수되는 것 아닌가」* 가 나오면 그 답이 틀린다.

## 왜 문면을 좁히지 않고 수량으로 갈랐는가

표가 *「1:1 이 아닐 수 있다」* 고 말하게 하는 안을 버렸다. 그것은 **틀린 귀속을
그대로 인쇄한 채 각주로 면책하는 것**이며, 이 저장소에는 각주로 면책한 문장이
낡아 거짓이 된 사례가 `method_sections.py` 한 파일에만 둘 있다(R34 의 「고정
운영비」 · R39-E 의 「교체 · 잔존가치 미포함」). 규약은 *「문장으로 박지 않고
실린 항목에서 짓는다」* 다.

⚠ **화폐화를 건드리지 않는다.** 여기서 바뀌는 것은 **이미 난 돈을 누구 몫으로
적는가** 뿐이며, 어느 편익을 켜고 끌지는 사람 판정이다
(`docs/evidence/판정요구-이중계상-2026-08-29.md`). 그래서 연 편익 합계도 NPV 도
움직이지 않는다 — 그 불변이 이 모듈의 항등식이다.

## 무엇이 안분 대상인가 — **편익이 선언한다**

`scales_with_dispatch_window` 가 참인 편익은 금액이 **계통 송전 창**에서 나온다
(러너가 `grid_export_result` 를 넘긴다). 그 수량이 자원별로 나뉘므로 금액도 같은
비율로 나뉜다. 거짓인 편익은 그 창을 읽지 않으므로(첨두 절감의 수량은
`ESS.reducible_peak_kw()` 에서 온다) **선언된 자원에 전액** 간다.

여기에 태그 목록을 두지 않은 것이 요점이다 — 목록은 편익이 늘 때 낡는다.
연간화 규약(`e2e_runner.py` 의 `scales_with_dispatch_window` 분기)이 같은 근거로
선언을 쓴다.

## 잔차 규약 — **합계는 원 단위로 보존된다**

몫마다 `to_won()` 으로 반올림하면 합이 원액과 1원 어긋날 수 있다(`NFR-103-M1`).
잔차는 `core/asset/common_asset.py` 가 공통설비 안분에서 이미 정한 규약 그대로
**최종 몫**에 가산한다 — 그 파일의 상수를 import 하지 않는 이유는 받는 쪽이
가구가 아니라 자원이어서 같은 값을 공유할 대상이 아니기 때문이며, **규약이
같다는 사실은 이 문단이 갖는다.**
"""
from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from decimal import Decimal

from core.casegrid.models import BenefitAttribution, BenefitLine, ResourceLine
from core.contracts.engine import SystemDispatch
from core.contracts.units import to_won

#: 반올림 잔차를 받는 몫의 인덱스. **-1(최종 몫)로 고정한다** — 상수로 두는
#: 이유는 검사와 설명이 같은 값을 참조하게 하기 위해서다
#: (`common_asset.RESIDUAL_HOLDER_INDEX` 와 같은 규약이며 대상만 다르다).
RESIDUAL_HOLDER_INDEX = -1

#: 안분 근거가 없을 때의 문면 — **「전액 귀속」과 구별한다.** 둘을 한 문면으로
#: 적으면 *「가르지 않기로 했다」* 와 *「가를 수 없었다」* 가 표에서 같아 보인다.
NO_EXPORT_NOTE = "계통 송전 0kWh · 수량으로 가를 근거가 없다"

#: 창을 읽지 않는 편익의 문면. 근거를 적어 두지 않으면 4.3 이 「1:1」을 다시
#: 문장으로 박게 된다.
WHOLE_NOTE = "계통 송전 창을 읽지 않는다"


def export_share_kwh(dispatch: SystemDispatch) -> dict[str, float]:
    """계통 송전량을 자원별로 가른다 — **송전이 난 스텝의 양의 출력 비례.**

    ⚠ **스텝마다 가른다.** 하루 합계끼리 비례배분하면 심야 충전(음수)과 주간
    발전이 상쇄된 뒤의 수로 나누게 되고, 그러면 **송전이 없던 시각의 출력이
    송전 몫을 받는다.** 대표일 13~16시에만 저장장치가 방전하는 이 구성에서
    그 차이가 그대로 금액이 된다.

    ⚠ **음수는 0으로 클램프한다** — 부호 규약상 음수는 받아들임(충전·소비)이며
    송전을 만들지 않는다(`DispatchHour` 독스트링의 부호 규약). 클램프하지
    않으면 충전 중인 자원이 **음수 몫**을 받아 다른 자원의 몫이 100%를 넘는다.
    """
    share = {name: 0.0 for name in dispatch.per_resource}
    for step, exported in enumerate(dispatch.grid_export):
        if exported <= 0.0:
            continue
        positive = {
            name: max(result.electric[step], 0.0)
            for name, result in dispatch.per_resource.items()
        }
        produced = math.fsum(positive.values())
        if produced <= 0.0:
            continue
        for name, value in positive.items():
            share[name] += exported * value / produced
    return share


def _split_with_residual(
    total_won: int, weights: Sequence[float]
) -> tuple[int, ...]:
    """가중치대로 나누고 **반올림 잔차를 최종 몫에 가산**한다.

    각 몫은 `to_won()` 한 곳에서만 반올림되고(`NFR-103` 경계 정의), 잔차는
    원액에서 반올림된 몫의 합을 뺀 값이므로 **결과 합계는 정의상 원액과
    정확히 같다.**
    """
    weight_total = math.fsum(weights)
    shares = [
        int(to_won(Decimal(total_won) * Decimal(str(w)) / Decimal(str(weight_total))))
        for w in weights
    ]
    shares[RESIDUAL_HOLDER_INDEX] += total_won - sum(shares)
    return tuple(shares)


def attribute_benefits(
    benefits: Sequence[BenefitLine],
    *,
    dispatch: SystemDispatch,
    export_window_tags: Collection[str],
    resources: Sequence[ResourceLine],
) -> tuple[BenefitAttribution, ...]:
    """편익 갈래마다 **어느 자원이 얼마를 벌었는가**를 낸다.

    *export_window_tags* 는 `scales_with_dispatch_window` 가 참인 편익의 태그다
    — 여기서 목록을 짓지 않고 **호출측이 편익의 선언에서 모아 넘긴다**(위
    머리말).

    ⚠ **창을 읽지 않는 편익은 종전 귀속을 그대로 쓴다** — `resource.produces`
    조인이다. 그 자리에서는 선언이 아직 참이고(첨두 절감은 저장장치가 혼자
    만든다), 짧은 코드→자원 이름 대응표를 여기 새로 적으면 **같은 대응이
    저장소에 셋이 되어** 그중 하나가 낡는다(R43-B 가 이름을 갈라 둔 이유).

    ⚠ **자원 이름으로 싣는다** — 4.3 이 `ResourceLine` 과 조인하는 키가 이름
    이기 때문이며, 짧은 코드를 그대로 실으면 그 조인이 **빈 교집합**이 된다.
    """
    share = export_share_kwh(dispatch)
    exporting = [(name, kwh) for name, kwh in share.items() if kwh > 0.0]
    exported_total = math.fsum(kwh for _, kwh in exporting)

    rows: list[BenefitAttribution] = []
    for line in benefits:
        if line.tag in export_window_tags and exporting:
            amounts = _split_with_residual(
                line.annual_won, [kwh for _, kwh in exporting]
            )
            rows += [
                BenefitAttribution(
                    tag=line.tag,
                    resource_name=name,
                    annual_won=amount,
                    basis_note=(
                        f"계통 송전 {kwh:,.2f}kWh / {exported_total:,.2f}kWh "
                        f"· {kwh / exported_total:.1%}"
                    ),
                )
                for (name, kwh), amount in zip(exporting, amounts, strict=True)
            ]
            continue
        rows.append(
            BenefitAttribution(
                tag=line.tag,
                resource_name=next(
                    (r.name for r in resources if line.tag in r.produces), ""
                ),
                annual_won=line.annual_won,
                basis_note=(
                    NO_EXPORT_NOTE if line.tag in export_window_tags else WHOLE_NOTE
                ),
            )
        )
    return tuple(rows)
