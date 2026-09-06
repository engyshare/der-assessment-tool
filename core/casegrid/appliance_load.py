"""가구의 **추가 전력사용기기 부하** — 히트펌프 · 전기차 (R64/WP-2 · 사용자 요구 2).

## 무엇을 여는가

사용자 요구 2 는 *「가구의 전기 부하 설정을 변경할 수 있어야 함 (EV, heatpump,
AI 가전)」* 이다. 종전에는 바꿀 방법이 없었다 — 러너
(`core/casegrid/e2e_runner.py::run_single_case_e2e`)가
`extra_appliance_load_kwh` 인자를 **갖고만 있었고 배포 경로에서 아무도
넘기지 않았다**(R64/WP-2 착수 실측: `grep -rn "extra_appliance_load_kwh="`
가 시험 밖에서 0건). 그래서 그 인자의 기본값 `0.0` 만 살았다.

이 모듈은 **시나리오 yaml · 화면이 적은 두 수**를 받아 그 인자를 채운다.

    단지 총부하 = ( 가구 한 호의 연간 사용량 + 히트펌프 + 전기차 ) × 가구 수

## ⚠⚠⚠ **부하이지 자원이 아니다** — 설비를 세우지 않는다

사용자 요구의 문면이 **「가구의 전기 부하 설정」**이다 — *그 기기가 전기를
얼마나 쓰는가*. 히트펌프·전기차를 **자원**(`core/der/heatpump.py::HeatPump` ·
`core/der/ev_v2g.py::EV_V2G`)으로 세우면 설치비·유지보수비·편익 갈래가 함께
서고 그것은 **다른 요구**(설비 구성)이며 결론축을 크게 움직인다.

그리고 부하에 편익을 붙일 수는 없다 — `Load.value_streams()` 가 비어 있는
것이 정답이고(`RC-LD-B0`), 부하가 만드는 절감은 그 절감을 **일으킨 자원**의
편익이다. 양쪽에 붙이면 같은 화폐 흐름이 두 번 계상된다(`FR-402-AC2.C`).

⇒ 그래서 이 모듈이 내는 것은 **kWh 둘**이고, 그것이 가구 부하 총량에
더해진다. 자원 클래스를 만들지 않는다.

## ⚠⚠ 「AI 가전」은 이 모듈에 **없다** — 세우면 두 번 세어진다

사용자 판정(2026-09-06): *「가구와 AI가전을 나눌 이유가 있는가? 기존 가전에
AI 기능이 포함된다고 보면 어떠한가? 냉장고, 세탁기 등 **DR 자원으로 활용
가능한** 전자기기에 대해서 **기능이 추가되는 것**임」*.

⇒ AI 가전은 전기를 더 쓰는 **새 기기가 아니라 이미 있는 가전에 붙는
기능**이다. 여기에 `ai_appliance` 항목을 세워 총량에 더하면 냉장고·세탁기의
소비가 `load.household.annual`(일반가전 포함)과 **두 번 세어진다.** 그
기능의 값어치는 kWh 를 더하는 데 있지 않고 **그 kWh 를 언제 쓸지 옮길 수
있다**는 데 있다 — 즉 **부하 형상**의 문제이고, 이 모듈은 형상을 만지지
않는다(총량만 다룬다. 형상은 계절 축의 몫이다).

## ⚠⚠⚠ 값을 지어내지 않는다 — 기본이 **미지정**인 이유

`docs/assumptions.yaml` 의 `load.heatpump.annual` · `load.ev.annual` 은
`track: blocked` · `value: null` 이다. 두 수는 **이 단지의 가구가 그 기기를
갖는가**에 달려 있고 그것은 사업 계획이 정하는 사실이다 —
`load.household.count` 가 같은 자리에서 같은 판정을 적었다
(`core/casegrid/household_scale.py` 머리말 ⚠⚠⚠).

⇒ 그래서 **기본값이 없다.** 안 주면 `None` 이고 더해지는 값은 0 이며, 러너는
이 배선이 생기기 전과 **원소 하나까지** 같다. 골든 회귀
(`tests/golden/test_regression_scenarios.py`)가 그 동일성을 잰다.

## ⚠ 「0 이라고 적었다」와 「적지 않았다」를 가른다

둘 다 더해지는 값은 0 이지만 **다른 진술**이다 — 앞의 것은 *「이 단지의
가구에는 히트펌프가 없다」*이고 뒤의 것은 *「히트펌프가 있는지 아직
모른다」*다. 산출물이 그 둘을 다르게 인쇄해야 검토자가 *「반영했다」*와
*「반영하지 않았다」*를 가릴 수 있다. `core/cba/baseline.py::
resolve_pool_metering` 이 같은 구별을 적는다.

## ⚠ 왜 두 칸인가 — 뭉뚱그린 칸 하나로 내보내지 않는다

러너의 인자는 **합계 하나**(`extra_appliance_load_kwh`)이고 그것을 바꾸지
않는다. 그러나 **입력과 산출물은 둘로 갈라 둔다** — 하나로 합쳐 「추가 기기」
라고 붙이면 사용자가 히트펌프와 전기차를 **따로 바꾸지 못하고**, 산출물도
어느 쪽이 얼마인지 말하지 못한다. 사용자 요구가 기기를 나열한 이유가 그것이다.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from core.contracts.validation import ValidationError

#: 시나리오 yaml 이 **히트펌프 연간 소비전력량**을 싣는 필드 이름.
#:
#: ⚠ **통로는 이 필드 하나다.** 케이스 그리드 변수축·환경 변수·CLI 플래그를
#: 따로 세우지 않는다 — 통로가 둘이면 어느 것이 이겼는지 산출물에서 알 수
#: 없다(`core/casegrid/household_scale.py::HOUSEHOLD_COUNT_FIELD` 와 같은 규약).
HEATPUMP_LOAD_FIELD = "heatpump_load_annual_kwh"

#: 시나리오 yaml 이 **전기차 충전 연간 전력량**을 싣는 필드 이름.
EV_LOAD_FIELD = "ev_load_annual_kwh"

#: 히트펌프 부하의 **대장 자리**. 값은 비어 있고(`track: blocked` ·
#: `value: null`) 이 코드가 채우지 않는다 — 위 머리말 ⚠⚠⚠ 참조.
HEATPUMP_LOAD_LEDGER_KEY = "load.heatpump.annual"

#: 전기차 충전 부하의 **대장 자리**. 위와 같다.
EV_LOAD_LEDGER_KEY = "load.ev.annual"

#: 두 칸의 **표시 이름** — 거부 문면과 산출물이 같은 낱말을 쓰게 한다.
HEATPUMP_LOAD_TITLE = "히트펌프 연간 소비전력량"
EV_LOAD_TITLE = "전기차 충전 연간 전력량"

#: 기기 부하를 적지 않은 실행이 산출물에 **글자로** 남기는 문면.
#:
#: ⚠⚠ **빈칸으로 두지 않는다.** 빈칸은 「반영됐다」와 「반영하지 않았다」를
#: 구별해 주지 않고, 사용자는 앞쪽으로 읽는다. 이 저장소의 규약이 *「못 하는
#: 것은 「칸 + 사유」로 남긴다」* 이며 `core/casegrid/household_scale.py::
#: HOUSEHOLD_COUNT_UNSPECIFIED` 가 같은 사유를 적는다.
APPLIANCE_LOAD_UNSPECIFIED = "미지정 — 0으로 돌았다"

#: 두 칸의 **단위**. 대장의 `value_unit` 과 같은 문면이어야 한다 —
#: 갈리면 화면이 적는 단위와 대장이 적는 단위가 다른 값이 된다.
APPLIANCE_LOAD_UNIT = "kWh/호·년"


@dataclass(frozen=True)
class ApplianceLoads:
    """한 호가 추가로 쓰는 전력 — **호당**이며 가구 수를 곱하기 **전**의 값이다.

    ⚠⚠ **「호당」이라는 사실이 이 자료형의 전부다.** 근거는 대장이다:
    `docs/assumptions.yaml` 의 `load.household.annual` 이 `kWh/호·년`이고 그
    `applicable_scope` 가 *「그 기기의 연간 소비전력량을 **이 값에 더해** 총량이
    비례 증가하는 형태여야 한다」* 라고 적는다. 그러므로 증분도 한 호의 것이고
    **더한 뒤에 가구 수를 곱한다** — 곱한 뒤에 더하면 추가 기기가 단지에 딱 한
    대 있는 사업이 되고, 그 실행은 「모든 가구에 히트펌프를 놓았다」와 산출물에서
    구별되지 않는다. 그 순서를 재는 시험이
    `tests/casegrid/test_appliance_load.py` 다.

    `None` 은 **「적지 않았다」**이고 `0.0` 은 **「그 기기가 없다고 적었다」**다 —
    더해지는 값은 둘 다 0 이지만 산출물이 다르게 인쇄한다(머리말 ⚠).
    """

    #: 히트펌프(난방+냉방) 연간 소비전력량. `None` 이 미지정이다.
    heatpump_kwh: float | None
    #: 전기차 충전 연간 전력량. `None` 이 미지정이다.
    ev_kwh: float | None

    @property
    def total_kwh(self) -> float:
        """러너의 `extra_appliance_load_kwh` 로 갈 **합계**(kWh/호·년).

        ⚠ 미지정을 0 으로 세는 자리는 **여기 하나다.** 호출부마다
        `or 0.0` 을 적으면 「미지정」이 층마다 다른 수로 읽힐 수 있고, 그때
        본문과 스윕이 서로 다른 부하로 돈다.
        """
        return (self.heatpump_kwh or 0.0) + (self.ev_kwh or 0.0)

    @property
    def any_specified(self) -> bool:
        """둘 중 **하나라도** 적혔는가 — 산출물이 문면을 가르는 데 쓴다."""
        return self.heatpump_kwh is not None or self.ev_kwh is not None


#: 아무것도 적지 않은 실행의 값. 이것으로 도는 실행은 이 배선이 생기기 전과
#: **원소 하나까지** 같다(`total_kwh` 가 0.0 이고 러너 인자의 기본값이 0.0 이다).
NO_APPLIANCE_LOADS = ApplianceLoads(heatpump_kwh=None, ev_kwh=None)


def resolve_appliance_load(
    value: object | None, *, ledger_key: str, title: str
) -> float | None:
    """시나리오·화면이 적은 기기 부하 → `float`(0 이상) 또는 `None`(미지정).

    `None` 과 빈 문자열이 **「적지 않았다」**이며 그것이 기본이다. 여기서
    기본 소비량으로 바꿔 내지 않는다 — 그 수는 대장이 갖지 않으며
    (`track: blocked`) 우리가 고르면 그것이 단지 총부하를 정한다.

    ## 왜 실수를 받는가 (가구 수와 다르다)

    가구 수는 **세는 값**이라 정수만 받는다(`core/casegrid/household_scale.py::
    resolve_household_count`). 이것은 **재는 값**이므로 `2675.0` 도
    `2675.4` 도 뜻이 있다. 문자열은 화면의 빈 칸(`""`)과 수 문면만 받는다 —
    폼이 GET 질의로 보내는 모양이 그 둘뿐이기 때문이다.

    ## ⚠ 무엇을 거부하는가

    **음수** — 「부하가 마이너스」는 발전이며, 그것을 부하 칸으로 적으면
    자원 없이 발전이 서고 그 발전에는 아무 설비도 편익도 없다.
    **`nan`·`inf`** — 총량에 더해지면 리포트의 모든 수가 조용히 `nan` 이 된다.
    **`bool`** — 파이썬에서 `True` 는 `int` 의 하위형이라 그냥 두면
    `히트펌프 = 참` 이 **1kWh** 로 조용히 통과한다.
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
            raise _rejected(value, ledger_key=ledger_key, title=title) from None
        return resolve_appliance_load(number, ledger_key=ledger_key, title=title)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _rejected(value, ledger_key=ledger_key, title=title)
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise _rejected(value, ledger_key=ledger_key, title=title)
    return number


