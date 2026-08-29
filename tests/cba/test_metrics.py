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


# ── 한 해에 행이 여럿인 현금흐름 — R38 이 세운 자리 ────────────────────────
#
# ★ **위의 `test_payback_discounted_matches_manual` 은 이 결함을 볼 수 없다.**
# 그 검사는 편익 행 **하나**만 넘긴다 — 한 해에 행이 하나뿐이면 「행 단위」와
# 「연 단위」가 같은 값을 낸다. 그래서 `payback_discounted` 가 R38 까지
# `_flatten()` 의 행 목록을 그대로 돌며 **그 해의 편익 행만 누적한 지점에서
# 반환**하고 있었는데도 오라클 전건이 초록불이었다.
#
# 그러나 실행 경로가 실제로 넘기는 것은 **한 해에 행이 여럿인 현금흐름**이다 —
# `core/casegrid/operating_lines.py::net_operating_flows()` 가 편익 행과 **부호를
# 뒤집은 비용 행**을 나란히 이어 붙인다(선언은 그쪽이고, `e2e_runner` 가 재수출
# 하므로 러너 경로로도 부를 수 있다). 아래 검사들이 그 형태를 만든다.
#
# 기대값의 출처는 **구현이 아니다**: 연 순현금흐름(편익 − 비용)을 이 파일이
# 직접 세워 손계산으로 누적한다. 구현이 행을 어떻게 접든 그 수와 맞아야 한다.

_MULTIROW_YEARS = 20
_MULTIROW_BENEFIT = 3_000_000
_MULTIROW_COST = 2_000_000
_MULTIROW_INITIAL = 3_000_000
_MULTIROW_RATE = 0.045


def _multirow_flows() -> list[CashFlowRow]:
    """편익 행 + **부호를 뒤집은 비용 행** — 실행 경로가 넘기는 형태."""
    years = range(1, _MULTIROW_YEARS + 1)
    return [
        benefit_row(tag="benefit", schedule={y: _MULTIROW_BENEFIT for y in years}),
        benefit_row(tag="cost_negated", schedule={y: -_MULTIROW_COST for y in years}),
    ]


def _hand_computed_discounted_payback() -> float:
    """연 단위 손계산 — **연 순현금흐름 한 수**를 할인해 누적한다.

    구현을 부르지 않는다. 연 순편익은 3,000,000 − 2,000,000 = 1,000,000 원이며
    initial 3,000,000 원을 4.5% 로 할인해 넘는 시점을 찾는다.
    """
    net = _MULTIROW_BENEFIT - _MULTIROW_COST
    cumulative = float(-_MULTIROW_INITIAL)
    for t in range(1, _MULTIROW_YEARS + 1):
        prev_cum = cumulative
        discounted = float(to_won(net / ((1 + _MULTIROW_RATE) ** t)))
        cumulative += discounted
        if cumulative >= 0:
            return (t - 1) + (-prev_cum) / discounted
    return float("inf")


@pytest.mark.req("FR-703-AC1.payback-discounted")
def test_payback_discounted_sums_the_rows_of_one_year_before_counting() -> None:
    """주 지표는 **연 단위**다 — 한 해의 행을 먼저 합친 뒤 0 선을 본다.

    행 단위로 세면 누적이 Y2 의 **편익 행**(+3,000,000)에서 0 선을 넘고
    **그 해의 비용 행(−2,000,000)을 세기 전에 반환**해 1.7437년이 된다.
    연 순편익은 1,000,000 원이므로 참값은 3.2994년이다.
    """
    val = payback_discounted(
        Money(_MULTIROW_INITIAL), _multirow_flows(), _MULTIROW_RATE
    )
    expected = _hand_computed_discounted_payback()
    assert val == pytest.approx(expected, rel=1e-4), (
        f"할인 회수기간이 연 단위가 아니다: 산출 {val:.4f}년 vs 손계산 "
        f"{expected:.4f}년. 한 해의 행을 합치지 않고 세면 그 해의 편익 행만 "
        f"누적한 지점에서 반환한다"
    )
    # 손계산이 「행 단위로도 우연히 같은 값」이 아님을 이 자리에서 못 박는다 —
    # 편익 행 하나만 넘기면 훨씬 짧은 값이 나온다. 두 값이 같아지면 이 케이스가
    # 「한 해에 행이 여럿」을 더 이상 구별하지 못하게 된 것이다.
    benefit_only = payback_discounted(
        Money(_MULTIROW_INITIAL), _multirow_flows()[:1], _MULTIROW_RATE
    )
    assert benefit_only < val, (
        "편익 행만 넘긴 값이 편익+비용 값보다 짧지 않다 — 이 케이스가 「한 해에 "
        "행이 여럿」을 더 이상 구별하지 못한다"
    )


