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
