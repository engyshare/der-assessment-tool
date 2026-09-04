"""영향도 스윕 한 덩어리 — `core/report/case_report.py` 에서 R54/WP-2 가 옮겼다.

## 왜 뗐는가 — 줄 상한에 걸렸고, 그래서 생략된 배선이 있다

`case_report.py` 가 `NFR-206` 코드 줄 상한(500)에 **정확히** 걸려 있었다.
R53/WP-1 이 상한에 맞추느라 `_Sweeper` 쪽 배선 하나를 넣을 자리가 없어
생략했고(경위는 `case_report.py` 의 `DISTRIBUTED_CREDIT_LEDGER_KEYS` 옆
주석이 갖는다), 이 WP 가 쪼개 자리를 내고 **그 배선을 넣는다** — 아래
`_Sweeper.conclusion_at_many` 의 `distributed_sub_items`(R54/WP-3 이후로는
스칼라 하나가 아니라 `DistributedSubItems` 다섯 칸이다).

★ **분리는 동작을 바꾸지 않는다.** 여섯을 주석·독스트링째로 통째로 옮겼고
호출 방향은 `case_report.py` → 이 모듈 하나뿐이다.

## 무엇의 본보기를 따랐는가

`core/casegrid/pv_allocation.py`(R51/WP-5) · `core/report/perspective_section.py`
(R52/WP-A) · `core/casegrid/grid_support.py`(R51/WP-7 · R54/WP-1) — 발명한
것은 없다.

## 누가 쓰는가 — `case_report.py` 하나, 그리고 재수출 경로

`case_report.py` 가 import 한다. 상수 넷과 `MAX_SUBSIDY_RATE`·`InfluenceEntry`
는 **거기서 재수출된다** — `CONCLUSION_METRIC` 를 `core/report/shortfall.py`
와 검사 파일 넷이 `case_report` 경로로 읽고, `narrative.py` 가
`InfluenceEntry` 를 그 경로로 읽는다. 그 경로가 깨지면 「분리가 동작을 안
바꾼다」가 어긋난다(`scripts/check_docstring_references.py` 머리말의
「재수출을 참으로 인정한다」 규약, R43 · WP-F3).

## 왜 상수가 이쪽에 있는가 — 순환 import

`pv_allocation.py` 독스트링이 적은 이유와 같다. `_Sweeper` 가 `PLAN_VARIANT`·
`CONCLUSION_METRIC` 를 읽고 `residual_gap_at_full_support_won` 이
`MAX_SUBSIDY_RATE` 를 읽는데, 이 모듈이 그것을 `case_report` 에서 import 하면
`case_report` → 이 모듈 → `case_report` 의 순환이 되어 `lint-imports` 의 계층
계약이 깨진다. 방향은 하나뿐이다: **이 모듈이 상수를 갖고, `case_report` 가
이 모듈에서 읽는다.** 그래서 `MAX_SUBSIDY_RATE` 는 옮길 상수 넷에 끼지
않았지만 같은 규칙에 걸려 함께 넘어왔다 — 읽는 쪽(
`residual_gap_at_full_support_won`)이 이곳에 있고, 대장에 남겨두면 같은
순환이다(재수출로 `narrative.py`·검사 파일의 경로는 산다).

## ⚠ `_provenance` 는 여기에 없다 — 호출부가 주입한다

`_influences` 가 부기 칸을 `_provenance()` 로 만드는데, 그 함수는 이 WP 가
옮기지 않기로 한 것이다(영향도 스윕 한 덩어리만 뗀다 — 둘을 떼면 전건이
달라졌을 때 어느 쪽 탓인지 갈라낼 수 없다). 그런데 이 모듈이 그것을
import 하면 위와 같은 순환이다. 그래서 `_influences` 는 **호출부가
`provenance` 를 넘기게** 한다 — `_Sweeper` 가 `rec_price_won_per_unit` 를
생성자로 받는 것과 같은 형태다.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from core.assumption.provider import AssumptionSet
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import (
    design_variables,
    ledger_backed_variables,
    ledger_unit_scales,
)
from core.casegrid.profiles import DailyShapes
from core.cba.baseline import BaselineArrangement, PoolMeteringDeclaration
from core.contracts.assumptions import AssumptionValue
from core.incentive.schemas import IncentiveScheme
from core.report.sensitivity import rank_influences
from core.valuestream import DistributedSubItems

#: 주 지표 — 표시되는 결론이다 (`FR-1002-AC1`).
HEADLINE_METRIC = "payback_years"
#: 전환 판정에 쓰는 축. 근거 절(「결론 지표를 NPV 로 잡은 이유」)은 조립기
#: 쪽 — `case_report.py` 모듈 독스트링 — 에 남아 있다.
CONCLUSION_METRIC = "npv"
#: 결론을 읽는 변형 — **지원을 반영한 사업**이다.
#:
#: ⚠ `CaseOutcome.metrics` 는 지원을 반영하지 않는다. 러너가 케이스 지표를
#: **총사업비를 `t=0` 에 둔 값**으로 내기 때문이며(`e2e_runner` 독스트링), 그것은
#: 규약이지 결함이 아니다 — 지원의 효과는 `variants` 가 나른다. 그래서 보조율
#: 80% 시나리오와 무보조 시나리오의 `metrics` 는 **같다.** 리포트가 그 수를
#: 결론으로 적으면 *「80% 를 지원해도 결과가 같다」* 는 틀린 진술이 된다.
PLAN_VARIANT = "as_planned"
#: 무지원 기준선 — `FR-607-AC1` 이 「모든 실행에 자동 포함」을 요구하는 변형.
BASELINE_VARIANT = "unsupported"
#: 지원의 **상한** — 사업비 전액(100%).
#:
#: ★ 리포트가 스스로 정한 값이 아니다. `DV-1`(보조금 + 융자가 총사업비를 넘어
#: **자부담이 음수**가 되는 상태를 거부)이 강제하는 천장이며, 그 검증이 살아
#: 있는 한 이보다 높은 지원율은 **실행 자체가 거부된다** — 실측으로 확인했다
#: (132.2% 를 넣으면 `[DV-1] incentivescheme.subsidy_rate_or_loan_rate`).
#: 그래서 환산이 이 값을 넘은 순간 그 수는 *「이만큼 지원하면 된다」* 가 아니라
#: *「지원만으로는 안 된다」* 를 말한다(판정 `docs/decisions-2026-08-31-R49.md`
#: §2).
#:
#: 🚫 **여기 숫자를 올려 천장을 넓히지 마라.** `DV-1` 을 먼저 반박하지 않으면
#: 리포트가 **실행되지 않는 조건**을 달성 조건으로 싣게 된다.
MAX_SUBSIDY_RATE = 1.0


def break_even_subsidy_rate(
    *, subsidy_rate: float, npv_won: float, total_project_cost_won: float
) -> float:
    """결론 축을 0 으로 만드는 지원율 — **환산 한 곳**.

    `CaseReport.break_even_subsidy_rate`(본문 5.1 이 싣는 값)와 붙임 3 의 산식
    대입값이 **같은 함수**를 쓴다. 갈라 두면 본문과 붙임이 서로 다른 수를 싣게
    되고, 그 어긋남은 검토자가 두 자리를 대조할 때에야 드러난다 — 이 저장소가
    「사본을 만들지 않는다」로 반복해 막아 온 형태다.

    규약과 근거는 `CaseReport.break_even_subsidy_rate` 독스트링에 있다.
    """
    if total_project_cost_won <= 0.0:
        # 0 으로 나누어 `inf` 를 싣지 않는다. 총사업비가 0 인 실행은 「지원할
        # 대상이 없다」이며, 그 상태를 비율로 적으면 검토자는 그것을 달성
        # 불가능한 지원율로 읽는다.
        raise ValueError(
            "총사업비가 0 이어서 전환 지원율을 환산할 수 없습니다 — "
            "무지원 기준선의 초기지출이 0 인 실행입니다"
        )
    return subsidy_rate - npv_won / total_project_cost_won


def residual_gap_at_full_support_won(
    *, subsidy_rate: float, npv_won: float, total_project_cost_won: float
) -> float:
    """**전액(`MAX_SUBSIDY_RATE`) 지원해도 남는 결손** — 환산 한 곳.

    부호 있는 값이다 — 음수면 전액 지원으로도 여전히 결손이고, 0 이상이면
    지원만으로 결론이 선다. 전환 지원율이 상한을 넘어 **답으로 제시할 수 없는**
    자리에서 리포트가 그 대신 싣는 수이며(판정 §2 의 *「얼마나 모자라는가」*),
    근거는 `break_even_subsidy_rate` 와 **같은 한 문장**이다 —
    *「지원 1원은 결론 축을 정확히 1원 올린다」*
    (`CaseReport.break_even_subsidy_rate` 독스트링의 「왜 환산인가」 절).
    지원율을 상한까지 올리면 결론 축은 남은 지원분 `(1 - s) × I_total` 만큼
    오르고, 상한 위로는 올릴 곳이 없다.

    ⚠ 여기서 나누지 않으므로 총사업비 0 을 막지 않는다 — 그 실행은 위
    `break_even_subsidy_rate` 가 먼저 사유를 말하며 멈춘다.
    """
    return npv_won + (MAX_SUBSIDY_RATE - subsidy_rate) * total_project_cost_won


@dataclass(frozen=True)
class InfluenceEntry:
    """영향도 한 줄 — 순위와 **부기**를 함께 나른다 (`FR-1002-AC3`).

    부기를 여기서 함께 담는 이유는 `AssumptionValue` 가 값과 부기를 함께 나르는
    이유와 같다: 순위를 만든 뒤 출처를 따로 찾아 붙이는 구조라면 반드시 빠지고,
    빠진 자리는 「출처 미상」이 아니라 그냥 **빈칸**으로 나타난다.
    """

    variable: str
    ledger_key: str | None
    #: ⚠ **대장 단위로 되돌린 값이다** (`ledger_unit_scales`). 계산에 쓰이는
    #: 값은 환산된 것이지만, 리포트는 `value_unit` 과 같은 행에 이 값을
    #: 싣는다 — 환산값을 대장 단위와 나란히 두면 「0.025 %/년」처럼 값과
    #: 단위가 어긋나고, 그것은 실제의 100분의 1로 조용히 읽힌다.
    used_value: float
    low: float
    high: float
    #: 결론 축(NPV, 원)이 low~high 에서 움직인 폭.
    delta_won: float
    #: ★ **두 끝에서의 결론 축 값**(원). 변동폭과 함께 나르는 이유는 폭만으로는
    #: 본문이 답할 수 없는 물음이 둘 남기 때문이다 — *「어느 끝으로 밀어야
    #: 결론에 가까워지는가」* 와 *「끝까지 밀어도 얼마가 남는가」*. 전환 인자가
    #: 0건인 리포트에서 5.1 이 지는 물음이 바로 그 둘이다(R35 가 「없음」 한 줄만
    #: 실었고, 그러면 검토자는 *얼마나 부족한가*를 본문에서 읽을 수 없다).
    npv_low: float
    npv_high: float
    flips_conclusion: bool
    #: 결론이 뒤집히는 인자 값. 뒤집히지 않으면 `None`.
    threshold: float | None
    #: 사용값에서 임계값까지의 여유(%). 뒤집히지 않으면 `None`.
    margin_pct: float | None
    #: ★ **인자를 끝에서 끝까지 흔들어도 결론 축이 한 원도 움직이지 않았다.**
    #:
    #: 「영향이 작다」가 아니라 **정확히 0** 이다. low~high 가 배 이상 벌어진
    #: 구간에서 그런 일은 경제적으로 일어나지 않으므로, 이것이 뜨면 사실상
    #: **파이프라인이 그 인자를 읽지 않는다**는 뜻이다. 리포트가 이것을 「영향도
    #: 최하위」로만 적으면 검토자는 *「요금 인상률은 사업성에 영향이 없다」* 는
    #: **틀린 결론**을 리포트에서 배워 간다 — 실제로는 계산에 들어가지도 않았다.
    #:
    #: 기계는 둘(진짜 무영향/미배선)을 가를 수 없다. 그래서 판정하지 않고
    #: **드러낸다** — 검사가 무엇을 보지 않았는지 말하지 않으면 읽는 사람은
    #: 「전부 검사했고 깨끗하다」로 읽는다.
    unread_by_pipeline: bool
    # ── 부기 (대장 항목이 아닌 모형 파라미터면 비어 있다) ──────────────
    value_unit: str
    base_year: str
    source: str
    confidence: str
    verified_at: date | None
    derivation_method: str


class _Sweeper:
    """한 변수만 움직여 파이프라인을 다시 도는 1변수 스윕 (`FR-1002-AC2`).

    ⚠ **값으로 memo 한다.** 이진탐색이 같은 값을 여러 번 묻고, 한 번이 17ms 다.
    memo 가 없으면 변수 넷에 200회를 넘게 돈다.

    ★ **형상을 본 실행과 같은 것으로 받는다 (R37).** 스윕이 형상 없이 돌면
    본문 2절은 일사 곡선으로, 3·4절(민감도·용량 검토)은 **평탄 발전**으로
    계산되어 두 절이 서로 다른 사업을 그린다 — 그리고 두 절 모두 자기
    기준에서는 매끈하므로 아무 검사도 걸리지 않는다. 인자를 필수로 두지 않고
    기본값 `None` 을 남기는 것이 아니라 **호출부가 넘기게** 하고, 그 배선을
    검사가 붙든다(`tests/report/test_irradiance_wired.py`).

    ★★ **기준선 갈래도 같은 이유로 받는다 (R60/WP-2 · `FR-705-AC2`).**
    갈래가 자가소비를 가르므로(ⓐ 는 0) 스윕이 갈래 없이 돌면 본문 4절과
    5·6절이 **서로 다른 기준선** 위에 서고, 두 절 모두 자기 기준에서는
    매끈하다 — 위 형상과 **완전히 같은 함정**이다. 그래서 기본값을 두지 않고
    **필수 인자**로 받는다: 기본값을 두면 호출부가 잊어도 아무 예외가 나지
    않는다.
    """

    def __init__(
        self,
        *,
        level_map: Mapping[str, Mapping[str, float]],
        horizon_years: int,
        scheme: IncentiveScheme | None,
        daily_shapes: DailyShapes,
        rec_price_won_per_unit: float,
        rec_weight_pv: float,
        distributed_sub_items: DistributedSubItems | None,
        baseline_arrangement: BaselineArrangement,
        pool_metering: PoolMeteringDeclaration | None = None,
    ) -> None:
        self._baseline_arrangement = baseline_arrangement
        # ★ ⓒ 의 계측 선언 (R60/WP-3). **기본값을 두는 것이 안전한 자리다** —
        # 잊으면 ⓒ 의 스윕이 `DV-15` 로 **거부**되므로 어긋남이 조용히
        # 지나가지 않는다. 위 갈래는 그렇지 않아서(기본값이 조용히 다른
        # 기준선을 세운다) 필수 인자로 두었다 — 두 인자의 처리가 다른 것이
        # 그 차이다.
        self._pool_metering = pool_metering
        self._level_map = level_map
        self._horizon_years = horizon_years
        self._scheme = scheme
        self._daily_shapes = daily_shapes
        self._rec_price_won_per_unit = rec_price_won_per_unit
        self._rec_weight_pv = rec_weight_pv
        self._distributed_sub_items = distributed_sub_items
        self._memo: dict[tuple[tuple[str, float], ...], float] = {}

    def conclusion_at(self, variable: str, value: float) -> float:
        """그 변수를 `value` 로 두었을 때의 결론 축(NPV, 원)."""
        return self.conclusion_at_many({variable: value})

    def conclusion_at_many(self, assignment: Mapping[str, float]) -> float:
        """**여럿을 함께** 옮겼을 때의 결론 축 (`core/report/combined.py`).

        1변수 스윕은 이것의 특수한 경우다. 갈라 두면 결합 쪽만 변형을
        (`PLAN_VARIANT`) 읽지 않는 어긋남이 생기고, 그때 두 표가 서로 다른
        사업을 그리면서 아무 검사도 걸리지 않는다.
        """
        key = tuple(sorted(assignment.items()))
        cached = self._memo.get(key)
        if cached is not None:
            return cached
        probe = {
            name: dict(levels) for name, levels in self._level_map.items()
        }
        for variable, value in assignment.items():
            probe[variable] = {**probe[variable], "base": value}
        outcome = run_single_case_e2e(
            {},
            level_map=probe,
            horizon_years=self._horizon_years,
            scheme=self._scheme,
            daily_shapes=self._daily_shapes,
            # ★ **본 실행과 같은 부하를 세운다** (판정 B-1,
            # `docs/decisions-2026-08-31-R48.md` §5). `household_load_annual_kwh`
            # 축을 스윕하는 동안에도 이 자리가 그 값을 읽어야 「그 값을 흔들면
            # 결론이 얼마나 움직이는가」가 실제로 재진다 — 안 읽으면 5.1 표에
            # 그 변수가 올라도 변동폭이 항상 0원이다(`pv_inverter_share` 등이
            # 올라올 때 이 코드가 `case_report.py` 에 살던 시절에 이미 겪은
            # 함정).
            annual_load_kwh=probe["household_load_annual_kwh"]["base"],
            # ★ **본 실행과 같은 REC 단가·가중치를 쓴다** (사용자 판정 §4·§5 ·
            # R51/WP-6·R52/WP-6). 안 넘기면 러너의 기본값이 쓰이고, 대장이
            # 값을 얻는 날 **본문과 5.1 이 서로 다른 사업을 그린다** — 위
            # `annual_load_kwh` 가 적어 둔 것과 같은 함정이다.
            rec_price_won_per_unit=self._rec_price_won_per_unit,
            rec_weight_pv=self._rec_weight_pv,
            # ★ **본 실행과 같은 분산편익 크레딧을 쓴다** (R53/WP-1 ·
            # R54/WP-2 판정 ③ · R54/WP-3 — 대장이 다섯 칸으로 나뉘어 이제는
            # `DistributedSubItems` 하나를 그대로 넘긴다). 지금은 이 값이
            # 사회 열(`.perspectives`)에만 닿고 결론 축(`variants` 의
            # `CONCLUSION_METRIC`)을 움직이지 않으므로 넘겨도 어떤 수도
            # 바뀌지 않는다. 그러나 스윕 결과가 `.perspectives` 를 읽는 날
            # 이 자리가 비어 있으면 **본문과 5.1 이 서로 다른 사업을 그린다**
            # — 위 둘이 적어 둔 것과 같은 함정이다.
            distributed_sub_items=self._distributed_sub_items,
            # ★ **본 실행과 같은 기준선 갈래로 돈다** (`FR-705-AC2` · R60/WP-2).
            # 안 넘기면 러너가 `DEFAULT_BASELINE_ARRANGEMENT` 로 떨어지고,
            # 그러면 본문 4절과 5.1 이 **서로 다른 기준선** 위에 선다 — 위
            # 셋(부하·REC·분산편익)이 적어 둔 것과 같은 함정이며, 이 축은
            # 자가소비를 가르므로 갈래가 다르면 스윕의 절대값이 실제로
            # 어긋난다. **기본값을 여기 적지 않는다** — 호출부가 넘긴다.
            baseline_arrangement=self._baseline_arrangement,
            # ★ **본 실행과 같은 계측 선언으로 돈다** (R60/WP-3). 안 넘기면
            # ⓒ 를 고른 실행에서 5.1·용량 검토가 `DV-15` 로 거부되어 본문
            # 4절만 서고 나머지가 서지 않는다 — 위 넷과 같은 자리이며, 이
            # 인자는 어긋나도 **조용하지 않다**(거부가 난다).
            pool_metering=self._pool_metering,
        )
        result = float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])
        self._memo[key] = result
        return result


def _probe_for(sweeper: _Sweeper, variable: str) -> Callable[[float], float]:
    """그 변수 하나를 움직이는 탐침 함수.

    루프 안에서 `lambda` 로 만들면 **변수를 늦게 묶어** 마지막 이름이 전건에
    적용된다(파이썬의 고전적 함정이며 기본인자로 우회하면 형이 흐려진다).
    함수로 감싸면 묶임이 호출 시점에 고정되고 형도 선다.
    """
    def probe(value: float) -> float:
        return sweeper.conclusion_at(variable, value)

    return probe


def _influences(
    *,
    sweeper: _Sweeper,
    level_map: Mapping[str, Mapping[str, float]],
    provider: AssumptionSet,
    provenance: Callable[[AssumptionValue | None], dict[str, Any]],
) -> tuple[InfluenceEntry, ...]:
    """변수마다 따로 순위 엔진을 부르고 영향폭으로 다시 정렬한다.

    `rank_influences()` 는 `metric_fn` 을 **변수 전체에 하나** 받는다. 스윕은
    변수마다 다른 함수여야 하므로 한 건씩 부른 뒤 여기서 합친다 — 순위 엔진을
    고쳐 변수별 함수를 받게 하는 안은 버렸다. 그 함수는 이미 조항 넷
    (`FR-1002-AC2`·`AC4` 등)에 매여 있고, 합치는 일은 호출부의 몫이다.

    ⚠ **부기 칸 만들기는 주입받는다** — `provenance` 로 넘어오는 함수가
    `case_report.py` 의 `_provenance` 다. 그 함수는 이 WP 가 옮기지 않기로
    했고, 여기서 import 하면 순환이 된다(모듈 독스트링 「`_provenance` 는
    여기에 없다」). 값의 규약은 그 독스트링이 적어 둔 대로다 — 대장 항목이
    아니면 **빈칸이 아니라 그렇게 적는다.**
    """
    ledger_keys = ledger_backed_variables()
    scales = ledger_unit_scales()
    entries: list[InfluenceEntry] = []

    # ★ **설계 변수는 여기서 뺀다** (4.4 가 진다). 5절이 답하는 물음은
    # *「우리가 모르는 것 중 무엇이 결론을 좌우하는가」*, 즉 **무엇을 확보할
    # 것인가**다. 용량은 모르는 값이 아니라 **고르는 값**이고, 한 표에 섞으면
    # 「자료를 더 알아보라」와 「설계를 다시 하라」가 같은 우선순위 표에서
    # 경쟁한다 — 할인율을 5.2 로 가른 것과 같은 판단이다.
    design = {variable.name for variable in design_variables()}

    for variable, levels in level_map.items():
        if variable in design:
            continue
        ranked = rank_influences(
            {variable: dict(levels)},
            metric_fn=_probe_for(sweeper, variable),
        )[0]
        ledger_key = ledger_keys.get(variable)
        note = provenance(provider.get(ledger_key) if ledger_key else None)
        flips = bool(ranked["flips_conclusion"])
        # 표시값을 **대장 단위로 되돌린다** — 위 `used_value` 독스트링 참조.
        scale = scales.get(variable, 1.0) or 1.0
        entries.append(
            InfluenceEntry(
                variable=variable,
                ledger_key=ledger_key,
                used_value=float(levels["base"]) / scale,
                low=float(levels["low"]) / scale,
                high=float(levels["high"]) / scale,
                delta_won=float(ranked["delta"]),
                # 스윕은 **값으로 memo** 한다(`_Sweeper`). 순위 엔진이 이미 두
                # 끝을 물었으므로 여기서 다시 묻는 것은 파이프라인 실행이 아니라
                # 사전 조회다 — 끝값을 순위 엔진의 반환에 태우려면 그 함수가
                # 조항 넷에 매인 자기 계약을 넓혀야 한다(위 독스트링).
                npv_low=sweeper.conclusion_at(variable, float(levels["low"])),
                npv_high=sweeper.conclusion_at(variable, float(levels["high"])),
                flips_conclusion=flips,
                threshold=float(ranked["threshold"]) / scale if flips else None,
                margin_pct=float(ranked["margin_pct"]) if flips else None,
                unread_by_pipeline=(
                    float(ranked["delta"]) == 0.0
                    and float(levels["low"]) != float(levels["high"])
                ),
                **note,
            )
        )

    entries.sort(key=lambda entry: (entry.flips_conclusion, entry.delta_won), reverse=True)
    return tuple(entries)
