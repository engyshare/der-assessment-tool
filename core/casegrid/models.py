from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from core.contracts.validation import ValidationError


@dataclass(frozen=True)
class CaseVariable:
    name: str
    values: tuple[object, ...]
    target: str = "scalar"
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(self.values))
        if not self.name.strip():
            raise ValidationError(
                field="casegrid.variable_name",
                reason="케이스 변수 이름이 비어 있습니다",
                action="공백이 아닌 이름을 지정하십시오",
            )
        if not self.values:
            raise ValidationError(
                field="casegrid.variable_values",
                reason=f"케이스 변수 {self.name!r} 의 값 목록이 비어 있습니다",
                action="값을 최소 1개 이상 지정하십시오",
            )
        if not self.target.strip():
            raise ValidationError(
                field="casegrid.variable_target",
                reason=f"케이스 변수 {self.name!r} 의 target 이 비어 있습니다",
                action="공백이 아닌 target 값을 지정하십시오",
            )


@dataclass(frozen=True)
class CoupledSet:
    name: str
    variable_names: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_names", tuple(self.variable_names))
        if not self.name.strip():
            raise ValidationError(
                field="casegrid.coupled_set_name",
                reason="결합 집합 이름이 비어 있습니다",
                action="공백이 아닌 이름을 지정하십시오",
            )
        if len(self.variable_names) < 2:
            raise ValidationError(
                field="casegrid.coupled_set_variables",
                reason=(
                    f"결합 집합 {self.name!r} 이 변수를 "
                    f"{len(self.variable_names)}개만 가지고 있습니다"
                ),
                action="결합 집합에 변수를 2개 이상 지정하십시오",
            )
        if len(set(self.variable_names)) != len(self.variable_names):
            raise ValidationError(
                field="casegrid.coupled_set_variables",
                reason=f"결합 집합 {self.name!r} 에 같은 변수가 중복 지정되었습니다",
                action="변수 이름을 서로 다르게 지정하십시오",
            )


@dataclass(frozen=True)
class Case:
    index: int
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValidationError(
                field="casegrid.case_index",
                reason=f"케이스 인덱스가 음수입니다: {self.index}",
                action="0 이상의 정수를 지정하십시오",
            )
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    def __getstate__(self) -> dict[str, object]:
        return {"index": self.index, "values": dict(self.values)}

    def __setstate__(self, state: dict[str, object]) -> None:
        object.__setattr__(self, "index", state["index"])
        val = state["values"]
        if isinstance(val, Mapping):
            object.__setattr__(self, "values", MappingProxyType(dict(val)))
        else:
            object.__setattr__(self, "values", MappingProxyType({}))


