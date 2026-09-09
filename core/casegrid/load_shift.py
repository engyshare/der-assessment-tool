"""「AI 가전」— 가전 부하를 **하루 안에서 옮기는** 자리 (R64/WP-7 · 사용자 요구 2).

## 무엇을 여는가

사용자 요구 2 는 *「가구의 전기 부하 설정을 변경할 수 있어야 함 (EV, heatpump,
AI 가전)」* 이다. R64/WP-2 가 앞의 둘(히트펌프·전기차)을 **총량**으로 열었고
(`core/casegrid/appliance_load.py`), 「AI 가전」은 **일부러 떼어냈다** — 가산
항목으로 세우면 냉장고·세탁기의 소비가 두 번 세어지기 때문이다.

사용자 판정(2026-09-06, `docs/decisions-2026-09-06-R64.md` §4)이 그 자리를
정했다:

> 가전과 AI가전을 나눌 이유가 있는가? 기존 가존에 AI 기능이 포함된다고 보면
> 어떠한가? 냉장고, 세탁기 등 DR 자원으로 활용 가능한 전자기기에 대해서 기능이
> 추가되는 것임

⇒ AI 기능의 값어치는 kWh 를 **더하는** 데 있지 않고 그 kWh 를 **언제 쓸지 옮길
수 있다**는 데 있다. 그래서 이 모듈이 만지는 것은 **총량이 아니라 형상**이다.

    옮긴 하루[j] = 하루[j] − (잉여 없는 시각에서 뺀 몫) + (잉여 있는 시각에 준 몫)

## ⚠⚠⚠ **총량은 한 kWh 도 변하지 않는다** — 그것이 이 모듈의 정의다

옮기는 것이지 더하거나 빼는 것이 아니다. `shift_into_pv_surplus()` 가 빼는
합과 주는 합이 **같은 수(`LoadShift.moved_kwh`)** 이며, 그 성질을
`tests/casegrid/test_load_shift.py` 가 잰다. 총량이 움직이면 대장
(`docs/assumptions.yaml::load.household.annual`)이 정한 부하가 아닌 것으로
결론이 서고, 그 어긋남은 아무 예외도 내지 않는다.

## 어디로 옮기나 — **그 날 PV 잉여가 있는 시각으로** (사용자 판정 §5)

사용자가 고른 갈래는 *「(가)만. 집 전체 가전 부하 중 비율로 간단히」* 이고,
(가)는 *「내가 만든 전기를 더 많이 쓰게 한다」* 다. 그러므로 목적지는 **그 날
태양광 잉여(`max(0, 발전 − 부하)`)가 있는 시각**이다.

⛔ **요금 단가가 싼 시각으로 옮기지 않는다** — 그것은 (가)가 아니고, 시간대별
요금표를 이 축에 끌어들인다(저장소에 시간대 요금 자산이 없다).
⛔ **정산금(시장) 갈래를 만들지 않는다** — `FR-401-AC2.DemandResponse` 는
**미매핑 그대로** 둔다. 정산단가가 없고, 넣으면 사용자가 지적한 참고자료의
결함(없는 시장의 수익이 결론의 부호를 만든다)을 우리가 되풀이한다. 그 결손은
붙임 8 이 신고한다(`core/report/unreflected.py`).
✅ 절감은 **사는 전기가 줄어서** 요금 엔진에서 나온다 — 부하는 편익을 만들지
않는다(`RC-LD-B0` · `core/der/load.py` 의 `Load.value_streams()` 가 비어 있다).

## ⚠ **옮길 곳이 없으면 옮기지 않는다** — 값을 지어내지 않는다

그 날 잉여가 하루 종일 0 이면(겨울처럼 발전이 적은 계절) `moved_kwh` 가 0 이고
하루가 **원소 하나까지 그대로**다. 그것은 결함이 아니라 사실이며, 산출물이
그 사실을 글자로 남긴다(붙임 1 의 「AI 가전」 표).

## ⚠ 원천은 **잉여가 없는 시각**뿐이다

잉여가 있는 시각의 부하를 같은 잉여 시각으로 옮기는 것은 아무 일도 하지 않는
연산이다(그 시각의 소비는 이미 자기 발전으로 덮인다). 그래서 빼는 자리는
`잉여 == 0` 인 시각뿐이고, 그 시각의 부하에 비례해 뺀다 — 계통에서 사 오는
전기가 그 시각에 있다.

## ⚠⚠ 주는 몫은 **그 시각의 잉여를 넘지 않는다**

목적지에 잉여보다 많이 실으면 그 시각이 다시 계통 수전으로 돌아서고, 그러면
「자가소비를 늘렸다」가 거짓이 된다. 그래서 옮기는 총량을 **그 날 잉여의 합**
으로 자르고 잉여에 비례해 나눈다 — 그러면 시각마다 준 몫이 그 시각 잉여
이하다.

## ⚠ 분모는 **가전 부하**다 — 히트펌프·전기차를 포함하지 않는다

사용자 문면이 *「집 전체 **가전** 부하 중 비율」* 이고, 이 저장소는 가전
(`load.household.annual`)과 추가 전력사용기기(`load.heatpump.annual` ·
`load.ev.annual`)를 **다른 대장 항목**으로 갖는다. 그래서 호출부가
`appliance_ratio` 로 *「그 하루 부하 중 가전의 몫」* 을 함께 넘긴다.

⛔ **전기차 충전을 이 비율에 포함하지 않는다.** 전기차 충전은 옮길 수 있는
정도가 가전과 크게 다르고(야간 집중), 그 결손은 대장
(`load.ev.annual` 의 `impact_note`)이 이미 **형상 축의 몫**으로 신고해 두었다 —
여기 포함하면 그 부채를 가정으로 조용히 갚는 것이 된다.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from core.contracts.validation import ValidationError

#: 이 비율의 **대장 자리**. 값은 대장이 갖고 이 코드가 리터럴로 두지 않는다
#: (`NFR-202`) — 두면 대장을 고쳐도 옛 값이 쓰인다.
DR_SHIFTABLE_SHARE_LEDGER_KEY = "load.dr_shiftable_share"

#: 이 비율의 **표시 이름** — 거부 문면과 산출물이 같은 낱말을 쓰게 한다.
DR_SHIFTABLE_SHARE_TITLE = "하루 안에서 옮길 수 있는 가전 부하 비율"

#: 이 비율의 **단위**. 대장의 `value_unit` 과 같은 문면이어야 한다 — 갈리면
#: 화면이 적는 단위와 대장이 적는 단위가 다른 값이 된다.
DR_SHIFTABLE_SHARE_UNIT = "% (가구 가전 부하 중)"

#: 옮긴 몫이 0 인 계절이 산출물에 **글자로** 남기는 문면.
#:
#: ⚠⚠ **빈칸으로 두지 않는다.** 빈칸은 「옮겼다」와 「옮길 곳이 없었다」를
#: 구별해 주지 않고, 사용자는 앞쪽으로 읽는다 — `core/casegrid/appliance_load.py
#: ::APPLIANCE_LOAD_UNSPECIFIED` 가 같은 사유를 적는다.
DR_SHIFT_NOTHING_MOVED = "옮긴 몫 없음 — 그 계절 하루에 태양광 잉여가 없다"

#: 비율의 상한. **100 을 넘는 「비율」은 입력 실수다** — 넘겨 받으면 옮길 몫이
#: 그 시각 부하보다 커져 부하가 음수가 되고, 음수 부하는 설비 없는 발전이다.
MAX_SHIFTABLE_SHARE_PCT = 100.0

#: 백분율 → 비율. 환산하는 자리를 **하나로** 둔다 — 호출부마다 적으면 그중
#: 하나가 빠져도 「10% 대신 1,000%」가 아니라 **그럴듯한 큰 수**가 나온다.
_PERCENT = 100.0


@dataclass(frozen=True)
class LoadShift:
    """하루 한 벌을 옮긴 결과 — **옮긴 하루와 옮긴 몫**.

    ⚠ 둘을 함께 든다. 하루만 돌려주면 *「옮길 곳이 없어 그대로다」* 와
    *「비율이 0 이라 그대로다」* 가 호출부에서 구별되지 않고, 그 구별이
    산출물의 문면을 가른다(`DR_SHIFT_NOTHING_MOVED`).
    """

    #: 옮긴 뒤의 하루. 스텝 수와 **합**이 받은 하루와 같다.
    day: tuple[float, ...]
    #: 실제로 옮긴 몫(kWh/일). 뺀 합과 준 합이 **같은 이 수**다.
    moved_kwh: float


def resolve_shiftable_share(value: object | None) -> float | None:
    """대장·시나리오가 적은 비율 → `float`(0~100) 또는 `None`(미지정).

    `None` 과 빈 문자열이 **「적지 않았다」**이며 그때 형상을 만지지 않는다 —
    여기서 기본 비율로 바꿔 내지 않는다. 기본값의 자리는 **대장**
    (`DR_SHIFTABLE_SHARE_LEDGER_KEY`)이고, 코드가 그 값을 갖게 되면 대장을
    고쳐도 옛 값이 쓰인다(`core/casegrid/appliance_load.py::
    resolve_appliance_load` 가 같은 규약을 적는다).

    ## ⚠ 무엇을 거부하는가

    **음수** — 「옮길 수 있는 몫이 마이너스」는 뜻이 없다. 받아 주면 잉여
    시각의 부하를 잉여 없는 시각으로 **거꾸로** 옮기게 되고, 그것은 자가소비를
    줄이는 운전이면서 리포트에는 「DR 을 반영했다」로 적힌다.
    **100 초과** — 시각별 부하보다 많이 빼게 되어 부하가 음수가 된다.
    **`nan`·`inf`** — 하루에 곱해지면 리포트의 모든 수가 조용히 `nan` 이 된다.
    **`bool`** — 파이썬에서 `True` 는 `int` 의 하위형이라 그냥 두면
    `비율 = 참` 이 **1%** 로 조용히 통과한다.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            raise _rejected(value) from None
        return resolve_shiftable_share(number)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _rejected(value)
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > MAX_SHIFTABLE_SHARE_PCT:
        raise _rejected(value)
    return number


