"""Case-grid generation, execution, aggregation, and benchmark harness."""

from core.casegrid.analysis import (
    compare_metric,
    feasible_region,
    filter_results,
    tornado_ranking,
)
from core.casegrid.execution import (
    CaseGridExecutionCancelled,
    execution_plan,
    run_cases,
)
from core.casegrid.export import ResultTable, result_table
from core.casegrid.grid import (
    CaseGrid,
    coupled_variable_sets,
    full_preset_grid,
    quick_preset_grid,
)
from core.casegrid.models import (
    Case,
    CaseResult,
    CaseVariable,
    CoupledSet,
    EnvironmentProfile,
    FeasibleCell,
    PerformancePoint,
    Progress,
    RunPlan,
    TornadoInfluence,
)
from core.casegrid.performance import (
    detect_environment,
    measure_performance,
)

__all__ = (
    "Case",
    "CaseGrid",
    "CaseGridExecutionCancelled",
    "CaseResult",
    "CaseVariable",
    "CoupledSet",
    "EnvironmentProfile",
    "FeasibleCell",
    "PerformancePoint",
    "Progress",
    "ResultTable",
    "RunPlan",
    "TornadoInfluence",
    "compare_metric",
    "coupled_variable_sets",
    "detect_environment",
    "execution_plan",
    "feasible_region",
    "filter_results",
    "full_preset_grid",
    "measure_performance",
    "quick_preset_grid",
    "result_table",
    "run_cases",
    "tornado_ranking",
)