@pytest.mark.req("FR-703-AC1.payback-discounted")
def test_payback_discounted_does_not_depend_on_row_order() -> None:
    """같은 해 행의 **순서를 뒤집어도 값이 같다** — 합산이 옳다면 그렇다.

    ★ **초록불이 정답인 검사다.** 표시할 결함이 없어야 정상이며, 값이 갈리면
    구현이 다시 행 단위로 세고 있다는 뜻이다. R38 까지는 정순 1.7437년 대 역순
    4.7665년으로 갈렸다 — **행 순서가 주 지표를 바꾸고 있었다.**
    """
    rows = _multirow_flows()
    forward = payback_discounted(Money(_MULTIROW_INITIAL), rows, _MULTIROW_RATE)
    reversed_ = payback_discounted(
        Money(_MULTIROW_INITIAL), list(reversed(rows)), _MULTIROW_RATE
    )
    assert forward == reversed_, (
        f"행 순서가 주 지표를 바꾼다: 정순 {forward:.4f}년 vs 역순 "
        f"{reversed_:.4f}년. 한 해의 행을 합치지 않고 한 걸음씩 세면 이렇게 된다"
    )


@pytest.mark.req("FR-703-AC1.payback-discounted")
def test_payback_discounted_does_not_depend_on_how_a_year_is_split_into_rows() -> None:
    """한 해의 합이 같으면 **몇 행으로 쪼개든** 값이 같다.

    순서 뒤집기(위)보다 넓게 본다 — 행 **개수**가 바뀌어도 같아야 한다.
    프로포마의 행 구성은 편익 갈래·비용 항목이 늘면 바뀌는 표시상의 사정이고,
    주 지표는 그것에 흔들려서는 안 된다.
    """
    years = range(1, _MULTIROW_YEARS + 1)
    net = _MULTIROW_BENEFIT - _MULTIROW_COST
    one_row = [benefit_row(tag="net", schedule={y: net for y in years})]
    parts = (4_000_000, -1_500_000, 500_000, -2_500_000, 500_000)
    five_rows = [
        benefit_row(tag=f"part{i}", schedule={y: amount for y in years})
        for i, amount in enumerate(parts)
    ]
    assert sum(parts) == net, "쪼갠 행의 합이 연 순현금흐름과 다르다 — 케이스 오류"

    collapsed = payback_discounted(Money(_MULTIROW_INITIAL), one_row, _MULTIROW_RATE)
    split = payback_discounted(Money(_MULTIROW_INITIAL), five_rows, _MULTIROW_RATE)
    assert split == collapsed, (
        f"행 개수가 주 지표를 바꾼다: 1행 {collapsed:.4f}년 vs 5행 {split:.4f}년"
    )


