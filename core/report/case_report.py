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
    ledger_backed_variables,
    ledger_unit_scales,
)
from core.casegrid.models import CaseBasis
from core.casegrid.variants import run_order
from core.contracts.assumptions import AssumptionValue
from core.incentive.schemas import IncentiveScheme
from core.report.combined import CoupledSweep, build_coupled_sweeps
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
    """

    def __init__(
        self,
        *,
        level_map: Mapping[str, Mapping[str, float]],
        horizon_years: int,
        scheme: IncentiveScheme | None,
    ) -> None:
        self._level_map = level_map
        self._horizon_years = horizon_years
        self._scheme = scheme
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

    for variable, levels in level_map.items():
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


def _formulas(basis: CaseBasis, metrics: Mapping[str, float]) -> tuple[Formula, ...]:
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
    net = basis.annual_benefit_won - basis.annual_cost_won
    return (
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
                "분석기간 안에 도달하지 못하면 「미회수」이며, 그것은 NPV 가 "
                "음수인 것과 같은 말이다"
            ),
            expression="min{ T' : Σ(t=1..T') CF_t / (1+r)^t ≥ I₀ }",
            substituted=(
                f"{payback_text} — I₀ = {outlay:,}원 · "
                f"r = {basis.discount_rate:.1%} · T = {basis.horizon_years}년"
            ),
        ),
    )


def _appendix(provider: AssumptionSet) -> tuple[AssumptionRow, ...]:
    """전 가정 목록 — 영향도 순위와 **별개로** 제공한다 (`FR-1002-AC6`)."""
    return tuple(
        AssumptionRow(
            key=item.key,
            value=item.value,
            value_unit=item.value_unit,
            base_year=item.base_year,
            source=item.source or "출처 미기재",
            confidence=item.confidence.value,
            verified_at=item.verified_at,
        )
        for item in sorted(provider.items().values(), key=lambda i: i.key)
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

    outcome = run_single_case_e2e(
        {}, level_map=level_map, horizon_years=horizon_years, scheme=scheme
    )
    sweeper = _Sweeper(
        level_map=level_map, horizon_years=horizon_years, scheme=scheme
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
        formulas=_formulas(outcome.basis, outcome.variants[PLAN_VARIANT]),
        assumptions=_appendix(provider),
        manifest_hash=manifest.hash,
    )
