from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from typing import TypeAlias

from core.casegrid.models import EnvironmentProfile, PerformancePoint

DEFAULT_BENCHMARK_REPEATS = 10

BenchmarkRunner: TypeAlias = Callable[[int], None]


def measure_performance(
    case_counts: Sequence[int],
    *,
    repeat: int = DEFAULT_BENCHMARK_REPEATS,
    environment: EnvironmentProfile | None = None,
    runner: BenchmarkRunner | None = None,
) -> tuple[PerformancePoint, ...]:
    if repeat < 1:
        raise ValueError("benchmark repeat must be at least one")
    benchmark_runner = runner or _noop_benchmark
    profile = environment or detect_environment()
    points: list[PerformancePoint] = []
    for case_count in case_counts:
        if case_count < 0:
            raise ValueError("benchmark case counts must be non-negative")
        samples = _measure_samples(case_count, repeat, benchmark_runner)
        points.append(
            PerformancePoint(
                case_count=case_count,
                repeat_count=repeat,
                average_seconds=sum(samples) / len(samples),
                samples_seconds=samples,
                environment=profile,
            )
        )
    return tuple(points)


def detect_environment() -> EnvironmentProfile:
    cpu_count = os.cpu_count()
    return EnvironmentProfile(
        label="local process",
        cpu_count=cpu_count,
        memory_mb=None,
        free_tier_like=False,
    )


def _measure_samples(
    case_count: int,
    repeat: int,
    benchmark_runner: BenchmarkRunner,
) -> tuple[float, ...]:
    samples: list[float] = []
    for _ in range(repeat):
        start = time.perf_counter()
        for case_index in range(case_count):
            benchmark_runner(case_index)
        samples.append(time.perf_counter() - start)
    return tuple(samples)


def _noop_benchmark(_: int) -> None:
    return
