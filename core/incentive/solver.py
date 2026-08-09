from collections.abc import Callable
from typing import Literal, NamedTuple


class SolverResult(NamedTuple):
    success: bool
    subsidy_rate: float
    shortfall: float | None = None
    reason: str | None = None


def solve_min_subsidy_rate(  # noqa: PLR0912
    evaluate_func: Callable[[float], float],
    target_value: float,
    target_type: Literal["NPV", "IRR", "PAYBACK"],
    precision: float = 0.001,  # 0.1%p = 0.001
) -> SolverResult:
    """FR-608: 최소 지원 수준 역산 (Goal Seek)."""

    # 1. 양끝점 평가
    val_0 = evaluate_func(0.0)
    val_100 = evaluate_func(1.0)

    def is_met(val: float) -> bool:
        if target_type in ("NPV", "IRR"):
            return val >= target_value
        else:
            return val <= target_value

    # 지원 없이도 이미 달성한 경우
    if is_met(val_0):
        return SolverResult(success=True, subsidy_rate=0.0)

    # 최대 지원으로도 달성 불가한 경우 (FR-608-AC5)
    if not is_met(val_100):
        shortfall = (
            target_value - val_100 if target_type in ("NPV", "IRR") else val_100 - target_value
        )
        return SolverResult(
            success=False,
            subsidy_rate=1.0,
            shortfall=shortfall,
            reason="최대 지원(100%)으로도 목표 미달",
        )

    # 2. 단조성 검사 (FR-608-AC3)
    # 10개의 구간(10%) 단위로 추세가 꺾이는지 확인
    grid_points = [i / 10.0 for i in range(11)]
    vals = [evaluate_func(p) for p in grid_points]

    is_monotonic = True
    for i in range(len(vals) - 1):
        if target_type in ("NPV", "IRR"):
            if vals[i] > vals[i + 1] + 1e-6:  # 약간의 부동소수점 오차 허용
                is_monotonic = False
                break
        elif vals[i] < vals[i + 1] - 1e-6:
            is_monotonic = False
            break

    # 3. 탐색 수행
    if is_monotonic:
        # 이분 탐색 (FR-608-AC2)
        low, high = 0.0, 1.0
        while (high - low) > precision:
            mid = (low + high) / 2
            val_mid = evaluate_func(mid)
            if is_met(val_mid):
                high = mid
            else:
                low = mid
        return SolverResult(success=True, subsidy_rate=high)
    else:
        # 비단조 구간이 있는 경우 안전한 격자 스캔 후 세밀 탐색
        best_rate = 1.0
        steps = int(1.0 / precision)
        for i in range(1, steps + 1):
            rate = i * precision
            if is_met(evaluate_func(rate)):
                best_rate = rate
                break
        return SolverResult(success=True, subsidy_rate=best_rate)


class IsoSupportPoint(NamedTuple):
    """FR-609-AC1, AC2, AC3: 등가 지원 조합 상의 한 지점."""

    subsidy_rate: float
    loan_rate: float
    loan_interest: float
    owner_metric: float
    gov_fiscal_pv: float
    is_minimum_fiscal_burden: bool = False


class IsoSupportCurveResult(NamedTuple):
    """FR-609-AC1, AC2: 등가 지원 조합 곡선 산출 결과."""

    points: list[IsoSupportPoint]
    min_fiscal_point: IsoSupportPoint | None


def generate_iso_support_curve(
    evaluate_func: Callable[[float, float, float], tuple[float, float]],
    target_value: float,
    target_type: Literal["NPV", "IRR", "PAYBACK"],
    loan_candidates: list[tuple[float, float]],
    precision: float = 0.001,
) -> IsoSupportCurveResult:
    """FR-609-AC1, AC2, AC3: 등가 지원 조합(iso-support curve) 산출.

    보조율 × 융자조건 2차원 평면에서 목표 지표를 동일하게 달성하는 조합 곡선을 산출하고,
    정부 재정 부담 현가를 병기하여 최소 부담 조합을 구한다.
    evaluate_func(subsidy_rate, loan_rate, loan_interest) -> (owner_metric, gov_fiscal_pv)
    """
    raw_points: list[dict[str, float]] = []
    min_fiscal: float = float("inf")
    min_idx: int | None = None

    for loan_rate, loan_interest in loan_candidates:

        def eval_sub(s: float, lr: float = loan_rate, li: float = loan_interest) -> float:
            return evaluate_func(s, lr, li)[0]

        res = solve_min_subsidy_rate(eval_sub, target_value, target_type, precision)
        if res.success:
            s_rate = res.subsidy_rate
            owner_val, gov_pv = evaluate_func(s_rate, loan_rate, loan_interest)
            raw_points.append(
                {
                    "subsidy_rate": s_rate,
                    "loan_rate": loan_rate,
                    "loan_interest": loan_interest,
                    "owner_metric": owner_val,
                    "gov_fiscal_pv": gov_pv,
                }
            )
            if gov_pv < min_fiscal:
                min_fiscal = gov_pv
                min_idx = len(raw_points) - 1

    points: list[IsoSupportPoint] = []
    min_point: IsoSupportPoint | None = None
    for i, pt in enumerate(raw_points):
        is_min = i == min_idx
        iso_pt = IsoSupportPoint(
            subsidy_rate=pt["subsidy_rate"],
            loan_rate=pt["loan_rate"],
            loan_interest=pt["loan_interest"],
            owner_metric=pt["owner_metric"],
            gov_fiscal_pv=pt["gov_fiscal_pv"],
            is_minimum_fiscal_burden=is_min,
        )
        points.append(iso_pt)
        if is_min:
            min_point = iso_pt

    return IsoSupportCurveResult(points=points, min_fiscal_point=min_point)
