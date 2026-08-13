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


#: 골든 회귀 허용오차 — **조항이 정한 값이다** (`NFR-104`: 승인 기준값 대비
#: 0.1% 이내). R26 까지 이 자리는 `0.15`(=15%) 였다. 손픽스처에만 쓰여 게이트를
#: 무르게 하지는 않았지만, **`NFR-104-M1` 마커가 붙은 경로에 조항의 150배
#: 허용치가 상수로 박혀 있었다** — 이 헬퍼를 실제 골든 파일에 재사용하는 순간
#: 조용히 15%가 적용된다. 실물 대조는 `tests/golden/test_regression_scenarios.py`
#: 가 `rel=1e-3`(NPV 는 완전 일치)로 하고 있으며, 두 값이 같아야 한다.
GOLDEN_TOLERANCE = 0.001


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
            expected, actual_by_scenario.get(scenario, {}), tolerance=GOLDEN_TOLERANCE
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
    """손 오라클: 기준값 100 에 대해 **조항 허용치(0.1%) 안쪽은 통과, 밖은 실패**.

    R26 까지 이 픽스처는 `114.0`(14% 높음)이 통과하도록 되어 있었다 — 헬퍼의
    허용치가 15% 였기 때문이다. **조항(`NFR-104`)은 0.1% 이고**, 픽스처가
    허용치에 맞춰져 있으면 허용치가 조항에서 얼마나 멀어졌는지 이 테스트는
    영영 말해 주지 않는다. 허용치를 조항 값으로 되돌리고 픽스처를 그에 맞췄다.

        100.05  0.05% 높음 → 통과 (경계 안쪽)
        140.0   40% 높음   → 실패
    """
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
        [case], {"demo": {"npv_won": 100.05}}
    )
    assert checked == ["scenario_demo.yaml"]
    assert skipped == []

    with pytest.raises(AssertionError, match="npv_won"):
        _golden_regression_status([case], {"demo": {"npv_won": 140.0}})

    # ★ **경계 바깥이 실제로 걸리는지** — 통과 케이스만 두면 허용치를 넓혀도
    # 아무것도 빨간불이 되지 않는다. 0.2% 는 조항(0.1%) 밖이므로 실패해야 한다.
    with pytest.raises(AssertionError, match="npv_won"):
        _golden_regression_status([case], {"demo": {"npv_won": 100.2}})

    # ⚠ R26 에 여기 있던 세 줄을 지웠다 — `assert "npv_won" in ({...})["demo"]`
    # 는 **리터럴에 대한 단언**이라 아무것도 검증하지 않았고, `detect_environment()`
    # 단언도 두 값 중 하나면 통과라 항상 참이었다. 주석은 「CI 게이트 경로에
    # 있음을 확인」이라 적고 있었으나 확인하는 것이 없었다.
