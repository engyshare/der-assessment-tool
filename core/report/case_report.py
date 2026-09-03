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
자원 구성을 담지 않는다. 여기서 그 파일에서 취는 것은 **지원 조건(보조율)
하나**이고, 나머지 값은 전부 대장(`docs/assumptions.yaml`)의 `base` 수준에서
온다. 그 사실을 리포트 본문이 밝힌다 — 밝히지 않으면 검토자는 픽스처의
`expected_values` 가 이 리포트의 근거라고 읽는다.

## R54/WP-2 — 영향도 스윕 한 덩어리를 뗐다

`break_even_subsidy_rate`·`residual_gap_at_full_support_won`·`InfluenceEntry`
·`_Sweeper`·`_probe_for`·`_influences` 와 상수 넷·`MAX_SUBSIDY_RATE` 는
`core/report/case_influences.py` 로 옮겼다(그 독스트링이 경위를 갖는다).
이 파일은 그것을 import 해 그대로 쓴다 — 밖에서 `case_report` 의
`CONCLUSION_METRIC`·`InfluenceEntry` 를 읽던 경로는 재수출로 그대로 산다.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from core.assumption.provider import AssumptionSet
from core.casegrid.e2e_runner import PV_CAPACITY_FACTOR, run_single_case_e2e
from core.casegrid.ledger_levels import (
    build_level_map,
    design_variables,
    ledger_unit_scales,
    required_scalar,
)
from core.casegrid.models import CaseBasis, CashflowSplit
from core.casegrid.perspectives import PerspectiveWiring
from core.casegrid.profiles import load_daily_shapes
from core.casegrid.variants import run_order
from core.contracts.assumptions import AssumptionProvider, AssumptionValue
from core.contracts.validation import ValidationError
from core.engine.rule_based import DispatchRule
from core.incentive.schemas import IncentiveScheme
from core.report.capacity import CapacityFinding, build_capacity_review
from core.report.case_influences import (
    BASELINE_VARIANT,
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    MAX_SUBSIDY_RATE,
    PLAN_VARIANT,
    InfluenceEntry,
    _influences,
    _Sweeper,
    break_even_subsidy_rate,
    residual_gap_at_full_support_won,
)
from core.report.combined import CoupledSweep, build_coupled_sweeps
from core.report.dispatch_notes import (
    DispatchHour,
    DispatchNote,
    build_dispatch_notes,
    build_hourly_profile,
)
from core.report.manifest import create_manifest
from core.report.sizing import (
    MONTHS_PER_YEAR,
    USER_EXAMPLE_MONTHLY_KWH,
    SelfSufficiencySizing,
    build_self_sufficiency_sizing,
)
from core.valuestream import DistributedSubItems

#: R54/WP-2 재수출 — 이 여섯은 `core/report/case_influences.py` 에서 왔다.
#: 밖(`narrative.py`·`shortfall.py`·`verification.py`·검사 파일)이 이 모듈
#: 경로로 읽는 한 그 경로는 살아 있어야 한다 — 분리가 「동작을 안 바꾼다」를
#: 지키는 자리다. `mypy` strict 는 import 를 재수출로 세지 않으므로 여기
#: `__all__` 로 밝힌다 — noqa 주석으로 덮는 것은 마지막 수단이다(지시문 2절
#: 판정 ②). **튜플로 쓴다** — 리스트는 모듈 수준 가변 컨테이너라 `NFR-205-M1`
#: 검사가 막는다(저장소의 모든 `__all__` 이 튜플인 이유).
__all__ = (
    "BASELINE_VARIANT",
    "CONCLUSION_METRIC",
    "HEADLINE_METRIC",
    "MAX_SUBSIDY_RATE",
    "PLAN_VARIANT",
    "InfluenceEntry",
)

