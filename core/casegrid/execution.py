from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Executor, Future, ProcessPoolExecutor, as_completed
from typing import TypeAlias, cast

from core.casegrid.models import Case, CaseOutcome, CaseResult, Progress, RunPlan
from core.contracts.validation import ValidationError

DEFAULT_CONFIRMATION_THRESHOLD = 500
DEFAULT_SECONDS_PER_CASE = 3.0
DEFAULT_BACKGROUND_THRESHOLD_SECONDS = 60.0

#: 러너는 지표 사전을 돌려주거나, 변형별 지표까지 실은 `CaseOutcome` 을 돌려준다
#: (`FR-607-AC1` / R32). 후자를 받으면 `CaseResult.variants` 가 채워진다 —
#: **그 통로가 없어서** R31 까지 변형을 채우는 배포 코드가 0곳이었다.
CaseRunner: TypeAlias = Callable[[Case], Mapping[str, float] | CaseOutcome]
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
        raise ValidationError(
            field="casegrid.seconds_per_case",
            reason=f"케이스당 예상 소요시간이 음수입니다: {seconds_per_case}",
            action="0 이상의 값을 지정하십시오",
        )
    if parallelism < 1:
        raise ValidationError(
            field="casegrid.parallelism",
            reason=f"병렬도가 1 미만입니다: {parallelism}",
            action="1 이상의 정수를 지정하십시오",
        )
    if threshold < 0:
        raise ValidationError(
            field="casegrid.confirmation_threshold",
            reason=f"확인 임계치가 음수입니다: {threshold}",
            action="0 이상의 정수를 지정하십시오",
        )
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
    confirmed: bool = False,
    threshold: int = DEFAULT_CONFIRMATION_THRESHOLD,
) -> tuple[CaseResult, ...]:
    case_count = len(cases)
    if case_count > threshold and not confirmed:
        raise ValidationError(
            field="casegrid.case_count",
            reason=(
                f"케이스 수 {case_count}건이 확인 임계치 {threshold}건을 "
                "초과했습니다"
            ),
            action="케이스 수를 줄이거나, 사용자 확인 후 confirmed=True 로 다시 호출하십시오",
            rule="DV-10",
        )
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
    """러너를 한 번 돌려 케이스 결과를 만든다.

    ★ **변형별 지표를 여기서 나른다 (`FR-607-AC1` / R32).** 러너가 `CaseOutcome`
    을 돌려주면 그 변형을 결과에 싣는다. 지표 사전만 돌려주면 `variants` 는
    비어 있고, 그것은 「변형을 산출하지 않은 실행」이라는 정당한 상태다
    (`CaseOutcome` 독스트링 — 그 구별을 두는 근거가 거기 있다).

    ⚠ **`isinstance` 로 갈랐다.** `hasattr(outcome, "variants")` 로 가르면 우연히
    같은 이름의 속성을 가진 사전형이 변형으로 읽히고, 그 오독은 아무 예외도
    내지 않는다.
    """
    outcome = runner(case)
    if isinstance(outcome, CaseOutcome):
        return CaseResult(
            case_index=case.index,
            values=case.values,
            metrics=dict(outcome.metrics),
            variants={tag: dict(m) for tag, m in outcome.variants.items()},
        )
    return CaseResult(case_index=case.index, values=case.values, metrics=dict(outcome))


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
