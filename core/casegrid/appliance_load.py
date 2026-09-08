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
있다**는 데 있다 — 즉 **하루 안의 형상**의 문제이고, 이 모듈은 하루 안의
형상을 만지지 않는다(`core/casegrid/load_shift.py` 가 그것을 한다).

## ★★★ 계절 몫 — **이 모듈이 다루는 「형상」은 계절 축 하나다** (R64/WP-3b-1)

사용자 요구 3 은 *「계절별로 냉난방수요를 차등하여 설정할 수 있어야 함」*
이다. 종전에는 그럴 자리가 없었다 — 히트펌프·전기차 부하는 위 두 필드를
지나 **합계 하나**로 러너에 들어갔고, 러너는 그 합계를 기본 부하와 **먼저
합친 뒤** 자산이 선언한 **기본 부하의 계절 몫**으로 나눴다
(`core/casegrid/seasonal_dispatch.py::_season_inputs`). 그러므로 계절 `i` 의
부하 총량은

    ( 기본부하총량 + 냉난방총량 ) × 기본부하_몫[i]

였고, 냉난방 몫이 기본부하 몫과 **강제로 같았다** — 그것이 「차등할 수 없다」
의 정체다. `ApplianceSeasonShares` 가 여는 것은 그 강제를 푸는 것 하나다:

    기본부하총량 × 기본부하_몫[i]  +  냉난방총량 × 냉난방_몫[i]

⛔ **비우면 종전과 동치다.** 몫을 하나도 주지 않으면 이 자료형이 서지 않고
러너는 **손대지 않은 종전 식**(`DailyShape.representative_day_by_season`)을
그대로 지난다 — 새 식으로 「같은 값이 나오도록」 다시 계산하지 않는다. 두
식은 부동소수 마지막 자리에서 갈릴 수 있고, 그러면 골든 회귀가 움직인다.

⚠⚠ **총량은 한 kWh 도 변하지 않는다.** 몫의 합이 1 이므로 계절 사이에서
**옮겨갈 뿐**이며, 그 성질은 자산 머리말의 `share` 규약과 같다. 그래서 합이
1 이 아니면 **고쳐 주지 않고 거부한다** — 0.9 를 적으면 연간 에너지의 10%가
조용히 사라진다.

⚠ **이 소스에 기본 몫을 적지 않는다.** 몫을 파이썬 리터럴로 두면 그것이 대장
밖의 값이 된다(`NFR-202`). 몫이 있다면 그것은 **자산이 갖는다** — 아래 ★★★
R65 절 참조.

## ⚠⚠⚠ 값을 지어내지 않는다 — 이 소스에 기본값이 없는 이유

두 수(`load.heatpump.annual` · `load.ev.annual`)는 **이 단지의 가구가 그
기기를 갖는가**에 달려 있고 그것은 사업 계획이 정하는 사실이다 —
`load.household.count` 가 같은 자리에서 같은 판정을 적었다
(`core/casegrid/household_scale.py` 머리말 ⚠⚠⚠).

⇒ 그래서 **이 소스에 기본값이 없다.** 값이 있다면 대장이나 실행 입력이
갖는다. 셋 다 비어 있으면 `None` 이고 더해지는 값은 0 이며, 러너는 이 배선이
생기기 전과 **원소 하나까지** 같다.

## ★★★ R65 — 값이 왔다. 통로가 **셋**이고 차례가 있다

사용자 요구(2026-09-07)가 *「히트펌프, 전기차 충전 연간 소비전력량 · 계절별
냉난방 부하 … 조사하거나 … 엑셀 상의 수치를 사용(**조사 권장**)」* 을 정했다.
조사와 엑셀 판독으로 셋이 섰다:

    ① 시나리오 yaml · 화면이 적은 수                 ← `resolve_appliance_loads`
    ② 대장 `load.heatpump.annual`(3,289.0 · `가정`)   ← `with_ledger_defaults`
      · `load.ev.annual`(2,784 · `추정` — 조사값)
    ③ 자산의 `appliance_season_shares:` 절            ← `with_ledger_defaults`
      (봄 .1293 · 여름 .2331 · 가을 .1662 · 겨울 .4714)

★ **②③ 의 수가 R66/WP-5 에 갈렸다** — 히트펌프가 **2,675 → 3,289.0** 이고
계절 몫이 `.1121/.2019/.1533/.5327` → `.1293/.2331/.1662/.4714` 다. 사용자
지시(*「히트펌프에 대한 월별 난방, 냉방, **급탕** 전력을 조사한 후에 적용해줘」*)
로 **없던 급탕 501.6 이 서고** 냉방이 조사값 712.4 로 갈렸다(난방 2,075 은
유지). 급탕이 열두 달에 깔려 **겨울 몫이 희석된 것**이 ③ 의 이동이다 —
값의 정본은 그 대장 항목과 형상 자산이고 이 목록은 **가리키기만** 한다.

**①이 이기고 칸마다 따로 본다.** ①이 `None`(= 적지 않았다)인 칸만 ②·③이
채운다 — 함수 독스트링이 그 차례와 `0.0` 을 채우지 않는 사유를 갖는다.

