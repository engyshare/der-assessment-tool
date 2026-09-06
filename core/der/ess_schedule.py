"""ESS 대표일 계획 — **시각별로 얼마나 넣고 빼는가** (`core/der/ess.py` 에서 갈랐다).

## 왜 갈랐나 — 코드 499/500

`core/der/ess.py` 는 R64/WP-6a 착수 시점에 **코드 499줄 / 상한 500줄**이었다
(`scripts/check_file_size.py --code-strict` 실측, 2026-09-06). 코드 줄 여유가
**한 줄**이라 이 라운드가 세우는 방전 배분 갈래를 그 파일 안에 둘 수 없었다.
⛔ **상한을 올려 푸는 것은 금지다**(NFR-206 · spec §16.5 절차). 같은 이유로 이
저장소가 이미 세 번 같은 방법을 썼고 — `core/casegrid/pv_allocation.py`(R51/WP-5) ·
`core/casegrid/ess_build.py`(R57/WP-5) · `core/casegrid/household_scale.py`(R64/WP-1)
— 이 모듈은 그 넷째다.

## 무엇을 모았나 — **밖에서 받는 시계열 둘**과 그것으로 짓는 대표일 계획

`ESS` 는 형제 구획을 import 할 수 없으므로(NFR-208-AC2) PV 도 부하도 참조하지
않고 **시계열로 받는다.** 그 시계열이 이제 둘이다.

    충전 쪽   `pv_surplus_profile_kwh`   시각별 PV 잉여 kWh   (판정 A-3)
    방전 쪽   `load_profile_kwh`         시각별 가구 부하 kWh (R64/WP-6a · 요구 5)

둘의 **형태 검사**와 둘로 짓는 **시각별 계획**을 한자리에 둔다. 따로 두면 같은
모양의 거부문이 두 파일에 갈려 한쪽만 고쳐지는 표류가 생긴다.

⚠ **충전 쪽은 옮겨온 것이고 행동이 한 줄도 바뀌지 않았다.**
`ESS._check_pv_surplus` · `ESS._pv_surplus_charge_kwh_by_hour` 는 이 모듈을 부르는
**얇은 위임**으로 남는다 — 그 두 이름을 `core/casegrid/pv_allocation.py` 와
`tests/casegrid/test_ess_build.py` · `tests/casegrid/test_pv_surplus_allocation_priority.py`
의 문면이 가리키므로 이름을 없애지 않았다.

## 방전 배분 두 갈래 — 사용자 요구 5

사용자 요구 5 는 *「ESS는 가구의 전력 수요를 **최우선적으로 대응**할 수 있도록
운전되야 함」* 이다. 그런데 종전 방전은 방전창(`ESS.discharge_hours`) 안의 모든
시각에 **같은 양**을 실었다 — 수요가 0인 시각에도, 수요가 몰린 시각에도 같다.
「대응」이 *수요가 있는 시각에 낸다* 는 뜻이므로 고정 창 균등 분배는 그 요구를
만족하지 않는다. 그래서 배분을 **고를 수 있는 축**으로 세운다.

    고정 창(기본값)   방전창 안에서 균등 — 종전 그대로
    부하 추종         방전창 안에서 **그 시각의 부하에 비례**

★ **기본값은 고정 창이다.** 기본값을 바꾸면 이 축을 모르는 기존 호출자 전부의
수가 조용히 움직인다 — `pv_surplus_profile_kwh` 옆의 `charge_source` 가 `GRID`
를 기본값으로 남긴 것과 같은 이유다. 골든 회귀(`tests/golden/`)가 그 동일성을
잰다.

★ **바뀌는 것은 배분뿐이다 — 창은 그대로다.** 부하 추종도 `discharge_hours`
**안에서** 나눈다. 창 밖으로 나가면 `pv_surplus_charge_kwh_by_hour` 가 「방전창을
뺀 시각에 충전한다」로 짓는 충전 계획과 서로를 참조하게 되어(방전창이 부하로
정해지고, 그 방전창이 다시 충전창을 정한다) 계획이 순환한다. 하루 방전 **총량**도
그대로다 — 달라지는 것은 그 총량을 시각에 나누는 방법 하나뿐이다.

## ★★ 판정 — 비례 배분이 정격출력을 넘으면 **잘라내지 않고 다시 나눈다**

부하가 한 시각에 몰리면 비례 배분이 정격출력을 넘을 수 있다. 세 길이 있었다.

    ⓐ 잘라낸다        ⛔ 그만큼의 방전이 사라지는데 편익은 남는다 — 이 파일이
                      `ESS._check_power` 독스트링에 *「잘라내면 없는 출력으로
                      편익이 난다」* 로 이미 못 박은 것을 정면으로 어긴다.
    ⓑ 거부한다        정직하지만 **부하 추종이 가장 필요한 경우**(저녁 한두
                      시각에 수요가 몰린 가구)에 이 갈래를 못 쓰게 만든다.
    ⓒ 다시 나눈다 ✅  넘는 시각을 **정격에 묶고**, 남은 에너지를 나머지 시각에
                      다시 부하 비례로 나눈다(물채우기).

⇒ **ⓒ 를 골랐다.** 하루 방전 총량이 **정확히** 보존되고(잘라낸 에너지가 없다),
정격출력을 **한 시각도** 넘지 않으며, 부하가 큰 시각이 여전히 더 많이 낸다.
ⓐ 와 다른 점은 **에너지가 사라지지 않는다**는 것이다 — 묶인 시각의 몫은 없어지지
않고 다른 시각으로 간다.

⚠ **그래도 못 담으면 거부한다.** 부하가 있는 시각을 전부 정격까지 채우고도 남으면
둘 곳이 없다 — 그때는 부하가 0인 시각에 몰래 싣지 않고(그것은 「수요에 대응했다」가
거짓이 된다) **3요소로 거부한다.**
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum
from typing import Final, NoReturn

from core.contracts.units import ENERGY_TOLERANCE_KWH
from core.contracts.validation import ValidationError

HOURS_PER_DAY: Final[int] = 24
#: 부동소수 비교 여유. kW 비교이므로 에너지 허용오차(kWh)와 구분해 둔다.
#: 시각별 계획은 1시간 몫이라 「그 시각의 kWh」와 「그 시각의 평균 kW」가 수로는
#: 같다 — 상한 비교에 이 여유를 그대로 쓴다.
KW_TOLERANCE: Final[float] = 1e-9


class ESSDischargeAllocation(StrEnum):
    """하루 방전량을 방전창 안에서 **어떻게 나누는가** (R64/WP-6a · 사용자 요구 5).

    값이 한국어인 것은 `ESSOperatingMode`·`ESSChargeSource` 와 같은 이유다 —
    케이스 그리드가 문자열로 축을 건네고, 그 문자열이 그대로 화면·리포트에 뜬다.
    """

    #: 종전 동작 — 방전창 안의 모든 시각에 같은 양. **기본값이며 바꾸지 않는다.**
    FIXED_WINDOW = "고정 창"
    #: 그 시각의 가구 부하에 비례. 부하 시계열이 있어야 고를 수 있다.
    LOAD_FOLLOWING = "부하 추종"


DISCHARGE_ALLOCATIONS: Final[tuple[ESSDischargeAllocation, ...]] = tuple(ESSDischargeAllocation)


def coerce_discharge_allocation(
    value: ESSDischargeAllocation | str, *, name: str
) -> ESSDischargeAllocation:
    """문자열을 방전 배분 열거값으로 승격하고 목록 소속을 검사한다.

    `ESS._coerce_charge_source()` 와 같은 모양이다 — 케이스 그리드가 문자열로
    축을 건넬 수 있어야 한다(`FR-105-AC5` 가 운전 방법에 대해 세운 관례).

    ⚠ **규칙 ID 를 비운다.** `DV-14` 는 「운전 방법이 선언 목록에 속함」이고 방전
    배분은 그 규칙이 아니다 — 충전원이 같은 이유로 규칙 ID 를 비웠다.
    """
    try:
        return ESSDischargeAllocation(value)
    except ValueError as e:
        allowed = ", ".join(a.value for a in DISCHARGE_ALLOCATIONS)
        raise ValidationError(
            field="ess.discharge_allocation",
            reason=f"{name}: 선언되지 않은 방전 배분입니다: {value!r}",
            action=f"ESS 방전 배분을 다음 중 하나로 고르십시오 — [{allowed}]",
        ) from e


def _reject_load_profile(reason: str, action: str) -> NoReturn:
    """부하 시계열 거부 넷을 한 곳으로 모은다(코드 스프롤 방지, NFR-206).

    이 모듈의 `_reject_pv_surplus_profile` 과 같은 모양이되 **`action` 문면이
    다르다** — 저쪽은 *「`pv_surplus_profile_kwh` 에 … 를 지정하십시오」* 라
    **화면 사용자가 할 수 없는 조치**를 시킨다(R64/WP-6a 실측. 그 문면은 옮겨오면서
    한 글자도 바꾸지 않았다 — 고치면 이설이 아니라 변경이 된다). 여기서는 파이썬
    인자 이름이 아니라 **사람이 화면에서 하는 일**로 적는다.
    """
    raise ValidationError(field="ess.load_profile_kwh", reason=reason, action=action)


def check_load_profile(
    allocation: ESSDischargeAllocation,
    profile: Sequence[float] | None,
    discharge_hours: Sequence[int],
    *,
    name: str,
) -> tuple[float, ...] | None:
    """방전 배분과 부하 시계열의 **조합·형태**를 검사한다.

    ⛔ **조용히 고정 창으로 되돌아가지 않는다.** 부하 추종을 골랐는데 부하가
    없으면 거부한다 — 되돌아가면 리포트의 *「부하 추종으로 돌았다」* 가 거짓이
    되고, 그 거짓은 결과 어디에도 남지 않는다.

    거부 넷: ① 고정 창인데 부하 시계열을 받음 ② 부하 추종인데 없거나 전부 0
    ③ 24행이 아님 ④ 방전 시간대 안의 부하가 전부 0.
    """
    if allocation is ESSDischargeAllocation.FIXED_WINDOW:
        if profile is not None:
            _reject_load_profile(
                f"{name}: 방전 배분이 「{allocation.value}」인데 부하 시계열을 받음",
                f"ESS 방전 배분을 「{ESSDischargeAllocation.LOAD_FOLLOWING.value}」로 "
                "고르거나, 부하 시계열 입력을 비우십시오 — 「고정 창」은 정해진 "
                "시간대에 똑같이 나누므로 부하를 보지 않습니다",
            )
        return None

    if profile is None or not any(v > 0.0 for v in profile):
        _reject_load_profile(
            f"{name}: 방전 배분이 「{allocation.value}」인데 부하 시계열이 없거나 전부 0입니다",
            "시나리오에 가구 전기부하를 넣어 시각별 사용량이 나오게 하거나, ESS 방전 "
            f"배분을 「{ESSDischargeAllocation.FIXED_WINDOW.value}」으로 되돌리십시오 — "
            "부하가 없으면 「수요에 맞춰 낸다」가 가리킬 대상이 없습니다",
        )
    if len(profile) != HOURS_PER_DAY:
        _reject_load_profile(
            f"{name}: 부하 시계열은 {HOURS_PER_DAY}행이어야 합니다(받은 값 {len(profile)}행)",
            f"부하 자료를 하루 {HOURS_PER_DAY}시각(0~23시) 한 행씩으로 맞추십시오 — 더 "
            "잔 간격으로 재었다면 시각별로 합쳐 넣습니다",
        )
    if not any(profile[hour] > 0.0 for hour in discharge_hours):
        window = ", ".join(f"{hour}시" for hour in discharge_hours)
        _reject_load_profile(
            f"{name}: 방전 시간대({window})의 부하가 전부 0이라 무엇에 맞춰 낼지 정해지지 "
            "않습니다",
            "방전 시간대가 가구가 실제로 쓰는 시각과 겹치는 운전 방법으로 바꾸거나(예: "
            f"「자가소비 우선」), ESS 방전 배분을 「{ESSDischargeAllocation.FIXED_WINDOW.value}」"
            "으로 되돌리십시오",
        )
    return tuple(float(v) for v in profile)


def _reject_pv_surplus_profile(reason: str, action: str) -> NoReturn:
    """PV 잉여 시계열 거부 셋을 한 곳으로 모은다(코드 스프롤 방지, NFR-206)."""
    raise ValidationError(field="ess.pv_surplus_profile_kwh", reason=reason, action=action)


def check_pv_surplus_profile(
    profile: Sequence[float] | None, *, uses_pv_surplus: bool, name: str
) -> tuple[float, ...] | None:
    """`charge_source` 와 `pv_surplus_profile_kwh` 의 조합·형태만 검사한다
    (판정 §1 · A-8-d).

    ⚠⚠ **「시각별 충전량이 잉여를 넘으면 거부」는 판정 A-8-b 로 없어졌다** —
    모자라면 거부가 아니라 「가능한 만큼」 충전한다(`pv_surplus_charge_kwh_by_hour`
    가 그 계획을 짓는다). 여기 남는 것은 판정 §1 이 요구하는 **형태 검사 넷**뿐이다.

    ⚠ **충전원을 열거값이 아니라 참·거짓으로 받는다.** `ESSChargeSource` 는
    `core/der/ess.py` 가 선언하고 그 파일이 이 모듈을 부르므로, 여기서 그 열거값을
    import 하면 순환 import 가 된다 — `core/casegrid/pv_allocation.py` 머리말이
    같은 함정을 적는다.
    """
    if not uses_pv_surplus:
        if profile is not None:
            _reject_pv_surplus_profile(f"{name}: 충전원=계통인데 PV잉여 시계열을 받음",
                "charge_source 를 PV_SURPLUS 로 바꾸거나 인자를 빼십시오")
        return None

    if profile is None or not any(v > 0.0 for v in profile):
        _reject_pv_surplus_profile(
            f"{name}: 충전원이 태양광 잉여인데 잉여 시계열이 없거나 전부 0입니다",
            "pv_surplus_profile_kwh 에 시각별(0~23) PV 잉여 kWh 를 지정하십시오",
        )
    if len(profile) != HOURS_PER_DAY:
        _reject_pv_surplus_profile(
            f"{name}: PV 잉여 시계열은 {HOURS_PER_DAY}행이어야 합니다(받은 값 "
            f"{len(profile)}행)",
            f"pv_surplus_profile_kwh 를 {HOURS_PER_DAY}행 시계열로 맞추십시오",
        )
    return tuple(float(v) for v in profile)


def pv_surplus_charge_kwh_by_hour(
    *,
    profile: Sequence[float] | None,
    discharge_hours: Sequence[int],
    room_kwh: float,
    power_kw: float,
) -> dict[int, float]:
    """대표일 시각별 **실제** 충전량(kWh) — `PV_SURPLUS` 전용 (판정 A-8-a·b).

    시각(0~23)을 차례로 훑어 **방전창을 뺀, 잉여가 있는 모든 시각**에서
    `min(그 시각 잉여, 정격출력 1시간분, 남은 저장 여유)` 만큼 채운다. 여유가 다
    차거나 잉여가 없는 시각은 건너뛴다 — **거부하지 않는다**(A-8-b).

    ⚠ **이 충전이 가구 부하보다 앞선다** — 그 우선순위의 정본 선언은
    `e2e_runner._resolve_ess_dispatch_inputs` 독스트링에 있다(사본을 두지 않는다).

    `room_kwh` 는 부르는 쪽이 계산해 넘긴다 — 남는 여유의 상한이
    `cycles_per_year` 이고(A-8-c) 그 값은 자원의 열화·용량에 매여 있어 이 모듈이
    알 수 없다.
    """
    assert profile is not None  # charge_source==PV_SURPLUS 면 `ESS` 생성자가 보장한다
    charged: dict[int, float] = {}
    for hour in range(HOURS_PER_DAY):
        if hour in discharge_hours or room_kwh <= 0.0 or profile[hour] <= 0.0:
            continue
        amount = min(profile[hour], power_kw, room_kwh)  # 셋 다 양수라 amount>0
        charged[hour] = amount
        room_kwh -= amount
    return charged


def load_following_kwh_by_hour(
    *,
    daily_kwh: float,
    discharge_hours: Sequence[int],
    load_profile_kwh: Sequence[float] | None,
    power_kw: float,
    name: str,
) -> dict[int, float]:
    """하루 방전량을 방전창 안에서 **그 시각의 부하에 비례**해 나눈다 (요구 5).

    돌려주는 것은 **시각 → 그 시각의 방전 kWh** 이고, 합은 `daily_kwh` 와 같다
    (에너지 보존). 부하가 0인 시각은 0을 받는다 — 「대응」은 수요가 있는 곳에
    낸다는 뜻이므로, 수요가 없는 시각에 싣는 것은 추종이 아니다.

    **정격을 넘는 시각은 정격에 묶고 남은 에너지를 다시 나눈다**(모듈 머리말 판정
    ⓒ). 묶인 시각을 뺀 나머지에 같은 비례 배분을 다시 적용하므로, 두 번째 배분이
    또 정격을 넘으면 그 시각도 묶는다 — 넘는 시각이 없어질 때까지 되풀이한다.
    되풀이는 방전창의 시각 수만큼만 돌 수 있어 반드시 끝난다.
    """
    assert load_profile_kwh is not None  # 부하 추종이면 `ESS` 생성자가 보장한다
    weights = {hour: max(load_profile_kwh[hour], 0.0) for hour in discharge_hours}
    planned: dict[int, float] = dict.fromkeys(discharge_hours, 0.0)
    free = [hour for hour in discharge_hours if weights[hour] > 0.0]
    remaining = daily_kwh
    while free:
        total = math.fsum(weights[hour] for hour in free)
        share = {hour: remaining * weights[hour] / total for hour in free}
        over = [hour for hour in free if share[hour] > power_kw + KW_TOLERANCE]
        if not over:
            planned.update(share)
            return planned
        for hour in over:
            planned[hour] = power_kw
            remaining -= power_kw
        free = [hour for hour in free if hour not in over]
    if remaining > ENERGY_TOLERANCE_KWH:
        _reject_undischargeable(daily_kwh, remaining, power_kw, name=name)
    return planned


def _reject_undischargeable(
    daily_kwh: float, remaining_kwh: float, power_kw: float, *, name: str
) -> NoReturn:
    """부하가 있는 시각을 전부 정격까지 채우고도 남았다 — 둘 곳이 없다.

    ⛔ 여기서 잘라내면 하루 방전 총량이 조용히 줄고 편익은 그대로 남는다. 부하가
    0인 시각에 싣는 것도 같은 종류의 거짓이다 — 「수요에 대응했다」가 아니게 된다.
    """
    raise ValidationError(
        field="ess.power_kw",
        reason=f"{name}: 부하 추종 방전 — 부하가 있는 시각을 정격출력 {power_kw:.6g}kW 까지 "
        f"채우고도 하루 방전량 {daily_kwh:.6g}kWh 중 {remaining_kwh:.6g}kWh 가 남습니다",
        action="정격출력(power_kw)을 키우거나, 방전 시간대가 더 넓은 운전 방법을 고르거나, "
        "연간 사이클 수를 낮춰 하루 방전량을 줄이십시오 — 자동으로 잘라내면 그만큼의 "
        "편익이 조용히 사라집니다",
    )