@dataclass(frozen=True)
class CaseResult:
    """케이스 하나의 결과.

    ## `variants` — 변형 축을 **자료구조로** 세운다 (`FR-607-AC1` / R31 결정 §5)

    조항은 *「모든 실행에서 `지원 0` 케이스가 자동 포함되어 결과 상단에 표시」* 다.
    `run_order()` 가 그 목록을 보증하고 `incentive_cases` 가 현금흐름을 만드는데,
    **결과에 변형별 지표를 담을 자리가 없었다.**

    `metrics` 에 키 접두어(`"무지원.npv_won"`)를 붙이는 안을 버렸다. 접두어는
    **소비자마다 문자열 파싱을 만들게 하고 그 파싱이 갈린다** — 어느 소비자는
    첫 점에서 자르고 어느 소비자는 마지막 점에서 자른다. 그리고 변형이 셋 넷으로
    늘면 키가 곱으로 폭발한다.

    ⚠ **`__getstate__`/`__setstate__` 에 함께 넣어야 한다.** 케이스 그리드는
    `ProcessPool` 로 병렬 실행되므로(`FR-805-AC1`) 결과가 피클을 지난다 — 여기
    빠뜨리면 **직렬 실행에서는 보이고 병렬 실행에서만 변형이 사라진다.** 그 차이는
    케이스 수가 적은 테스트에서 드러나지 않는다.
    """

    case_index: int
    values: Mapping[str, object]
    metrics: Mapping[str, float]
    #: 변형 tag → 그 변형의 지표. 비어 있으면 「변형을 산출하지 않은 실행」이다.
    #:
    #: ⚠⚠ **`default_factory` 여야 한다 — `MappingProxyType({})` 를 직접 기본값으로
    #: 두면 Python 3.11 이 거부한다** (`ValueError: mutable default <class
    #: 'mappingproxy'> … use default_factory`). **3.12 부터는 허용하므로 3.13 로컬에서는
    #: 보이지 않고 CI(3.11)에서만 수집 오류가 난다** — R31 이 실제로 그렇게 겪었고,
    #: `pyproject.toml` 의 `requires-python = ">=3.11"` 이 정본이므로 3.11 이 기준이다.
    variants: Mapping[str, Mapping[str, float]] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(self, "variants", _freeze_variants(self.variants))

    def __getstate__(self) -> dict[str, object]:
        return {
            "case_index": self.case_index,
            "values": dict(self.values),
            "metrics": dict(self.metrics),
            # 병렬 실행이 이 줄에 달려 있다 — 위 독스트링 참조
            "variants": {tag: dict(m) for tag, m in self.variants.items()},
        }

    def __setstate__(self, state: dict[str, object]) -> None:
        object.__setattr__(self, "case_index", state["case_index"])
        val = state["values"]
        if isinstance(val, Mapping):
            object.__setattr__(self, "values", MappingProxyType(dict(val)))
        else:
            object.__setattr__(self, "values", MappingProxyType({}))
        met = state["metrics"]
        if isinstance(met, Mapping):
            object.__setattr__(self, "metrics", MappingProxyType(dict(met)))
        else:
            object.__setattr__(self, "metrics", MappingProxyType({}))
        var = state.get("variants")
        object.__setattr__(
            self, "variants", _freeze_variants(var) if isinstance(var, Mapping) else
            MappingProxyType({})
        )


def _freeze_variants(
    variants: Mapping[str, Mapping[str, float]],
) -> Mapping[str, Mapping[str, float]]:
    """중첩 사전을 **두 층 모두** 읽기 전용으로 만든다.

    바깥만 얼리면 안쪽 지표 사전을 밖에서 고칠 수 있고, 그것은 `NFR-205` 가
    막으려는 전역 가변 상태와 같은 결과다 — 병렬 실행에서 특히 나쁘다.
    """
    return MappingProxyType({
        tag: MappingProxyType(dict(metrics)) for tag, metrics in variants.items()
    })


@dataclass(frozen=True)
class ResourceLine:
    """**무엇을 평가했는가** — 리포트 0절의 한 행 (`FR-1001-AC2`).

    ## 왜 자원 제원이 경계를 넘는가

    리포트 첫 판을 검토에 걸었더니 *「분석 대상 모델에 대한 소개가 없다」* 가
    첫 지적이었다. 맞다 — 리포트는 「NPV −865,881원」과 「PV 단가가 결론을
    뒤집는다」를 말하면서 **PV 를 몇 kW 놓았는지, 무엇과 함께 놓았는지**를 한
    번도 말하지 않았다. 검토자는 대상을 모르는 채 민감도만 읽은 것이다.

    ⚠ **리포트가 자원을 다시 세우게 두지 않는다.** 표시 층이 `PV(...)` 를
    똑같이 한 번 더 만들면 그것은 사본이고, 러너의 제원이 바뀔 때 리포트는
    **옛 제원을 그럴듯하게 계속 인쇄한다.** 아무 예외도 나지 않는다.
    """

    name: str
    #: 자원 종류 — 클래스 이름이 아니라 사람이 읽는 말.
    kind: str
    #: 용량 문면. 단위가 자원마다 다르므로(kW · kWh) 문자열로 나른다.
    capacity: str
    operating_mode: str
    lifetime_years: int
    #: 단가 문면 — 「1,600,000원/kW」처럼 **무엇당 얼마인지**까지.
    unit_capex: str
    capex_won: int
    fixed_om_won_per_year: int
    #: 이 자원이 만드는 편익의 태그. 비어 있으면 **비용만 내는 자원**이다.
    produces: tuple[str, ...]