⛔ **골든 yaml 에 이 수들을 적지 않았다** — 적으면 같은 수가 대장과 픽스처 두
곳에 살고, 대장을 고쳐도 골든이 옛 값으로 돈다.

## ★ 이 부하가 한때 실행을 «거부»시켰다 — 그때 그랬고, 지금은 이렇다

**그때(R65/WP-2)**: 대장의 20호 × (3,600 + 2,675 + 2,784)를 골든의 설계
(⚠ 그때의 히트펌프 값이 2,675 다 — 지금은 3,289.0 이고 한 호 총량이 9,673 이다)
기본값(`pv_capacity_kw` base **3 kW**)에 얹으면 **낮에 태양광 잉여가 남지
않아** 잉여 충전 ESS 가 `DV` 로 거부했다(`core/der/ess_schedule.py::
check_pv_surplus_profile`). 실측: 기기 부하만이면 1호까지 성립하고 **2호부터
거부**되며, 기기 부하 없이 가구 수만이면 3호부터 거부됐다. 20호가 성립하려면
태양광이 **약 32.8 kW** 여야 했다.

⇒ **부하 값이 틀린 것이 아니라** 부하만 단지 규모로 커지고 **설비는 한 호분**
이었던 것이다. 그 실측이 「왜 설비에도 같은 배수를 걸어야 하는가」의 근거다.

**지금(R65/WP-2b·2c)**: 설계 변수 셋이 다 같은 배수를 탄다 —
`pv_capacity_kw`·`ess_capacity_kwh` 는 `core/casegrid/e2e_runner.py` 가
`_resolve` 직후에, ESS **정격출력**은
`core/casegrid/ess_build.py::ESS_POWER_KW`(한 호분 5 kW)에
`household_scale_factor` 가 곱해져서다. 20호 실행은 60 kW · 200 kWh · 100 kW
로 서고 **거부는 사라졌다** — 골든 3종을 그 구성으로 다시 뽑았다.
⚠ **위 두 거부(`ess.pv_surplus_profile_kwh` · `ess.power_kw`)는 이제 나지
않는다.** 경위를 지우지 않은 이유는 그것이 배수의 근거이기 때문이다.

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
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

# ⚠ **스텁이 없는 패키지다** — `core/casegrid/profiles.py:72` 가 같은 자리에서
# 같은 무시를 단다(저장소 관례). 형 오류를 덮는 것이 아니라 **배포되지 않은
# 스텁**을 지나는 것이며, `[tool.mypy] strict = true` 는 그대로다.
import yaml  # type: ignore[import-untyped]

from core.casegrid.profiles import (
    PROFILE_PATH,
    SHARE_TOLERANCE,
    DailyShape,
    Season,
)
from core.contracts.assumptions import AssumptionProvider
from core.contracts.validation import ValidationError

#: 시나리오 yaml 이 **히트펌프 연간 소비전력량**을 싣는 필드 이름.
#:
#: ⚠ **통로는 이 필드 하나다.** 케이스 그리드 변수축·환경 변수·CLI 플래그를
#: 따로 세우지 않는다 — 통로가 둘이면 어느 것이 이겼는지 산출물에서 알 수
#: 없다(`core/casegrid/household_scale.py::HOUSEHOLD_COUNT_FIELD` 와 같은 규약).
HEATPUMP_LOAD_FIELD = "heatpump_load_annual_kwh"

#: 시나리오 yaml 이 **전기차 충전 연간 전력량**을 싣는 필드 이름.
EV_LOAD_FIELD = "ev_load_annual_kwh"

#: 히트펌프 부하의 **대장 자리**. R65 부터 값이 있고 **R66/WP-5 가 갈았다**
#: (`track: assume` · `value: 3289.0` · `confidence: 가정`). 세 칸의 근거 등급이
#: 다르다 — 난방 2,075 은 참고 엑셀 유지 · 냉방 712.4 는 **조사값 그대로** ·
#: 급탕 501.6 은 **조사 환산**(없던 항목)이고, 항목의 등급은 가장 약한 칸을
#: 따라 `가정` 이다. 이 소스가 채우는 것이 아니라 대장이 갖는다 — 위 머리말 ★★★.
HEATPUMP_LOAD_LEDGER_KEY = "load.heatpump.annual"

#: 전기차 충전 부하의 **대장 자리**. R65 부터 값이 있다(`track: assume` ·
#: `value: 2784` · `confidence: 추정` — **조사값**이라 히트펌프와 근거 등급이
#: 다르다).
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

#: 시나리오 yaml·화면이 **냉난방(추가 기기) 부하의 계절별 몫**을 싣는 필드 이름.
#:
#: ⚠ **통로는 이 필드 하나다** — 위 두 필드와 같은 규약이다. 값의 꼴은
#: `{계절 이름: 몫}` 매핑이며, 계절 이름은 **자산이 선언한 것**이어야 한다
#: (`fixtures/profiles/representative-day.yaml` 의 `seasons[].name`).
#: ★ **계절 수를 4로 못 박지 않는다** — 자산이 적은 개수를 그대로 쓴다.
APPLIANCE_SEASON_SHARE_FIELD = "appliance_load_season_shares"

