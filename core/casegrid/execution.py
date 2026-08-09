from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Executor, Future, ProcessPoolExecutor, as_completed
from typing import TypeAlias, cast

from core.casegrid.models import Case, CaseResult, Progress, RunPlan

DEFAULT_CONFIRMATION_THRESHOLD = 500
DEFAULT_SECONDS_PER_CASE = 3.0
DEFAULT_BACKGROUND_THRESHOLD_SECONDS = 60.0

CaseRunner: TypeAlias = Callable[[Case], Mapping[str, float]]
ProgressCallback: TypeAlias = Callable[[Progress], None]
StopPredicate: TypeAlias = Callable[[], bool]
ExecutorFactory: TypeAlias = Callable[[int | None], Executor]


class CaseGridExecutionCancelled(RuntimeError):
    """Raised when a caller requests cancellation during case execution."""


def execution_plan(
    case_count: int,
    *,
    seconds_per_case: float = DEFAULT_SECONDS_PER_CASE,
    parallelism: int = 1,
    threshold: int = DEFAULT_CONFIRMATION_THRESHOLD,
    background_threshold_seconds: float = DEFAULT_BACKGROUND_THRESHOLD_SECONDS,
) -> RunPlan:
    if case_count < 0:
        raise ValueError("case count must be non-negative")
    if seconds_per_case < 0:
        raise ValueError("seconds per case must be non-negative")
    if parallelism < 1:
        raise ValueError("parallelism must be at least one")
    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    estimated = case_count * seconds_per_case / parallelism
    return RunPlan(
        case_count=case_count,
        threshold=threshold,
        estimated_seconds=estimated,
        requires_confirmation=case_count > threshold,
        should_run_background=estimated > background_threshold_seconds,
    )


def run_cases(
    cases: Sequence[Case],
    runner: CaseRunner,
    *,
    parallel: bool = False,
    max_workers: int | None = None,
    executor_factory: ExecutorFactory | None = None,
    progress: ProgressCallback | None = None,
    stop_requested: StopPredicate | None = None,
) -> tuple[CaseResult, ...]:
    ordered_cases = tuple(sorted(cases, key=lambda case: case.index))
    if not parallel:
        return _run_cases_sequential(ordered_cases, runner, progress, stop_requested)
    return _run_cases_parallel(
        ordered_cases,
        runner,
        max_workers=max_workers,
        executor_factory=executor_factory or _process_pool,
        progress=progress,
        stop_requested=stop_requested,
    )


def _run_cases_sequential(
    cases: Sequence[Case],
    runner: CaseRunner,
    progress: ProgressCallback | None,
    stop_requested: StopPredicate | None,
) -> tuple[CaseResult, ...]:
    start = time.perf_counter()
    results: list[CaseResult] = []
    total_cases = len(cases)
    for case in cases:
        _raise_if_cancelled(stop_requested)
        results.append(_execute_case(runner, case))
        _emit_progress(progress, len(results), total_cases, start)
    return tuple(results)


def _run_cases_parallel(
    cases: Sequence[Case],
    runner: CaseRunner,
    *,
    max_workers: int | None,
    executor_factory: ExecutorFactory,
    progress: ProgressCallback | None,
    stop_requested: StopPredicate | None,
) -> tuple[CaseResult, ...]:
    start = time.perf_counter()
    results: list[CaseResult] = []
    futures: list[Future[CaseResult]] = []
    with executor_factory(max_workers) as executor:
        for case in cases:
            _raise_if_cancelled(stop_requested)
            futures.append(cast(Future[CaseResult], executor.submit(_execute_case, runner, case)))
        for future in as_completed(futures):
            _raise_if_cancelled(stop_requested)
            results.append(future.result())
            _emit_progress(progress, len(results), len(cases), start)
    return tuple(sorted(results, key=lambda result: result.case_index))


def _process_pool(max_workers: int | None) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=max_workers)


def _execute_case(runner: CaseRunner, case: Case) -> CaseResult:
    return CaseResult(case_index=case.index, values=case.values, metrics=dict(runner(case)))


def _emit_progress(
    progress: ProgressCallback | None,
    completed_cases: int,
    total_cases: int,
    start: float,
) -> None:
    if progress is None:
        return
    elapsed = time.perf_counter() - start
    progress(
        Progress(
            completed_cases=completed_cases,
            total_cases=total_cases,
            estimated_remaining_seconds=_estimated_remaining_seconds(
                completed_cases,
                total_cases,
                elapsed,
            ),
        )
    )


def _estimated_remaining_seconds(
    completed_cases: int,
    total_cases: int,
    elapsed_seconds: float,
) -> float | None:
    if completed_cases == 0:
        return None
    return max(total_cases - completed_cases, 0) * elapsed_seconds / completed_cases


def _raise_if_cancelled(stop_requested: StopPredicate | None) -> None:
    if stop_requested is not None and stop_requested():
        raise CaseGridExecutionCancelled("case-grid execution was cancelled")