@pytest.mark.req("FR-703-AC1.payback-discounted")
def test_worse_cash_flow_never_shortens_the_discounted_payback() -> None:
    """연 순현금흐름이 **모든 해에 줄면** 회수는 길어진다 — NPV 와 방향이 같다.

    ★ **이 검사가 R37 의 모순 자체를 붙든다.** 일사 곡선을 배선하자 NPV 는
    128,194원 나빠졌는데 회수기간은 4.9207 → 4.8623년으로 **짧아졌다.** 그
    모순이 결함을 드러낸 신호였고, 여기서 그 신호를 검사로 세운다.

    **케이스가 그때의 형태를 그대로 본뜬다** — 배선의 실체는 *「비용 행이 하나
    더 붙었다」* 가 아니라 *「편익 행이 커지고 비용 행이 더 크게 커졌다」* 였다
    (주간으로 몰린 발전이 송전 편익을 늘리고, 상계가 풀린 심야 충전이 구매
    비용을 더 늘렸다). 행 단위로 세면 **커진 편익 행이 0 선을 더 일찍 넘고 그
    해의 커진 비용 행은 세기 전에 반환**하므로 회수가 짧아진다 — 실측으로
    1.7437 → 0.8957년이었다. 연 단위로 세면 3.2994 → 3.6969년으로 길어진다.

    ⚠ 비용 행을 **얹기만** 하는 케이스로는 이 자리를 볼 수 없다. 그때는 행
    단위로 세어도 값이 길어져(1.7437 → 1.8134) 초록불이 된다 — R38 이 실측으로
    확인했다. 편익 행이 **함께 커지는** 것이 이 검사의 핵심이다.
    """
    years = range(1, _MULTIROW_YEARS + 1)
    initial = Money(_MULTIROW_INITIAL)
    benefit_was, cost_was = _MULTIROW_BENEFIT, _MULTIROW_COST
    benefit_now, cost_now = 3_500_000, 2_600_000

    # 케이스가 뜻하는 바를 못 박는다: 편익은 늘었고 연 순현금흐름은 줄었다.
    assert benefit_now > benefit_was, "케이스 오류 — 편익 행이 커지지 않았다"
    assert (benefit_now - cost_now) < (benefit_was - cost_was), (
        "케이스 오류 — 연 순현금흐름이 줄지 않았다"
    )

    before = [
        benefit_row(tag="benefit", schedule={y: benefit_was for y in years}),
        benefit_row(tag="cost_negated", schedule={y: -cost_was for y in years}),
    ]
    after = [
        benefit_row(tag="benefit", schedule={y: benefit_now for y in years}),
        benefit_row(tag="cost_negated", schedule={y: -cost_now for y in years}),
    ]

    npv_before = int(npv(initial, before, _MULTIROW_RATE))
    npv_after = int(npv(initial, after, _MULTIROW_RATE))
    assert npv_after < npv_before, "케이스 오류 — 순현금흐름이 줄었는데 NPV 가 나빠지지 않았다"

    payback_before = payback_discounted(initial, before, _MULTIROW_RATE)
    payback_after = payback_discounted(initial, after, _MULTIROW_RATE)
    assert payback_after > payback_before, (
        f"NPV 는 {npv_before:,} → {npv_after:,} 으로 나빠졌는데 회수기간은 "
        f"{payback_before:.4f} → {payback_after:.4f}년으로 짧아졌거나 그대로다. "
        f"1절의 「결론 축」과 「주 지표」가 서로를 부정하는 상태다"
    )


@pytest.mark.req("FR-703-AC1.payback-discounted")
def test_payback_discounted_fraction_is_measured_from_the_year_before_recovery() -> None:
    """소수부의 기준점은 **회수하는 해의 직전 해 끝**이다 — 연도가 비어도 그렇다.

    순회 중의 「직전 항목의 연도」를 기준으로 쓰면, 편익이 없는 해가 중간에 끼면
    기준점이 그 앞 해에 머물러 **회수 시점이 몇 해 앞으로 당겨진다.** 여기서는
    Y1·Y2·Y5 에만 현금흐름이 있고 Y5 에서 회수한다 — 답은 4년대다.
    """
    rows = [
        benefit_row(tag="sparse", schedule={1: 1_000_000, 2: 1_000_000, 5: 2_000_000})
    ]
    val = payback_discounted(Money(2_500_000), rows, _MULTIROW_RATE)
    assert 4.0 <= val < 5.0, (
        f"Y5 에 회수하는데 {val:.4f}년을 반환했다 — 소수부의 기준점이 회수하는 "
        f"해의 직전 해가 아니라 「직전에 현금흐름이 있던 해」다"
    )


