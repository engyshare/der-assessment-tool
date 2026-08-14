"""영향도 순위 엔진 — FR-1002.

원칙 7-1 (domain-rules.md §7):
    결과 리포트는 결과에 실제로 영향을 미친 인자를
    영향도 순(민감도 분석 결과)으로 먼저 제시한다.

AC2 산출 방식:
    각 인자를 low / base / high 로 변동시켜 주 지표(metric_fn)가
    움직인 폭 |metric(high) - metric(low)| 으로 측정한다.

AC4 결론 전환:
    합리적 변동 범위(low~high) 안에서 metric 이 부호를 바꾸는 지점을
    이진탐색으로 찾아 threshold 로 반환한다.
    margin_pct = |base - threshold| / |base| * 100  (base 가 0 인 경우 inf).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

#: 수렴 기준을 **탐색 구간에 대한 비율**로 잡는다 (R33).
_RELATIVE_TOL = 1e-6


def _find_flip_threshold(
    metric_fn: Callable[[float], float],
    base: float,
    low: float,
    high: float,
    *,
    tol: float | None = None,
    max_iter: int = 64,
) -> float | None:
    """metric_fn 이 부호를 바꾸는 지점을 이진탐색으로 찾는다.

    base 쪽 부호와 다른 부호가 low 또는 high 쪽에 있어야 탐색 가능하다.
    찾지 못하면 None 을 반환한다.

    tol: 탐색 종료 폭. `None` 이면 **구간 폭의 비율**로 잡는다.

    ## ★ 절대 허용오차 `0.5` 가 기본값이었다 — 인자의 단위를 몰라서 생긴 결함

    종전 기본값은 `tol = 0.5` 였다. 원 단위 단가(구간 폭이 수십만)에서는 잘
    돌지만, **할인율처럼 구간 폭이 0.03 인 인자에서는 첫 줄에서 곧바로
    `hi - lo < tol` 이 성립해 이진탐색이 한 번도 돌지 않는다.** 그때 이 함수는
    실패를 알리지 않고 **구간의 중점을 임계값으로 돌려준다** — 계산과 아무
    관계가 없는 수인데 `flips_conclusion` 은 참이므로, 리포트는 *「할인율이
    3.75% 를 넘으면 사업성이 뒤집힌다」* 를 자신 있게 싣는다.

    R33 에 리포트 조립기를 붙이면서 **보고된 임계값으로 파이프라인을 다시
    돌려 보는 검사**(`tests/report/test_case_report.py`)를 세우자 즉시 잡혔다.
    그 전까지 이 함수를 검증하던 테스트는 구간이 `0~200` 이어서 우연히 이
    결함을 밟지 않았다 — **인자의 크기가 검사 결과를 갈랐고, 아무도 그 크기를
    보고 있지 않았다.**

    허용오차를 구간에 상대적으로 잡으면 단위를 몰라도 된다. `max_iter` 가
    회수를 막으므로 비율을 작게 잡아도 멈추지 않는 일은 없다.
    """
    if tol is None:
        tol = abs(high - low) * _RELATIVE_TOL
    base_positive = metric_fn(base) >= 0.0

    # low~base 구간과 base~high 구간 중 부호 전환이 있는 쪽을 찾는다
    for a, b in ((low, base), (base, high)):
        val_a = metric_fn(a)
        val_b = metric_fn(b)
        a_positive = val_a >= 0.0
        b_positive = val_b >= 0.0
        if a_positive != b_positive:
            # [a, b] 구간에 임계값 존재. base 쪽 부호를 기준으로 이진탐색.
            lo, hi = a, b
            # lo 에서의 부호가 base 와 같으면 임계값은 hi 쪽에, 다르면 lo 쪽에
            lo_same_as_base = (metric_fn(lo) >= 0.0) == base_positive
            for _ in range(max_iter):
                if hi - lo < tol:
                    break
                mid = (lo + hi) / 2.0
                mid_same_as_base = (metric_fn(mid) >= 0.0) == base_positive
                if lo_same_as_base:
                    # lo 쪽이 base 와 같은 부호 → 임계값은 hi 쪽
                    if mid_same_as_base:
                        lo = mid   # mid 도 base 쪽 부호 → 임계값은 더 hi 쪽
                    else:
                        hi = mid   # mid 가 반전 → 임계값은 lo~mid 사이
                # lo 쪽이 base 와 다른 부호 → 임계값은 lo 쪽
                elif mid_same_as_base:
                    hi = mid   # mid 는 base 쪽 → 임계값은 lo~mid 사이
                else:
                    lo = mid   # mid 도 반전 쪽 → 임계값은 더 lo 쪽
            return (lo + hi) / 2.0

    return None  # 범위 내 부호 전환 없음


def rank_influences(
    variables: dict[str, dict[str, Any]],
    metric_fn: Callable[[float], float] | None = None,
) -> list[dict[str, Any]]:
    """인자별 영향도를 민감도 계산으로 측정해 순위를 반환한다.

    Parameters
    ----------
    variables:
        인자 사전. 각 항목은 아래 키를 포함해야 한다.
          - base  : 기준값
          - low   : 합리적 하한 (없으면 base * 0.8)
          - high  : 합리적 상한 (없으면 base * 1.2)
    metric_fn:
        인자 하나의 값을 받아 주 지표(예: NPV, 회수기간)를 반환하는 함수.
        None 이면 항등 함수를 쓴다 (단독 실행 폴백).

    Returns
    -------
    list[dict]:
        영향도 내림차순으로 정렬된 목록. 각 항목:
          - name             : 인자 이름
          - delta            : |metric(high) - metric(low)|  (영향폭)
          - threshold        : 결론이 뒤집히는 임계값 (없으면 float('nan'))
          - flips_conclusion : 합리적 범위 내 부호 전환 여부
          - margin_pct       : base 에서 threshold 까지의 여유 (%)
    """
    if metric_fn is None:
        metric_fn = lambda x: x  # noqa: E731  # 폴백: 항등 함수

    ranked: list[dict[str, Any]] = []

    for name, data in variables.items():
        base: float = float(data["base"])
        low: float = float(data.get("low", base * 0.8))
        high: float = float(data.get("high", base * 1.2))

        metric_low = metric_fn(low)
        metric_high = metric_fn(high)
        delta = abs(metric_high - metric_low)

        threshold_val = _find_flip_threshold(metric_fn, base, low, high)
        flips = threshold_val is not None

        if flips and threshold_val is not None:
            threshold = threshold_val
            margin_pct = abs(base - threshold) / abs(base) * 100.0 if base != 0.0 else math.inf
        else:
            threshold = math.nan
            margin_pct = math.nan

        ranked.append({
            "name": name,
            "delta": delta,
            "threshold": threshold,
            "flips_conclusion": flips,
            "margin_pct": margin_pct,
        })

    ranked.sort(key=lambda x: x["delta"], reverse=True)
    return ranked