def _rejected(value: object, *, ledger_key: str, title: str) -> ValidationError:
    """거부 하나 — **3요소를 갖춘다** (`NFR-303`).

    ⚠ 문면을 한 곳에만 둔다. 갈래마다 새로 적으면 같은 실수에 다른 사유가
    나가고, 그때 사용자는 「무엇이 다른가」를 찾느라 시간을 쓴다 —
    `core/casegrid/household_scale.py` 의 같은 이름 함수가 같은 판단을 적는다.
    """
    return ValidationError(
        field=ledger_key,
        reason=(
            f"{title}은 0 이상의 수여야 합니다 (받은 값 {value!r}). "
            "이 수는 대장이 갖지 않는다 — 그 기기를 가구가 갖는지는 사업 "
            "계획이 정하는 사실이므로 저장소가 기본값으로 메우지 않습니다"
        ),
        action=(
            "칸을 비우거나(그때 그 기기 없이 돕니다) 0 이상의 수를 "
            f"{APPLIANCE_LOAD_UNIT} 단위로 지정하십시오"
        ),
    )


def resolve_appliance_loads(scenario: Mapping[str, object]) -> ApplianceLoads:
    """시나리오 매핑 → `ApplianceLoads` 하나.

    ⚠ **두 필드를 한 자리에서 읽는다.** 호출부가 각자 `scenario.get(...)` 을
    적으면 필드 이름이 층마다 복제되고, 셋째 기기가 오는 날 한쪽만 늘어난다 —
    `core/report/case_report.py::build_case_report` 와 화면이 함께 이 함수를
    부른다.
    """
    return ApplianceLoads(
        heatpump_kwh=resolve_appliance_load(
            scenario.get(HEATPUMP_LOAD_FIELD),
            ledger_key=HEATPUMP_LOAD_LEDGER_KEY,
            title=HEATPUMP_LOAD_TITLE,
        ),
        ev_kwh=resolve_appliance_load(
            scenario.get(EV_LOAD_FIELD),
            ledger_key=EV_LOAD_LEDGER_KEY,
            title=EV_LOAD_TITLE,
        ),
    )
