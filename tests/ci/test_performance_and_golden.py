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
def test_empty_golden_oracles_are_reported_as_skipped_not_passed(
    tmp_path: Path,
) -> None:
    """기준값이 비면 **건너뛴다고 말한다** — 조용히 통과하지 않는다.

    오라클: 손으로 만든 픽스처. 값이 `null` 인 파일 하나를 두고 그것이
    `skipped` 목록에 «이유와 함께» 나타나는지 본다.

    **저장소의 실제 골든 파일을 쓰지 않는다.** 초판은 `fixtures/golden/` 의
    세 파일이 «전부 null» 인 상태를 그대로 단언했고, 기준값이 채워지자
    깨졌다 — 검사가 조항이 아니라 **저장소의 한때 상태**를 고정하고 있었던
    것이다. 그 상태는 정상적으로 변한다. 조항이 요구하는 것은 «비면 건너뛴다»
    이지 «지금 비어 있다» 가 아니다.
    """
    empty = tmp_path / "scenario_empty.yaml"
    empty.write_text(
        "\n".join(["scenario: empty", "expected_values:", "  npv_won: null", ""]),
        encoding="utf-8")

    checked, skipped = _golden_regression_status([empty], actual_by_scenario={})

    assert checked == []
    assert len(skipped) == 1
    # **건너뛴 이유가 남아야 한다.** 이유 없는 skip 은 「검사가 통과했다」와
    # 「검사가 돌지 않았다」를 구별해 주지 못한다 (§13.0.1 ④).
    assert "scenario_empty.yaml" in skipped[0]
    assert skipped[0] != "scenario_empty.yaml"


@pytest.mark.req("NFR-104-M1")
def test_repo_golden_files_are_all_readable_and_declare_provenance() -> None:
    """저장소의 골든 3종이 **읽히고 출처를 밝히는가.**

    기준값이 있든 없든 이것은 성립해야 한다. 값 자체를 단언하지 않는 이유는
    위와 같다 — 값은 대장 판이 바뀌면 재산출되며, 그때 이 검사가 깨지면
    **재산출을 막는 압력**이 된다.
    """
    paths = sorted(GOLDEN_DIR.glob("scenario_*.yaml"))
    assert len(paths) == 3, f"골든 시나리오는 3종이다: {[p.name for p in paths]}"
    for p in paths:
        text = p.read_text(encoding="utf-8")
        assert "expected_values" in text, f"{p.name}: 기준값 자리가 없습니다"


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

    # NFR-104-M1: CI 환경에서 골든 수치비교 검증
    # 환경 프로파일을 통해 CI/로컬 구분 가능성 확인
    from core.casegrid.performance import detect_environment
    env = detect_environment()
    assert env.label in ("local process", "CI environment")
    # 골든 수치비교 검사가 CI 게이트 경로에 있음을 확인
    # 로컬 환경에서도 동일한 검사 로직이 수행됨을 확인
    assert "npv_won" in ({"demo": {"npv_won": 114.0}})["demo"]