#: 계절 몫의 **거부 문면이 지목하는 자리**. 대장 항목이 아니라 **형상 자산**
#: 이므로 `load.*` 가 아니다 — 이 몫은 총량이 아니라 총량의 분해다.
APPLIANCE_SEASON_SHARE_FIELD_KEY = "load.appliance.season_share"

#: 계절 몫 칸의 **표시 이름** — 거부 문면과 산출물이 같은 낱말을 쓰게 한다.
APPLIANCE_SEASON_SHARE_TITLE = "냉난방 부하의 계절별 몫"

#: 계절 몫을 적지 않은 실행이 산출물에 **글자로** 남기는 문면.
#:
#: ⚠⚠ **빈칸으로 두지 않는다** — `APPLIANCE_LOAD_UNSPECIFIED` 와 같은 사유다.
#: 「반영했다」와 「기본 부하와 같은 몫으로 돌았다」는 다른 진술이고, 뒤의 것이
#: 바로 사용자 요구 3 이 지적한 상태다.
APPLIANCE_SEASON_SHARE_UNSPECIFIED = "미지정 — 기본 부하와 같은 계절 몫으로 돌았다"


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
    #: 위 합계가 **계절마다 어떻게 갈리는가** (R64/WP-3b-1 · 사용자 요구 3).
    #: `None` 이 미지정이며 그때 기본 부하와 **같은 계절 몫**으로 돈다 —
    #: 그것이 이 라운드 전의 유일한 갈래였다(모듈 머리말 ★★★ 절).
    #:
    #: ⚠ **`total_kwh` 를 나누지 않는다.** 이 몫은 사용자·자산이 적은 것
    #: 그대로이며 러너의 인자는 여전히 합계 하나다(위 ⚠ 절) — 기기별 계절
    #: 몫을 **칸으로** 따로 받으면 화면 칸이 기기 수 × 계절 수로 늘어난다.
    #:
    #: ⚠⚠ **이 값을 러너로 그대로 넘기지 마라 — `blended_season_shares` 다**
    #: (R67/WP-N1). 이 몫은 자산이 **히트펌프의 것**으로 적은 것인데 그대로
    #: 넘기면 전기차 충전에도 그 겨울 몫이 씌워진다(그 속성의 ★ 절).
    season_shares: ApplianceSeasonShares | None = None

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

    @property
    def ev_ratio(self) -> float:
        """추가 기기 부하 중 **전기차의 몫**. 분모가 0 이면 `0.0` 이다.

        ⚠ **여기가 두 수를 다 아는 유일한 자리다** (R67/WP-N1). 러너는 합계
        하나(`total_kwh`)만 받고 계절 몫은 자산에서 오므로, 「그 합계의 몇
        할이 전기차인가」를 아는 것은 이 자료형뿐이다.

        ⚠⚠ **미지정(`None`)과 `0.0` 이 여기서는 같은 수를 낸다** — 둘 다
        더해지는 값이 0 이므로 *비중*도 0 이다. 갈리는 것은 산출물의 문면이고
        (`any_specified`) 그 판정은 이 속성이 지지 않는다.
        """
        total = self.total_kwh
        if total <= 0.0:
            return 0.0
        return (self.ev_kwh or 0.0) / total

    @property
    def blended_season_shares(self) -> ApplianceSeasonShares | None:
        """★ **러너로 갈 계절 몫** — 전기차 몫을 도장 찍은 사본 (R67/WP-N1).

        ## 무엇이 결함이었나

        자산(`fixtures/profiles/representative-day.yaml` 의
        `appliance_season_shares:` 절)이 적은 몫은 **냉난방의 것**이고 그
        파일이 스스로 그 결손을 적어 두었다: *「이 몫이 냉난방만의 것이 아니라
        전기차 충전에도 걸린다」*. 러너 인자가 **합계 하나**라서 히트펌프의
        겨울 몫이 전기차 충전에도 그대로 씌워졌고, 그러면 **겨울 부하가
        과대**해지고 그 위에서 역산한 겨울 ESS 용량이 부풀려진다.

        ## 무엇을 하는가

        `season_shares` 에 `ev_ratio` 를 실어 준다. 섞는 산식과 「전기차는
        **일수 비례**」라는 판정은 `ApplianceSeasonShares._matched` 가 갖는다 —
        이 속성은 **두 수를 아는 자리에서 그 비율을 건네줄 뿐**이다.

        ⚠ **몫을 안 적은 실행은 `None` 그대로다.** 그때 러너가 종전 식을
        지나며 출력이 원소 하나까지 같다(`ApplianceSeasonShares` 머리말 ⛔ 절).
        ⚠⚠ **전기차가 `None` 이거나 `0.0` 인 실행도 오늘과 같다** —
        `ev_ratio` 가 0.0 이고 `_matched` 가 그때 섞지 않는다.
        """
        if self.season_shares is None:
            return None
        return replace(self.season_shares, ev_ratio=self.ev_ratio)


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

    ⚠ **판정 자체는 `_non_negative` 하나가 진다** (R64/WP-3b-1). 계절 몫도
    「0 이상의 유한한 수 또는 미지정」이라는 **같은 엄격함**을 쓰는데, 그것을
    여기에 두면 두 번째 호출부가 갈래를 베껴 가고 그때 한쪽만 고쳐진다.
    갈리는 것은 **거부 문면**뿐이므로 그것만 인자로 받는다.
    """
    return _non_negative(
        value, reject=lambda bad: _rejected(bad, ledger_key=ledger_key, title=title)
    )


def _non_negative(
    value: object | None, *, reject: Callable[[object], ValidationError]
) -> float | None:
    """`None`·빈 문자열은 **「적지 않았다」**. 그 밖은 0 이상의 유한한 수여야 한다.

    거부 사유는 부르는 쪽이 짓는다(`reject`) — 이 함수가 문면을 갖고 있으면
    기기 부하와 계절 몫이 **같은 문장으로 거부**되고, 사용자는 어느 칸을
    고쳐야 하는지 알 수 없다.
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
            raise reject(value) from None
        return _non_negative(number, reject=reject)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise reject(value)
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise reject(value)
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
            "그 기기를 가구가 갖는지는 사업 계획이 정하는 사실이므로 "
            "저장소가 소스의 기본값으로 메우지 않습니다 — 값은 대장이나 "
            "실행 입력이 갖습니다"
        ),
        action=(
            f"칸을 비우거나(그때 대장 `{ledger_key}` 의 값으로 돌고, 대장도 "
            "비어 있으면 그 기기 없이 돕니다) 0 이상의 수를 "
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
        season_shares=resolve_appliance_season_shares(
            scenario.get(APPLIANCE_SEASON_SHARE_FIELD)
        ),
    )


