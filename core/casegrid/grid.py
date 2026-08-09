from __future__ import annotations

from collections.abc import Mapping
from itertools import product

from core.casegrid.execution import (
    DEFAULT_CONFIRMATION_THRESHOLD,
    DEFAULT_SECONDS_PER_CASE,
)
from core.casegrid.execution import execution_plan as build_execution_plan
from core.casegrid.models import Case, CaseVariable, CoupledSet, RunPlan


class CaseGrid:
    def __init__(
        self,
        variables: tuple[CaseVariable, ...],
        coupled_sets: tuple[CoupledSet, ...] = (),
        confirmation_threshold: int = DEFAULT_CONFIRMATION_THRESHOLD,
        seconds_per_case: float = DEFAULT_SECONDS_PER_CASE,
    ) -> None:
        self.variables = tuple(variables)
        self.coupled_sets = tuple(coupled_sets)
        self.confirmation_threshold = confirmation_threshold
        self.seconds_per_case = seconds_per_case
        if not self.variables:
            raise ValueError("case grid must contain at least one variable")
        if self.confirmation_threshold < 0:
            raise ValueError("confirmation threshold must be non-negative")
        if self.seconds_per_case < 0:
            raise ValueError("seconds per case must be non-negative")
        self._validate_variable_names()
        self._validate_coupled_sets()

    def case_count(self, *, filter_coupled: bool = True) -> int:
        count = 1
        for component in self._components(filter_coupled=filter_coupled):
            count *= len(component)
        return count

    def generate(self, *, filter_coupled: bool = True) -> tuple[Case, ...]:
        components = self._components(filter_coupled=filter_coupled)
        cases: list[Case] = []
        for index, fragments in enumerate(product(*components)):
            values: dict[str, object] = {}
            for fragment in fragments:
                values.update(fragment)
            cases.append(Case(index=index, values=values))
        return tuple(cases)

    def preview(self, limit: int | None = None) -> tuple[Case, ...]:
        if limit is not None and limit < 0:
            raise ValueError("preview limit must be non-negative")
        generated = self.generate()
        if limit is None:
            return generated
        return generated[:limit]

    def execution_plan(self, *, parallelism: int = 1) -> RunPlan:
        return build_execution_plan(
            self.case_count(),
            seconds_per_case=self.seconds_per_case,
            parallelism=parallelism,
            threshold=self.confirmation_threshold,
        )

    def _validate_variable_names(self) -> None:
        names = [variable.name for variable in self.variables]
        if len(set(names)) != len(names):
            raise ValueError("case grid variable names must be unique")

    def _validate_coupled_sets(self) -> None:
        variables_by_name = {variable.name: variable for variable in self.variables}
        assigned: dict[str, str] = {}
        for coupled in self.coupled_sets:
            lengths: set[int] = set()
            for variable_name in coupled.variable_names:
                variable = variables_by_name.get(variable_name)
                if variable is None:
                    raise ValueError(
                        f"coupled set {coupled.name!r} references unknown variable "
                        f"{variable_name!r}"
                    )
                if variable_name in assigned:
                    raise ValueError(
                        f"case variable {variable_name!r} appears in more than one coupled set"
                    )
                assigned[variable_name] = coupled.name
                lengths.add(len(variable.values))
            if len(lengths) != 1:
                raise ValueError(f"coupled set {coupled.name!r} values must have same length")

    def _components(self, *, filter_coupled: bool) -> tuple[tuple[Mapping[str, object], ...], ...]:
        if not filter_coupled:
            return tuple(
                tuple({variable.name: value} for value in variable.values)
                for variable in self.variables
            )

        coupled_by_variable = self._coupled_by_variable()
        emitted_coupled_sets: set[str] = set()
        components: list[tuple[Mapping[str, object], ...]] = []
        for variable in self.variables:
            coupled = coupled_by_variable.get(variable.name)
            if coupled is None:
                components.append(tuple({variable.name: value} for value in variable.values))
                continue
            if coupled.name in emitted_coupled_sets:
                continue
            emitted_coupled_sets.add(coupled.name)
            components.append(self._aligned_component(coupled))
        return tuple(components)

    def _aligned_component(self, coupled: CoupledSet) -> tuple[Mapping[str, object], ...]:
        variables_by_name = {variable.name: variable for variable in self.variables}
        first = variables_by_name[coupled.variable_names[0]]
        aligned: list[Mapping[str, object]] = []
        for value_index in range(len(first.values)):
            aligned.append(
                {
                    variable_name: variables_by_name[variable_name].values[value_index]
                    for variable_name in coupled.variable_names
                }
            )
        return tuple(aligned)

    def _coupled_by_variable(self) -> dict[str, CoupledSet]:
        lookup: dict[str, CoupledSet] = {}
        for coupled in self.coupled_sets:
            for variable_name in coupled.variable_names:
                lookup[variable_name] = coupled
        return lookup


def quick_preset_grid() -> CaseGrid:
    levels = ("low", "base", "high")
    return CaseGrid(
        variables=(
            CaseVariable("pv_unit_cost", levels),
            CaseVariable("ess_unit_cost", levels),
            CaseVariable("construction_cost", levels),
            CaseVariable("discount_rate", levels),
            CaseVariable("tariff_escalation", levels),
        ),
        coupled_sets=(
            CoupledSet(
                "equipment_cost_bundle",
                ("pv_unit_cost", "ess_unit_cost", "construction_cost"),
            ),
        ),
    )


def full_preset_grid() -> CaseGrid:
    levels = ("low", "base", "high")
    return CaseGrid(
        variables=(
            CaseVariable("pv_unit_cost", levels),
            CaseVariable("ess_unit_cost", levels),
            CaseVariable("heat_pump_unit_cost", levels),
            CaseVariable("construction_cost", levels),
            CaseVariable("discount_rate", levels),
            CaseVariable("tariff_escalation", levels),
        ),
    )
