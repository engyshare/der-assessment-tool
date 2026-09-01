"""심의용 리포트 **한 장**을 조립한다 — FR-1001 · FR-1002 · FR-1003 · FR-1005.

## 왜 이 파일이 생겼는가 (R33)

`core/report/` 에는 부품이 일습 있었다 — PDF·XLSX 생성기, 차트 7종, 영향도 순위
엔진, 변형 표, 관점별 병렬표, 매니페스트. **그런데 그 부품을 부르는 배포 코드가
한 곳도 없었다.** `generate_pdf()`·`generate_excel()`·`render_charts()`·
`rank_influences()` 의 호출자는 전부 `tests/` 안이었고, `app/routers/` 에 리포트
엔드포인트는 0건이었다.

매핑표는 그동안 초록불이었다. `FR-1001-AC1`~`AC4` 와 `FR-1002-AC1`~`AC6` 이 전부
「자동」으로 세어져 있었기 때문이다 — **부품을 직접 부르는 단위 테스트**가 조항을
가리키고 있었다. R32 가 세 번 만난 형태이며(`overrides()`·`exclusions()`·변형
생산자), 여기서는 그것이 **리포트 전체**에서 일어나 있었다.

그 결과 `MC-1`(Phase 1 인수를 막는 유일한 차단 수동검증)이 **시작될 수 없었다.**
그 검사는 *「검토자에게 리포트만 주고 두 가지를 설명하게 한다」* 인데 줄 리포트를
만드는 통로가 없었다.

## 이 조립기가 답해야 하는 두 질문

`MC-1` 이 검토자에게 시키는 질문이 그대로 이 파일의 산출 구조다.

    「이 회수기간이 왜 이 값인가」        → CaseBasis 의 대입값 + 3중 표기 산식
    「어떤 가정이 바뀌면 결론이 뒤집히나」 → 1변수 스윕 영향도 + 전환 임계값

## ★ 결론 지표를 NPV 로 잡은 이유 — 회수기간의 부호가 없기 때문이다

`FR-1002-AC1` 의 주 지표는 **할인 회수기간**이고 `AC4` 는 *「목표 달성 여부가
뒤바뀌는 인자」* 를 최상단에 두라고 한다. 그런데 회수기간은 **뒤바뀔 부호가
없다** — 회수하지 못하면 `math.inf` 이고, `inf - inf` 는 `nan` 이라 영향폭조차
정의되지 않는다.

**NPV 의 부호가 정확히 그 판정과 같다.** 분석기간 말 누적 할인 현금흐름이
초기투자를 넘느냐가 NPV ≥ 0 이고, 그것이 *「분석기간 안에 회수되는가」* 다.
즉 지표를 바꾼 것이 아니라 **같은 판정을 부호가 있는 축으로 옮긴 것**이며,
표시되는 주 지표는 그대로 할인 회수기간이다. 이 동치는 리포트 본문에도 적는다 —
적지 않으면 검토자가 「왜 갑자기 NPV 인가」에서 막히고, 그 막힘은 `MC-1` 의
미달로 나타나되 원인은 리포트가 설명을 빠뜨린 것이 된다.

## 이 리포트가 도는 「시나리오」가 무엇인가

`fixtures/golden/scenario_*.yaml` 은 머리말이 스스로 밝히듯 **회귀 스냅숏**이며
자원 구성을 담지 않는다. 여기서 그 파일에서 취하는 것은 **지원 조건(보조율)
하나**이고, 나머지 값은 전부 대장(`docs/assumptions.yaml`)의 `base` 수준에서
온다. 그 사실을 리포트 본문이 밝힌다 — 밝히지 않으면 검토자는 픽스처의
`expected_values` 가 이 리포트의 근거라고 읽는다.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from core.assumption.provider import AssumptionSet
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import (
    build_level_map,
    design_variables,
    ledger_backed_variables,
    ledger_unit_scales,
)
from core.casegrid.models import CaseBasis, CashflowSplit
from core.casegrid.profiles import DailyShapes, load_daily_shapes
from core.casegrid.variants import run_order
from core.contracts.assumptions import AssumptionValue
from core.engine.rule_based import DispatchRule
from core.incentive.schemas import IncentiveScheme
from core.report.capacity import CapacityFinding, build_capacity_review
from core.report.combined import CoupledSweep, build_coupled_sweeps
from core.report.dispatch_notes import (
    DispatchHour,
    DispatchNote,
    build_dispatch_notes,
    build_hourly_profile,
)
from core.report.manifest import create_manifest
from core.report.sensitivity import rank_influences

#: 저장소 뿌리 — 리포트에 **저장소 상대 경로**만 싣기 위한 기준이다.
#:
#: ⚠ **절대 경로를 리포트에 싣지 않는다.** 검토자에게 나가는 문서에 개발
#: 기계의 경로가 박히면 ⓐ `SC-3`(비공개 정보 유입) 검사가 커밋을 막고
#: ⓑ 무엇보다 **다른 기계에서 같은 리포트를 다시 뽑을 수 없다** — 재현
#: 정보로서 쓸모가 없어진다.
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: 주 지표 — 표시되는 결론이다 (`FR-1002-AC1`).
HEADLINE_METRIC = "payback_years"
#: 전환 판정에 쓰는 축. 위 독스트링 「결론 지표를 NPV 로 잡은 이유」 참조.
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

#: REC 단가를 담은 대장 키 (사용자 판정 §4 · R51/WP-6). 이 조립기가 대장에서
#: 읽어 러너에 넘긴다 — 이름을 여기 한 번만 적는 이유는 `TARIFF_KEY`
#: (`core/valuestream/settlement.py`)와 같다: 두 곳에 적으면 대장 키를 바꾸는
#: 날 한 곳이 남고, 그때 `provider.get()` 이 **조용히가 아니라** 멈추긴 하지만
#: 어느 쪽이 정본인지 다투게 된다.
REC_PRICE_LEDGER_KEY = "benefit.rec_price"


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
class Formula:
    """3중 표기 한 건 — 자연어 + 수식 + 대입값 (`FR-1001-AC3`)."""

    label: str
    natural: str
    expression: str
    substituted: str


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


@dataclass(frozen=True)
class AssumptionRow:
    """가정 부록 한 줄 (`FR-1002-AC6`)."""

    key: str
    value: float | int | str
    value_unit: str
    base_year: str
    source: str
    confidence: str
    verified_at: date | None


@dataclass(frozen=True)
class CaseReport:
    """검토자에게 건네는 산출물 하나."""

    scenario_name: str
    scenario_path: str
    #: 재현 명령의 `--scenario` 인자. 표제용 이름(`scenario_name`)과 다를 수
    #: 있으므로 따로 나른다 — 표제를 고치면 재현 명령이 조용히 틀려진다.
    scenario_name_slug: str
    subsidy_rate: float
    assumption_set_name: str
    assumption_set_version: str
    price_basis: str
    #: 결론 — **지원을 반영한** 변형의 지표 (`PLAN_VARIANT` 참조).
    metrics: Mapping[str, float]
    #: 무지원 기준선. `FR-607-AC1` 이 「모든 실행에 자동 포함」을 요구하며,
    #: `UI-4` 의 증분 병기가 이 둘의 차로 성립한다.
    baseline_metrics: Mapping[str, float]
    #: 변형 tag → (표시명, 지표). 등록 순서를 지킨다 — 기준선이 맨 위다.
    variant_labels: tuple[tuple[str, str], ...]
    variants: Mapping[str, Mapping[str, float]]
    basis: CaseBasis
    #: 영향도 내림차순 (`FR-1002-AC1`). **한 인자만 움직인 단독 기여**다.
    influences: tuple[InfluenceEntry, ...]
    #: 함께 움직이는 인자를 함께 흔든 결과 (`core/report/combined.py`).
    #: 저장소가 이미 결합으로 선언한 묶음만 나온다 — 여기서 새로 묶지 않는다.
    coupled_sweeps: tuple[CoupledSweep, ...]
    formulas: tuple[Formula, ...]
    assumptions: tuple[AssumptionRow, ...]
    manifest_hash: str
    #: 자원별 「운전 방법 × 디스패치 규칙 × 순위」 (`FR-105-AC4` · 의견 2).
    dispatch_notes: tuple[DispatchNote, ...]
    #: 이 실행이 적용한 규칙 순서. **엔진의 선언을 그대로 나른다** — 리포트가
    #: 기본 순서를 다시 적으면 순서를 바꾼 실행에서 표가 조용히 틀린다.
    rule_order: tuple[DispatchRule, ...]
    #: 대표일 스텝별 운전 (의견 3). **부하·일사 형상을 함께 세운 본 실행**이며
    #: 결론(프로포마·NPV)이 같은 실행 위에 선다 (R48/WP-B · 판정 B-1).
    dispatch_hours: tuple[DispatchHour, ...]
    #: 설계 변수(용량)를 탐색 구간에서 훑은 결과 — 4.4 · 붙임 10.
    #: *「적정 용량 검토가 선행되어야 한다」* 는 지적이 만든 절이다.
    capacity_review: tuple[CapacityFinding, ...]
    #: ★ 엔진이 만든 현금흐름 행 — **5.3 이 결손을 가르는 재료** (판정 §3 ⓐ).
    #:
    #: ⚠ 여기서 요약하지 않는다. `metrics` 는 합계 하나이고 5.3 이 묻는 것은
    #: *「그 합계가 어느 항에서 왔는가」* 다 — 1년차 값으로 되지으면 물가
    #: 상승이 빠져 합계가 결손과 어긋난다(`CashflowSplit` 독스트링).
    cashflows: CashflowSplit

    @property
    def uncertain_influences(self) -> tuple[InfluenceEntry, ...]:
        """**틀릴 수 있는 값** — 대장 항목에서 온 인자만.

        ## ★ 왜 할인율을 여기서 빼는가 (검토 지적 4)

        첫 판은 할인율을 영향도 1위로 실었다. 지적이 정확했다 — *「대부분의
        분석은 할인율을 통제할 수 있는 값으로 보지 않는다. 고정적으로 적용하는
        값을 주요 요인으로 뽑는 것이 의미가 있는가」*.

        영향도 순위가 답하려는 물음은 *「우리가 모르는 것 중 무엇이 결론을
        좌우하는가」*, 즉 **어느 자료를 먼저 확보할 것인가**다. 할인율은 모르는
        값이 아니라 **평가자가 정하는 값**이다. 둘을 한 표에 섞으면 순위 1위가
        「확보할 자료」가 아니라 「이미 정한 규칙」이 되고, 그 표를 읽은 사람은
        확보 우선순위를 잘못 잡는다.

        그렇다고 **버리지도 않는다** — 할인율을 몇으로 정하느냐가 결론을 바꾸는
        것은 사실이며, 그것은 *자료 문제가 아니라 정책 선택*이다. 그래서
        `policy_influences` 로 갈라 **따로** 싣는다.
        """
        return tuple(
            entry for entry in self.influences if entry.ledger_key is not None
        )

    @property
    def policy_influences(self) -> tuple[InfluenceEntry, ...]:
        """**평가자가 정하는 값** — 대장 항목이 아닌 모형 파라미터.

        불확실성이 아니라 **선택**이다. 위 `uncertain_influences` 참조.
        """
        return tuple(entry for entry in self.influences if entry.ledger_key is None)

    @property
    def flipping(self) -> tuple[InfluenceEntry, ...]:
        """결론을 뒤집는 **불확실** 인자 — 최상단에 별도 강조 (`FR-1002-AC4`).

        ⚠ 모형 파라미터는 여기 들어오지 않는다. 위 `uncertain_influences` 참조.
        """
        return tuple(
            entry for entry in self.uncertain_influences if entry.flips_conclusion
        )

    @property
    def provisional_warning(self) -> tuple[InfluenceEntry, ...]:
        """신뢰도 `가정` 이면서 결론을 뒤집는 인자 (`FR-1002-AC5`).

        비면 경고를 띄우지 않는다 — 상시 경고는 읽히지 않고, 읽히지 않는 경고는
        경고가 아니다.
        """
        return tuple(entry for entry in self.flipping if entry.confidence == "가정")

    @property
    def unread_variables(self) -> tuple[InfluenceEntry, ...]:
        """파이프라인이 읽지 않은 것으로 보이는 인자 (`InfluenceEntry` 참조)."""
        return tuple(entry for entry in self.influences if entry.unread_by_pipeline)

    @property
    def recovers_within_horizon(self) -> bool:
        """분석기간 안에 회수되는가 — 리포트의 결론 한 줄."""
        return self.metrics[CONCLUSION_METRIC] >= 0.0

    @property
    def total_project_cost_won(self) -> float:
        """총사업비 — **무지원 기준선의 초기지출**이다.

        지원을 받은 변형의 `initial_outlay_won` 은 지원을 뺀 뒤의 금액이므로
        총사업비가 아니다. 기준선은 `FR-607-AC1` 이 「모든 실행에 자동 포함」을
        요구하므로 **어느 시나리오에서도 이 값이 있다** — 시나리오마다 다른
        분모를 쓰면 같은 사업의 결손 비율이 지원율에 따라 달라진다.
        """
        return float(self.baseline_metrics["initial_outlay_won"])

    @property
    def conclusion_gap_won(self) -> float:
        """결론 축이 **0 에서 떨어진 거리**(원).

        판정하지 않는다 — 부호가 어느 쪽인지는 `recovers_within_horizon` 이
        말한다(미회수면 결손, 회수면 여유). 거리만 재는 이유는 두 방향에서
        같은 물음이기 때문이다: *「0 선까지 얼마인가」*.
        """
        return abs(float(self.metrics[CONCLUSION_METRIC]))

    @property
    def break_even_subsidy_rate(self) -> float:
        """결론 축을 **0 으로 만드는 지원율**.

        ## ★ 왜 이것이 「비율」이 아니라 **환산**인가

        지원은 `t=0` 초기지출 감액이고 순현재가치 산식은 초기투자를 할인하지
        않는다(`NPV = Σ CF_t/(1+r)^t − I₀`). 그래서 **지원 1원은 결론 축을
        정확히 1원 올린다** — 근사도 회귀도 아니다. 총사업비로 나누면 그 금액이
        지원율 단위로 서고, 4.2 가 나란히 싣는 두 변형과 같은 축이 된다.

        ## ★ 이 값이 두 시나리오에서 **같아야** 한다

        무보조(`0%`)와 보조 `80%` 는 서로 다른 결론 축 값을 갖지만, 위 규약이
        옳다면 둘이 내는 전환 지원율은 **같은 수**다. 그 일치가 검사이며
        (`tests/report/test_conclusion_gap.py`), 어긋나면 지원이 `t=0` 감액이
        아닌 다른 경로로 들어왔다는 뜻이다 — 그때는 이 환산을 쓸 수 없다.
        """
        return break_even_subsidy_rate(
            subsidy_rate=self.subsidy_rate,
            npv_won=float(self.metrics[CONCLUSION_METRIC]),
            total_project_cost_won=self.total_project_cost_won,
        )

    @property
    def residual_gap_at_full_support_won(self) -> float:
        """전액(`MAX_SUBSIDY_RATE`) 지원해도 남는 결손 — 부호 있는 값.

        ⚠ **이 값도 두 시나리오에서 한 수여야 한다.** 전환 지원율이 지원율에
        무관한 것과 **같은 이유**다(지원은 `t=0` 감액). 어긋나면 지원이 다른
        경로로 들어온 것이며, 그 대조가 검사다
        (`tests/report/test_conclusion_gap.py`).
        """
        return residual_gap_at_full_support_won(
            subsidy_rate=self.subsidy_rate,
            npv_won=float(self.metrics[CONCLUSION_METRIC]),
            total_project_cost_won=self.total_project_cost_won,
        )

    @property
    def support_alone_can_flip(self) -> bool:
        """**지원만으로 결론을 전환할 수 있는가** (판정 §2).

        환산된 전환 지원율이 상한(`MAX_SUBSIDY_RATE`) 안에 있는가 하나만
        묻는다. 거짓이면 그 환산값은 **넣어 돌릴 수 없는 지원율**이므로
        (`DV-1` 이 거부한다) 리포트는 그것을 답으로 제시하지 않고,
        `residual_gap_at_full_support_won` 과 *「지원율 외의 수단이 필요하다」*
        를 대신 싣는다.

        ⚠ **갈래를 지우지 않는다.** 보조율 대장이 오르거나 사업비가 바뀌면
        이 값은 다시 참이 되고, 그때 리포트는 종전 문면으로 돌아간다.
        """
        return self.break_even_subsidy_rate <= MAX_SUBSIDY_RATE


def _repo_relative(path: Path) -> str:
    """저장소 상대 경로. 밖에 있으면 **파일 이름만** 남긴다 (위 `_REPO_ROOT`)."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return resolved.name


