from __future__ import annotations

from collections.abc import Sequence

from core.casegrid.models import CaseResult, FeasibleCell, TornadoInfluence


def feasible_region(
    results: Sequence[CaseResult],
    *,
    x: str,
    y: str,
    metric: str,
    target: float,
    comparator: str = ">=",
) -> tuple[FeasibleCell, ...]:
    cells: list[FeasibleCell] = []
    for result in sorted(results, key=lambda item: item.case_index):
        cells.append(
            FeasibleCell(
                x_value=result.values[x],
                y_value=result.values[y],
                metric_value=result.metrics[metric],
                achieved=compare_metric(result.metrics[metric], target, comparator),
                case_index=result.case_index,
            )
        )
    return tuple(cells)


def filter_results(
    results: Sequence[CaseResult],
    *,
    metric: str,
    target: float,
    achieved: bool,
    comparator: str = ">=",
) -> tuple[CaseResult, ...]:
    return tuple(
        result
        for result in sorted(results, key=lambda item: item.case_index)
        if compare_metric(result.metrics[metric], target, comparator) is achieved
    )


def tornado_ranking(results: Sequence[CaseResult], *, metric: str) -> tuple[TornadoInfluence, ...]:
    variable_names = sorted({name for result in results for name in result.values})
    influences: list[TornadoInfluence] = []
    for variable_name in variable_names:
        averages = _metric_averages_by_value(results, variable_name, metric)
        influence = max(averages) - min(averages) if averages else 0.0
        influences.append(TornadoInfluence(variable_name=variable_name, influence=influence))
    return tuple(sorted(influences, key=lambda item: (-item.influence, item.variable_name)))


def compare_metric(value: float, target: float, comparator: str = ">=") -> bool:
    if comparator == ">=":
        return value >= target
    if comparator == ">":
        return value > target
    if comparator == "<=":
        return value <= target
    if comparator == "<":
        return value < target
    if comparator == "==":
        return value == target
    raise ValueError(f"unsupported comparator: {comparator!r}")


def _metric_averages_by_value(
    results: Sequence[CaseResult],
    variable_name: str,
    metric: str,
) -> tuple[float, ...]:
    grouped: dict[object, list[float]] = {}
    for result in results:
        grouped.setdefault(result.values[variable_name], []).append(result.metrics[metric])
    return tuple(sum(values) / len(values) for values in grouped.values())