def shiftable_share_pct(value: object | None) -> float:
    """대장·화면이 적은 값 → **러너에 넘길 비율**. 미지정은 `0`(옮기지 않는다).

    ⚠ **미지정을 0 으로 세는 자리는 여기 하나다.** 호출부마다 `or 0.0` 을
    적으면 「적지 않았다」가 층마다 다른 수로 읽힐 수 있고, 그때 본문과 스윕이
    서로 다른 하루로 돈다 — `core/casegrid/appliance_load.py::
    ApplianceLoads.total_kwh` 가 같은 판단을 적는다.

    ⚠ 거부는 `resolve_shiftable_share` 하나가 진다 — 이 함수는 그 판정을
    지나온 값의 **미지정만** 메운다.
    """
    return resolve_shiftable_share(value) or 0.0


def _rejected(value: object) -> ValidationError:
    """거부 하나 — **3요소를 갖춘다** (`NFR-303`).

    ⚠ 문면을 한 곳에만 둔다. 갈래마다 새로 적으면 같은 실수에 다른 사유가
    나가고, 그때 사용자는 「무엇이 다른가」를 찾느라 시간을 쓴다 —
    `core/casegrid/appliance_load.py` 의 같은 이름 함수가 같은 판단을 적는다.
    """
    return ValidationError(
        field=DR_SHIFTABLE_SHARE_LEDGER_KEY,
        reason=(
            f"{DR_SHIFTABLE_SHARE_TITLE}은 0 이상 "
            f"{MAX_SHIFTABLE_SHARE_PCT:,.0f} 이하의 수여야 합니다 "
            f"(받은 값 {value!r}). 이 수는 「가전 부하 중 하루 안에서 옮길 수 "
            "있는 몫」이므로 음수도 100%를 넘는 값도 뜻이 없습니다"
        ),
        action=(
            "칸을 비우거나(그때 부하를 옮기지 않고 돕니다) 0 이상 "
            f"{MAX_SHIFTABLE_SHARE_PCT:,.0f} 이하의 수를 "
            f"{DR_SHIFTABLE_SHARE_UNIT} 단위로 지정하십시오"
        ),
    )