@dataclass(frozen=True)
class BenefitLine:
    """편익 한 갈래가 **얼마이며 무엇에서 나왔는가** — 리포트 2절의 한 행.

    ## 왜 갈래별로 나누는가

    검토 지적 둘째가 *「pv.rooftop capex 는 잡혀 있는데 그 비용 대비 편익이
    적정한지는 어떻게 보는가」* 였다. 연 편익을 **한 덩어리(904,860원)** 로만
    실으면 그 물음에 답할 자리가 없다 — 검토자는 PV 에 480만원을 쓴 것이
    타당한지 판단하려는데, 리포트는 PV 가 그중 얼마를 벌어 오는지 말하지
    않았다.
    """

    tag: str
    label: str
    #: 1년차 금액(원).
    annual_won: int
    #: 이 편익을 만든 자원 이름. 규약이 아니라 **이 파이프라인의 실제 귀속**이다.
    from_resource: str
    #: 산식 문면 — 대입값까지 (`FR-1001-AC3`).
    formula: str


@dataclass(frozen=True)
class CaseBasis:
    """산식의 **대입값** — `FR-1001-AC3` 의 3중 표기 중 셋째 줄이 여기서 온다.

    ## 왜 지표만으로는 안 되는가

    `MC-1` 은 *「비개발자 검토자가 리포트만 보고 **회수기간의 근거**를 설명할 수
    있는가」* 를 잰다. 지표 사전(`{"npv": …, "payback_years": …}`)은 **답이지
    근거가 아니다** — 검토자가 「왜 10.5년인가」를 재구성하려면 초기투자·연
    편익·할인율·분석기간이 그 자리에 있어야 하고, 없으면 리포트가 *"계산했더니
    그렇습니다"* 로 끝난다. 그것이 이 저장소가 `AssumptionValue` 에서 이미 한 번
    내린 판단이다(*「값만 넘기면 리포트가 그 값이 어디서 왔는가에 답할 수
    없다」*).

    ⚠ **선택 필드로 두지 않았다.** 두면 안 채운 실행에 근거가 없고 **빠졌을 때
    나는 증상이 없다** — 리포트가 조용히 빈 산식을 그린다. R21 이 `is_baseline`
    깃발에서, R32 가 `with_variants` 에서 두 번 없앤 형태다.

    ⚠ **여기 담는 것은 「무엇을 넣었는가」이지 「무엇이 나왔는가」가 아니다.**
    지표는 `CaseOutcome.metrics` 가 갖는다. 같은 수를 두 곳에 담으면 한쪽만
    고쳐진다.
    """

    #: `t=0` 초기투자(원). 지원을 반영하지 않은 **케이스 기준** 총사업비다 —
    #: 변형별 초기지출은 `CaseOutcome.variants` 가 따로 갖는다.
    initial_investment_won: int
    #: 1년차 편익 합계(원).
    annual_benefit_won: int
    #: 1년차 운영비 합계(원). **양수로 담는다** — 부호를 뒤집는 자리는
    #: `net_operating_flows()` 하나여야 한다(R32).
    annual_cost_won: int
    discount_rate: float
    horizon_years: int
    #: 평가 대상 자원 — 위 `ResourceLine` 참조.
    resources: tuple[ResourceLine, ...]
    #: 편익 갈래별 금액 — 위 `BenefitLine` 참조.
    benefits: tuple[BenefitLine, ...]
    #: 디스패치 규약 문면 — 「대표일 24스텝 × 365일」처럼 **결과를 읽는 데
    #: 필요한 전제**다. 규약을 적지 않으면 검토자가 시간해상도를 모른 채
    #: 연간 금액을 읽는다(재현도 불가능하다).
    dispatch_note: str


