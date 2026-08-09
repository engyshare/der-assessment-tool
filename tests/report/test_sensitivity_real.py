"""민감도 순위 엔진 검증 — FR-1002-AC1, AC2, AC4.

테스트 순서: Red → (구현) → Green.

기대값 산출 근거
-----------------
아래 모든 기대값은 손으로 계산하거나 수식 추론으로 구했다.
코드를 돌려 나온 값을 그대로 쓰지 않는다.

metric_fn(x) = x  (항등 함수) 를 쓸 때:
- 인자 dominant: base=100, low=1, high=1000  →  영향폭 = |1000 - 1| = 999
- 인자 tiny:      base=100, low=95, high=105  →  영향폭 = |105 - 95| = 10
- 인자 mid:       base=100, low=80, high=120  →  영향폭 = |120 - 80| = 40

순위: dominant(999) > mid(40) > tiny(10)  → dominant 가 1위

임계값 테스트:
- metric_fn(x) = x - 50 (부호가 x=50 에서 바뀜)
- base=100, low=0, high=200 → 이진탐색으로 x≈50 을 찾아야 함
- margin_pct = (100 - 50) / 100 × 100 = 50.0 %  (base 에서 임계값까지의 비율)
"""
import math
from typing import Any

import pytest

from core.report.sensitivity import rank_influences

# ---------------------------------------------------------------------------
# 13.1 [T] 인자를 인위적으로 지배적으로 만들어 순위 1위로 나오는지 검증
# ---------------------------------------------------------------------------


@pytest.mark.req("FR-1002-AC1", "FR-1002-AC2")
def test_sensitivity_ranking_dominated_factor() -> None:
    """지배적 인자가 영향도 순위 1위로 나오는지 확인한다.

    영향폭 계산 (metric_fn = 항등 함수):
      dominant:  |high - low| = |1000 - 1| = 999
      mid:       |high - low| = |120 - 80|  = 40
      tiny:      |high - low| = |105 - 95|  = 10

    따라서 dominant > mid > tiny 순이어야 한다.
    가짜 구현(미리 주어진 impact 없음)이면 이 테스트는 실패한다.
    """

    def identity(x: float) -> float:
        return x

    variables: dict[str, dict[str, Any]] = {
        "tiny": {"base": 100.0, "low": 95.0, "high": 105.0},
        "dominant": {"base": 100.0, "low": 1.0, "high": 1000.0},
        "mid": {"base": 100.0, "low": 80.0, "high": 120.0},
    }
    ranked = rank_influences(variables, metric_fn=identity)

    assert ranked[0]["name"] == "dominant", (
        f"1위는 dominant 여야 하는데 {ranked[0]['name']} 이 나왔다. "
        "가짜 구현(하드코딩 impact)이면 이 순서가 보장되지 않는다."
    )
    assert ranked[1]["name"] == "mid"
    assert ranked[2]["name"] == "tiny"


# ---------------------------------------------------------------------------
# 13.1 [T] 결론 전환 임계값 탐지 (FR-1002-AC4)
# ---------------------------------------------------------------------------


@pytest.mark.req("FR-1002-AC4")
def test_threshold_sign_flip_detection() -> None:
    """결론이 뒤집히는 임계값이 올바르게 찾아지는지 확인한다.

    metric_fn(x) = x - 50 을 쓰면:
      - x < 50  → metric < 0  (비사업성)
      - x = 50  → metric = 0  (임계점)
      - x > 50  → metric > 0  (사업성)

    base=100 > 50 이므로 기준 결론은 "양수(사업성)".
    low=0 에서 metric = 0 - 50 = -50  (음수 → 결론 뒤집힘).

    이진탐색 임계값 ≈ 50.  허용 오차 ±1.0.

    margin_pct = (base - threshold) / base × 100
               = (100 - 50) / 100 × 100 = 50.0 %
    """

    def flip_fn(x: float) -> float:
        return x - 50.0

    variables: dict[str, dict[str, Any]] = {
        "price": {"base": 100.0, "low": 0.0, "high": 200.0},
    }
    ranked = rank_influences(variables, metric_fn=flip_fn)
    row = ranked[0]

    assert row["name"] == "price"
    assert row["flips_conclusion"] is True, "결론 전환 인자가 flips_conclusion=True 여야 한다"

    threshold = row["threshold"]
    assert math.isfinite(threshold), f"threshold 는 유한한 실수여야 한다, got {threshold}"
    assert abs(threshold - 50.0) <= 1.0, (
        f"임계값은 ≈50.0 이어야 하는데 {threshold:.4f} 가 나왔다."
    )

    margin_pct = row["margin_pct"]
    # margin_pct = (100 - 50) / 100 × 100 = 50.0 (±2 허용)
    assert abs(margin_pct - 50.0) <= 2.0, (
        f"margin_pct 는 ≈50.0 이어야 하는데 {margin_pct:.4f} 가 나왔다."
    )


# ---------------------------------------------------------------------------
# 13.1 [T] 결론 전환이 없는 인자는 flips_conclusion=False
# ---------------------------------------------------------------------------


@pytest.mark.req("FR-1002-AC4")
def test_no_flip_when_range_safe() -> None:
    """low~high 범위 전체에서 결론이 바뀌지 않으면 flips_conclusion=False 여야 한다.

    metric_fn(x) = x - 1  이고 base=100, low=50, high=200.
    low 에서 metric = 50 - 1 = 49 > 0  → 뒤집히지 않음.
    """

    def always_positive(x: float) -> float:
        return x - 1.0

    variables: dict[str, dict[str, Any]] = {
        "stable": {"base": 100.0, "low": 50.0, "high": 200.0},
    }
    ranked = rank_influences(variables, metric_fn=always_positive)
    row = ranked[0]

    assert row["flips_conclusion"] is False