# ── 계절 몫 — 냉난방 부하가 「자기」 계절 몫을 갖고 다닌다 (R64/WP-3b-1) ────


@dataclass(frozen=True)
class ApplianceSeasonShares:
    """냉난방(추가 기기) 부하의 **계절별 몫**과, 그것이 걸릴 총부하 안의 비중.

    ## 왜 몫과 비중을 한 자료형이 갖는가

    러너가 계절마다 갖는 수는 **단지 총부하 하나**(`load_total_kwh`)이고, 그
    안에서 기본 부하와 추가 기기 부하는 이미 합쳐져 있다. 계절을 가르려면 그
    합계를 **다시 갈라야** 하는데, 그 비중은

        기본 = 가구 연간사용량 / (가구 연간사용량 + 추가 기기)
        기기 = 추가 기기      / (가구 연간사용량 + 추가 기기)

    이며 **가구 수는 약분된다**(총량과 증분에 같은 배수가 곱해진다) —
    `core/casegrid/seasonal_dispatch.py::_appliance_ratio` 가 「AI 가전」축에서
    이미 같은 판단을 적었다. 그래서 러너는 가구 수를 다시 곱하지 않고, 이
    자료형은 **비중 둘만** 갖고 다닌다.

    ⚠ 비중은 `of()` 가 채운다. 사용자가 적은 것은 `by_season` 뿐이고, 그것을
    읽는 자리(`core/report/case_report.py`)는 총량을 아직 모른다.

    ⚠⚠ **`by_season` 의 차례는 결론을 만들지 않는다** — 자산의 달력과 **이름
    으로** 맞추기 때문이다(`_matched`). 차례로 맞추면 사용자가 계절을 적는
    순서만 바꿔도 겨울 몫이 봄에 걸리고, 그 어긋남은 아무 예외도 내지 않는다.
    """

    #: (계절 이름, 그 계절의 몫). 합이 1 이며 **정규화하지 않는다**(머리말 ⚠⚠).
    by_season: tuple[tuple[str, float], ...]
    #: 단지 총부하 중 **기본 부하**의 비중. `of()` 가 채우기 전에는 1.0 이다.
    base_ratio: float = 1.0
    #: 단지 총부하 중 **추가 기기 부하**의 비중. 채우기 전에는 0.0 이며, 그때
    #: 이 자료형은 어떤 수도 움직이지 않는다.
    appliance_ratio: float = 0.0
    #: ★ **그 추가 기기 부하 중 전기차의 몫** (R67/WP-N1). `by_season` 이
    #: **냉난방의** 계절 몫이므로, 전기차에는 그것을 씌우지 않고 **일수 비례**를
    #: 씌운다 — 섞는 산식은 `_matched` 가 갖는다.
    #:
    #: ⚠ 기본값 `0.0` 은 *「전기차가 없다」*이며 그때 `_matched` 가 **섞지
    #: 않고** 적힌 몫을 그대로 낸다 — 출력이 이 필드가 서기 전과 원소 하나까지
    #: 같다. 채우는 자리는 `ApplianceLoads.blended_season_shares` 하나다
    #: (두 수를 다 아는 곳이 거기뿐이다).
    ev_ratio: float = 0.0

    @staticmethod
    def of(
        shares: ApplianceSeasonShares | None,
        annual_load_kwh: float | None,
        extra_appliance_load_kwh: float,
    ) -> ApplianceSeasonShares | None:
        """비중 둘을 채운 사본. **몫을 주지 않았으면 `None` 그대로다.**

        ⚠ 부하를 세우지 않는 실행(`annual_load_kwh is None`)과 총량이 0 인
        실행에서는 기기 비중이 0 이다 — 그때 옮길 에너지 자체가 없어 어떤
        몫을 적어도 결과가 같다. `_appliance_ratio` 가 같은 자리에서 같은
        판단을 적었다.
        """
        if shares is None:
            return None
        base = annual_load_kwh or 0.0
        total = base + extra_appliance_load_kwh
        if total <= 0.0:
            return replace(shares, base_ratio=1.0, appliance_ratio=0.0)
        return replace(
            shares, base_ratio=base / total,
            appliance_ratio=extra_appliance_load_kwh / total,
        )

    @staticmethod
    def load_days(
        shape: DailyShape,
        total_kwh: float,
        shares: ApplianceSeasonShares | None,
        *,
        days: int,
    ) -> tuple[tuple[Season, tuple[float, ...], int], ...]:
        """계절마다 (계절, **그 계절의 부하 대표일**, 그 계절의 일수).

        ⛔ **몫이 없으면 자산의 메서드를 그대로 부른다** — 아래 갈래로 「같은
        값이 나오도록」 다시 계산하지 않는다. 두 식은 부동소수 마지막 자리에서
        갈릴 수 있고, 그러면 몫을 주지 않은 실행(골든 셋)이 움직인다.

        몫이 있으면 총부하를 비중으로 갈라 **각각 자기 계절 몫으로** 편 뒤
        더한다. 연산 차례는 자산 쪽과 같다(`per_day` 를 먼저 짓고 가중치를
        곱한다 — `DailyShape.representative_day_by_season` 의 ⚠ 절).
        """
        if shares is None:
            return shape.representative_day_by_season(total_kwh, days=days)
        matched = shares._matched(shape)
        base = shape.representative_day_by_season(
            total_kwh * shares.base_ratio, days=days
        )
        extra_total = total_kwh * shares.appliance_ratio
        built: list[tuple[Season, tuple[float, ...], int]] = []
        for (season, day, season_days), (weights, share) in zip(base, matched, strict=True):
            per_day = extra_total * share / season_days
            built.append((
                season,
                tuple(v + per_day * w for v, w in zip(day, weights, strict=True)),
                season_days,
            ))
        return tuple(built)

    @staticmethod
    def folded_year(
        shape: DailyShape,
        total_kwh: float,
        shares: ApplianceSeasonShares | None,
        *,
        days: int,
    ) -> list[float]:
        """**연간등가 하루**를 `days` 일 되풀이한 시계열 — 위 메서드의 형제.

        러너는 계절별 하루와 별도로 「일수 가중 평균 하루」한 벌을 세운다
        (`core/casegrid/seasonal_dispatch.py` 머리말 ★★★). 그 하루가 계절별
        하루와 다른 식으로 서면 **인쇄하는 하루와 배터리가 따라가는 하루가
        갈린다** — 그래서 여기서도 같은 분해를 쓴다.

        ⛔ 몫이 없으면 자산의 `spread_over_representative_day` 를 그대로
        부른다(위와 같은 사유).
        """
        if shares is None:
            return shape.spread_over_representative_day(total_kwh, days=days)
        matched = shares._matched(shape)
        base = shape.representative_day(total_kwh * shares.base_ratio, days=days)
        extra_total = total_kwh * shares.appliance_ratio
        day = tuple(
            value + math.fsum(
                extra_total * share / days * weights[step]
                for weights, share in matched
            )
            for step, value in enumerate(base)
        )
        return [value for _day in range(days) for value in day]

    def _matched(self, shape: DailyShape) -> tuple[tuple[tuple[float, ...], float], ...]:
        """자산의 계절 차례대로 (그 계절 가중치, **그 계절에 실제로 걸릴 몫**).

        ⚠⚠ **달력이 다르면 여기서 거부한다.** 자산 머리말이 *「부하와 발전이
        같은 달력을 적어야 한다 … 읽는 쪽이 거부한다」* 로 못 박은 것과 같은
        규칙이며, 계절 이름이 다르면 **같은 인덱스가 서로 다른 날을 가리킨다.**
        고쳐 주지 않는다 — 이름을 짐작해 붙이면 겨울 몫이 봄에 걸린다.

        ## ★ 적힌 몫과 「실제로 걸릴 몫」이 다른 경우 — 전기차 (R67/WP-N1)

        `by_season` 은 **냉난방의** 계절 몫이다. 그런데 러너로 가는 것은
        히트펌프와 전기차의 **합계 하나**라, 그대로 쓰면 히트펌프의 겨울 몫이
        전기차 충전에도 씌워진다 — 전기차는 통상 심야·**연중 고른 충전**이므로
        그것은 겨울 부하를 과대하게 만들고, 그 위에서 역산한 겨울 ESS 용량이
        부풀려진다. 자산 파일이 그 결손을 스스로 적어 두었다
        (`appliance_season_shares` 의 `derivation_method` 안 ⚠⚠ 절).

        ⇒ 전기차 몫에는 **자산 달력의 일수 비례**를 씌우고 둘을 섞는다:

            유효 몫[i] = (1 − ev_ratio) × 적힌 몫[i]
                       + ev_ratio × ( 일수[i] ÷ 일수 합 )

        ⚠ **일수 비례를 상수로 박지 않는다.** `SHARE_TOLERANCE` 가 `1e-9` 라
        네 자리로 끊으면(`0.2521 + … = 1.0001`) 합 검사가 거부하고, 무엇보다
        자산이 달력을 고치는 날 그 상수만 낡는다 — 여기서 **자산의 `days` 를
        그 자리에서 나눈다.** 새 수를 발명하지 않는 것이 이 갈래의 근거다.

        ⚠⚠ **「기본 부하와 같은 몫」을 쓰지 않는 이유** — 기본 부하의 계절
        몫은 자산이 그 사유를 *「**냉난방 때문에** 여름·겨울이 높다」* 로
        적었다. 그것을 전기차에 씌우면 냉난방 사유의 계절성을 전기차에 붙이는
        것이 되어 결함이 형태만 바뀐다.

        ⛔ **`ev_ratio` 가 0 이면 섞지 않고 적힌 몫을 그대로 낸다** — 다시
        계산하면 부동소수 마지막 자리가 갈릴 수 있고, 그러면 전기차를 적지
        않은 실행이 조용히 움직인다(`load_days` 의 ⛔ 절과 같은 사유).
        """
        given = dict(self.by_season)
        names = [season.name for season in shape.seasons]
        if len(given) != len(self.by_season) or sorted(given) != sorted(names):
            raise ValidationError(
                field=APPLIANCE_SEASON_SHARE_FIELD_KEY,
                reason=(
                    f"{APPLIANCE_SEASON_SHARE_TITLE}에 적은 계절 "
                    f"{[name for name, _s in self.by_season]} 이(가) 형상 자산의 "
                    f"달력 {names} 과 다릅니다 — 이름이 다르면 같은 몫이 다른 "
                    "날에 걸리므로 짐작해 맞추지 않습니다"
                ),
                action=(
                    f"계절 {names} 을(를) 그대로 적거나, 칸을 모두 비우십시오 "
                    "(비우면 냉난방이 기본 부하와 같은 계절 몫으로 돕니다)"
                ),
            )
        declared = tuple(
            (weights, given[season.name]) for season, weights in shape.by_season
        )
        if not self.ev_ratio:
            return declared
        return tuple(
            (weights, (1.0 - self.ev_ratio) * share + self.ev_ratio * day_share)
            for (weights, share), day_share in zip(
                declared, _day_proportional(shape), strict=True
            )
        )