def _load_scenario(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "subsidy_rate" not in data:
        raise ValueError(
            f"시나리오 {path.name} 에 subsidy_rate 가 없습니다. 이 조립기가 "
            "시나리오 파일에서 읽는 것은 지원 조건 하나이며, 나머지 값은 "
            "docs/assumptions.yaml 의 base 수준에서 옵니다"
        )
    return data


def _scheme_for(subsidy_rate: float) -> IncentiveScheme | None:
    """보조율만 다른 지원 조건. 0 이면 **스킴을 주지 않는다**.

    0% 짜리 스킴을 주는 것과 주지 않는 것은 변형 지표에서 같은 결과를 내지만,
    「지원 조건이 없는 사업」과 「지원율이 0인 사업」은 다른 진술이다. 리포트가
    후자로 적으면 검토자는 어딘가에 지원 제도가 있다고 읽는다.
    """
    if subsidy_rate <= 0.0:
        return None
    return IncentiveScheme.create_baseline().model_copy(
        update={"subsidy_rate": subsidy_rate}
    )


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
    """

    def __init__(
        self,
        *,
        level_map: Mapping[str, Mapping[str, float]],
        horizon_years: int,
        scheme: IncentiveScheme | None,
        daily_shapes: DailyShapes,
        rec_price_won_per_unit: float,
    ) -> None:
        self._level_map = level_map
        self._horizon_years = horizon_years
        self._scheme = scheme
        self._daily_shapes = daily_shapes
        self._rec_price_won_per_unit = rec_price_won_per_unit
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
            # 올라올 때 이 파일이 이미 겪은 함정).
            annual_load_kwh=probe["household_load_annual_kwh"]["base"],
            # ★ **본 실행과 같은 REC 단가를 쓴다** (사용자 판정 §4 · R51/WP-6).
            # 안 넘기면 러너의 기본값 0 이 쓰이고, 대장이 단가를 얻는 날
            # **본문과 5.1 이 서로 다른 사업을 그린다** — 위 `annual_load_kwh`
            # 가 적어 둔 것과 같은 함정이다.
            rec_price_won_per_unit=self._rec_price_won_per_unit,
        )
        result = float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])
        self._memo[key] = result
        return result


def _provenance(value: AssumptionValue | None) -> dict[str, Any]:
    """부기 7종을 꺼낸다. 대장 항목이 아니면 **빈칸이 아니라 그렇게 적는다.**"""
    if value is None:
        return {
            "value_unit": "",
            "base_year": "",
            "source": "모형 파라미터 — 대장 항목이 아니다",
            "confidence": "모형",
            "verified_at": None,
            "derivation_method": "평가자가 고르는 값이며 시장에서 관측하지 않는다",
        }
    return {
        "value_unit": value.value_unit,
        "base_year": value.base_year,
        "source": value.source or "출처 미기재",
        "confidence": value.confidence,
        "verified_at": value.verified_at,
        "derivation_method": value.derivation_method,
    }


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
) -> tuple[InfluenceEntry, ...]:
    """변수마다 따로 순위 엔진을 부르고 영향폭으로 다시 정렬한다.

    `rank_influences()` 는 `metric_fn` 을 **변수 전체에 하나** 받는다. 스윕은
    변수마다 다른 함수여야 하므로 한 건씩 부른 뒤 여기서 합친다 — 순위 엔진을
    고쳐 변수별 함수를 받게 하는 안은 버렸다. 그 함수는 이미 조항 넷
    (`FR-1002-AC2`·`AC4` 등)에 매여 있고, 합치는 일은 호출부의 몫이다.
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
        note = _provenance(provider.get(ledger_key) if ledger_key else None)
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


def _formulas(
    basis: CaseBasis,
    metrics: Mapping[str, float],
    *,
    subsidy_rate: float,
    total_project_cost_won: float,
) -> tuple[Formula, ...]:
    """주 지표와 결론 축의 3중 표기 (`FR-1001-AC2`·`AC3`).

    ⚠ `I₀` 는 `CaseBasis` 의 총사업비가 아니라 **그 변형이 실제로 낸 초기지출**
    이다. 총사업비를 적으면 지원을 받은 사업의 산식이 지원 전 금액으로 서고,
    검토자가 대입값을 따라가면 리포트의 결론과 다른 수가 나온다.
    """
    payback = metrics[HEADLINE_METRIC]
    payback_text = (
        f"{payback:.2f}년" if payback != float("inf") else "분석기간 내 미회수"
    )
    outlay = int(metrics["initial_outlay_won"])
    flip_rate = break_even_subsidy_rate(
        subsidy_rate=subsidy_rate,
        npv_won=float(metrics[CONCLUSION_METRIC]),
        total_project_cost_won=total_project_cost_won,
    )
    net = basis.annual_benefit_won - basis.annual_cost_won
    # ★ **환산이 지원 상한을 넘으면 붙임 3 이 그것을 함께 진다** (판정 §2).
    # 산식은 **지우지 않는다** — 본문의 그 수가 어디서 왔는지 대입값으로 말하는
    # 자리가 사라지면 검토자가 따라갈 통로가 없어진다(`MC-1` 의 첫 물음).
    # 대신 그 결과가 **답으로 성립하지 않는다**는 것을 대입값 줄이 함께 적고,
    # *「그러면 얼마가 모자라는가」* 는 아래 「전액 지원 시 잔여 결손」 산식이
    # 답한다 — 요구된 수가 **감사 가능해야** 하기 때문이다.
    over_ceiling = flip_rate > MAX_SUBSIDY_RATE
    residual = residual_gap_at_full_support_won(
        subsidy_rate=subsidy_rate,
        npv_won=float(metrics[CONCLUSION_METRIC]),
        total_project_cost_won=total_project_cost_won,
    )
    ceiling_note = (
        f" — ⚠ 지원 상한 {MAX_SUBSIDY_RATE:.0%}(사업비 전액)를 넘어 "
        "지원율로는 답이 성립하지 않는다"
        if over_ceiling
        else ""
    )
    formulas = (
        Formula(
            label="연 순현금흐름",
            natural="연 순현금흐름 = 연 편익 - 연 운영비",
            expression="CF = B - C",
            substituted=(
                f"{net:,}원 = {basis.annual_benefit_won:,}원 "
                f"- {basis.annual_cost_won:,}원"
            ),
        ),
        Formula(
            label="순현재가치",
            natural=(
                "순현재가치 = 분석기간 동안의 순현금흐름을 할인해 더한 뒤 "
                "초기투자를 뺀 값"
            ),
            expression="NPV = Σ(t=1..T) CF_t / (1+r)^t - I₀",
            substituted=(
                f"{metrics[CONCLUSION_METRIC]:,.0f}원 = Σ(t=1..{basis.horizon_years}) "
                f"CF_t / (1+{basis.discount_rate:.3f})^t - {outlay:,}원"
            ),
        ),
        Formula(
            label="할인 회수기간",
            natural=(
                "할인 회수기간 = 누적 할인 현금흐름이 초기투자에 도달하는 시점. "
                "분석기간 안에 도달하지 못하면 「미회수」"
            ),
            expression="min{ T' : Σ(t=1..T') CF_t / (1+r)^t ≥ I₀ }",
            substituted=(
                f"{payback_text} — I₀ = {outlay:,}원 · "
                f"r = {basis.discount_rate:.1%} · T = {basis.horizon_years}년"
            ),
        ),
        # ★ **본문 5.1 의 「전환 지원율」이 여기서 감사된다.** 본문은 환산값만
        # 싣고, 그 값이 어디서 왔는지는 이 산식이 대입값으로 말한다 — 붙임 없이
        # 본문에만 두면 검토자가 52.6% 를 따라갈 자리가 없다(`MC-1` 의 첫 물음).
        Formula(
            label="결론 전환 지원율",
            natural=(
                "결론 전환 지원율 = 현 지원율 - 순현재가치 ÷ 총사업비. "
                "지원은 t=0 초기지출 감액이고 순현재가치 산식은 초기투자를 "
                "할인하지 않으므로, 지원 1원이 결론 축을 정확히 1원 올린다"
            ),
            expression="s* = s - NPV / I_total",
            substituted=(
                f"{flip_rate:.1%} = {subsidy_rate:.1%} - "
                f"({metrics[CONCLUSION_METRIC]:,.0f}원) "
                f"÷ {total_project_cost_won:,.0f}원{ceiling_note}"
            ),
        ),
    )
    if not over_ceiling:
        return formulas
    # RUF001: 「×」는 검토자가 읽는 **산식 문면**이다. `x` 로 바꾸면 곱셈이
    # 변수 이름처럼 읽힌다 — `core/casegrid/operating_lines.py` 가 같은 자리에
    # 같은 판정을 적어 두었다.
    return (
        *formulas,
        Formula(
            label="전액 지원 시 잔여 결손",
            natural=(
                "전액 지원 시 잔여 결손 = 순현재가치 + (지원 상한 - 현 지원율) "
                "× 총사업비. 지원은 t=0 초기지출 감액이므로 지원율을 상한"  # noqa: RUF001
                f"({MAX_SUBSIDY_RATE:.0%})까지 올려도 결론 축은 남은 지원분"
                "만큼만 오르고, 그 위로는 올릴 곳이 없다"
            ),
            expression="R = NPV + (1 - s) × I_total",  # noqa: RUF001
            substituted=(
                f"{residual:,.0f}원 = {metrics[CONCLUSION_METRIC]:,.0f}원 + "
                f"({MAX_SUBSIDY_RATE:.1%} - {subsidy_rate:.1%}) "
                f"× {total_project_cost_won:,.0f}원"  # noqa: RUF001
            ),
        ),
    )


def _appendix(provider: AssumptionSet) -> tuple[AssumptionRow, ...]:
    """전 가정 목록 — 영향도 순위와 **별개로** 제공한다 (`FR-1002-AC6`).

    ## ★ 값은 **실행이 쓴 값**이다 — `items()` 는 기준값만 안다 (R48-E1)

    `items()` 가 내주는 `AssumptionItem.value` 는 대장에 적힌 **기준값**이고,
    오버라이드는 `AssumptionSet.get()` 에만 반영된다. 종전 이 함수는
    `items()` 의 값을 그대로 실었으므로, **전제를 덮어쓴 실행에서도 붙임 1 은
    덮어쓰기 전 값을 실었다** — 계산은 새 값으로 하고 「전 가정 전건」은 옛
    값을 싣는 것이다. 검토자가 리포트만으로 결과를 재구성하면 **다른 수가
    나오고**, 그 어긋남은 아무 예외도 내지 않는다.

    ⚠ **목록의 범위는 여전히 `items()` 가 짓는다.** `get()` 은 키 하나에만
    답하므로 전건을 세는 자리를 오버라이드 쪽으로 옮기면 **덮어쓰지 않은
    항목이 붙임 1 에서 사라진다** — 그 순간 `FR-1002-AC6` 위반이다. 여기서
    바뀌는 것은 **행의 값**뿐이고 행의 집합이 아니다.

    ⚠ **「덮어썼다」는 표시는 이 자리가 만들지 않는다.** 기준값과 나란히
    보일지, 어느 조항이 그 표시를 소유하는지는 아직 사람 판정이 남은
    자리다(`status-human.md`). 이 함수가 지는 것은 **실린 값이 실행이 쓴
    값인가**까지다 — 재료는 `provider.overridden_items()` 에 이미 있다.
    """
    rows: list[AssumptionRow] = []
    for item in sorted(provider.items().values(), key=lambda i: i.key):
        effective = provider.get(item.key)
        rows.append(
            AssumptionRow(
                key=item.key,
                # `get()` 은 `items()` 에 있는 키에 `None` 을 내지 않는다. 그
                # 불변이 이 파일 밖(`AssumptionSet`)에 있으므로 기준값으로
                # 내려서 둔다 — 깨져도 **값이 사라지는 대신 기준값이 실린다.**
                value=item.value if effective is None else effective.value,
                value_unit=item.value_unit,
                base_year=item.base_year,
                source=item.source or "출처 미기재",
                confidence=item.confidence.value,
                verified_at=item.verified_at,
            )
        )
    return tuple(rows)


def build_case_report(
    scenario_path: Path, *, assumptions_path: Path
) -> CaseReport:
    """골든 시나리오 하나를 돌려 심의용 리포트를 조립한다.

    ⚠ **부품을 호출부가 다시 조립하게 두지 않는다.** 이 함수 하나가 실행·영향도·
    산식·부기·부록·매니페스트를 한 자료형으로 닫는다. 갈라 두면 출구(라우터·CLI)
    마다 다른 조립 순서가 생기고, 그중 하나가 영향도 절을 빠뜨려도 아무 검사도
    걸리지 않는다 — 그것이 이 파일이 생기기 전의 상태였다.
    """
    scenario = _load_scenario(scenario_path)
    provider = AssumptionSet.load_from_yaml(str(assumptions_path))
    level_map = build_level_map(assumptions_path)
    horizon_years = provider.analysis_years()
    subsidy_rate = float(scenario["subsidy_rate"])
    scheme = _scheme_for(subsidy_rate)

    # ★ **일사 곡선을 기본 경로에 배선한다 (R37 · 당시 `todo.md` 4번 — 그 파일은
    # R45 에 `status.md` 「다음에 집을 것」 절로 합쳐졌다).**
    # 넘기지 않으면 러너가 이용률 하나로 24스텝을 **균등 배분**하고, 그러면
    # 심야에도 태양광이 0.45kWh 를 낸다 — 붙임 8 이 그것을 「미반영 항목」으로
    # 싣고 있었다. 통로(`PV.generation_profile_kwh`)와 자산(야간 가중치 0.0)은
    # 이미 있었고 **쓰지 않았을 뿐**이다.
    #
    # ⚠ **총량은 옮기지 않는다.** 형상은 합이 1 인 배분 벡터라 연간 발전량은
    # 그대로이고 시간대만 옮겨간다(`DailyShape.spread`). 총량은 계속 대장이
    # 갖는다 — 이 배선은 소유를 바꾸지 않는다.
    shapes = load_daily_shapes()
    # ★★ **REC 단가는 대장에서 온다** (사용자 판정 §4 · R51/WP-6). 지금 값은
    # 0 이며(`track: default0` — 제도·값 근거 미확인) 그래서 편익이 0원을
    # 낸다. **대장 한 줄이 이 배선의 전부**이고, 러너에 리터럴을 두지 않은
    # 이유는 `level_map` 단가들과 같다 — 두면 대장을 고쳐도 옛 값이 쓰인다.
    # ⚠ `level_map` 이 아니라 `provider` 에서 직접 읽는 이유: 수준표는
    # `sensitivity` 3수준을 **필수**로 요구하는데(`ledger_levels._levels_of`)
    # `default0` 항목은 그것을 갖지 않는다 — 「크기를 추정하지 않는다」가
    # 그 갈래의 정의이므로 흔들 범위 자체가 없다. `analysis.period_years`·
    # `tax.vat_rate` 가 이미 같은 통로로 읽힌다.
    # ⚠ **없으면 0 으로 메우지 않는다.** 메우면 대장에서 항목이 사라져도
    # 리포트가 조용히 「REC 0원」을 계속 싣고, 그 상태는 「단가가 0 이라 0원」과
    # 산출물에서 구별되지 않는다 — `AssumptionProvider` 계약이 *「없으면 멈추며
    # 기본값으로 메우지 않는다」* 로 세운 규약 그대로다.
    rec_price_item = provider.get(REC_PRICE_LEDGER_KEY)
    if rec_price_item is None:
        raise ValueError(
            f"전제 대장에 {REC_PRICE_LEDGER_KEY!r} 항목이 없습니다 — REC 편익이 "
            "단가를 읽을 자리가 없습니다. docs/assumptions.yaml 에 등재하십시오"
            "(사용자 판정 2026-09-01-R51 §4)"
        )
    rec_price = float(rec_price_item.value)
    # ★ **가구 부하를 본 실행에 세운다** (판정 B-1, `docs/decisions-
    # 2026-08-31-R48.md` §5·§1·§4). 종전에는 이 호출이 `annual_load_kwh` 를
    # 넘기지 않아 결론이 부하 없는 사업(PV+ESS 만) 위에 섰고, 그래서 §4 가
    # 지적한 「피크 저감이 자가 부하를 못 본다」가 실행에서 드러나지 않았다.
    # 값은 대장 축(`household_load_annual_kwh` · `load.household.annual`)의
    # `base` 수준에서 온다 — 리터럴로 두면 5.1 스윕이 이 값을 흔들 수 없다.
    outcome = run_single_case_e2e(
        {}, level_map=level_map, horizon_years=horizon_years, scheme=scheme,
        daily_shapes=shapes,
        annual_load_kwh=level_map["household_load_annual_kwh"]["base"],
        rec_price_won_per_unit=rec_price,
    )
    sweeper = _Sweeper(
        level_map=level_map, horizon_years=horizon_years, scheme=scheme,
        daily_shapes=shapes, rec_price_won_per_unit=rec_price,
    )
    influences = _influences(
        sweeper=sweeper, level_map=level_map, provider=provider
    )
    coupled_sweeps = build_coupled_sweeps(
        level_map=level_map,
        probe=sweeper.conclusion_at_many,
        scales=ledger_unit_scales(),
        base_npv=float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC]),
    )

    # ★ 용량 스윕은 **1변수 스윕과 같은 기계**를 쓴다 (`sweeper.conclusion_at`).
    # 갈라 두면 용량 쪽만 변형(`as_planned`)을 읽지 않는 어긋남이 생긴다.
    capacity_review = build_capacity_review(
        sweeper.conclusion_at,
        used={
            name: levels["base"]
            for name, levels in level_map.items()
            if "base" in levels
        },
    )

    manifest = create_manifest({
        "scenario": scenario.get("scenario", scenario_path.stem),
        "subsidy_rate": subsidy_rate,
        "assumption_set": provider.set_name,
        "assumption_version": provider.set_version,
        "horizon_years": horizon_years,
        "levels": {
            name: dict(levels) for name, levels in sorted(level_map.items())
        },
        "metrics": {
            tag: dict(metrics) for tag, metrics in sorted(outcome.variants.items())
        },
    })

    return CaseReport(
        scenario_name=str(scenario.get("scenario", scenario_path.stem)),
        scenario_path=_repo_relative(scenario_path),
        scenario_name_slug=scenario_path.stem,
        subsidy_rate=subsidy_rate,
        assumption_set_name=provider.set_name,
        assumption_set_version=provider.set_version,
        price_basis=provider.price_basis.value,
        metrics=outcome.variants[PLAN_VARIANT],
        baseline_metrics=outcome.variants[BASELINE_VARIANT],
        variant_labels=tuple(
            (variant.tag, variant.label) for variant in run_order()
        ),
        variants=outcome.variants,
        basis=outcome.basis,
        influences=influences,
        coupled_sweeps=coupled_sweeps,
        formulas=_formulas(
            outcome.basis,
            outcome.variants[PLAN_VARIANT],
            subsidy_rate=subsidy_rate,
            # 총사업비는 **기준선의 초기지출**이다 (`total_project_cost_won`).
            # 여기서 `basis` 의 총사업비를 쓰지 않는 이유는 그 값이 지원 반영
            # 전인지 후인지를 이 자리에서 다시 판단하게 되기 때문이다 —
            # 변형의 지표에서 읽으면 판단할 것이 없다.
            total_project_cost_won=float(
                outcome.variants[BASELINE_VARIANT]["initial_outlay_won"]
            ),
        ),
        assumptions=_appendix(provider),
        manifest_hash=manifest.hash,
        # ★ 엔진 규칙과 운전 결과를 **실행이 내놓은 것에서** 읽는다 (의견 2·3).
        # 여기서 자원을 다시 세우거나 순서를 다시 적으면 사본이 되고, 러너가
        # 운전 방법·규칙 순서를 바꿔도 리포트는 옛 표를 계속 인쇄한다.
        dispatch_notes=tuple(
            build_dispatch_notes(
                list(outcome.resources), rule_order=outcome.rule_order
            )
        ),
        rule_order=outcome.rule_order,
        dispatch_hours=build_hourly_profile(outcome.dispatch),
        capacity_review=capacity_review,
        # ★ 러너가 **가른 채로** 낸 현금흐름 행을 그대로 받는다 (판정 §3 ⓐ).
        # 여기서 다시 묶거나 태그로 분류하지 않는다 — 그 순간 5.3 의 분해가
        # 러너의 사본이 된다(`CashflowSplit` 독스트링).
        cashflows=outcome.cashflows,
    )