#: 저장소 뿌리 — 리포트에 **저장소 상대 경로**만 싣기 위한 기준이다.
#:
#: ⚠ **절대 경로를 리포트에 싣지 않는다.** 검토자에게 나가는 문서에 개발
#: 기계의 경로가 박히면 ⓐ `SC-3`(비공개 정보 유입) 검사가 커밋을 막고
#: ⓑ 무엇보다 **다른 기계에서 같은 리포트를 다시 뽑을 수 없다** — 재현
#: 정보로서 쓸모가 없어진다.
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: REC 단가를 담은 대장 키 (사용자 판정 §4 · R51/WP-6). 이 조립기가 대장에서
#: 읽어 러너에 넘긴다 — 이름을 여기 한 번만 적는 이유는 `TARIFF_KEY`
#: (`core/valuestream/settlement.py`)와 같다: 두 곳에 적으면 대장 키를 바꾸는
#: 날 한 곳이 남고, 그때 `provider.get()` 이 **조용히가 아니라** 멈추긴 하지만
#: 어느 쪽이 정본인지 다투게 된다.
REC_PRICE_LEDGER_KEY = "benefit.rec_price"

#: REC 가중치를 담은 대장 키 (사용자 판정 §5 · R52/WP-6). `REC_PRICE_LEDGER_KEY`
#: 와 같은 이유로 이름을 여기 한 번만 적는다. `ledger_levels._LEDGER_VARS` 에
#: 없는 이유는 그 파일 옆 주석에 있다(폭을 지어낼 수 없어 스윕 축이 아니다).
REC_WEIGHT_LEDGER_KEY = "benefit.rec_weight_pv"

#: 분산편익 크레딧 대장 키 다섯 (R53/WP-1 · R54/WP-3 — 대장이 다섯 칸으로
#: 나뉘었다). `REC_PRICE_LEDGER_KEY` 와 같은 통로. `DistributedSubItems`
#: 필드명과 짝지어 `_read_distributed_sub_items()` 가 다섯을 한 번에 읽는다.
DISTRIBUTED_CREDIT_LEDGER_KEYS: tuple[tuple[str, str], ...] = (
    ("transmission_avoidance_won", "benefit.distributed_credit.transmission_avoidance"),
    ("loss_reduction_won", "benefit.distributed_credit.loss_reduction"),
    ("grid_service_won", "benefit.distributed_credit.grid_service"),
    ("ghg_reduction_won", "benefit.distributed_credit.ghg_reduction"),
    ("resilience_won", "benefit.distributed_credit.resilience"),
)


def _read_distributed_sub_items(provider: AssumptionProvider) -> DistributedSubItems:
    """대장 다섯 칸을 읽어 `DistributedSubItems` 를 짓는다 (R54/WP-3 판정 ①).

    `required_scalar()` 를 다섯 번 부른다 — 없으면 0 으로 메우지 않고
    멈춘다(그 함수 독스트링과 같은 이유, `REC_PRICE_LEDGER_KEY` 와 같은
    통로). 항목 하나가 대장에서 빠지면 곧바로 예외로 드러나야 한다 —
    조용히 0 으로 메우면 「대장에 없다」와 「대장이 0 이다」가 산출물에서
    구별되지 않는다.
    """
    return DistributedSubItems(**{
        field: required_scalar(provider, key, note="분산편익")
        for field, key in DISTRIBUTED_CREDIT_LEDGER_KEYS
    })


