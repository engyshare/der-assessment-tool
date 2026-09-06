"""주 지표·결론 축의 **3중 표기 산식** — `FR-1001-AC2`·`AC3` (R64/WP-2 분리).

## 왜 `case_report.py` 에서 갈랐는가

`NFR-206` 코드 스프롤 상한(500줄)이다. R64/WP-2 가 사용자 요구 2(가구의 추가
전력사용기기 부하)를 배선하며 `core/report/case_report.py` 를 **코드 508/500**
으로 밀었다(`scripts/check_file_size.py --code-strict` 실측, 2026-09-06 —
착수 시점 499). ⛔ **상한을 올려 푸는 것은 금지다**(NFR-206 · spec §16.5 절차).

쪼갤 자리를 **산식 조립**으로 잡은 이유는 그것이 이 모듈 안에서 가장 크고
(코드 99줄) 가장 독립적인 덩어리이기 때문이다 — 이 함수는 인자만 읽고
`CaseReport` 를 모른다. 같은 사유로 이미 갈라진 선례가 셋 있다:
`core/casegrid/pv_allocation.py`(R51/WP-5) · `core/casegrid/ess_build.py`
(R57/WP-5) · `core/casegrid/household_scale.py`(R64/WP-1).

## ⚠ 동작을 바꾸지 않았다

옮긴 것은 `Formula` 자료형과 `build_formulas()`(옛 이름 `_formulas()`) 둘이며
**이름 하나 말고는 한 글자도 고치지 않았다.** 둘 다 `case_report.py` 밖에서
읽는 곳이 없었으므로(저장소 전수 확인) 재수출로 살려 둘 옛 경로가 없다 —
**앞으로 읽을 자리는 이 모듈 하나다.**
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.casegrid.models import CaseBasis
from core.report.case_influences import (
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    MAX_SUBSIDY_RATE,
    break_even_subsidy_rate,
    residual_gap_at_full_support_won,
)


@dataclass(frozen=True)
class Formula:
    """3중 표기 한 건 — 자연어 + 수식 + 대입값 (`FR-1001-AC3`)."""

    label: str
    natural: str
    expression: str
    substituted: str


def build_formulas(
    basis: CaseBasis,
    metrics: Mapping[str, float],
    *,
    subsidy_rate: float,
    total_project_cost_won: float,
) -> tuple[Formula, ...]:
    """주 지표와 결론 축의 3중 표기 (`FR-1001-AC2`·`AC3`).

    ⚠ `I₀` 는 `CaseBasis` 의 총사업비가 아니라 **그 변형이 실제로 낸 초기지출**
    이다. 총사업비를 적으면 지원을 받은 사업의 산식이 지원 전 금액으로 서고,
    검토자가 대입값을 따라가면 리포트의 결론과 다른 수가 나온다.
    """
    payback = metrics[HEADLINE_METRIC]
    payback_text = (
        f"{payback:.2f}년" if payback != float("inf") else "분석기간 내 미회수"
    )
    outlay = int(metrics["initial_outlay_won"])
    flip_rate = break_even_subsidy_rate(
        subsidy_rate=subsidy_rate,
        npv_won=float(metrics[CONCLUSION_METRIC]),
        total_project_cost_won=total_project_cost_won,
    )
    net = basis.annual_benefit_won - basis.annual_cost_won
    # ★ **환산이 지원 상한을 넘으면 붙임 3 이 그것을 함께 진다** (판정 §2).
    # 산식은 **지우지 않는다** — 본문의 그 수가 어디서 왔는지 대입값으로 말하는
    # 자리가 사라지면 검토자가 따라갈 통로가 없어진다(`MC-1` 의 첫 물음).
    # 대신 그 결과가 **답으로 성립하지 않는다**는 것을 대입값 줄이 함께 적고,
    # *「그러면 얼마가 모자라는가」* 는 아래 「전액 지원 시 잔여 결손」 산식이
    # 답한다 — 요구된 수가 **감사 가능해야** 하기 때문이다.
    over_ceiling = flip_rate > MAX_SUBSIDY_RATE
    residual = residual_gap_at_full_support_won(
        subsidy_rate=subsidy_rate,
        npv_won=float(metrics[CONCLUSION_METRIC]),
        total_project_cost_won=total_project_cost_won,
    )
    ceiling_note = (
        f" — ⚠ 지원 상한 {MAX_SUBSIDY_RATE:.0%}(사업비 전액)를 넘어 "
        "지원율로는 답이 성립하지 않는다"
        if over_ceiling
        else ""
    )
    formulas = (
        Formula(
            label="연 순현금흐름",
            natural="연 순현금흐름 = 연 편익 - 연 운영비",
            expression="CF = B - C",
            substituted=(
                f"{net:,}원 = {basis.annual_benefit_won:,}원 "
                f"- {basis.annual_cost_won:,}원"
            ),
        ),
        Formula(
            label="순현재가치",
            natural=(
                "순현재가치 = 분석기간 동안의 순현금흐름을 할인해 더한 뒤 "
                "초기투자를 뺀 값"
            ),
            expression="NPV = Σ(t=1..T) CF_t / (1+r)^t - I₀",
            substituted=(
                f"{metrics[CONCLUSION_METRIC]:,.0f}원 = Σ(t=1..{basis.horizon_years}) "
                f"CF_t / (1+{basis.discount_rate:.3f})^t - {outlay:,}원"
            ),
        ),
        Formula(
            label="할인 회수기간",
            natural=(
                "할인 회수기간 = 누적 할인 현금흐름이 초기투자에 도달하는 시점. "
                "분석기간 안에 도달하지 못하면 「미회수」"
            ),
            expression="min{ T' : Σ(t=1..T') CF_t / (1+r)^t ≥ I₀ }",
            substituted=(
                f"{payback_text} — I₀ = {outlay:,}원 · "
                f"r = {basis.discount_rate:.1%} · T = {basis.horizon_years}년"
            ),
        ),
        # ★ **본문 5.1 의 「전환 지원율」이 여기서 감사된다.** 본문은 환산값만
        # 싣고, 그 값이 어디서 왔는지는 이 산식이 대입값으로 말한다 — 붙임 없이
        # 본문에만 두면 검토자가 52.6% 를 따라갈 자리가 없다(`MC-1` 의 첫 물음).
        Formula(
            label="결론 전환 지원율",
            natural=(
                "결론 전환 지원율 = 현 지원율 - 순현재가치 ÷ 총사업비. "
                "지원은 t=0 초기지출 감액이고 순현재가치 산식은 초기투자를 "
                "할인하지 않으므로, 지원 1원이 결론 축을 정확히 1원 올린다"
            ),
            expression="s* = s - NPV / I_total",
            substituted=(
                f"{flip_rate:.1%} = {subsidy_rate:.1%} - "
                f"({metrics[CONCLUSION_METRIC]:,.0f}원) "
                f"÷ {total_project_cost_won:,.0f}원{ceiling_note}"
            ),
        ),
    )
    if not over_ceiling:
        return formulas
    # RUF001: 「×」는 검토자가 읽는 **산식 문면**이다. `x` 로 바꾸면 곱셈이
    # 변수 이름처럼 읽힌다 — `core/casegrid/operating_lines.py` 가 같은 자리에
    # 같은 판정을 적어 두었다.
    return (
        *formulas,
        Formula(
            label="전액 지원 시 잔여 결손",
            natural=(
                "전액 지원 시 잔여 결손 = 순현재가치 + (지원 상한 - 현 지원율) "
                "× 총사업비. 지원은 t=0 초기지출 감액이므로 지원율을 상한"  # noqa: RUF001
                f"({MAX_SUBSIDY_RATE:.0%})까지 올려도 결론 축은 남은 지원분"
                "만큼만 오르고, 그 위로는 올릴 곳이 없다"
            ),
            expression="R = NPV + (1 - s) × I_total",  # noqa: RUF001
            substituted=(
                f"{residual:,.0f}원 = {metrics[CONCLUSION_METRIC]:,.0f}원 + "
                f"({MAX_SUBSIDY_RATE:.1%} - {subsidy_rate:.1%}) "
                f"× {total_project_cost_won:,.0f}원"  # noqa: RUF001
            ),
        ),
    )