def _day_proportional(shape: DailyShape) -> tuple[float, ...]:
    """자산 달력의 **일수 비례 몫** — 계절 차례대로, 합이 1 이다 (R67/WP-N1).

    「연중 고르게 쓴다」를 계절 축에 옮긴 것이 이것이다. 전기차 충전이 그
    성질을 갖는다고 본 근거는 `ApplianceSeasonShares._matched` 의 ★ 절이다.

    ⚠ **일수를 여기서 세지 않는다** — 자산이 선언한 `Season.days` 를 그대로
    나눈다. 배포 자산은 봄 92 · 여름 92 · 가을 91 · 겨울 90 (합 365)이므로
    `0.252055 · 0.252055 · 0.249315 · 0.246575` 이고 **합이 정확히 1** 이다.

    ⚠⚠ **일수를 안 적은 계절**(`days is None`)은 「읽는 쪽이 준 `days` 전부」를
    뜻하며 `DailyShape.__post_init__` 이 **계절이 하나일 때만** 허용한다. 그때
    그 계절이 한 해 전부이므로 몫은 1.0 이고, 이것은 그 계절의 `share` 가 1
    이라는 사실(합이 1)과 같은 값이라 섞어도 아무 수가 움직이지 않는다.
    """
    declared = [season.days for season in shape.seasons]
    if any(days is None for days in declared):
        return tuple(1.0 for _ in declared)
    total = float(math.fsum(days for days in declared if days is not None))
    return tuple((days or 0) / total for days in declared)


