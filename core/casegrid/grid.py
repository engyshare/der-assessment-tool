from __future__ import annotations

from collections.abc import Mapping
from itertools import product

from core.casegrid.execution import (
    DEFAULT_CONFIRMATION_THRESHOLD,
    DEFAULT_SECONDS_PER_CASE,
)
from core.casegrid.execution import execution_plan as build_execution_plan
from core.casegrid.models import Case, CaseVariable, CoupledSet, RunPlan
from core.contracts.validation import ValidationError


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
            raise ValidationError(
                field="casegrid.variables",
                reason="케이스 그리드는 변수를 최소 1개 이상 가져야 합니다",
                action="variables 에 CaseVariable 을 1개 이상 추가하십시오",
            )
        if self.confirmation_threshold < 0:
            raise ValidationError(
                field="casegrid.confirmation_threshold",
                reason=f"확인 임계치가 음수입니다: {self.confirmation_threshold}",
                action="0 이상의 정수를 지정하십시오",
            )
        if self.seconds_per_case < 0:
            raise ValidationError(
                field="casegrid.seconds_per_case",
                reason=f"케이스당 예상 소요시간이 음수입니다: {self.seconds_per_case}",
                action="0 이상의 값을 지정하십시오",
            )
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
            raise ValidationError(
                field="casegrid.preview_limit",
                reason=f"미리보기 한도가 음수입니다: {limit}",
                action="0 이상의 값을 지정하거나 생략하십시오",
            )
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
            duplicates = sorted({name for name in names if names.count(name) > 1})
            raise ValidationError(
                field="casegrid.variables",
                reason=f"변수 이름이 중복되었습니다: {duplicates}",
                action="변수 이름을 서로 다르게 지정하십시오",
            )

    def _validate_coupled_sets(self) -> None:
        variables_by_name = {variable.name: variable for variable in self.variables}
        assigned: dict[str, str] = {}
        for coupled in self.coupled_sets:
            lengths: set[int] = set()
            for variable_name in coupled.variable_names:
                variable = variables_by_name.get(variable_name)
                if variable is None:
                    raise ValidationError(
                        field="casegrid.coupled_sets",
                        reason=(
                            f"결합 집합 {coupled.name!r} 이 알 수 없는 변수 "
                            f"{variable_name!r} 를 참조합니다"
                        ),
                        action="결합 집합이 참조하는 변수 이름을 variables 목록에 선언하십시오",
                    )
                if variable_name in assigned:
                    raise ValidationError(
                        field="casegrid.coupled_sets",
                        reason=(
                            f"변수 {variable_name!r} 가 둘 이상의 결합 집합에 "
                            "속해 있습니다"
                        ),
                        action="변수 하나는 하나의 결합 집합에만 속하게 하십시오",
                    )
                assigned[variable_name] = coupled.name
                lengths.add(len(variable.values))
            if len(lengths) != 1:
                raise ValidationError(
                    field="casegrid.coupled_sets",
                    reason=(
                        f"결합 집합 {coupled.name!r} 의 값 목록 길이가 서로 다릅니다: "
                        f"{sorted(lengths)}"
                    ),
                    action="결합된 변수들의 값 개수를 모두 같게 맞추십시오",
                    rule="DV-9",
                )

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
    """빠른 탐색 프리셋 (FR-801-AC7.quick) — 27 케이스.

    ★ **결합 집합은 spec §FR-801 구성표의 「설비단가(PV·ESS·히트펌프)·시공비」
    넷이다.** R26 까지 히트펌프가 빠진 셋이었고, **케이스 수는 그래도 27이라
    개수를 보는 검사로는 드러나지 않았다** — 결합 집합은 몇 개를 묶든 축 하나이기
    때문이다. 그동안 빠른 탐색으로 돌리면 히트펌프 단가만 흔들리지 않았다.
    """
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
        coupled_sets=(
            CoupledSet(
                "equipment_cost_bundle",
                (
                    "pv_unit_cost",
                    "ess_unit_cost",
                    "heat_pump_unit_cost",
                    "construction_cost",
                ),
            ),
        ),
    )


