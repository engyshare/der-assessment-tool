"""NFR-004 and NFR-104 CI checks."""

from __future__ import annotations

import asyncio
import statistics
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
P95_LIMIT_SECONDS = 0.500
CONCURRENT_USERS = 20
REQUESTS_PER_USER = 5


@pytest.mark.req("NFR-004-M1")
def test_health_lookup_api_p95_under_500ms_at_20_concurrent_users() -> None:
    """Measured oracle: 20 concurrent clients call the read-only health endpoint."""

    async def run_probe() -> list[float]:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            for _ in range(CONCURRENT_USERS):
                warmup = await client.get("/health")
                assert warmup.status_code == 200

            async def one_request() -> float:
                start = time.perf_counter()
                response = await client.get("/health")
                elapsed = time.perf_counter() - start
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}
                return elapsed

            async def user_session() -> list[float]:
                return [await one_request() for _ in range(REQUESTS_PER_USER)]

            results = await asyncio.gather(
                *(user_session() for _ in range(CONCURRENT_USERS))
            )
        return [elapsed for user in results for elapsed in user]

    elapsed = asyncio.run(run_probe())
    p95 = statistics.quantiles(elapsed, n=100, method="inclusive")[94]

    assert len(elapsed) == CONCURRENT_USERS * REQUESTS_PER_USER
    assert p95 <= P95_LIMIT_SECONDS, (
        f"/health p95 {p95 * 1000:.1f}ms exceeds {P95_LIMIT_SECONDS * 1000:.0f}ms "
        f"under {CONCURRENT_USERS} concurrent users"
    )


def _filled_expected_values(case: dict[str, Any]) -> dict[str, float]:
    expected = case.get("expected_values")
    if not isinstance(expected, dict):
        return {}
    return {
        key: float(value)
        for key, value in expected.items()
        if isinstance(value, int | float)
    }


def _load_golden_case(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path.name} is not a mapping"
    return loaded


def _compare_golden_values(
    expected: dict[str, float], actual: dict[str, float], *, tolerance: float
) -> None:
    for key, expected_value in expected.items():
        assert key in actual, f"missing actual value for {key}"
        allowed = max(abs(expected_value) * tolerance, tolerance)
        delta = abs(actual[key] - expected_value)
        assert delta <= allowed, (
            f"{key}: expected {expected_value}, actual {actual[key]}, "
            f"delta {delta} > allowed {allowed}"
        )


def _golden_regression_status(
    paths: list[Path], actual_by_scenario: dict[str, dict[str, float]]
) -> tuple[list[str], list[str]]:
    checked: list[str] = []
    skipped: list[str] = []
    for path in paths:
        case = _load_golden_case(path)
        expected = _filled_expected_values(case)
        scenario = str(case["scenario"])
        if not expected:
            skipped.append(f"{path.name}: expected_values are all null")
            continue
        _compare_golden_values(
            expected, actual_by_scenario.get(scenario, {}), tolerance=0.15
        )
        checked.append(path.name)
    return checked, skipped


@pytest.mark.req("NFR-104-M1")
def test_empty_golden_oracles_are_reported_as_skipped_not_passed() -> None:
    """Fixture oracle: current golden files have null baselines and must not pass silently."""
    paths = sorted(GOLDEN_DIR.glob("scenario_*.yaml"))
    checked, skipped = _golden_regression_status(paths, actual_by_scenario={})

    assert len(paths) == 3
    assert checked == []
    assert skipped == [
        "scenario_subsidy_20.yaml: expected_values are all null",
        "scenario_subsidy_80.yaml: expected_values are all null",
        "scenario_unsubsidized.yaml: expected_values are all null",
    ]


@pytest.mark.req("NFR-104-M1")
def test_filled_golden_oracle_is_compared_and_can_fail(tmp_path: Path) -> None:
    """Hand oracle: 100 within 15 percent passes; 140 is 40 percent high and fails."""
    case = tmp_path / "scenario_demo.yaml"
    case.write_text(
        "\n".join(
            [
                "scenario: demo",
                "expected_values:",
                "  npv_won: 100",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    checked, skipped = _golden_regression_status(
        [case], {"demo": {"npv_won": 114.0}}
    )
    assert checked == ["scenario_demo.yaml"]
    assert skipped == []

    with pytest.raises(AssertionError, match="npv_won"):
        _golden_regression_status([case], {"demo": {"npv_won": 140.0}})