def resolve_appliance_season_shares(
    value: object | None,
) -> ApplianceSeasonShares | None:
    """화면·시나리오가 적은 `{계절: 몫}` → `ApplianceSeasonShares` 또는 `None`.

    ## 무엇이 「미지정」인가

    필드가 없거나, 매핑이 비었거나, **칸이 전부 비었을 때**다. 그때 냉난방은
    기본 부하와 같은 계절 몫으로 돌고 출력은 이 배선이 생기기 전과 원소
    하나까지 같다(모듈 머리말 ⛔ 절).

    ## ⚠ 무엇을 거부하는가 — **고쳐 주지 않는다**

    **일부만 적은 것** — 빈 칸을 0 으로 읽으면 그 계절의 냉난방이 통째로
    사라지는데 사용자는 *「아직 안 적었다」* 를 뜻했을 수 있다. 둘을 가를 수
    없으므로 묻는다.
    **합이 1 이 아닌 것** — 자산 머리말의 `share` 규약 그대로다. 0.9 면 연간
    에너지의 10%가 사라지고 1.1 이면 없던 것이 생긴다. 정규화하면 「자산이
    틀렸다」와 「이렇게 쓰기로 했다」가 구별되지 않는다.
    **매핑이 아닌 것** — 계절 이름이 붙지 않은 값의 나열은 어느 계절의 몫인지
    말하지 않은 것이고, 차례로 맞추면 위 `_matched` 가 막으려는 어긋남이
    검사 없이 통과한다.

    ⚠ 계절 **이름·개수**가 자산과 맞는가는 여기서 재지 않는다 — 이 함수는
    자산을 읽지 않으며, 그 대조는 형상이 손에 있는 `_matched` 가 한다.
    """
    if value is None:
        return None
    if isinstance(value, ApplianceSeasonShares):
        return value
    if not isinstance(value, Mapping):
        raise _season_share_rejected(
            f"계절 이름이 붙은 매핑이어야 합니다 (받은 값 {value!r})"
        )
    parsed = [
        (str(name), _non_negative(raw, reject=_season_share_value_rejected))
        for name, raw in value.items()
    ]
    if all(share is None for _name, share in parsed):
        return None
    blank = [name for name, share in parsed if share is None]
    if blank:
        raise _season_share_rejected(
            f"계절 {blank} 의 몫이 비어 있습니다 — 일부만 적으면 그 계절의 "
            "냉난방이 사라지는지 아직 안 적었는지 구별할 수 없습니다"
        )
    total = math.fsum(share for _name, share in parsed if share is not None)
    if abs(total - 1.0) > SHARE_TOLERANCE:
        raise _season_share_rejected(
            f"몫의 합이 {total!r} 입니다 — 1 이어야 합니다. 1 이 아니면 연간 "
            "에너지가 조용히 사라지거나 없던 것이 생기므로 정규화하지 않습니다"
        )
    return ApplianceSeasonShares(
        by_season=tuple((name, share) for name, share in parsed if share is not None)
    )


