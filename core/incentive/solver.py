from collections.abc import Callable, Sequence
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

    # 최대 지원으로도 달성 불가한 경우 (FR-608-AC4 — 「해가 없으면 그 사실과
    # 부족분을 명시」). ⚠ 이 주석은 R26 까지 `FR-608-AC5` 라 적고 있었고, AC5 는
    # 「역산 대상 변수를 보조율 외로도 지정 가능」이라 여기와 무관하다. 같은
    # 오기가 테스트 마커 둘에도 있었다.
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


class Goal(NamedTuple):
    """역산 목표 하나 (`FR-608-AC1`).

    `evaluate` 는 보조율(0~1)을 받아 **그 목표가 보는 지표**를 돌려준다 —
    목표마다 지표가 다르므로(NPV·IRR·회수기간) 평가 함수도 목표마다 따로다.
    `label` 은 어느 목표가 구속했는지를 사람에게 말해 주기 위한 것이다.
    """

    evaluate: Callable[[float], float]
    target_value: float
    target_type: Literal["NPV", "IRR", "PAYBACK"]
    label: str = ""


class MultiGoalResult(NamedTuple):
    """복수 목표 역산 결과 (`FR-608-AC1` 후반부).

    `binding_label` 은 **어느 목표가 답을 결정했는가**다. 이것이 없으면
    사용자는 지원율을 낮추려 할 때 어느 조건을 완화해야 하는지 알 수 없고,
    답만 보고 「전부 조금씩 완화」하게 된다.
    """

    success: bool
    subsidy_rate: float
    binding_label: str | None = None
    shortfall: float | None = None
    reason: str | None = None


def solve_min_subsidy_rate_for_goals(
    goals: Sequence[Goal],
    precision: float = 0.001,
) -> MultiGoalResult:
    """`FR-608-AC1`: 목표 **복수** — 전부 만족하는 최소 지원율.

    조항 문면은 *「"할인 회수기간 ≤ 10년" / "NPV ≥ 0" / "IRR ≥ 5%" 중 **택일
    또는 복수**」* 다. R26 까지 「택일」만 있었고 **복수는 자료형 자체가
    없었다** — `solve_min_subsidy_rate` 의 시그니처가 스칼라 목표 하나다.

    답은 **각 목표의 최소 해 중 최댓값**이다. 목표가 단조라면 그 지원율에서
    모든 목표가 이미 충족되기 때문이다. 하나라도 100%로 달성 불가하면 전체가
    실패이며, **그 목표를 이름으로 지목한다** — 「어딘가 안 된다」로는 무엇을
    고쳐야 할지 알 수 없다.

    **비단조 목표가 섞여도 성립한다** — 각 목표는 `solve_min_subsidy_rate` 를
    그대로 지나므로 AC3 의 격자 스캔 갈래를 각자 탄다.
    """
    if not goals:
        raise ValueError(
            "목표가 하나도 없습니다 — 역산할 대상이 없습니다 (FR-608-AC1)"
        )

    best_rate = 0.0
    binding: str | None = None
    for goal in goals:
        result = solve_min_subsidy_rate(
            goal.evaluate, goal.target_value, goal.target_type, precision
        )
        if not result.success:
            return MultiGoalResult(
                success=False,
                subsidy_rate=1.0,
                binding_label=goal.label or goal.target_type,
                shortfall=result.shortfall,
                reason=(
                    f"최대 지원(100%)으로도 목표 미달 — "
                    f"{goal.label or goal.target_type}"
                ),
            )
        if result.subsidy_rate > best_rate:
            best_rate = result.subsidy_rate
            binding = goal.label or goal.target_type

    return MultiGoalResult(
        success=True, subsidy_rate=best_rate, binding_label=binding
    )


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
