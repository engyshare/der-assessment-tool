from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
    case_index: int
    values: Mapping[str, object]
    metrics: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    def __getstate__(self) -> dict[str, object]:
        return {
            "case_index": self.case_index,
            "values": dict(self.values),
            "metrics": dict(self.metrics),
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
    x_value: object
    y_value: object
    metric_value: float
    achieved: bool
    case_index: int


@dataclass(frozen=True)
class TornadoInfluence:
    variable_name: str
    influence: float