def shift_into_pv_surplus(
    load_day: Sequence[float],
    generation_day: Sequence[float],
    *,
    share_pct: float,
    appliance_ratio: float,
) -> LoadShift:
    """그 날 부하 중 옮길 수 있는 몫을 **PV 잉여가 있는 시각으로** 옮긴다.

    ## 산식

        잉여[j]   = max(0, 발전[j] − 부하[j])
        원천[j]   = 부하[j]  단 잉여[j] == 0 인 시각만, 나머지는 0
        옮길몫    = 비율 × 가전몫 × Σ 원천
        옮긴몫    = min(옮길몫, Σ 잉여)                     ← 잉여를 넘지 않는다
        옮긴하루[j] = 부하[j] − 옮긴몫 × 원천[j] / Σ원천
                            + 옮긴몫 × 잉여[j] / Σ잉여

    ## 성립하는 항등식

        Σ_j 옮긴하루[j] == Σ_j 부하[j]            총량 보존 (판정 ①)
        옮긴하루[j] ≥ 0                            원천에서 빼는 몫이 그 시각
                                                   부하의 `비율×가전몫` 이하다
        옮긴하루[j] ≤ 발전[j]  (잉여 시각에서)     준 몫이 그 시각 잉여 이하다

    첫째는 뺀 합과 준 합이 둘 다 `옮긴몫` 이기 때문에 성립한다. 둘째는
    `resolve_shiftable_share` 가 비율을 100% 이하로 자르고 `가전몫 ≤ 1` 이므로
    `옮긴몫 × 원천[j] / Σ원천 ≤ 원천[j] = 부하[j]` 이기 때문이다. 셋째는
    `옮긴몫 ≤ Σ잉여` 이므로 `옮긴몫 × 잉여[j] / Σ잉여 ≤ 잉여[j]` 이기 때문이다.

    ## ⚠ 잉여를 **옮기기 전 하루**로 잰다

    옮긴 뒤의 잉여로 다시 재어 되풀이하면(수렴 반복) 옮기는 양이 잉여를
    잠식하는 순환이 되고, 그 반복 횟수가 결론을 정한다 — **반복 횟수라는 지어낸
    수가 결론에 서는 것**이므로 하지 않는다. 한 번만 옮기고, 옮긴 뒤 그 시각의
    잉여가 줄어드는 것은 운전(`core/casegrid/seasonal_dispatch.py`)이 그대로
    잰다(ESS 의 잉여 충전 계획이 그만큼 작아진다 — 그것이 사실이다).

    ⚠ **되풀이하지 않는 대가**: 옮긴 뒤에도 잉여가 남는 시각이 있을 수 있다.
    그때 「더 옮길 수 있었는데 안 옮겼다」가 되며, 방향은 **보수적**이다
    (자가소비를 과대 계상하지 않는다).
    """
    headroom = [
        max(0.0, generation - load)
        for generation, load in zip(generation_day, load_day, strict=True)
    ]
    total_headroom = math.fsum(headroom)
    # ⚠ 잉여가 있는 시각은 **원천이 아니다** — 모듈 머리말의 ⚠ 절.
    source = [
        load if room <= 0.0 else 0.0
        for load, room in zip(load_day, headroom, strict=True)
    ]
    total_source = math.fsum(source)
    moved = min(
        share_pct / _PERCENT * appliance_ratio * total_source, total_headroom
    )
    if moved <= 0.0:
        # ★ **하루를 새로 짓지 않고 그대로 돌려준다** — 옮긴 것이 없으면
        # 이 배선이 생기기 전과 **원소 하나까지** 같아야 하고, `x - 0 + 0` 도
        # 부동소수에서는 같은 수이지만 여기서는 그 성질에 의존하지 않는다.
        return LoadShift(day=tuple(load_day), moved_kwh=0.0)
    return LoadShift(
        day=tuple(
            load - moved * taken / total_source + moved * given / total_headroom
            for load, taken, given in zip(load_day, source, headroom, strict=True)
        ),
        moved_kwh=moved,
    )
