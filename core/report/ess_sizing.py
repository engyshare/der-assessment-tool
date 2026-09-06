"""ESS 적정용량 역산 (경우 「ESS」 · 겨울 하루의 결손) — R64/WP-8a.

## 왜 이 모듈이 생겼는가

`docs/적정용량-산출방법-검토.md` §5-④ 가 이 경우에 대해 *「다루지 않는다」* 고
적어 두었다. PV 에는 역산이 있고(`core/report/sizing.py` · 경우 「가」 · 리포트
붙임 10) `core/der/ess.py::ESS.usable_capacity_kwh` 에 정방향 산식
(`정격용량 × (SOC상한 − SOC하한) × SOH × (1 − 백업예비)`)도 있었는데, 그 둘을 잇는
**역함수**가 저장소 어디에도 없었다. 이 모듈이 채우는 것이 그 자리다: 겨울철 하루의
시각별 결손을 ESS 방전만으로 감당하는 데 필요한 **최소 저장용량(kWh)과 최소
정격출력(kW)** 을 역산한다.

## 왜 `sizing.py` 에 넣지 않고 새 모듈로 뽑았는가

`sizing.py` 는 경우 「가」의 모듈이고 그것이 재는 축은 **연간 총량**이다 — 입력이
스칼라 하나(연간 부하 kWh)이고 나오는 것도 스칼라 하나(kW)다. 이 모듈이 재는 축은
**하루 안의 시각별 형상**이다 — 입력이 시계열 둘이고 나오는 것이 둘(kWh 와 kW)이며,
그 둘은 **같은 시계열의 다른 통계**(합과 첨두)에서 나온다. 재는 축도 입력의 모양도
다르므로 한 모듈에 두면 「어느 함수가 어느 경우의 것인가」를 이름으로 가려야 하고,
그러면 다음 경우가 붙을 때마다 그 접두사가 길어진다. 이 저장소가 이미 네 번 쓴
방법이다 — `pv_allocation.py` · `ess_build.py` · `household_scale.py` ·
`ess_schedule.py`.

## 이 모듈이 답하지 않는 것 — 「겨울이 얼마인가」

검토서 §5-③ 이 *「겨울철 부하 프로파일 — 없다」* 라고 적고, 그 말은 지금도 맞다.
자산(`fixtures/profiles/representative-day.yaml`)의 계절 넷은 **가정값**이며
(`docs/decisions-2026-09-06-R64.md` §2), 참고 자료로 쓴 엑셀의 계절 몫도 사용자가
*「가정한 값임」* 이라고 못 박았다. **그러므로 이 모듈은 「겨울이 얼마인가」를 고르지
않는다** — 시각별 부하와 시각별 PV 발전을 **인자로만** 받아 역산할 뿐이고, 기본값으로
겨울 프로파일을 박아 두지 않는다. `sizing.py` 가 이용률에 대해 취한 태도와 같다.

## 탐색 구간을 넓히지 않는다

역산 용량이 `core/casegrid/ledger_levels.py::_DESIGN_VARS` 의 `ess_capacity_kwh`
탐색 상한을 넘을 수 있다 — 그때 이 모듈은 구간을 넓히지 않고
`within_search_range=False` 를 **값으로** 싣는다. 구간을 넓히는 것은 결론축
(`core/report/capacity.py` 의 4.4 적정 용량 검토)이 훑는 폭 자체를 바꾸는 일이라 이 WP
밖이고, 넘는 점을 지우지도 않는다 — `sizing.py` 머리 독스트링 셋째 절과 같은 태도다.

## 충전측 손실(RTE)을 여기서 다시 세지 않는다

`usable_capacity_kwh` 는 이미 **낼 수 있는 양**을 낸다. 그 위에 왕복효율을 또 곱하면
「어디서 한 번 세는가」가 두 곳에 산다. `ESS` 는 왕복손실을 **충전 측**에 싣는 관례이고
(`ESS.annual_charge_kwh` = 방전량 / RTE), 그 자리는 이 모듈이 아니다. ⇒ 역산은
**낼 수 있는 양** 기준으로 하고, 그 용량을 채우는 데 드는 충전 전력량은 이 모듈 밖이다.

## 결손을 음수로 상계하지 않는다

시각별 결손은 `max(0, 부하 − PV)` 다. 낮에 남은 PV 를 저녁 결손에서 빼면 **저장 없이
시간을 건너뛴 것**이 되어 ESS 를 세우는 이유 자체가 사라진다 — 남은 PV 가 저녁에
쓰이려면 그것을 담을 용량이 있어야 하고, 그 용량이 바로 여기서 구하는 값이다.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from core.contracts.validation import ValidationError


class UsableCapacityKwh(Protocol):
    """정격용량과 연차를 주면 **그 해 낼 수 있는 양**(kWh)을 돌려주는 함수.

    `core/der/ess.py::ESS.usable_capacity_kwh` 를 그 자원의 용량에 대해 여는
    모양이며, 호출측이 다음처럼 싸서 넘긴다::

        def usable(*, capacity_kwh: float, year: int) -> float:
            return ESS(name="탐침", capacity_kwh=capacity_kwh, power_kw=..., ...
                       ).usable_capacity_kwh(year=year)

    **왜 `ESS` 를 직접 받지 않는가.** ① 이 모듈은 「사용 가능 비율」을 스스로 짓지
    않고 정방향 함수에 되물어 얻는데, 되물으려면 **용량을 바꿔 가며** 부를 수 있어야
    한다 — 인스턴스 하나로는 그 인스턴스의 용량밖에 물을 수 없다. ② 산식을 여기에
    옮겨 적으면 그 사본이 정본과 갈리는 날 **아무 오류 없이** 용량만 조용히 달라진다.
    ③ `core.report` 가 `core.der` 를 import 해도 계층 계약(NFR-208-AC1)에는 걸리지
    않으나, 지금 `core/report/` 어느 파일도 그 변을 갖고 있지 않다 — 배선하지 않는
    WP 에서 새 의존 변을 긋지 않는다.
    """

    def __call__(self, *, capacity_kwh: float, year: int) -> float: ...


#: 역산 결과를 정방향 함수에 되먹여 **미달을 올릴 때** 허용하는 최대 자리 수.
#: 필요한 것은 실측상 한 자리이고(모듈 아래 `required_ess_capacity_kwh` 독스트링),
#: 넉넉히 잡되 무한 루프가 되지 않게 막는다.
_MAX_ULP_STEPS: Final[int] = 64


def shortfall_kwh_by_step(
    *,
    load_kwh_by_step: Sequence[float],
    pv_kwh_by_step: Sequence[float],
) -> tuple[float, ...]:
    """시각별 결손 = `max(0, 부하 − PV)` — **음수로 상계하지 않는다**.

    두 시계열은 같은 길이여야 하고 둘 다 음수를 담을 수 없다. 못 세우는 입력은
    잘라내거나 0으로 메우지 않고 **3요소로 거부한다**(NFR-303) — 조용히 맞추면
    「몇 시간이 사라졌는가」가 아무데도 남지 않는다.
    """
    if not load_kwh_by_step:
        raise ValidationError(
            field="ess.load_profile_kwh",
            reason="시각별 부하가 비어 있어 역산할 하루가 없습니다",
            action="한 스텝 이상의 시각별 부하(kWh)를 지정하십시오",
        )
    if len(load_kwh_by_step) != len(pv_kwh_by_step):
        raise ValidationError(
            field="pv.generation_profile_kwh",
            reason=(
                f"시각별 PV 발전의 길이({len(pv_kwh_by_step)})가 "
                f"시각별 부하의 길이({len(load_kwh_by_step)})와 다릅니다"
            ),
            action="두 시계열을 같은 시간 해상도로 맞춰 같은 길이로 지정하십시오",
        )
    for label, field_name, profile in (
        ("부하", "ess.load_profile_kwh", load_kwh_by_step),
        ("PV 발전", "pv.generation_profile_kwh", pv_kwh_by_step),
    ):
        negatives = [i for i, value in enumerate(profile) if value < 0.0]
        if negatives:
            first = negatives[0]
            raise ValidationError(
                field=field_name,
                reason=(
                    f"시각별 {label}에 음수가 {len(negatives)}개 있습니다 "
                    f"(첫 자리 {first}번 스텝의 {profile[first]})"
                ),
                action=f"시각별 {label}(kWh)을 0 이상의 값으로 고치십시오",
            )
    return tuple(
        max(0.0, load - pv) for load, pv in zip(load_kwh_by_step, pv_kwh_by_step, strict=True)
    )


def required_ess_capacity_kwh(
    *,
    required_discharge_kwh: float,
    usable_capacity_kwh: UsableCapacityKwh,
    year: int,
) -> float:
    """그 방출 에너지를 낼 수 있는 **최소 정격용량**(kWh).

    `ESS.usable_capacity_kwh` 의 **역함수**다 — 그 함수가 정격용량에 곱하는 것
    (`(SOC상한 − SOC하한) × SOH × (1 − 백업예비)`)을 **여기에 옮겨 적지 않고**
    정격용량 1kWh 로 한 번 불러 얻는다. 그 곱은 용량에 비례하지 않는 항만으로 이루어져
    있어 1kWh 에서 읽은 값이 곧 비율이다.

    ⚠ **연차를 필수 인자로 받는다.** SOH 가 해마다 떨어지므로 같은 정격용량이
    20년차에는 덜 낸다 — 기본값을 두면 「어느 해에 그 결손을 감당하는가」가 조용한
    가정이 된다.

    ## 나눗셈이 아래로 떨어지는 것을 되먹여 올린다

    `필요 방출 / 비율` 을 그대로 내면 **부동소수 반올림 때문에 그 용량이 실제로는
    미달**일 수 있다. 실측했다 — SOC 창과 연차를 무작위로 흔든 표본 200,000건 중
    **34,289건**에서 역산 용량으로 세운 `ESS` 의 `usable_capacity_kwh` 가 필요
    방출량보다 작았다(최대 상대 미달 3.56e-16). 「최소 용량」이 미달을 내면 그것은
    반올림 오차가 아니라 **틀린 답**이므로, 결과를 정방향 함수에 되먹여 미달이면 한
    자리씩 올린다. 반대로 넘친 한 자리를 깎지는 않는다 — 그 차이는 표현 가능한 마지막
    한 자리이고, 깎아도 답이 더 「최소」가 되지 않으면서 호출만 두 배가 된다.
    """
    if required_discharge_kwh < 0.0:
        raise ValidationError(
            field="ess.required_discharge_kwh",
            reason=f"필요 방출 에너지는 0 이상이어야 합니다 (받은 값 {required_discharge_kwh})",
            action="필요 방출 에너지(kWh)를 0 이상의 값으로 지정하십시오",
        )
    if required_discharge_kwh == 0.0:
        return 0.0

    unit_kwh = usable_capacity_kwh(capacity_kwh=1.0, year=year)
    if unit_kwh <= 0.0:
        raise ValidationError(
            field="ess.usable_capacity_kwh",
            reason=(
                f"{year}년차에 정격용량 1kWh 가 낼 수 있는 양이 {unit_kwh} 입니다 "
                "(SOC 창, SOH, 백업 예비의 곱이 0 이하입니다)"
            ),
            action=(
                "SOC 상한과 하한의 간격을 넓히거나, 백업 예비율을 낮추거나, "
                "SOH 가 남아 있는 연차를 지정하십시오"
            ),
        )

    capacity_kwh = required_discharge_kwh / unit_kwh
    for _ in range(_MAX_ULP_STEPS):
        if usable_capacity_kwh(capacity_kwh=capacity_kwh, year=year) >= required_discharge_kwh:
            return capacity_kwh
        capacity_kwh = math.nextafter(capacity_kwh, math.inf)
    raise RuntimeError(
        f"역산 용량 {capacity_kwh} kWh 를 {_MAX_ULP_STEPS} 자리 올려도 필요 방출 "
        f"{required_discharge_kwh} kWh 에 닿지 않습니다 — 넘겨받은 usable_capacity_kwh 가 "
        "정격용량에 대해 단조 증가가 아닙니다"
    )


def required_ess_power_kw(
    *,
    shortfall_by_step_kwh: Sequence[float],
    step_hours: float,
) -> float:
    """그 결손 형상을 따라가는 데 필요한 **최소 정격출력**(kW).

    첨두 스텝의 결손을 그 스텝의 시간으로 나눈다. ⚠ **저장용량과 달리 이 값은 시간
    해상도에 따라 커진다** — 한 시간을 둘로 쪼개면 에너지 합은 그대로지만 첨두는
    쪼갠 안쪽의 편차만큼 올라간다. 둘을 한 값으로 뭉치면 정격출력이 조용히 작아진다.
    """
    if step_hours <= 0.0:
        raise ValidationError(
            field="timeseries.step_hours",
            reason=f"한 스텝의 시간은 0보다 커야 합니다 (받은 값 {step_hours})",
            action="한 스텝의 시간(h)에 0보다 큰 값을 지정하십시오",
        )
    if not shortfall_by_step_kwh:
        return 0.0
    return max(shortfall_by_step_kwh) / step_hours


@dataclass(frozen=True)
class ESSDailySizing:
    """겨울 하루 결손에 대한 ESS 역산 결과 한 벌."""

    #: 어느 해에 이 결손을 감당하는가 — SOH 가 해마다 떨어지므로 답이 달라진다.
    year: int
    #: 한 스텝의 시간(h). 24스텝 대표일이면 1.0, 48스텝이면 0.5.
    step_hours: float
    #: 시각별 결손. **역산에서 사라지지 않는다** — 어느 시각이 얼마나 모자랐는지를
    #: 다음 WP(배선)와 리포트가 그대로 읽는다.
    shortfall_by_step_kwh: tuple[float, ...]
    #: 하루치 필요 방출 에너지 = 시각별 결손의 합.
    required_discharge_kwh: float
    #: 첨두 스텝의 결손(kWh) — `required_power_kw` 가 이것에서 나온다.
    peak_shortfall_kwh: float
    required_capacity_kwh: float
    required_power_kw: float
    search_low_kwh: float
    search_high_kwh: float
    #: 역산 용량이 지금 탐색 구간(`ess_capacity_kwh`) 안에 있는가.
    #: **밖이면 구간을 넓히지 않고 「밖이다」를 싣는다** — 구간을 움직이면 결론축이
    #: 움직인다.
    within_search_range: bool


def build_ess_daily_sizing(
    *,
    load_kwh_by_step: Sequence[float],
    pv_kwh_by_step: Sequence[float],
    step_hours: float,
    usable_capacity_kwh: UsableCapacityKwh,
    year: int,
    search_low_kwh: float,
    search_high_kwh: float,
) -> ESSDailySizing:
    """하루치 시각별 부하와 PV 발전에서 필요 저장용량과 정격출력을 한 번에 역산한다.

    `load_kwh_by_step` 과 `pv_kwh_by_step` 은 **같은 하루를 같은 해상도로** 적은
    시계열이고, `step_hours` 는 그 한 스텝의 길이다 — 24스텝 대표일이면 1.0 이다.
    「그 하루가 겨울인가」는 이 함수가 판정하지 않는다(머리 독스트링 셋째 절).
    """
    if search_low_kwh > search_high_kwh:
        raise ValidationError(
            field="ess.capacity_kwh",
            reason=(
                f"탐색 구간 하한({search_low_kwh})이 상한({search_high_kwh})보다 큽니다"
            ),
            action="search_low_kwh 를 search_high_kwh 이하의 값으로 지정하십시오",
        )
    shortfall = shortfall_kwh_by_step(
        load_kwh_by_step=load_kwh_by_step, pv_kwh_by_step=pv_kwh_by_step
    )
    required_discharge_kwh = math.fsum(shortfall)
    required_power_kw = required_ess_power_kw(
        shortfall_by_step_kwh=shortfall, step_hours=step_hours
    )
    required_capacity_kwh = required_ess_capacity_kwh(
        required_discharge_kwh=required_discharge_kwh,
        usable_capacity_kwh=usable_capacity_kwh,
        year=year,
    )
    return ESSDailySizing(
        year=year,
        step_hours=step_hours,
        shortfall_by_step_kwh=shortfall,
        required_discharge_kwh=required_discharge_kwh,
        peak_shortfall_kwh=max(shortfall),
        required_capacity_kwh=required_capacity_kwh,
        required_power_kw=required_power_kw,
        search_low_kwh=search_low_kwh,
        search_high_kwh=search_high_kwh,
        within_search_range=search_low_kwh <= required_capacity_kwh <= search_high_kwh,
    )