def full_preset_grid() -> CaseGrid:
    """전체 탐색 프리셋 (FR-801-AC7.full) — 729 케이스.

    ★ **구성은 spec §FR-801 구성표 6행이다** — 결합 **2집합** + 독립 **4변수**,
    각 3수준이므로 `3 × 3 × 3⁴ = 729`(조항의 v0.5 정정 사유가 이 산식을 적는다).

    R29 까지 이 함수는 **결합 집합이 하나도 없었고** 뒤 3변수(직접거래·PPA 단가·
    PV 이용률·EV 보급률)가 통째로 빠진 채 설비단가 4종을 독립축으로 펼쳐 729를
    맞췄다. **개수는 맞고 구성이 달랐으며**, 붙드는 검사가 `3**6` 하나뿐이라
    드러나지 않았다 — `quick_preset_grid` 에서 고친 것과 **같은 형태**다.

    「직접거래·PPA 단가」가 SMP 와 결합인 이유는 구성표가 *「결합 (SMP와 동조)」*
    라고 적기 때문이다. 두 단가가 독립으로 흔들리면 SMP 최저 + PPA 최고 같은
    실현 불가 조합이 생기고, 그것이 `FR-802` 가 없애려던 것이다.
    """
    levels = ("low", "base", "high")
    return CaseGrid(
        variables=(
            # 결합 ① 설비단가·시공비
            CaseVariable("pv_unit_cost", levels),
            CaseVariable("ess_unit_cost", levels),
            CaseVariable("heat_pump_unit_cost", levels),
            CaseVariable("construction_cost", levels),
            # 결합 ② 직접거래·PPA 단가 (SMP 동조)
            CaseVariable("direct_trade_price", levels),
            CaseVariable("smp_price", levels),
            # 독립 4
            CaseVariable("discount_rate", levels),
            CaseVariable("tariff_escalation", levels),
            CaseVariable("pv_capacity_factor", levels),
            CaseVariable("ev_adoption_rate", levels),
        ),
        coupled_sets=(
            CoupledSet(
                "equipment_cost_bundle",
                (
                    "pv_unit_cost",
                    "ess_unit_cost",
                    "heat_pump_unit_cost",
                    "construction_cost",
                ),
            ),
            CoupledSet(
                "trade_price_bundle",
                ("direct_trade_price", "smp_price"),
            ),
        ),
    )


def coupled_variable_sets() -> Mapping[str, tuple[str, ...]]:
    """프리셋이 선언한 **결합 집합 전건** — 「무엇이 함께 움직이는가」의 정본.

    ## 왜 밖으로 내놓는가 (R33 검토 「1차 의견」 1)

    검토 의견이 물었다 — *「ESS, PV 단가가 같이 움직여도 동일한 결과가 나오는가」*.
    나오지 않는다. 그런데 **저장소는 이미 그 답을 갖고 있었다**: 두 프리셋이
    설비단가 넷을 `equipment_cost_bundle` 로 묶어 한 축으로 흔든다(§FR-801
    구성표). 즉 케이스 그리드는 결합으로 보는데 **리포트의 민감도만 인자별로
    독립**이었고, 그래서 *「PV 가 18% · ESS 가 17% 각각 내려가야 한다」* 로
    읽혔다 — 함께 내려가면 훨씬 앞에서 뒤집힌다.

    결합을 리포트 쪽에 다시 적으면 **사본**이 되고, 그러면 여기서 묶음을 바꿔도
    리포트는 옛 묶음을 그린다. 그래서 선언을 여기서 내놓고 리포트가 읽어 간다.

    ⚠ **두 프리셋의 합집합이다.** 빠른 탐색에만 있는 묶음, 전체 탐색에만 있는
    묶음이 따로 있으므로 하나만 읽으면 조용히 빠진다. 같은 이름의 묶음이 두
    프리셋에서 다른 변수를 들면 **합쳐서** 돌려준다 — 어느 한쪽을 이겼다고
    적으면 그 판단이 여기 숨는다.
    """
    merged: dict[str, tuple[str, ...]] = {}
    for grid in (quick_preset_grid(), full_preset_grid()):
        for coupled in grid.coupled_sets:
            seen = merged.get(coupled.name, ())
            merged[coupled.name] = seen + tuple(
                name for name in coupled.variable_names if name not in seen
            )
    return merged