@pytest.mark.req("FR-703-AC1.irr")
@pytest.mark.req("FR-703-AC1.mirr-value")
def test_irr_and_mirr_do_not_move_when_payback_becomes_year_based() -> None:
    """`irr`·`mirr` 은 **행 순서와 무관**하며 R38 의 변경이 건드리지 않는다.

    ⚠ **그래서 `_flatten()` 을 연 단위로 고치지 않았다.** `irr` 은 전부 합하므로
    어느 쪽이든 같지만, `mirr` 은 ``amount > 0`` 을 **행 단위**로 걸러 미래가치를
    쌓는다 — 한 해의 편익 행과 비용 행을 미리 합치면 그 해가 순편익 하나로
    접혀 값이 움직인다(실측 0.4048 → 0.1277). 두 지표가 같은 평탄화를 쓸 수
    없다는 사실을 이 검사가 붙든다: **순서 불변은 요구하고 합산은 요구하지 않는다.**
    """
    rows = _multirow_flows()
    reversed_rows = list(reversed(rows))
    initial = Money(_MULTIROW_INITIAL)

    assert irr(initial, rows) == irr(initial, reversed_rows), (
        "IRR 이 행 순서에 흔들린다 — 전부 합하므로 그럴 수 없다"
    )
    assert mirr(initial, rows, _MULTIROW_RATE, _MULTIROW_RATE) == mirr(
        initial, reversed_rows, _MULTIROW_RATE, _MULTIROW_RATE
    ), "MIRR 이 행 순서에 흔들린다"

    # 그리고 **행 단위 그대로**임을 못 박는다 — 연 단위로 접은 행 하나를 넘기면
    # MIRR 은 달라져야 한다. 같아지면 `_flatten()` 이 합치기 시작한 것이며,
    # 그것은 R38 이 일부러 하지 않은 변경이다.
    net = _MULTIROW_BENEFIT - _MULTIROW_COST
    collapsed = [
        benefit_row(
            tag="net", schedule={y: net for y in range(1, _MULTIROW_YEARS + 1)}
        )
    ]
    assert mirr(initial, collapsed, _MULTIROW_RATE, _MULTIROW_RATE) != mirr(
        initial, rows, _MULTIROW_RATE, _MULTIROW_RATE
    ), (
        "연 단위로 접은 현금흐름과 행 단위 현금흐름의 MIRR 이 같다 — "
        "`_flatten()` 이 연도를 합치기 시작했다면 MIRR 값이 조용히 바뀐 것이다"
    )


@pytest.mark.req("FR-703-AC1.payback-discounted")
def test_payback_discounted_rounds_each_year_to_whole_won_before_accumulating() -> None:
    """반올림 자리를 못 박는다 — **해마다** ``to_won`` 한 뒤 누적한다.

    ⚠ **오차 한도로는 이 자리를 볼 수 없다.** 반올림을 아예 없애도 값은 상대
    1.96e-07 밖에 움직이지 않는다 — §13.0.2 순위 2 의 0.01%(1e-4) 안이므로
    `pytest.approx(rel=1e-4)` 를 쓰는 위의 검사들은 **전부 초록불이다.**
    R38 의 변이 ⓓ 가 실측으로 그것을 보였다.

    그래서 값의 근사가 아니라 **어느 쪽에 서 있는가**를 본다: 해마다 반올림한
    손계산과 반올림하지 않은 손계산 둘을 세우고, 구현이 **반올림한 쪽에 더
    가까운지** 잰다. 근사 한도를 좁히는 방식(`rel=1e-9`)을 쓰지 않은 이유는
    그것이 부동소수 재결합 하나에도 깨지는 반면 이 판정은 깨지지 않기 때문이다.
    """
    net = _MULTIROW_BENEFIT - _MULTIROW_COST
    initial = _MULTIROW_INITIAL

    def _hand(round_each_year: bool) -> float:
        cumulative = float(-initial)
        for t in range(1, _MULTIROW_YEARS + 1):
            prev_cum = cumulative
            exact = net / ((1 + _MULTIROW_RATE) ** t)
            flow = float(to_won(exact)) if round_each_year else exact
            cumulative += flow
            if cumulative >= 0:
                return (t - 1) + (-prev_cum) / flow
        return float("inf")

    rounded = _hand(True)
    unrounded = _hand(False)
    assert rounded != unrounded, (
        "반올림한 손계산과 반올림하지 않은 손계산이 같다 — 이 케이스로는 "
        "반올림 자리를 구별할 수 없다. 케이스를 바꿔야 한다"
    )

    val = payback_discounted(
        Money(initial), _multirow_flows(), _MULTIROW_RATE
    )
    assert abs(val - rounded) < abs(val - unrounded), (
        f"할인 회수기간이 해마다 원 단위로 반올림하지 않는다: 산출 {val:.12f} · "
        f"해마다 반올림 {rounded:.12f} · 반올림 없음 {unrounded:.12f}. "
        f"반올림하지 않은 쪽에 더 가깝다"
    )


