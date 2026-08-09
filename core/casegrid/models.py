from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class CaseVariable:
    name: str
    values: tuple[object, ...]
    target: str = "scalar"
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(self.values))
        if not self.name.strip():
            raise ValueError("case variable name must not be blank")
        if not self.values:
            raise ValueError(f"case variable {self.name!r} must have at least one value")
        if not self.target.strip():
            raise ValueError(f"case variable {self.name!r} target must not be blank")


@dataclass(frozen=True)
class CoupledSet:
    name: str
    variable_names: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_names", tuple(self.variable_names))
        if not self.name.strip():
            raise ValueError("coupled set name must not be blank")
        if len(self.variable_names) < 2:
            raise ValueError(f"coupled set {self.name!r} must contain at least two variables")
        if len(set(self.variable_names)) != len(self.variable_names):
            raise ValueError(f"coupled set {self.name!r} repeats a variable")


@dataclass(frozen=True)
class Case:
    index: int
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("case index must be non-negative")
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
