from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.casegrid import (
    Case,
    CaseGrid,
    CaseGridExecutionCancelled,
    CaseVariable,
    CoupledSet,
    EnvironmentProfile,
    compare_metric,
    execution_plan,
    feasible_region,
    filter_results,
    full_preset_grid,
    measure_performance,
    quick_preset_grid,
    result_table,
    run_cases,
    tornado_ranking,
)


@pytest.mark.req("FR-802-AC1")
@pytest.mark.req("FR-802-AC2")
@pytest.mark.req("FR-802-AC3")
@pytest.mark.req("FR-802-AC4")
@pytest.mark.req("FR-802-AC5")
def test_coupled_filter_counts_are_generated_from_grid_definition() -> None:
    """12.1 oracle: 3 aligned cost levels * 3 discount levels * 3 tariff levels.

    The same five variables without the coupled filter are 3 ** 5 full Cartesian cases.
    A mismatched coupled set must fail before execution so 0 passing cases cannot mask
    a filter that never matched.
    """

    grid = quick_preset_grid()
    filtered_cases = grid.generate()
    unfiltered_cases = grid.generate(filter_coupled=False)

    assert len(filtered_cases) == len(("low", "base", "high")) * len(
        ("low", "base", "high")
    ) * len(("low", "base", "high"))
    assert len(unfiltered_cases) == len(("low", "base", "high")) ** len(grid.variables)
    assert grid.preview(limit=2) == filtered_cases[:2]

    with pytest.raises(ValueError, match="same length"):
        CaseGrid(
            variables=(
                CaseVariable("pv_cost", ("low", "base", "high")),
                CaseVariable("ess_cost", ("low", "base")),
            ),
            coupled_sets=(CoupledSet("bad_cost_bundle", ("pv_cost", "ess_cost")),),
        )


@pytest.mark.req("FR-801-AC1")
@pytest.mark.req("FR-801-AC2")
@pytest.mark.req("FR-801-AC3")
@pytest.mark.req("FR-801-AC4")
@pytest.mark.req("FR-801-AC5")
@pytest.mark.req("FR-801-AC6")
@pytest.mark.req("FR-801-AC7.quick")
@pytest.mark.req("FR-801-AC7.full")
@pytest.mark.req("NFR-002-M1")
def test_presets_show_case_counts_thresholds_and_export_results() -> None:
    """12.2-12.3 oracle: quick is coupled 3 * 3 * 3; full is six 3-level axes.

    DV-10 confirmation depends on generated count versus threshold 500, while
    NFR-002 background mode depends on estimated runtime exceeding 60 seconds.
    """

    quick = quick_preset_grid()
    full = full_preset_grid()

    assert quick.case_count() == len(("low", "base", "high")) ** 3
    assert quick.case_count(filter_coupled=False) == len(("low", "base", "high")) ** 5
    assert full.case_count() == len(("low", "base", "high")) ** 6

    quick_plan = quick.execution_plan()
    full_plan = full.execution_plan()

    assert quick_plan.requires_confirmation is False
    assert quick_plan.should_run_background is True
    assert full_plan.requires_confirmation is True
    assert full_plan.should_run_background is True

    table = result_table(
        [
            Case(index=0, values={"discount_rate": "low", "tariff_escalation": "base"}),
            Case(index=1, values={"discount_rate": "high", "tariff_escalation": "base"}),
        ],
        [{"npv": 100.0}, {"npv": -5.0}],
    )

    assert table.columns == ("case_index", "discount_rate", "tariff_escalation", "npv")
    assert "case_index,discount_rate,tariff_escalation,npv" in table.to_csv()
    assert b"xl/worksheets/sheet1.xml" in table.to_xlsx_bytes()