@dataclass(frozen=True)
class Formula:
    """3중 표기 한 건 — 자연어 + 수식 + 대입값 (`FR-1001-AC3`)."""

    label: str
    natural: str
    expression: str
    substituted: str


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
class OverrideRow:
    """기준 전제 대비 **변경 항목** 한 줄 (`FR-602-AC2`).

    `AssumptionSet.overridden_items()` 가 내주는 `{base, override, reason}`
    을 붙임까지 **문자열 키의 `dict` 로 나르지 않는다** — `AssumptionRow` 가
    자료형인 이유와 같다. 키를 잘못 적으면 예외 대신 **빈 칸**이 인쇄되고,
    빈 칸은 「바뀌지 않았다」와 산출물에서 구별되지 않는다.
    """

    key: str
    #: 대장에 적힌 값 — **바뀌기 전**이다. 이것이 없으면 「변경」이 성립하지
    #: 않는다(그 메서드 독스트링).
    base_value: float | int | str
    #: 시나리오가 덮어쓴 값. 이 실행의 계산이 쓴 값이다.
    override_value: float | int | str
    #: 오버라이드 사유 (`FR-602-AC3`). 조항이 **권장** 필드로 두므로 없을 수
    #: 있고, 없는 것과 빈 문자열을 가르려고 `None` 을 그대로 나른다.
    reason: str | None


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
    #: 기준 전제 대비 변경 항목 (`FR-602-AC2`) — 붙임 1 이 표로 낸다.
    #:
    #: ⚠ **비어 있는 것이 이 배포 경로의 정상이다.** `build_case_report()` 는
    #: 대장을 그대로 싣고 오버라이드를 걸지 않는다. 그래서 붙임은 「없다」를
    #: **인쇄해야** 한다 — 절을 지우면 검토자가 「기준 전제 그대로 돌렸다」와
    #: 「그 표시를 싣지 못했다」를 가릴 수 없다.
    overrides: tuple[OverrideRow, ...]
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
    #: 경우 「가」(100% 에너지 자립) 역산 — 붙임 10 의 별도 소절 (R55/WP-2).
    #: **진단이지 결론이 아니다** — `capacity_review` 의 탐색 구간·기준 구성을
    #: 여기서 바꾸지 않는다(검토서 §1-⑥).
    self_sufficiency: SelfSufficiencySizing
    #: ★ 엔진이 만든 현금흐름 행 — **5.3 이 결손을 가르는 재료** (판정 §3 ⓐ).
    #:
    #: ⚠ 여기서 요약하지 않는다. `metrics` 는 합계 하나이고 5.3 이 묻는 것은
    #: *「그 합계가 어느 항에서 왔는가」* 다 — 1년차 값으로 되지으면 물가
    #: 상승이 빠져 합계가 결손과 어긋난다(`CashflowSplit` 독스트링).
    cashflows: CashflowSplit
    #: 관점 넷 — 4.5 절이 이 재료로 병렬표를 낸다 (R52/WP-A).
    perspectives: PerspectiveWiring

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

    ⚠ **「덮어썼다」는 표시는 이 자리가 만들지 않는다.** 이 함수가 지는 것은
    **실린 값이 실행이 쓴 값인가**까지이고, 기준값과 나란히 놓는 표는
    `_overrides()` 가 짓는다(`FR-602-AC2`) — 한 행이 두 값을 함께 지면 이
    목록의 「전건」이 무엇을 세는 것인지가 흐려진다.
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