@dataclass(frozen=True)
class CaseOutcome:
    """케이스 러너 하나의 산출 — 지표 **와 변형별 지표** (`FR-607-AC1` / R32).

    ## 왜 자료형을 하나 더 두는가

    `CaseRunner` 의 반환형이 `Mapping[str, float]` 하나였다. 그래서 R31 이
    `CaseResult.variants` 를 만들어도 **러너가 그것을 채울 통로가 없었고**,
    실제로 `variants=` 를 쓰는 배포 코드가 0곳이었다(채우는 것은 테스트뿐).
    소비자(`core/report/variant_report.py`)는 있고 생산자가 없었다.

    통로를 `run_cases()` 의 **선택 인자**(`variant_runner=…`)로 두는 안을 버렸다.
    안 넘기면 변형이 그냥 없고 **빠졌을 때 나는 증상이 없다** — R21 이
    `build_capex_cashflows(..., is_baseline=True)` 에서 없앤 깃발과 같은 형태다
    (`core/contracts/casevariant.py` 머리말).

    ⚠ **`run_cases()` 는 지표 사전만 돌려주는 러너도 계속 받는다.** 그것이
    깃발의 부활이 아닌 이유: `run_cases` 는 케이스 목록을 도는 **범용 기반**이고
    「변형 없는 실행」(민감도 스윕·성능 측정)은 정당한 상태다. `FR-607-AC1` 이
    말하는 「모든 실행」은 **평가 파이프라인**이며 그 진입점
    (`core/casegrid/e2e_runner.py::run_single_case_e2e`)은 이 자료형을 **항상**
    돌려준다 — 거기에는 켜고 끄는 인자가 없다.
    """

    metrics: Mapping[str, float]
    #: 변형 tag → 그 변형의 지표. `run_order()` 의 변형 **전부**가 들어 있어야
    #: 하며, 그 확인은 표시 층(`build_variant_table`)이 거부로 한다.
    variants: Mapping[str, Mapping[str, float]]
    #: 산식의 대입값 — 위 `CaseBasis` 참조. 리포트가 근거를 그리는 재료다.
    basis: CaseBasis

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(self, "variants", _freeze_variants(self.variants))


@dataclass(frozen=True)
class RunPlan:
    case_count: int
    threshold: int
    estimated_seconds: float
    requires_confirmation: bool
    should_run_background: bool


@dataclass(frozen=True)
class Progress:
    completed_cases: int
    total_cases: int
    estimated_remaining_seconds: float | None


@dataclass(frozen=True)
class EnvironmentProfile:
    label: str
    cpu_count: int | None
    memory_mb: int | None
    free_tier_like: bool


@dataclass(frozen=True)
class PerformancePoint:
    case_count: int
    repeat_count: int
    average_seconds: float
    samples_seconds: tuple[float, ...]
    environment: EnvironmentProfile


@dataclass(frozen=True)
class FeasibleCell:
    """달성영역 격자의 칸 하나 — `FR-803-AC1`.

    ## `x_index`/`y_index` — **수치 축** (R31 결정 §8)

    프리셋 축의 값은 `"low"`/`"base"`/`"high"` **문자열**이라 등고선·음영 차트가
    원리상 그려지지 않는다(차트는 수치 좌표를 받는다). 그래서 축의 **수준
    인덱스**를 함께 싣는다.

    **문자열을 정렬해서 지수를 만들지 않는다** — 사전순으로는
    `base < high < low` 가 되어 **중간 수준이 맨 앞에 오고**, 그 격자는 좌표가
    뒤섞인 채 그럴듯하게 그려진다. 인덱스는 케이스 그리드가 **선언한 수준
    순서**에서만 나온다(`feasible_region(axis_levels=…)`).

    `None` 은 「수준 순서를 받지 못했다」이며 「0번 수준」이 아니다 — 그 둘을 같은
    값으로 두면 축을 못 그린 격자가 첫 수준에 뭉친다.
    """

    x_value: object
    y_value: object
    metric_value: float
    achieved: bool
    case_index: int
    x_index: int | None = None
    y_index: int | None = None


@dataclass(frozen=True)
class TornadoInfluence:
    variable_name: str
    influence: float
