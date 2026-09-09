"""ESS 적정용량 역산의 **배선과 인쇄** — 붙임 10 (R64/WP-8b · 사용자 요구 4).

## 왜 이 모듈이 생겼는가 — 산식은 섰는데 **부르는 배포 코드가 0곳이었다**

R64/WP-8a 가 `core/report/ess_sizing.py` 에 역산 산식을 세웠다. 그런데 그
함수를 부르는 코드는 `tests/report/test_ess_sizing.py` 뿐이었고 **화면·리포트에
한 자도 나오지 않았다** — 이 저장소가 R32·R33 에서 여섯 번 만난 「선언·계산은
있는데 읽는 쪽이 없다」와 같은 형태이며, 그 형태를 잡으려고 선 검사가
`scripts/check_unread_extension_points.py` 다. 이 모듈이 그 배선이다.

    실행이 낸 계절별 운전   →  시각별 결손 = max(0, 부하 − PV 발전)
                            →  `build_ess_daily_sizing` 로 계절마다 역산
                            →  붙임 10 의 소절로 인쇄

## 왜 `ess_sizing.py` 안에 넣지 않았는가

그 파일은 **산식**이고, 그 머리말이 *「시각별 부하와 시각별 PV 발전을 **인자로만**
받아 역산할 뿐」* 이라고 스스로 못 박았다 — 실행 결과(`SeasonRun`)·자원(`ESS`)·
탐색 구간을 아는 것은 **배선**의 일이다. 그리고 그 파일은 294줄이라 배선과 인쇄를
더하면 NFR-206 상한(500줄)에 닿는다. ⛔ 상한을 올려 푸는 것은 금지다(spec §16.5) —
이 저장소가 이미 다섯 번 쓴 방법(`pv_allocation.py`·`ess_build.py`·
`household_scale.py`·`ess_schedule.py`·`measured_run.py`)이 새 모듈로 뽑는 것이다.

## ★★★ 판정 — **역산 결과를 실행에 되먹이지 않는다**

역산은 *「이만큼 필요하다」* 를 **말하는** 것이지 설비를 **바꾸는** 것이 아니다.
되먹이면 사업이 스스로 자기 설비를 키우고 결론축이 그 크기를 따라 움직인다 —
**어느 수가 입력이고 어느 수가 결과인지 말할 수 없게 된다.** PV 역산
(`core/report/sizing.py::self_sufficiency_section`)이 이미 그렇게 서 있고(인쇄만
한다) 이 소절도 같다. ⇒ **이 모듈은 결론축을 한 자리도 움직이지 않는다.**
⚠ 골든 회귀(`tests/golden/`)가 그 불변을 잰다.

## ★★ 어느 연차로 역산하나 — **분석기간 말**이다

`ESS.usable_capacity_kwh` 는 SOH 를 곱하므로 같은 정격용량이 해마다 덜 낸다.
사용자 요구 4 가 요구하는 것은 **분석기간 내내** 그 결손을 감당하는 용량이므로,
매는 연차는 **가장 덜 내는 해**, 곧 분석기간 말(`CaseBasis.horizon_years`)이다.
⛔ 1년차로 재지 않는다 — 그러면 20년차에 미달인 용량을 「적정」이라 인쇄한다.

⚠⚠ **그러면서 이 수는 하한이다.** 결손 **형상**은 1년차 운전에서 읽는다 — 운전
창이 `DispatchContext(..., year=Year(1))` 하나이고(`core/casegrid/
seasonal_dispatch.py`) 이 모듈은 자원을 다시 세워 다른 해를 돌리지 않는다(다시
세우면 인쇄된 하루와 결론이 선 하루가 갈린다). 연차가 가면 PV 도 열화해 결손
자체가 커지므로 말년차의 참 결손은 여기 인쇄된 것보다 크다. **소절이 그 사실을
글자로 적는다** — 적지 않으면 검토자가 이 수를 상한으로 읽는다.

## 탐색 구간을 넓히지 않는다

역산 용량이 `core/casegrid/ledger_levels.py::_DESIGN_VARS` 의 `ess_capacity_kwh`
탐색 상한을 넘을 수 있다 — 그때 넓히지 않고 **「밖이다」를 인쇄한다**
(`ESSDailySizing.within_search_range`). 구간을 넓히는 것은 결론축(4.4 적정 용량
검토)이 훑는 폭 자체를 바꾸는 일이고, 넘는 점을 지우지도 않는다.
⛔ **넘는데 넘지 않는 것처럼 적지 않는다.**

## ★★★ 두 값을 나란히 싣고 **어느 쪽이 역산의 답인지 적는다** (R67/WP-N3)

역산이 두 값을 낸다 — **완전 자립분**(저녁 피크를 전량 배터리로 덮는 용량)과
**완화분**(결손의 일부를 계통에서 받는 것을 허용한 용량)이며 **역산 채택안은
완화분**이다(사용자 판정 · `docs/decisions-2026-09-07-R66.md` §4). 완화의 산식과
그 성질(용량·출력이 둘 다 같은 비율로 준다)은 `core/report/ess_sizing.py::
relaxed_shortfall_kwh_by_step` 이 갖는다 — 여기서 다시 적지 않는다.

⚠⚠ **「역산 채택안」은 실행 구성이 아니다.** 실행은 여전히 수준표
(`core/casegrid/ledger_levels.py::_DESIGN_VARS`)가 정한 용량으로 돌고, 이 소절은
머리말 ★★★ 그대로 **진단**이다. ⇒ 표의 마지막 주가 그 둘을 갈라 적는다 —
적지 않으면 검토자가 *「이 용량으로 돌렸다」* 로 읽는다.

⚠⚠⚠ **낱말이 두 가지를 가리켰다** — 그래서 R68/WP-1 이 「채택」에 **무엇의
채택인지**를 붙였다: 역산의 답은 `ADOPTED_TERM`(「역산 채택안」)이고, 「진단값
중 실행에 반영하기로 결정한 값」은 `CAPACITY_KIND_APPLIED`(「채택 용량」)이다.
셋을 갈라 세우는 표는 `capacity_kind_lines` 가 낸다.

⚠ **허용 비율을 소절이 고르지 않는다.** 전제 대장 `policy.grid_supply_allowance`
가 그 값을 갖고 배선부(`core/report/case_report.py`)가 수준표에서 읽어 넘긴다.

## 못 하는 것은 산출물이 말한다

역산할 수 없는 실행이 셋 있다 — 저장장치가 없는 실행 · 잴 운전이 없는 실행 ·
부하 자원이 없는 실행. 그때 절을 **지우지 않고** 사유를 글자로 적는다
(`ESSSizingReview.unmeasurable_reason`). 지우면 검토자가 *「역산이 필요 없었다」*
와 *「역산을 싣지 못했다」* 를 가릴 수 없다.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from core.casegrid.models import SeasonRun
from core.contracts.der import DER
from core.der.ess import ESS
from core.report.capacity import search_range_note
from core.report.dispatch_notes import (
    DispatchHour,
    build_hourly_profile,
    split_by_direction,
)
from core.report.ess_sizing import ESSDailySizing, UsableCapacityKwh, build_ess_daily_sizing
from core.report.sizing import SelfSufficiencySizing, base_level_point

#: 하루의 시각 수. `core/report/dispatch_sections.py::_hour_label` 이 같은 층에서
#: 같은 수를 갖는다 — `core/contracts/units.py` 는 이 값을 내놓지 않고(`HOURS_PER_YEAR`
#: 만 있다), 자원 구획의 사적 상수(`core/der/ess_schedule.py::HOURS_PER_DAY`)를
#: 리포트가 import 하면 표시 층이 한 자원의 하루 정의에 매인다.
_HOURS_PER_DAY: Final[int] = 24

#: 계절이 서지 않은 실행에서 그 하루를 부르는 이름. `CaseReport.dispatch_hours`
#: 독스트링이 그 하루를 「연간등가 하루」라고 부르며, 같은 말을 쓴다.
ANNUAL_EQUIVALENT_LABEL: Final[str] = "연간등가 하루"

# ═════════════════════════════════════════════════════════════════════════
# ★★ 낱말의 정본 — **같은 자료를 그리는 렌더러가 둘이다** (R67/WP-N3-fix)
#
#   심의 리포트 붙임 10  `ess_daily_sizing_section`  (이 파일)
#   검증 리포트 2단계    `core/report/verification_inputs.py::_ess_sizing_table`
#
# ⛔ **둘을 합치지 않았다** — 단위 표기 관례와 절 번호가 달라 표 자체가 다르다.
# 그래서 **낱말만** 여기 한 자리에 둔다: 아래 상수·함수가 문면의 정본이고 두
# 렌더러가 그것을 들여와 쓴다. 베껴 적으면 한쪽만 고쳐지고, 그때 두 산출물이
# **같은 물음에 다르게 답한다** — WP-N3 가 실제로 그 상태를 만들었다(붙임 10 은
# 역산 채택안 642.07kWh 를 싣고 검증 리포트는 917.25kWh 만 실었다).
# ═════════════════════════════════════════════════════════════════════════

#: 역산 채택안 열에 붙는 표시. 표에서 **어느 열이 역산의 답인가**를 한 글자로
#: 가리킨다.
ADOPTED_MARK: Final[str] = "★"

#: 완전 자립분(허용 비율 0) 열 이름의 머리.
SELF_SUFFICIENT_HEAD: Final[str] = "완전 자립"

#: ★★ **「채택」이 두 가지를 가리켰다 — 그래서 무엇의 채택인지를 붙였다**
#: (R68/WP-1 · `docs/verification-report-improvement-2026-09-09.md` §3.2).
#:
#: 종전 낱말은 「채택」 하나였고, 그것이 **역산 갈래 둘 중 답으로 고른 쪽**을
#: 뜻했다(사용자 판정 · `docs/decisions-2026-09-08-R67b.md` §3-3). 그런데 검토서와
#: 독자는 같은 낱말을 **「진단값 중 실행에 반영하기로 결정한 값」**으로 읽었고,
#: 그래서 겨울 642.07kWh 가 *「이 용량으로 돌렸다」* 로 읽혔다 — 실제로 돌린
#: 저장장치는 200kWh / 100kW 다.
#:
#: ⛔ **완화분이 역산의 답이라는 판정을 뒤집지 않았다.** 없앤 것이 아니라
#: **낱말을 갈랐다** — 이 이름이 「역산의 답」 쪽이고, 「실행 반영」 쪽은
#: `CAPACITY_KIND_APPLIED` 다.
ADOPTED_TERM: Final[str] = "역산 채택안"

#: 역산 채택안(완화분) 열 이름의 머리.
ADOPTED_HEAD: Final[str] = f"{ADOPTED_MARK} {ADOPTED_TERM}"

#: ★★★ **용량을 부르는 말 셋** — 「채택」 하나가 두 가지를 가리키던 자리를
#: 갈라 세운 이름이며 `capacity_kind_lines` 의 표가 이 셋을 인쇄한다
#: (R68/WP-1 · `docs/verification-report-improvement-2026-09-09.md` §3.2 의 표).
#:
#:     진단 용량   수요 충족 기준으로 역산한 필요 용량 (② · ③ 이 내는 수)
#:     실행 용량   이 실행의 디스패치와 경제성 계산이 실제로 쓴 용량
#:     채택 용량   진단 용량 중 **실행에 반영하기로 결정한** 값
#:
#: ⚠ 셋을 한 표에 세우지 않으면 독자가 「채택」을 **자기가 아는 뜻**으로 읽는다 —
#: 그것이 이 낱말이 실제로 오독된 형태다(검토서 §3.2 · §6 의 1번).
CAPACITY_KIND_DIAGNOSTIC: Final[str] = "진단 용량"
CAPACITY_KIND_RUNNING: Final[str] = "실행 용량"
CAPACITY_KIND_APPLIED: Final[str] = "채택 용량"


def within_range_head(*, sweep_where: str) -> str:
    """구간 칸의 **이름** — 판정 대상이 「역산 채택안」임을 두 표가 같은 말로 적는다.

    ⚠ `sweep_where` 만 다르다 — 심의 리포트는 본문 `4.4 의`, 검증 리포트는
    `①의` 다(절 번호가 문서마다 다르다). 「밖」이 무슨 뜻인가는 이 칸이 아니라
    `core/report/capacity.py::search_range_note` 가 표 아래에서 답한다.
    """
    return f"{ADOPTED_TERM}이 {sweep_where} 경제성 스윕 구간 안인가"


@dataclass(frozen=True)
class ESSSeasonSizing:
    """계절 하나의 역산 결과 — **이름과 일수를 함께 든다.**

    ⚠ 일수를 여기 싣는 이유는 *「그 결손이 한 해에 며칠인가」* 가 표를 읽는
    사람의 첫 물음이기 때문이다. 계절이 서지 않은 실행에서는 그 하루가 계절이
    아니므로 `days` 가 `None` 이고, 소절은 그것을 「—」로 적는다.
    """

    season_name: str
    days: int | None
    #: **완전 자립분** — 허용 비율 0 으로 돌린 역산(저녁 피크를 전량 배터리로).
    sizing: ESSDailySizing
    #: ★ **완화분이자 역산 채택안** — 결손의 `policy.grid_supply_allowance` 만큼을
    #: 계통에서 받는 것을 허용한 역산(머리말 ★★★). **같은 형의 인스턴스**이며
    #: 담긴 수의 이름이 전부 같다 — 그래서 칸을 늘리지 않고 벌을 둘 둔다.
    relaxed: ESSDailySizing


@dataclass(frozen=True)
class ESSSizingReview:
    """붙임 10 의 ESS 소절이 그리는 것 한 벌.

    ⚠ **못 한 것을 「없음」으로 두지 않는다** — 역산할 수 없는 실행에서는
    `seasons` 가 비고 `unmeasurable_reason` 이 그 사유를 글자로 갖는다(머리말
    마지막 절).
    """

    #: 어느 해에 그 결손을 감당하는가 — 분석기간 말이다(머리말 ★★).
    year: int
    #: 한 스텝의 시간(h). 24스텝 대표일이면 1.0.
    step_hours: float
    #: 정격용량 1kWh 가 `year` 년차에 낼 수 있는 양(kWh). 산식 줄이 이것을
    #: 분모로 적는다 — **적지 않으면 검토자가 SOC 창·SOH·백업 예비의 곱을
    #: 저장소 밖에서 찾아야 한다.**
    usable_per_capacity_kwh: float | None
    seasons: tuple[ESSSeasonSizing, ...]
    unmeasurable_reason: str | None
    search_low_kwh: float
    search_high_kwh: float
    #: ★ **계통 전력공급 허용 비율**(0~1) — 역산 채택안이 어느 완화 위에 섰는가.
    #: 소절이 이 수를 산식 줄에 인쇄한다. 역산할 수 없는 실행에서도 **비율은
    #: 안다**(대장에서 왔다) — 그래서 `_unmeasurable` 도 이것을 싣는다.
    grid_supply_allowance: float
    #: ★★ **이 실행이 실제로 세운 배터리의 정격출력**(kW) — 역산값이 아니다
    #: (R67/WP-③ · 사용자 판정 §4-3 *「진단값과 실제 실행값을 구분한다」*).
    #: 검증 리포트 2단계가 역산 표 **위에** 「지금 도는 구성」을 적을 때 이 수를
    #: 읽는다(`core/report/verification_inputs.py::_run_configuration_lines`) —
    #: 그 줄이 수를 리터럴로 갖지 않게 하는 것이 이 칸의 유일한 쓰임이다.
    #: ⚠ 용량 쪽은 설계 변수라 `capacity_review` 가 이미 갖는다. 정격출력은
    #: 설계 변수가 아니어서 **`CaseReport` 어디에도 수로 없었다.**
    #: `None` 은 「이 실행에 배터리가 없다」다(`_unmeasurable` 갈래).
    run_power_kw: float | None = None


#: ★★★ ③ 의 1가구 값이 **역산이 아니라 나눗셈**임을 말하는 낱말
#: (R67/WP-③-fix · 오케스트레이터 판정 §2-2).
#:
#: ## 왜 낱말을 상수로 두는가
#:
#: 이 낱말은 **렌더러와 시험이 함께 갖는다**(지시문 §4-2 *「낱말을 리터럴로 두
#: 곳에 적지 말고 상수 하나를 시험과 렌더러가 나눠 갖게 하라」*). 두 곳에 적으면
#: 문면을 고치는 날 한쪽만 고쳐지고, 그때 **시험은 옛 낱말을 찾아 초록불**이다.
PER_HOUSEHOLD_SCALED: Final[str] = "비례 환산"

#: 그 낱말이 붙은 열 이름의 **머리**. ②(`연간 부하(1가구)`)와 **일부러 다르다** —
#: ② 의 1가구 값은 산식을 1호분 부하로 **다시 돈** 것이고 이쪽은 **나눈** 것이다.
#: 같은 이름을 쓰면 두 성질이 같은 표 모양 뒤로 숨는다(지시문 §2-4).
PER_HOUSEHOLD_HEAD: Final[str] = f"1가구({PER_HOUSEHOLD_SCALED})"


def per_household_scaled(value: float, household_count: int | None) -> float:
    """단지 값을 **가구 수로 나눈** 1가구 값.

    ⛔ **이것은 역산이 아니다.** `build_ess_daily_sizing` 의 입력은
    **20호로 돈 운전의 스텝별 시계열**이라 1호분 입력이 저장소에 없고, 1호분
    운전을 만들려면 계절 디스패치를 다시 돌아야 한다(`core/casegrid/**`) —
    리포트 렌더링에서 파이프라인을 다시 도는 일이므로 하지 않는다.

    ⇒ 그래서 **나눈다.** 그 나눗셈이 옳다는 근거는 실측 하나다 —
    `household_count: 1` 로 따로 돌려 **네 계절 전부 비 20.0000**(정확한 선형)임을
    확인했다(R67/WP-③). 부하와 설비가 같은 배수를 타므로 스텝별 결손도 비례한다.
    ⚠ 그 근거를 산출물에서 지우지 마라 — 지우면 다음 사람이 이 열을 **역산
    결과로 읽는다**(`per_household_scaled_notes` 가 그 줄을 갖는다).

    ⚠ 가구 수가 없거나 1 이면 나눌 것이 없다 — 그대로 돌려준다.
    """
    if household_count is None or household_count <= 1:
        return value
    return value / household_count


def per_household_scaled_notes(household_count: int | None) -> list[str]:
    """③ 의 1가구 열이 **무엇인지 · 왜 환산인지 · ②와 무엇이 다른지** 세 줄.

    ⚠ **표가 스스로 말해야 한다.** 열 이름의 「비례 환산」 넷 글자만으로는
    *왜* 환산인지가 서지 않고, 그러면 검토자는 ②의 1가구 열과 **같은 성질**로
    읽는다 — 그 둘은 다르다(②는 다시 돈 것 · ③은 나눈 것).
    """
    if household_count is None or household_count <= 1:
        # ② 와 **같은 규칙**이다(지시문 §2-5) — 두 벌이 같은 수이므로 열을 접고
        # 접었다는 사실만 적는다. 정본 문면은
        # `core/report/sizing.py::household_first_notes` 쪽과 짝이다.
        return [
            "- 단지 확대 — **없다**(가구 "
            f"{'한 호' if household_count is None else f'{household_count}호'}"
            " 실행). 1가구 값과 단지 값이 같은 수이므로 **1가구 열을 접었다** — "
            "지운 것이 아니다",
        ]
    return [
        f"- 1가구 열은 **{PER_HOUSEHOLD_SCALED}**이다 — 단지 값을 가구 수 "
        f"{household_count}로 나눈 수이며 **역산을 1호분으로 다시 돈 것이 "
        "아니다.** 이 역산의 입력은 **20호로 돈 운전의 스텝별 시계열**이라 "
        "1호분 운전이 없다",
        "- 환산의 근거 — `household_count: 1` 로 따로 돌려 **네 계절 전부 비 "
        "20.0000**(정확한 선형)임을 확인했다(R67/WP-③). 부하와 설비가 같은 "
        "배수를 타므로 스텝별 결손도 비례한다",
        "- ⚠ **②의 1가구 열과 성질이 다르다** — ②는 같은 산식을 **1호분 부하로 "
        "다시 돈** 값이고, 이 표의 1가구 열은 단지 값을 **나눈** 값이다. 표 "
        "모양이 같아도 두 수가 서 있는 근거는 같지 않다",
    ]


def usable_capacity_probe(ess: ESS) -> UsableCapacityKwh:
    """그 배터리를 **정격용량에 대해 열어** 준다 — `UsableCapacityKwh` 모양.

    ## ⚠ 산식을 옮겨 적지 않는다

    `(SOC상한 − SOC하한) × SOH × (1 − 백업예비)` 를 여기 다시 쓰지 않고, 그
    자원의 `usable_capacity_kwh` 를 **그 자원의 정격용량으로 나눠 비율을 되물어**
    얻는다. 그 곱이 용량에 비례하지 않는 항만으로 이루어져 있다는 사실은
    `core/report/ess_sizing.py::required_ess_capacity_kwh` 독스트링이 이미
    근거로 삼고 있는 것과 같다.

    ## ⚠ 새 `ESS` 를 세우지 않는 이유

    `ESS` 는 dataclass 가 아니라 손으로 쓴 `__init__` 을 가지며 인자가 스물
    남짓이다 — `dataclasses.replace` 가 듣지 않고, 인자를 여기 다시 적으면
    **그것이 사본**이 되어 러너가 SOC 창을 바꾸는 날 조용히 갈린다.
    """

    def usable(*, capacity_kwh: float, year: int) -> float:
        return capacity_kwh * ess.usable_capacity_kwh(year=year) / ess.capacity_kwh

    return usable


def _unmeasurable(
    reason: str, *, year: int, low: float, high: float, allowance: float
) -> ESSSizingReview:
    return ESSSizingReview(
        year=year,
        step_hours=0.0,
        usable_per_capacity_kwh=None,
        seasons=(),
        unmeasurable_reason=reason,
        search_low_kwh=low,
        search_high_kwh=high,
        grid_supply_allowance=allowance,
    )


def _size_pair(
    *,
    load_kwh_by_step: Sequence[float],
    pv_kwh_by_step: Sequence[float],
    step_hours: float,
    usable_capacity_kwh: UsableCapacityKwh,
    year: int,
    search_low_kwh: float,
    search_high_kwh: float,
    grid_supply_allowance: float,
) -> tuple[ESSDailySizing, ESSDailySizing]:
    """같은 하루를 허용 비율 **둘로** 역산한 한 쌍 — (완전 자립분, 완화분).

    ⚠ **허용 비율 0 을 «적어» 부른다** — `core/report/ess_sizing.py::
    build_ess_daily_sizing` 이 그 인자에 기본값을 두지 않는 사유가 그 함수
    독스트링에 있다. 두 호출의 나머지 인자가 **한 글자도 다르지 않아야** 하므로
    호출부에 늘어놓지 않고 이 함수 하나가 갖는다.
    """
    return (
        build_ess_daily_sizing(
            load_kwh_by_step=load_kwh_by_step,
            pv_kwh_by_step=pv_kwh_by_step,
            step_hours=step_hours,
            usable_capacity_kwh=usable_capacity_kwh,
            year=year,
            search_low_kwh=search_low_kwh,
            search_high_kwh=search_high_kwh,
            grid_supply_allowance=0.0,
        ),
        build_ess_daily_sizing(
            load_kwh_by_step=load_kwh_by_step,
            pv_kwh_by_step=pv_kwh_by_step,
            step_hours=step_hours,
            usable_capacity_kwh=usable_capacity_kwh,
            year=year,
            search_low_kwh=search_low_kwh,
            search_high_kwh=search_high_kwh,
            grid_supply_allowance=grid_supply_allowance,
        ),
    )


def _windows(
    hours: Sequence[DispatchHour], seasons: Sequence[SeasonRun]
) -> tuple[tuple[str, int | None, tuple[DispatchHour, ...]], ...]:
    """역산할 하루들 — 계절이 서면 계절마다, 안 서면 연간등가 하루 하나.

    ⚠ **계절을 접어 한 벌로 재지 않는다.** 결손은 스텝마다 `max(0, 부하 − PV)`
    이고 그 `max` 는 비선형이라, 계절을 일수로 가중 평균한 하루에서 재면 겨울의
    부족과 여름의 잉여가 **같은 시각에서 상쇄돼** 결손이 사라진다 — R64/WP-4 가
    운전에서 푼 그 상쇄를 역산 쪽에서 다시 접는 것이 된다.
    """
    if seasons:
        return tuple(
            (season.name, season.days, build_hourly_profile(season.dispatch))
            for season in seasons
        )
    return ((ANNUAL_EQUIVALENT_LABEL, None, tuple(hours)),)


def build_ess_sizing_review(
    *,
    hours: Sequence[DispatchHour],
    seasons: Sequence[SeasonRun],
    resources: Sequence[DER],
    year: int,
    search_low_kwh: float,
    search_high_kwh: float,
    grid_supply_allowance: float,
) -> ESSSizingReview:
    """실행이 낸 운전에서 **계절마다** ESS 적정용량을 역산한다.

    ★ **계절마다 역산을 «두 번» 돈다** — 허용 비율 0(완전 자립분)과
    `grid_supply_allowance`(완화분·역산 채택안). 한 번 돌고 결과에 비율을 곱하지
    않는 이유는 `core/report/ess_sizing.py::build_ess_daily_sizing` 안의 주석이
    갖는다(되먹임 보정이 곱한 뒤 다시 미달로 떨어질 수 있다).

    ⚠ **자원을 다시 세우지 않는다** — 배터리는 `resources`(러너가 실제로 세운
    것)에서 고르고, 결손은 `seasons`(러너가 실제로 돌린 하루)에서 읽는다. 다시
    세우면 인쇄된 하루와 결론이 선 하루가 갈릴 수 있다(`CaseOutcome.resources`
    독스트링이 같은 판단을 이미 받은 자리다).

    ⚠ 배터리가 몫으로 갈린 실행(`ess_shares`)에서는 **첫 배터리**를 고른다 —
    비율(`SOC 창 × SOH × (1 − 백업예비)`)은 몫마다 같고 역산이 쓰는 것은 그
    비율 하나뿐이다(용량은 `usable_capacity_probe` 가 나눠 없앤다).
    """
    ess = next((r for r in resources if isinstance(r, ESS)), None)
    if ess is None or ess.capacity_kwh <= 0.0:
        return _unmeasurable(
            "이 실행에는 저장장치가 없습니다 — 역산할 대상이 없습니다",
            year=year, low=search_low_kwh, high=search_high_kwh,
            allowance=grid_supply_allowance,
        )
    usable = usable_capacity_probe(ess)
    sized: list[ESSSeasonSizing] = []
    step_hours = 0.0
    for name, days, profile in _windows(hours, seasons):
        if not profile:
            return _unmeasurable(
                "이 실행에는 잴 운전이 없습니다 — 결손을 읽을 하루가 없습니다",
                year=year, low=search_low_kwh, high=search_high_kwh,
                allowance=grid_supply_allowance,
            )
        generation, load = split_by_direction(profile)
        if not load:
            return _unmeasurable(
                f"「{name}」에 부하 자원이 없습니다 — 결손을 잴 분모가 없습니다",
                year=year, low=search_low_kwh, high=search_high_kwh,
                allowance=grid_supply_allowance,
            )
        step_hours = _HOURS_PER_DAY / len(profile)
        self_sufficient, relaxed = _size_pair(
            load_kwh_by_step=[
                -sum(hour.per_resource.get(n, 0.0) for n in load)
                for hour in profile
            ],
            pv_kwh_by_step=[
                sum(hour.per_resource.get(n, 0.0) for n in generation)
                for hour in profile
            ],
            step_hours=step_hours,
            usable_capacity_kwh=usable,
            year=year,
            search_low_kwh=search_low_kwh,
            search_high_kwh=search_high_kwh,
            grid_supply_allowance=grid_supply_allowance,
        )
        sized.append(
            ESSSeasonSizing(
                season_name=name,
                days=days,
                sizing=self_sufficient,
                relaxed=relaxed,
            )
        )
    return ESSSizingReview(
        year=year,
        step_hours=step_hours,
        usable_per_capacity_kwh=usable(capacity_kwh=1.0, year=year),
        seasons=tuple(sized),
        unmeasurable_reason=None,
        search_low_kwh=search_low_kwh,
        search_high_kwh=search_high_kwh,
        grid_supply_allowance=grid_supply_allowance,
        # ⚠ **러너가 세운 그 배터리에서 읽는다** — 자원을 다시 세우지 않는다
        # (위 독스트링의 같은 판단). 역산값이 아니라 **실행값**이다.
        run_power_kw=ess.power_kw,
    )


def _range_note(review: ESSSizingReview, sizing: ESSDailySizing) -> str:
    if sizing.within_search_range:
        return "예"
    if sizing.required_capacity_kwh > review.search_high_kwh:
        return f"아니오 — 구간 상한 {review.search_high_kwh:g}kWh 초과"
    return f"아니오 — 구간 하한 {review.search_low_kwh:g}kWh 미만"


def binding_season(review: ESSSizingReview) -> ESSSeasonSizing:
    """가장 큰 용량을 요구하는 하루 — **매는 하루**를 코드가 고른다.

    ⚠⚠ **계절 이름을 어디에도 박지 않는다.** 실측에서 그것은 「겨울」이지만
    그 사실은 자산과 형상이 정한 것이고, 박으면 형상이 바뀌는 날 **틀린 계절이
    매는 하루로 인쇄된다.** 이 함수가 그 선택의 유일한 자리이며
    `_binding_lines` 와 `capacity_kind_lines` 가 나눠 갖는다.

    ⚠ **매는 하루는 두 값에서 같다** — 완화가 스텝마다 같은 상수를 곱하므로
    계절 사이의 순서가 보존된다(`core/report/ess_sizing.py::
    relaxed_shortfall_kwh_by_step` 의 성질). 그래서 완전 자립분으로 고른
    하루가 역산 채택안으로 고른 하루와 같다.
    """
    return max(review.seasons, key=lambda s: s.sizing.required_capacity_kwh)


def _binding_lines(review: ESSSizingReview) -> list[str]:
    """매는 하루를 **한 줄로 집어 준다.**

    ⚠ 표에서 사람이 눈으로 고르게 두지 않는다 — 계절이 넷이면 어느 행이 매는
    행인지가 표를 훑는 순서에 달리고, 그 순서는 자산이 계절을 적은 순서다.

    ⚠ 그래도 **역산 채택안을 함께 적는다**: 적지 않으면 이 줄만 완전 자립분을
    말하고 표는 역산 채택안을 말한다.
    """
    binding = binding_season(review)
    return [
        f"- 매는 하루는 **{binding.season_name}**이다 — {ADOPTED_TERM}으로 저장용량 "
        f"**{binding.relaxed.required_capacity_kwh:,.2f}kWh** · 정격출력 "
        f"**{binding.relaxed.required_power_kw:,.2f}kW**(완전 자립분은 "
        f"{binding.sizing.required_capacity_kwh:,.2f}kWh · "
        f"{binding.sizing.required_power_kw:,.2f}kW)이며, 이 구성이 한 해를 "
        "다 감당하려면 그 계절을 넘겨야 한다",
    ]





def adopted_value_note(review: ESSSizingReview) -> str:
    """★ **역산 채택안이 무엇이고 그 비율이 어디서 왔는가** — 한 줄의 정본.

    ⚠⚠ **출처를 잃지 않는 것이 이 줄의 요점이다.** 「30%」는 이 저장소에 없던
    값이고 **사용자 문면 하나가 유일한 출처**이며 근거 법령·고시는 확인되지
    않았다 — 그 사실이 표에서 빠지면 검토자는 그 수를 제도로 읽는다.
    """
    return (
        f"{ADOPTED_MARK} **{ADOPTED_TERM}은 「계통 허용」 완화분**이다 — 계통에서 받는 "
        f"것을 허용한 비율 **{review.grid_supply_allowance:.0%}** 를 **결손 "
        "시계열에** 걸고"
        # ⚠ 코드 칸 안은 **ASCII** 다 — 아래 결손 산식 줄과 같은 사유이며
        # (`RUF001`) 그 자리는 산식을 그대로 읽는 자리라 ASCII 가 맞다.
        "(`완화 결손 = 결손 x (1 - 허용 비율)`) 그 위에서 위와 **같은 역산**을 "
        "돌린 값이다. 전제 대장 `policy.grid_supply_allowance` 가 그 비율의 "
        "정본이며, 근거 법령·고시는 **확인되지 않았다**"
    )


def relaxation_reach_note(review: ESSSizingReview) -> str:
    """⚠ **완화가 용량에만 걸리는가 출력에도 걸리는가** — 한 줄의 정본.

    다음 사람이 반드시 묻는 물음이고, 적지 않으면 표의 두 열(용량·출력)이 같은
    비율로 준 것을 보고 *「출력까지 깎은 것은 실수」* 로 읽을 수 있다.
    """
    return (
        "⚠ **완화는 용량과 출력에 «둘 다» 걸린다** — 스텝마다 같은 상수를 "
        "곱하므로 합(용량)도 첨두(출력)도 정확히 "
        f"{1.0 - review.grid_supply_allowance:.0%} 가 된다. 「저녁 한 시각에 "
        "계통에서 받는다」가 곧 「그 시각에 배터리가 낼 출력이 그만큼 적다」이므로 "
        "출력이 함께 주는 것이 이 산식의 뜻이다"
    )


def _pv_diagnostic_cell(pv: SelfSufficiencySizing) -> tuple[str, str | None]:
    """진단 용량 칸의 **태양광 조각**과 그 부하 수준의 이름.

    ⚠ **수준을 이름으로 고른다** — `core/report/sizing.py::base_level_point` 의
    `base` 이고 차례를 세어 고르지 않는다. ② 표가 부하 수준 넷을 다 싣고 이
    칸은 **대장 기준 수준 하나**를 대표로 든다 — 넷을 다 들면 한 칸이 표를 넘는다.

    ⚠⚠ **그 규칙을 여기서 다시 쓰지 않는다**(R68/WP-2 부수 정리). R68/WP-1 이
    이 칸을 세울 때 `core/casegrid/ledger_levels.py::LEVEL_NAMES` 에서
    `index("base")` 로 규칙을 다시 썼는데, 같은 규칙이 `sizing.py` 의
    `_mismatch_lines` 에도 있었다 — **사본이 하나 생긴 것**이다. 지금은 그
    모듈이 공개 접근자를 갖고 두 자리가 **그 하나**를 부른다.

    ⚠ 20호 실행에서는 **단지 값**을 든다. 아래 실행 용량이 단지 값이므로 같은
    규모끼리 견줘야 하고, 1가구 값은 ② 표가 싣는다.
    """
    point = base_level_point(pv)
    if point is None:
        return ("태양광 — 역산한 점이 없다", None)
    if pv.scales_to_estate:
        capacity = f"{point.required_capacity_kw:,.2f}kW({pv.estate_label})"
    else:
        capacity = f"{point.household_capacity_kw:,.2f}kW(1가구)"
    return (f"태양광 **{capacity}**", point.source_label)


def _ess_diagnostic_cell(review: ESSSizingReview) -> str:
    """진단 용량 칸의 **저장장치 조각** — 매는 하루의 두 값.

    ⚠⚠ **계절 이름을 박지 않는다** — 매는 하루는 `binding_season` 이 고른다.
    ⚠ 정격출력을 함께 든다 — 실행 용량 쪽이 용량과 출력 둘을 적으므로, 출력이
    빠지면 견줄 수 없는 절반이 생긴다.
    """
    if review.unmeasurable_reason is not None or not review.seasons:
        reason = review.unmeasurable_reason or "역산할 하루가 없습니다"
        return f"저장장치 — 역산하지 못했다({reason})"
    binding = binding_season(review)
    return (
        f"저장장치 {SELF_SUFFICIENT_HEAD}분 "
        f"**{binding.sizing.required_capacity_kwh:,.2f}kWh** / {ADOPTED_TERM} "
        f"**{binding.relaxed.required_capacity_kwh:,.2f}kWh · "
        f"{binding.relaxed.required_power_kw:,.2f}kW** "
        f"({binding.season_name} 기준)"
    )


def capacity_kind_lines(
    *,
    review: ESSSizingReview,
    pv: SelfSufficiencySizing,
    run_used: Sequence[str],
) -> list[str]:
    """★★★ **「채택」이 두 가지를 가리켰다** — 셋으로 갈라 세운 구분 표 (R68/WP-1).

    ## 무엇이 어긋나 있었나 (검토서 §3.2 · §6 의 1번)

    ③ 표의 열 이름이 「★ 채택 정격용량」이고 겨울 값이 642.07kWh 였는데, 이
    실행이 **실제로 돌린** 저장장치는 200kWh / 100kW 다. 한 낱말이 ⓐ *「역산
    갈래 둘 중 답으로 고른 쪽」*(사용자 판정이 정한 뜻)과 ⓑ *「진단값 중 실행에
    반영하기로 결정한 값」*(검토서와 독자가 읽는 뜻)을 함께 가리켰다.

    ⛔ **사용자 판정을 뒤집지 않았다** — 완화분이 역산의 답이라는 것은 그대로다
    (`docs/decisions-2026-09-08-R67b.md` §3-3). 바꾼 것은 **낱말**이다: ⓐ 는
    `ADOPTED_TERM`, ⓑ 는 `CAPACITY_KIND_APPLIED` 이고 이 표가 그 둘 사이에
    `CAPACITY_KIND_RUNNING` 을 세워 셋을 한자리에서 갈라 적는다.

    ## ⚠ 「채택 용량」 칸이 **상수인 이유**

    이 저장소는 **역산 결과를 실행에 되먹이지 않는다**(머리말 ★★★ · 골든
    회귀가 그 불변을 잰다). 그래서 진단값이 실행에 반영된 실행은 **있을 수
    없고**, 그 칸은 계산이 아니라 **규약의 진술**이다. ⛔ 되먹임이 생기는 날
    이 칸을 고치기 전에 머리말 ★★★ 부터 다시 읽어야 한다.

    ## ⚠ 수를 리터럴로 갖지 않는다

    태양광은 `pv` 의 대장 기준 점, 저장장치는 `review` 의 매는 하루,
    실행 용량은 `run_used`(설계 변수의 사용값과 배터리 정격출력)에서 온다.
    """
    pv_cell, pv_source = _pv_diagnostic_cell(pv)
    running = (
        " · ".join(run_used)
        if run_used
        else "**없다** — 이 실행에는 설계 변수가 서지 않았다"
    )
    lines = [
        "| 구분 | 뜻 | 이 실행의 값 |",
        "|---|---|---|",
        f"| **{CAPACITY_KIND_DIAGNOSTIC}** | 수요 충족 기준으로 역산한 필요 "
        f"용량 | {pv_cell} · {_ess_diagnostic_cell(review)} |",
        f"| **{CAPACITY_KIND_RUNNING}** | 이 실행의 디스패치와 경제성 계산이 "
        f"실제로 쓴 용량 | {running} |",
        f"| **{CAPACITY_KIND_APPLIED}** | {CAPACITY_KIND_DIAGNOSTIC} 중 "
        "**실행에 반영하기로 결정한** 값 | **없음 — 이 실행은 진단값을 반영하지 "
        "않았다** |",
        "",
        f"- **{CAPACITY_KIND_RUNNING}이 {CAPACITY_KIND_DIAGNOSTIC}과 다른 사유는 "
        "이 리포트가 갖고 있지 않다 — 사람 판단 자리다.**",
    ]
    if pv_source is not None:
        lines.append(
            f"- {CAPACITY_KIND_DIAGNOSTIC}의 태양광은 **{pv_source}** 의 부하로 "
            "역산한 값이다 — 다른 부하 수준은 아래 ② 표가 싣는다"
        )
    return lines


def ess_daily_sizing_section(review: ESSSizingReview) -> list[str]:
    """**붙임 10** 의 소절 — 경우 「ESS」(하루 결손) 역산 결과.

    ## 왜 본문 4.4 가 아니라 붙임 10 인가

    PV 역산과 **같은 사유이며 같은 자리다** —
    `core/report/sizing.py::self_sufficiency_section` 독스트링이 그 실측(본문
    분량 상한 219줄을 넘겨 빨간불이 났고, 그 실패 문면이 *「늘어난 것을 붙임으로
    내릴 것」* 이라 적었다)을 갖는다. ⛔ **새 붙임을 만들지 않는다** — 붙임 10 이
    이미 *「설계 변수마다 역산 결과를 적는 자리」* 이고 PV 가 거기 있다.

    이 표도 PV 쪽과 같이 **진단이지 답이 아니다** — `_DESIGN_VARS` 탐색 구간도
    실행의 용량도 여기서 바꾸지 않는다(머리말 ★★★).

    ## ⚠⚠ **같은 자료를 그리는 렌더러가 하나 더 있다** (R67/WP-N3-fix)

    검증 리포트 2단계의 `core/report/verification_inputs.py::_ess_sizing_table`
    이 **같은 `ESSSizingReview`** 를 다른 관례(단위를 값에 붙여 쓴다 · 절 번호가
    `①`)로 그린다. ⛔ **한쪽만 고치지 마라** — WP-N3 가 이 표에만 역산 채택안을
    실었고, 그동안 검증 리포트는 완전 자립분 917.25kWh 만 실어 **두 산출물이
    같은 물음에 다르게 답했다.** 낱말의 정본은 이 파일 머리의 상수·함수 넷이다
    (`ADOPTED_HEAD` · `SELF_SUFFICIENT_HEAD` · `within_range_head` ·
    `adopted_value_note`).
    """
    lines = [
        "### 경우 「ESS」 — 하루의 결손을 방전만으로 감당하는 최소 용량 (역산)",
        "",
    ]
    if review.unmeasurable_reason is not None:
        # ⚠ 절을 지우지 않는다 — 머리말 마지막 절.
        lines += [f"- 역산하지 못했다 — {review.unmeasurable_reason}", ""]
        return lines
    lines += [
        # ★ **두 값을 나란히 싣는다** (R67/WP-N3 · 머리말 ★★★). ★ 열이 역산 채택안이다.
        # ⚠ 열 이름의 낱말은 **파일 머리의 상수**에서 온다 — 검증 리포트의 같은
        # 표가 그것을 나눠 갖는다(위 독스트링 ⚠⚠).
        "| 하루 | 연 일수 | 하루 결손 합 (kWh) | 첨두 결손 (kWh) | "
        f"{SELF_SUFFICIENT_HEAD} 저장용량 (kWh) | "
        f"{SELF_SUFFICIENT_HEAD} 정격출력 (kW) | "
        f"{ADOPTED_HEAD} 저장용량 (kWh) | {ADOPTED_HEAD} 정격출력 (kW) | "
        f"{within_range_head(sweep_where='4.4 의')} |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for season in review.seasons:
        sizing = season.sizing
        lines.append(
            f"| {season.season_name} | "
            f"{'—' if season.days is None else f'{season.days:,}'} | "
            f"{sizing.required_discharge_kwh:,.4f} | "
            f"{sizing.peak_shortfall_kwh:,.4f} | "
            f"{sizing.required_capacity_kwh:,.2f} | "
            f"{sizing.required_power_kw:,.2f} | "
            f"{season.relaxed.required_capacity_kwh:,.2f} | "
            f"{season.relaxed.required_power_kw:,.2f} | "
            f"{_range_note(review, season.relaxed)} |"
        )
    lines.append("")
    lines += [
        # ⚠ 코드 칸(`max(...)`) 안은 **ASCII 붙임표**다 — 유니코드 마이너스를 쓰면
        # `RUF001` 이 울고, 그 자리는 산식을 그대로 읽는 자리라 ASCII 가 맞다.
        "- 결손 — 시각마다 `max(0, 부하 - PV 발전)` 이며 **음수로 상계하지 "
        "않는다**: 낮에 남은 PV 를 저녁 결손에서 빼면 저장 없이 시간을 건너뛴 "
        "것이 되어 ESS 를 세우는 이유가 사라진다",
        f"- 산식 — 필요 저장용량(kWh) = 하루 결손 합 ÷ (정격용량 1kWh 가 "
        f"{review.year}년차에 낼 수 있는 양 "
        f"{review.usable_per_capacity_kwh:.6f}kWh) · 필요 정격출력(kW) = 첨두 "
        f"결손 ÷ 한 스텝의 시간 {review.step_hours:g}h",
        # ★ **완화가 무엇에 걸렸는가** — 산식과 그 성질을 표 아래에 적는다.
        # ⚠ 문면의 정본은 파일 머리의 함수 둘이다 — 검증 리포트의 같은 표가
        # 그것을 나눠 갖는다(위 독스트링 ⚠⚠).
        f"- {adopted_value_note(review)}",
        f"- {relaxation_reach_note(review)}",
        f"- 연차 **{review.year}년차(분석기간 말)** 기준이다 — SOH 가 해마다 "
        "떨어져 같은 정격용량이 덜 내므로, 분석기간 내내 감당하려면 가장 덜 내는 "
        "해로 재야 한다",
        "- ⚠ **이 수는 하한이다** — 결손 형상은 1년차 운전에서 읽었고(운전 창이 "
        "하나다) 연차가 가면 태양광도 열화해 결손 자체가 커진다",
    ]
    lines += _binding_lines(review)
    lines += [
        # ★ 「구간 밖」이 무슨 뜻인가 — 문면의 정본은 `capacity.py` 다
        # (R67/WP-N2 · 판정 §2-2). 실측에서 겨울 필요 용량이 탐색 상한을 넘어
        # 「밖」이 붙는데, 그것을 *「넘었으니 못 믿는다」* 로 읽으면 사용자 판정
        # (*「용량 범위 제한이 없어야 하며」*)과 반대가 된다.
        f"- {search_range_note(sweep_where='본문 4.4')}",
        # ★★ 「역산 채택안」과 「실행 구성」을 갈라 적는다 (머리말 ⚠⚠ · 사용자
        # 판정 R67 §4-4 *「적용 전이면 결과를 만들어 낸 것처럼 표시하지 않는다」*).
        # ⛔ 이 줄을 지우면 검토자가 ★ 열을 *「이 용량으로 돌렸다」* 로 읽는다.
        f"- 이 표는 **진단이다 — 아직 적용 전이다.** {ADOPTED_MARK} 는 두 역산값 "
        f"중 **{ADOPTED_TERM}**(제시하는 값)이라는 뜻이고, 그 용량을 이 실행의 "
        f"설비로 **채택한 것이 아니다** — {CAPACITY_KIND_APPLIED}은 **없다.** "
        "역산 결과를 실행에 되먹이지 않으므로 위 4.4 의 결론축은 이 수에 "
        "움직이지 않는다",
        "",
    ]
    return lines