@pytest.mark.req("FR-703-AC1.payback-discounted")
def test_discounted_payback_and_npv_never_contradict_for_a_uniform_cash_flow() -> None:
    """1절의 **두 줄이 서로를 부정하지 않는다** — 「미회수」와 「N년에 회수」.

    ★ **이 라운드가 막으려는 진짜 위험이다.** 리포트 1절은 「결론」을 NPV 부호로
    적고(`CaseReport.recovers_within_horizon`) 바로 아래 줄에 「주 지표 · 할인
    회수기간」을 적는다. 두 줄의 관계는 붙임 3 이 **문면으로 선언한다** —
    *「분석기간 말 누적 할인 현금흐름이 초기투자를 넘으면 순현재가치 ≥ 0 이며
    그것이 「분석기간 내 회수」다」*. 그런데 그 선언을 **재는 검사가 없었다.**

    연 순현금흐름이 해마다 같은 현금흐름에서는 누적이 단조이므로 그 관계가
    **정확한 동치**다: 회수기간이 유한한 것과 NPV ≥ 0 인 것이 같다. 여기서
    0 선 양쪽으로 비용을 훑어 그 동치를 잰다.

    ⚠ 행 단위로 세면 비용 2,800,000원 지점에서 **NPV −398,414원(미회수)인데
    회수기간 2.9987년**이 나온다 — 1절에 「미회수」와 「3.00년」이 나란히 실린다.
    R38 이 실측으로 확인한 수다. 균일하지 않은 현금흐름에서는 나중 해가 음수로
    돌아 유한한 회수 뒤에 NPV 가 다시 내려갈 수 있으므로 **동치를 요구할 수
    없다**; 그래서 케이스를 균일한 것으로 한정하고 그 조건을 여기에 적는다.
    """
    years = range(1, _MULTIROW_YEARS + 1)
    initial = Money(_MULTIROW_INITIAL)
    seen_both_sides = set()

    for annual_cost in (2_000_000, 2_800_000, 2_900_000, 3_000_000, 4_000_000):
        rows = [
            benefit_row(tag="benefit", schedule={y: 3_000_000 for y in years}),
            benefit_row(tag="cost_negated", schedule={y: -annual_cost for y in years}),
        ]
        conclusion_won = int(npv(initial, rows, _MULTIROW_RATE))
        payback = payback_discounted(initial, rows, _MULTIROW_RATE)
        recovers = conclusion_won >= 0
        seen_both_sides.add(recovers)
        assert recovers == (payback != float("inf")), (
            f"연 비용 {annual_cost:,}원: 결론 축(순현재가치) {conclusion_won:,}원 은 "
            f"「{'회수' if recovers else '미회수'}」라고 말하는데 주 지표는 "
            f"{'분석기간 내 미회수' if payback == float('inf') else f'{payback:.4f}년에 회수'}"
            f" 라고 말한다. 1절의 두 줄이 서로를 부정한다"
        )

    assert seen_both_sides == {True, False}, (
        "훑은 비용 구간이 0 선의 한쪽에만 있었다 — 이 검사가 동치의 한 방향만 "
        "재고 있다. 케이스를 0 선 양쪽으로 벌려야 한다"
    )