@pytest.mark.req("FR-805-AC1")
def test_parallel_results_are_returned_in_case_index_order_with_progress() -> None:
    """12.4 oracle: collection may complete in reverse order, but output is case-index order."""

    cases = tuple(Case(index=index, values={"x": index}) for index in range(6))
    progress_updates: list[tuple[int, int]] = []

    def runner(case: Case) -> dict[str, float]:
        time.sleep((len(cases) - case.index) / 1_000)
        return {"score": float(case.index)}

    results = run_cases(
        cases,
        runner,
        parallel=True,
        max_workers=3,
        executor_factory=ThreadPoolExecutor,
        progress=lambda progress: progress_updates.append(
            (progress.completed_cases, progress.total_cases)
        ),
    )

    assert [result.case_index for result in results] == [case.index for case in cases]
    assert progress_updates[-1] == (len(cases), len(cases))

    with pytest.raises(CaseGridExecutionCancelled):
        run_cases(
            cases,
            runner,
            progress=lambda progress: progress_updates.append(
                (progress.completed_cases, progress.total_cases)
            ),
            stop_requested=lambda: True,
        )


@pytest.mark.req("NFR-001-M1")
@pytest.mark.req("NFR-002-M1")
def test_performance_harness_measures_required_case_counts_and_environment_basis() -> None:
    """12.6 oracle: the harness records 27/100/500 endpoints and repeat averages."""

    counts = (quick_preset_grid().case_count(), 100, execution_plan(501).threshold)
    profile = EnvironmentProfile(
        label="unit-test host",
        cpu_count=8,
        memory_mb=None,
        free_tier_like=False,
    )

    points = measure_performance(counts, repeat=2, environment=profile)

    assert [point.case_count for point in points] == list(counts)
    assert all(point.repeat_count == 2 for point in points)
    assert all(point.average_seconds >= 0 for point in points)
    assert all(point.environment.free_tier_like is False for point in points)


@pytest.mark.req("FR-803-AC1")
@pytest.mark.req("FR-803-AC2")
@pytest.mark.req("FR-803-AC3")
def test_feasible_region_filters_and_tornado_ranking_use_case_results() -> None:
    """12.8 oracle: target-achieved shading, achieved/missed filters, and influence rank."""

    cases = (
        Case(index=0, values={"discount_rate": "low", "tariff": "low"}),
        Case(index=1, values={"discount_rate": "low", "tariff": "high"}),
        Case(index=2, values={"discount_rate": "high", "tariff": "low"}),
        Case(index=3, values={"discount_rate": "high", "tariff": "high"}),
    )
    results = run_cases(
        cases,
        lambda case: {
            "npv": float((100 if case.values["tariff"] == "high" else 0) - (
                30 if case.values["discount_rate"] == "high" else 0
            ))
        },
    )

    cells = feasible_region(results, x="discount_rate", y="tariff", metric="npv", target=50)
    achieved = filter_results(results, metric="npv", target=50, achieved=True)
    missed = filter_results(results, metric="npv", target=50, achieved=False)
    ranking = tornado_ranking(results, metric="npv")

    assert {(cell.x_value, cell.y_value, cell.achieved) for cell in cells} == {
        ("low", "low", False),
        ("low", "high", True),
        ("high", "low", False),
        ("high", "high", True),
    }
    assert [result.case_index for result in achieved] == [1, 3]
    assert [result.case_index for result in missed] == [0, 2]
    assert ranking[0].variable_name == "tariff"
    assert compare_metric(50, 50, ">=") is True


@pytest.mark.req("NFR-001-M1")
def test_parallel_execution_determinism_across_10_runs() -> None:
    """12.6 oracle: 10 repeated runs of parallel case execution yield identical ordered results."""
    cases = tuple(Case(index=i, values={"x": i}) for i in range(27))

    first_run_indexes = None
    for _ in range(10):
        results = run_cases(
            cases,
            lambda c: {"npv": float(c.index)},
            parallel=True,
            executor_factory=ThreadPoolExecutor,
        )
        ordered_indexes = tuple(r.case_index for r in results)
        if first_run_indexes is None:
            first_run_indexes = ordered_indexes
        assert ordered_indexes == first_run_indexes
        assert ordered_indexes == tuple(range(27))