def _overrides(provider: AssumptionSet) -> tuple[OverrideRow, ...]:
    """기준 전제 대비 변경 항목 — **대장이 가른 것을 옮긴다** (`FR-602-AC2`).

    ## ⚠ 기준값과 변경값을 **여기서 맞대 보지 않는다**

    `items()` 와 `get()` 을 각각 조회해 나란히 놓으면 「변경」의 정의가
    리포트와 대장 두 곳에 생기고, `overridden_items()` 독스트링이 적은
    *「이 메서드가 대장의 원래 값을 함께 붙여 리포트가 그대로 표에 얹을 수
    있게 한다」* 가 거짓이 된다. 그 메서드가 이미 짝을 짓는다 —
    **여기서는 자료형만 입힌다.**

    ⚠ **사유를 버리지 않는다** (`FR-602-AC3`). 같은 절이 사유를 요구하고 그
    메서드가 사유를 함께 내놓으므로, 여기서 떨어뜨리면 리포트가 대장에 다시
    물어야 하고 그 통로가 또 하나 생긴다.

    ⚠ **키 순으로 세운다.** `overridden_items()` 는 오버라이드를 **넣은
    순서**로 내주는데(`dict` 삽입 순서), 그 순서는 시나리오 파일의 편집
    순서라 산출물이 실행마다 달라진다 — 붙임 1 의 주제별 표가 키 순인 것과
    같은 이유다.
    """
    return tuple(
        OverrideRow(
            key=key,
            base_value=changed["base"],
            override_value=changed["override"],
            reason=changed["reason"],
        )
        for key, changed in sorted(provider.overridden_items().items())
    )


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
    rec_price = required_scalar(
        provider, REC_PRICE_LEDGER_KEY, note="REC 편익 단가 (사용자 판정 2026-09-01-R51 §4)"
    )
    # ★★ **REC 가중치도 대장에서 온다** (사용자 판정 §5 · R52/WP-6). 단가가
    # `default0`(값 0)인 동안은 가중치를 몰라도 편익이 0원이라 상관없었으나,
    # `assume`(70원/kWh)으로 오른 지금은 이 값이 결론을 정한다 — `rec_price`
    # 와 같은 통로(`required_scalar`)로 읽는다.
    rec_weight = required_scalar(
        provider, REC_WEIGHT_LEDGER_KEY, note="REC 편익 가중치 (사용자 판정 §5, R52/WP-6)"
    )
    # ★ **분산편익 크레딧도 대장에서 온다** (R53/WP-1 · R54/WP-3 판정 ① — 대장이
    # 다섯 칸으로 나뉘었다). 지금 값은 다섯 모두 0이며(`track: default0`) 사회
    # 열 편익이 0원을 낸다 — `build_society_annualised()` 가 이 값으로 사회
    # 열만 짓고 결론축에는 닿지 않는다.
    # ⚠ `_Sweeper` 에도 넘긴다 (R54/WP-2 판정 ③ — R53 이 줄 상한에 걸려
    # 생략했던 배선). 스윕 결과는 지금 `variants[..][CONCLUSION_METRIC]`
    # 만 읽고 `.perspectives` 를 안 보므로 이 값이 어떤 수도 바꾸지는
    # 않지만, 읽는 날을 대비해 본 실행과 같은 값을 본다 — result_1.md 8절의
    # 「판정 필요」를 R54/WP-3 이 답한 자리다.
    distributed_sub_items = _read_distributed_sub_items(provider)
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
        rec_price_won_per_unit=rec_price, rec_weight_pv=rec_weight,
        distributed_sub_items=distributed_sub_items,
    )
    sweeper = _Sweeper(
        level_map=level_map, horizon_years=horizon_years, scheme=scheme,
        daily_shapes=shapes, rec_price_won_per_unit=rec_price, rec_weight_pv=rec_weight,
        distributed_sub_items=distributed_sub_items,
    )
    # ★ 부기 칸 만들기(`_provenance`)를 주입한다 — 그 함수는 이 파일에 남아
    # 있고(R54/WP-2 는 영향도 스윕 한 덩어리만 뗐다), `case_influences` 가
    # 여기서 import 하면 순환이 된다(그 모듈 독스트링의 「`_provenance` 는
    # 여기에 없다」 절이 같은 이유를 적는다).
    influences = _influences(
        sweeper=sweeper, level_map=level_map, provider=provider,
        provenance=_provenance,
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

    # ★ 경우 「가」(100% 자립) 역산 — 붙임 10 의 별도 소절 (R55/WP-2 · 검토서 §1).
    # `pv_capacity_kw` 탐색 구간은 `design_variables()` 에서 읽는다 — 1.0·9.0 을
    # 여기 리터럴로 적으면 `_DESIGN_VARS` 가 바뀌어도 이 소절만 낡는다.
    if "household_load_annual_kwh" not in level_map:
        raise ValidationError(
            field="load.household.annual",
            reason="대장에 가구 연간 사용량(household_load_annual_kwh) 수준표가 없습니다",
            action="docs/assumptions.yaml 의 load.household.annual 을 확인하십시오",
        )
    pv_design_variable = next(
        v for v in design_variables() if v.name == "pv_capacity_kw"
    )
    self_sufficiency = build_self_sufficiency_sizing(
        load_levels=level_map["household_load_annual_kwh"],
        capacity_factor=PV_CAPACITY_FACTOR,
        capacity_factor_source=(
            "core/casegrid/e2e_runner.py::PV_CAPACITY_FACTOR (소스 상수 · 대장 미등재)"
        ),
        search_low_kw=pv_design_variable.low,
        search_high_kw=pv_design_variable.high,
        reference_loads=[
            (
                f"사용자 예시(월 {USER_EXAMPLE_MONTHLY_KWH:g}kWh)",
                USER_EXAMPLE_MONTHLY_KWH * MONTHS_PER_YEAR,
            ),
        ],
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
        # ★ 이 경로는 오버라이드를 걸지 않으므로 **빈 짝**이 정상이다. 그래도
        # 실어 보내는 이유는 붙임이 「없다」를 인쇄해야 하기 때문이다 —
        # 위 `CaseReport.overrides` 주석 참조.
        overrides=_overrides(provider),
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
        self_sufficiency=self_sufficiency,
        # ★ 러너가 **가른 채로** 낸 현금흐름 행을 그대로 받는다 (판정 §3 ⓐ).
        # 여기서 다시 묶거나 태그로 분류하지 않는다 — 그 순간 5.3 의 분해가
        # 러너의 사본이 된다(`CashflowSplit` 독스트링).
        cashflows=outcome.cashflows,
        perspectives=outcome.perspectives,
    )
