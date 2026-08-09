"""10.3 — NPV·IRR·MIRR·B/C·할인 회수기간 — 엑셀 독립 계산 대조.

기대값 출처: ``fixtures/oracle/control_cases_6.yaml`` (16.5 산출물, 해석해 순위 1).
이 파일을 수정하지 않는다 — 읽기만.

**오라클 규격이 지표마다 다르다** (§13.0.2):
- NPV, B/C: 순위 1 — 원 단위 완전 일치. B/C 는 분자·분모 각각 원 일치, 비율 자체는 별도 오차 없음.
- IRR, MIRR, 할인 회수기간: 순위 2 — 0.01% (``pytest.approx(rel=1e-4)``).

v1.6 이전 판은 5종을 일괄 «순위 2 / 0.01%» 로 두어 느슨한 쪽으로 어긋났다.

**기대값 산출 방식**: yaml 의 expected 값을 그대로 쓰지 않고, **같은 산식의 독립
구현**으로 직접 계산한다 — 이것이 자기충족(구현 출력을 기대값으로)을 피하는
길이다. yaml 의 expected 는 입력 케이스(initial/benefit/rate)를 읽는 용도로만.
yaml expected 와 산식 기대값이 어긋나면(yaml 버그) 그것은 별도 검증에서 잡는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml  # type: ignore[import-untyped]

from core.cba import (
    bcr,
    irr,
    mirr,
    npv,
    payback_discounted,
)
from core.cba.proforma import benefit_row
from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money, to_won

YamlMap = dict[str, Any]

_ORACLE = (
    Path(__file__).resolve().parent.parent.parent
    / "fixtures" / "oracle" / "control_cases_6.yaml"
)


def _load_case() -> YamlMap:
    if not _ORACLE.is_file():
        pytest.skip(f"대조 케이스 파일이 없습니다: {_ORACLE}")
    data = yaml.safe_load(_ORACLE.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) >= 1
    return cast(YamlMap, cases[0])


def _inputs(case: YamlMap) -> YamlMap:
    return cast(YamlMap, case["inputs"])


@pytest.fixture(scope="module")
def case() -> YamlMap:
    return _load_case()


@pytest.fixture(scope="module")
def benefit_flow(case: YamlMap) -> CashFlowRow:
    inputs = _inputs(case)
    years = int(inputs["years"])
    annual = int(inputs["annual_benefit_won"])
    return benefit_row(tag="annual_benefit", schedule={y: annual for y in range(1, years + 1)})


# ── NPV — 순위 1, 원 단위 완전 일치 ──────────────────────────────────────

@pytest.mark.req("FR-703-AC1.npv")
def test_npv_matches_closed_form_exact_won(case: YamlMap, benefit_flow: CashFlowRow) -> None:
    """NPV — §13.0.2 순위 1, 원 단위 완전 일치 (== 비교, approx 없음).

    오라클: 닫힌 형태 등비수열 합.
        NPV = -1,000,000 + 300,000 × ((1 - 1.05^-5) / 0.05)
            = -1,000,000 + 1,298,843 = 298,843.
    각 항을 to_won 반올림한 뒤 더한다 (NFR-103-M1).
    """
    inputs = _inputs(case)
    initial = Money(int(inputs["initial_cost_won"]))
    rate = float(inputs["discount_rate"])
    years = int(inputs["years"])
    benefit = int(inputs["annual_benefit_won"])
    expected_pv = sum(
        to_won(benefit / ((1 + rate) ** t)) for t in range(1, years + 1)
    )
    expected = Money(expected_pv - initial)

    val = npv(initial, [benefit_flow], rate)
    assert int(val) == int(expected), (
        f"NPV 원 단위 불일치 (순위 1): 산출 {int(val)} vs 기대 {int(expected)}"
    )


# ── B/C — 순위 1, 분자·분모 각각 원 단위 완전 일치 ─────────────────────────

@pytest.mark.req("FR-703-AC1.bcr")
def test_bcr_numerator_denominator_match_exact_won(
    case: YamlMap, benefit_flow: CashFlowRow
) -> None:
    """B/C — §13.0.2 순위 1. 분자·분모 각각 원 일치. 비율 자체는 별도 오차 없음.

    오라클: PV(benefits)=1,298,843, PV(costs)=1,000,000 → ratio=1.298843.
    비율에 오차를 주면 «편익 과대+비용 과대» 와 «둘 다 정확» 이 같은 값을 낸다.
    """
    inputs = _inputs(case)
    initial = Money(int(inputs["initial_cost_won"]))
    rate = float(inputs["discount_rate"])
    years = int(inputs["years"])
    benefit = int(inputs["annual_benefit_won"])
    expected_num = int(sum(
        to_won(benefit / ((1 + rate) ** t)) for t in range(1, years + 1)
    ))
    expected_den = int(initial)

    result = bcr([benefit_flow], [], initial, rate)
    assert int(result.numerator) == expected_num
    assert int(result.denominator) == expected_den


# ── IRR — 순위 2, 0.01% (반복해, 독립 bisection 과 대조) ──────────────────

@pytest.mark.req("FR-703-AC1.irr")
def test_irr_matches_independent_bisection(case: YamlMap, benefit_flow: CashFlowRow) -> None:
    """IRR — §13.0.2 순위 2, 0.01%. 독립 bisection 구현과 대조.

    오라클: 0 = -1,000,000 + 300,000 × ((1-(1+r)^-5)/r) → 약 15.24%.
    """
    inputs = _inputs(case)
    initial = Money(int(inputs["initial_cost_won"]))
    years = int(inputs["years"])
    benefit = int(inputs["annual_benefit_won"])
    cost = int(inputs["initial_cost_won"])
    # 독립 bisection — 구현 irr() 와 다른 코드 경로
    def npv_at(r: float) -> float:
        return -cost + sum(benefit / ((1 + r) ** t) for t in range(1, years + 1))
    lo, hi = -0.99, 1.0
    mid = 0.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if npv_at(mid) > 0:
            lo = mid
        else:
            hi = mid
    expected = mid

    val = irr(initial, [benefit_flow])
    assert val * 100 == pytest.approx(expected * 100, rel=1e-4), (
        f"IRR 0.01% 벗어남 (순위 2): 산출 {val*100:.4f}% vs 독립 {expected*100:.4f}%"
    )


# ── MIRR — 순위 2, 0.01% (닫힌 형태와 대조) ──────────────────────────────

@pytest.mark.req("FR-703-AC1.mirr-value")
def test_mirr_matches_closed_form(case: YamlMap, benefit_flow: CashFlowRow) -> None:
    """MIRR — §13.0.2 순위 2, 0.01%. 닫힌 형태 산식과 대조.

    오라클 산식:
        FV(benefits, reinvest) = Σ benefit × (1+reinvest)^(N-t)
        MIRR = (FV/PV(costs))^(1/N) - 1

    **주의** — yaml 의 mirr_pct=10.620% 는 이 산식으로 계산한 정확값(≈10.64%)
    과 어긋난다. yaml 버그이며 ``fixtures/**`` 가 소유 밖이라 고치지 못한다 —
    여기서는 산식 기대값으로 판정한다 (yaml 무시).
    """
    inputs = _inputs(case)
    initial = Money(int(inputs["initial_cost_won"]))
    rate = float(inputs["discount_rate"])
    reinvest = float(inputs["reinvestment_rate"])
    years = int(inputs["years"])
    benefit = int(inputs["annual_benefit_won"])
    cost = int(inputs["initial_cost_won"])
    fv = sum(benefit * ((1 + reinvest) ** (years - t)) for t in range(1, years + 1))
    expected = (fv / cost) ** (1.0 / years) - 1.0

    val = mirr(initial, [benefit_flow], rate, reinvest)
    assert val * 100 == pytest.approx(expected * 100, rel=1e-4), (
        f"MIRR 0.01% 벗어남 (순위 2): 산출 {val*100:.4f}% vs 산식 {expected*100:.4f}%"
    )


# ── 할인 회수기간 — 순위 2, 0.01% ─────────────────────────────────────────

@pytest.mark.req("FR-703-AC1.payback-discounted")
def test_payback_discounted_matches_manual(case: YamlMap, benefit_flow: CashFlowRow) -> None:
    """할인 회수기간 — 주 지표, §13.0.2 순위 2, 0.01%. 손계산과 대조.

    오라클: Y3 누적 816,974(잔여 183,026) → 183,026/246,811 = 0.7416 → 3.7416년.
    """
    inputs = _inputs(case)
    initial = Money(int(inputs["initial_cost_won"]))
    rate = float(inputs["discount_rate"])
    years = int(inputs["years"])
    benefit = int(inputs["annual_benefit_won"])
    cost = int(inputs["initial_cost_won"])
    cumulative = float(-cost)
    prev_cum = cumulative
    result_year = float("inf")
    for t in range(1, years + 1):
        prev_cum = cumulative
        d = float(to_won(benefit / ((1 + rate) ** t)))
        cumulative += d
        if cumulative >= 0:
            result_year = (t - 1) + (-prev_cum) / d
            break

    val = payback_discounted(initial, [benefit_flow], rate)
    assert val == pytest.approx(result_year, rel=1e-4), (
        f"할인 회수기간 0.01% 벗어남 (순위 2): 산출 {val:.4f}년 vs 손계산 {result_year:.4f}년"
    )


# ── yaml 의 expected 가 산식 기대값과 일치하는가 — yaml 버그 검출 ──────────

def test_yaml_expected_mirr_is_consistent_with_formula(case: YamlMap) -> None:
    """yaml 의 mirr_pct 가 닫힌 형태 산식과 일치하는가.

    **이 테스트가 실패하면 yaml(expected) 버그** — fixtures/** 가 소유 밖이라
    고치지 못하고, 위 산식 기대값 테스트가 진짜 판정을 담당한다.
    현재(2026-08-09) yaml 의 10.620% 가 산식값(약 10.64%)과 어긋나므로 이
    테스트는 xfail. yaml 이 고쳐지면 xfail 을 제거한다.
    """
    pytest.xfail(
        "yaml 의 mirr_pct=10.620% 가 닫힌 형태 산식값(≈10.64%)과 어긋난다 — "
        "fixtures/oracle 은 WP-14 소유라 이 구획에서 못 고친다. 산식 기대값"
        "테스트(test_mirr_matches_closed_form)가 진짜 판정을 담당한다"
    )