def _season_share_value_rejected(value: object) -> ValidationError:
    """칸 하나가 수가 아닐 때 — `_non_negative` 가 부른다."""
    return _season_share_rejected(
        f"각 계절의 몫은 0 이상의 수여야 합니다 (받은 값 {value!r})"
    )


def _season_share_rejected(reason: str) -> ValidationError:
    """계절 몫 거부 하나 — **3요소를 갖춘다** (`NFR-303`).

    ⚠ 조치 문면을 한 곳에만 둔다 — `_rejected` 가 같은 판단을 적는다.
    """
    return ValidationError(
        field=APPLIANCE_SEASON_SHARE_FIELD_KEY,
        reason=f"{APPLIANCE_SEASON_SHARE_TITLE}: {reason}",
        action=(
            "계절 칸을 모두 비우거나(그때 냉난방이 기본 부하와 같은 계절 몫으로 "
            "돕니다), 형상 자산이 선언한 계절마다 0 이상의 몫을 적어 **합이 1** "
            "이 되게 하십시오"
        ),
    )


# ── 값이 왔다 — 대장과 자산이 「적지 않은 실행」의 기본이 된다 (R65/WP-2) ────

#: 냉난방 계절 몫의 **자산 자리** — 형상 자산 파일의 최상위 절 이름.
#:
#: ⚠ **대장이 아니다.** 대장 항목(`core/assumption/item.py::AssumptionItem`)의
#: `value` 는 `float | int | str` 스칼라 하나이므로 계절 몫 넷을 담으려면
#: 항목을 넷으로 쪼개야 하고, 그러면 **「합이 1」을 검사할 자리가 사라진다.**
#: 자산 파일은 계절 이름·일수의 정본이고 읽는 쪽이 이미 합을 검사한다.
APPLIANCE_SEASON_SHARE_ASSET_SECTION = "appliance_season_shares"


def asset_appliance_season_shares(
    path: Path | None = None,
) -> ApplianceSeasonShares | None:
    """형상 자산이 선언한 **냉난방 계절 몫** — 절이 없으면 `None` 이다.

    ## 왜 자산이 이것을 갖는가 (R65/WP-2 · 사용자 요구 「계절별 냉난방 부하」)

    계절 이름·일수의 정본이 그 파일이고, 그 파일이 스스로 *「교체는 이 파일 한
    곳에서 끝난다」* 고 적었다. 몫을 코드나 대장으로 옮기면 **계절 이름이 두
    곳에 살고** 한쪽만 고쳐진다 — 그때 같은 인덱스가 서로 다른 날을 가리킨다.

    ## ⚠ 여기서 계절 이름을 대조하지 않는다

    이름·개수가 형상과 맞는가는 `ApplianceSeasonShares._matched` 가 재고,
    합이 1 인가는 `resolve_appliance_season_shares` 가 잰다 — **판정하는 자리를
    늘리지 않는다.** 이 함수가 하는 것은 자산의 절을 `{이름: 몫}` 매핑으로
    읽어 그 관문에 넘기는 것뿐이다.

    ⚠ **절이 없으면 `None` 이고 메우지 않는다.** 그때 냉난방은 기본 부하와
    같은 계절 몫으로 돌며 출력은 이 절이 서기 전과 원소 하나까지 같다 —
    모듈 머리말 ⛔ 절이 그 동일성을 적는다.
    """
    source = path or PROFILE_PATH
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    section = data.get(APPLIANCE_SEASON_SHARE_ASSET_SECTION)
    if not isinstance(section, Mapping):
        return None
    seasons = section.get("seasons")
    if not seasons:
        return None
    return resolve_appliance_season_shares(
        {str(entry["name"]): entry["share"] for entry in seasons}
    )


def with_ledger_defaults(
    loads: ApplianceLoads,
    provider: AssumptionProvider,
    *,
    profile_path: Path | None = None,
) -> ApplianceLoads:
    """**적지 않은 칸만** 대장·자산의 값으로 채운 사본 (R65/WP-2).

    ## ⚠⚠ 차례가 있다 — 실행 입력이 이긴다

        ① 시나리오 yaml · 화면이 적은 수      ← `resolve_appliance_loads`
        ② 대장 `load.heatpump.annual` · `load.ev.annual`   ← 이 함수
        ③ 자산의 `appliance_season_shares:` 절             ← 이 함수

    ①이 `None`(= **적지 않았다**)인 칸만 ②·③이 채운다. 뒤집으면 사용자가
    화면에서 적은 수를 대장이 덮어쓰고, 그때 산출물이 인쇄하는 수와 사용자가
    적은 수가 갈린다.

    ⚠ **칸마다 따로 본다.** 히트펌프만 적은 실행에서 전기차는 대장 값으로
    돈다 — 「하나라도 적었으면 대장을 통째로 무시한다」로 하면 사용자가 한 칸을
    고치는 순간 다른 칸이 조용히 0 이 된다.

    ## ⚠ `0.0` 은 채우지 않는다 — 「없다고 적었다」이기 때문이다

    `resolve_appliance_load` 가 `0` 과 빈 칸을 이미 갈라 두었다(모듈 머리말
    ⚠ 절). `0.0` 인 칸에 대장 값을 얹으면 *「이 단지의 가구에는 히트펌프가
    없다」* 는 진술이 뒤집힌다. 여기서 보는 것은 **`is None` 하나**다.

    ## ⚠⚠ 대장이 아직 비어 있으면 종전과 같다

    `AssumptionSet.load_from_yaml` 이 `track: blocked` 항목을 **싣지 않으므로**
    그 상태에서는 `provider.get()` 이 `None` 이고 이 함수는 받은 것을 그대로
    돌려준다 — 더해지는 값이 0 이고 산출물이 「미지정」을 글자로 인쇄한다.
    **기본 소비량으로 메우는 자리는 이 저장소에 없다.**
    """
    return ApplianceLoads(
        heatpump_kwh=(
            loads.heatpump_kwh
            if loads.heatpump_kwh is not None
            else _ledger_kwh(provider, HEATPUMP_LOAD_LEDGER_KEY, HEATPUMP_LOAD_TITLE)
        ),
        ev_kwh=(
            loads.ev_kwh
            if loads.ev_kwh is not None
            else _ledger_kwh(provider, EV_LOAD_LEDGER_KEY, EV_LOAD_TITLE)
        ),
        season_shares=(
            loads.season_shares
            if loads.season_shares is not None
            else asset_appliance_season_shares(profile_path)
        ),
    )


def _ledger_kwh(
    provider: AssumptionProvider, ledger_key: str, title: str
) -> float | None:
    """대장 항목 하나 → `float` 또는 `None`(대장이 그 값을 갖지 않는다).

    ⚠ **대장 값도 같은 관문(`resolve_appliance_load`)을 지난다.** 대장이 음수나
    `nan` 을 갖게 되는 날 3요소 거부가 나가야 하고, 그 문면은 화면이 같은 값을
    적었을 때와 같아야 한다 — 판정하는 자리가 하나라는 이 모듈의 규약이다.

    ⚠ `required_scalar` 를 쓰지 않는 이유: 그 함수는 **없으면 멈춘다.** 여기서
    멈추면 대장이 이 항목을 갖지 않는 저장소·시험에서 실행이 통째로 죽는다 —
    「없으면 0 으로 돈다」는 뜻 있는 기본이 이미 있고, 그 뜻을 지우면 「적지
    않았다」를 표현할 방법이 사라진다.
    """
    item = provider.get(ledger_key)
    if item is None:
        return None
    return resolve_appliance_load(item.value, ledger_key=ledger_key, title=title)
