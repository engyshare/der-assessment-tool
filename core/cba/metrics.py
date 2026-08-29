"""경제성 지표 산출 — 작업 10.4 / FR-703.

13종 지표. **오라클 규격이 지표마다 다르다** (§13.0.2):

| 지표 | 순위 | 허용 오차 |
|---|---|---|
| NPV · B/C | **1** | 원 단위 완전 일치. B/C 는 분자·분모 각각 원 일치, |
|  |  | **비율 자체에는 별도 오차를 두지 않는다** |
| IRR · MIRR · 할인 회수기간 | 2 | 0.01% |
| LCOE(자원별) | 1 | 원 단위 일치(자원별 분모 명시) |

**lcoe-mixed 는 음성 케이스다** — 혼합 모델 전체 LCOE 는 분모 정의가 성립하지
않으므로 산출하지 않는다(v0.3 정정). «분모를 명시하면 낼 수 있다» 는 우회로는
v1.6 에서 닫혔다 — 되살리지 말 것.

**mirr-order 는 값이 아니라 조건부 표시 규칙**이다 — 현금흐름 부호변경이 다수일
때 MIRR 을 IRR 보다 우선 표시한다. ``mirr-value`` 와 검증 형태가 다르다.

**반올림은 ``to_won()`` 한 곳에서만** (NFR-103). NPV/B/C 의 할인 합산은 각 항을
``to_won`` 으로 반올림한 뒤 더한다 — 항목별 합계와 총계가 원 단위로 일치해야
한다 (NFR-103-M1).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.contracts.schemas import CashFlowRow
from core.contracts.units import ZERO, Money, to_won, won_sum


@dataclass(frozen=True)
class BCResult:
    """B/C 결과 — 분자·분모·비율. **판정은 분자·분모 각각 원 일치**로 한다.

    비율(ratio) 자체에는 별도 오차를 두지 않는다 (§13.0.2 순위 1, v0.12).
    비율에 오차를 주면 «편익 과대 + 비용 과대» 와 «둘 다 정확» 이 같은 값을
    낸다 — 어느 쪽이 틀렸는지 말하지 못하는 지표가 된다.
    """

    numerator: Money    # 총편익 현가
    denominator: Money  # 총비용 현가
    ratio: Decimal      # numerator / denominator (분모 0 이면 0)

    def matches(self, expected_num: int, expected_den: int) -> bool:
        """순위 1 판정 — 분자·분모 원 단위 완전 일치."""
        return (
            int(self.numerator) == expected_num
            and int(self.denominator) == expected_den
        )


def _pv(rows: list[CashFlowRow], discount_rate: float) -> Money:
    """현가 합계 — 각 항을 ``to_won`` 반올림한 뒤 더한다 (NFR-103-M1).

    CashFlowRow.year 이 t 를 직접 나타낸다(year=1 → t=1, factor=(1+r)^1).
    """
    discounted: list[float] = []
    for row in rows:
        for year, amount in row.amounts.items():
            factor = (1.0 + discount_rate) ** year
            discounted.append(float(amount) / factor)
    return won_sum(discounted)


def npv(
    initial_investment: Money,
    operating: list[CashFlowRow],
    discount_rate: float,
) -> Money:
    """NPV — 순위 1, 원 단위 완전 일치 (FR-703-AC1.npv).

    ``initial_investment`` 는 t=0 에 나가는 비용(양수)이며 NPV 에서 뺀다.
    ``operating`` 의 각 ``CashFlowRow.year`` 이 t(year=1 → t=1).
    """
    pv_benefits = _pv(operating, discount_rate)
    return Money(pv_benefits - initial_investment)


def bcr(
    benefit_flows: list[CashFlowRow],
    cost_flows: list[CashFlowRow],
    initial_investment: Money,
    discount_rate: float,
) -> BCResult:
    """B/C — 순위 1. 분자·분모 각각 원 단위 완전 일치 (FR-703-AC1.bcr).

    분자 = 편익 현가. 분모 = 초기투자(t=0) + 운영비용 현가(t=1..N).
    비율은 몫이며 별도 오차를 두지 않는다 — 분모가 0이면 0.
    """
    numerator = _pv(benefit_flows, discount_rate)
    pv_costs = _pv(cost_flows, discount_rate)
    denominator = Money(initial_investment + pv_costs)
    ratio = (
        Decimal(int(numerator)) / Decimal(int(denominator))
        if denominator != ZERO else Decimal(0)
    )
    return BCResult(numerator=numerator, denominator=denominator, ratio=ratio)


def _flatten(operating: list[CashFlowRow]) -> list[tuple[int, float]]:
    """operating 을 (year, amount) 평탄화, year 오름차순. **행을 합치지 않는다.**

    ⚠ **연 단위로 합치고 싶으면 `_by_year()` 를 쓴다.** 여기서 합치면
    `mirr()` 값이 바뀐다 — `mirr` 은 `amount > 0` 을 **행 단위**로 걸러
    미래가치를 쌓으므로, 한 해의 편익 행(+)과 비용 행(−)을 미리 합치면
    그 해가 순편익 하나로 접히고 미래가치가 줄어든다(실측: 0.4048 → 0.1277).
    `irr` 은 전부 합하므로 어느 쪽이든 같다.

    누적을 한 걸음씩 보는 쪽(`payback_*`)에는 이 목록을 **그대로 쓰면 안 된다** —
    한 해에 행이 여럿이면 그 해의 편익 행만 누적한 지점에서 0 선을 넘고 남은
    음수 행을 세기 전에 반환한다. R38 이 그것을 `_by_year()` 로 갈랐다.
    """
    pairs: list[tuple[int, float]] = []
    for row in operating:
        for year, amount in row.amounts.items():
            pairs.append((year, float(amount)))
    pairs.sort(key=lambda p: p[0])
    return pairs


def _by_year(operating: list[CashFlowRow]) -> list[tuple[int, float]]:
    """operating 을 **연도별 순현금흐름 한 수**로 접는다, year 오름차순.

    한 해에 행이 여럿인 것(편익 행 + 부호를 뒤집은 비용 행)은 이 저장소의
    **정상 형태**다 — `core/casegrid/operating_lines.py::net_operating_flows()` 가
    그렇게 넘긴다(선언은 그쪽이고, `e2e_runner` 가 재수출하므로 **러너 경로로도
    부를 수 있다** — 한쪽만 적으면 다음 사람이 재수출을 모르고 지운다).
    누적을 한 걸음씩 보는 지표는 그 행들을 **먼저 합쳐야** 한다. 합치지 않으면
    편익 행만 누적한 지점에서 0 선을 넘고 **행 순서가 값을 바꾼다.**

    `_flatten()` 과 갈라 둔 이유는 그쪽 독스트링에 있다 — `mirr` 이 부호를
    행 단위로 읽어 합치면 값이 바뀐다. **같은 함수로 둘 수 없다.**
    """
    totals: dict[int, float] = {}
    for row in operating:
        for year, amount in row.amounts.items():
            totals[year] = totals.get(year, 0.0) + float(amount)
    return sorted(totals.items())


def _npv_float(
    initial_investment: float, flows: list[tuple[int, float]], rate: float
) -> float:
    """IRR/MIRR 내부용 — float 그대로, 반올림 없음."""
    total = -initial_investment
    for year, amount in flows:
        total += amount / ((1.0 + rate) ** year)
    return total


def irr(
    initial_investment: Money, operating: list[CashFlowRow]
) -> float:
    """IRR — 순위 2, 0.01% (FR-703-AC1.irr). bisection.

    ``0 = -initial + Σ(amount/(1+r)^year)``. IRR 은 반복해라 — 닫힌 형태가 없다.
    """
    inv = float(initial_investment)
    flows = _flatten(operating)
    lo, hi = -0.99, 1.0  # IRR 은 -99% ~ 100% 범위에서 찾는다
    mid: float = 0.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        val = _npv_float(inv, flows, mid)
        if abs(val) < 0.01:  # 원 단위 미만 잔차
            return float(mid)
        if val > 0:
            lo = mid
        else:
            hi = mid
    return float(mid)


def mirr(
    initial_investment: Money,
    operating: list[CashFlowRow],
    finance_rate: float,
    reinvest_rate: float,
) -> float:
    """MIRR — 순위 2, 0.01% (FR-703-AC1.mirr-value).

    PV(costs, finance_rate) = initial (t=0).
    FV(benefits, reinvest_rate) = Σ(amount × (1+reinvest)^(N-year)).
    MIRR = (FV/PV)^(1/N) - 1.
    """
    inv = float(initial_investment)
    flows = _flatten(operating)
    if not flows:
        return 0.0
    n_years = max(year for year, _ in flows)
    fv_benefits = 0.0
    for year, amount in flows:
        if amount > 0:
            fv_benefits += amount * ((1.0 + reinvest_rate) ** (n_years - year))
    if inv <= 0 or fv_benefits <= 0:
        return 0.0
    return float((fv_benefits / inv) ** (1.0 / n_years) - 1.0)


def mirr_preferred_over_irr(cash_flow_series: list[float]) -> bool:
    """MIRR 우선 표시 규칙 (FR-703-AC1.mirr-order).

    **값이 아니라 조건부 표시 규칙이다.** 현금흐름 부호변경이 2회 이상이면
    IRR 은 복수해를 가질 수 있어 MIRR 을 우선 표시한다. ``mirr-value`` 와
    검증 형태가 다르다 — 이 함수는 bool 을 반환한다.
    """
    if len(cash_flow_series) < 2:
        return False
    sign_changes = 0
    prev_sign = 0
    for v in cash_flow_series:
        if v == 0:
            continue
        s = 1 if v > 0 else -1
        if prev_sign not in (0, s):
            sign_changes += 1
        prev_sign = s
    return sign_changes > 1


def payback_simple(
    initial_investment: Money, operating: list[CashFlowRow]
) -> float:
    """단순 회수기간 — 누적 현금흐름 0 도달 (FR-703-AC1.payback-simple).

    할인 없이 **연도별 순현금흐름**(`_by_year`)을 누적. 도달하지 못하면
    ``math.inf``. 회수는 해 안에서 선형 보간하므로 값은 ``(해-1) + 소수부`` 다.

    ⚠ **연도 단위다** — `_flatten()` 을 쓰면 한 해의 편익 행만 누적한 지점에서
    반환하고 **행 순서가 값을 바꾼다**(R38). `_by_year()` 독스트링 참조.
    """
    inv = float(initial_investment)
    flows = _by_year(operating)
    cumulative = -inv
    for year, amount in flows:
        prev_cum = cumulative
        cumulative += amount
        if cumulative >= 0:
            # 이 해 안에서 회수 — 선형 보간. 기준점은 **직전 해의 끝**이며
            # 그것은 `year - 1` 이다. 순회 중의 「직전 행의 연도」로 두면
            # 연도가 비어 있는 현금흐름에서 엉뚱한 해를 가리킨다.
            if amount == 0:
                return float(year)
            fraction = (-prev_cum) / amount
            return (year - 1) + fraction
    return float("inf")


def payback_discounted(
    initial_investment: Money,
    operating: list[CashFlowRow],
    discount_rate: float,
) -> float:
    """할인 회수기간 — 주 지표 (FR-703-AC1.payback-discounted). 순위 2, 0.01%.

    각 해의 현금흐름을 할인한 뒤 ``to_won`` 반올림, 누적이 initial 을 넘는 시점.

    ★ **문면대로 연 단위다.** 그 해의 행을 `_by_year()` 로 **먼저 합친 뒤**
    한 번 할인한다 — 반올림도 그 해에 한 번이다. R38 까지는 `_flatten()` 의
    행 목록을 그대로 돌아 **행 단위**로 셌고, 그래서 선언(이 문단)과 구현이
    갈려 있었다. 실측으로 보조 80% 가 4.8623년 → 6.3923년이 됐다.
    """
    inv = float(initial_investment)
    flows = _by_year(operating)
    cumulative = -inv
    for year, amount in flows:
        prev_cum = cumulative
        factor = (1.0 + discount_rate) ** year
        discounted = float(to_won(amount / factor))
        cumulative += discounted
        if cumulative >= 0:
            # 기준점은 직전 해의 끝(`year - 1`) — `payback_simple` 과 같다.
            if discounted == 0:
                return float(year)
            fraction = (-prev_cum) / discounted
            return (year - 1) + fraction
    return float("inf")


def lcoe_resource(
    total_cost_pv: Money,
    total_generation_kwh: float,
) -> Decimal | None:
    """LCOE (자원별) — 순위 1 (FR-703-AC1.lcoe-resource).

    발전 자원(PV 등) 1종에 한해 ``총비용 현가 / 총발전량``. **발전 자원만**
    대상 — 분모(kWh)가 정의되는 자원이어야 한다. ``generation=0`` 이면 None.
    """
    if total_generation_kwh <= 0:
        return None
    return Decimal(int(total_cost_pv)) / Decimal(total_generation_kwh)


def lcoe_mixed() -> None:
    """혼합 모델 전체 LCOE — **산출하지 않는다** (FR-703-AC1.lcoe-mixed).

    **음성 케이스** — 값이 나오면 실패다. 히트펌프·ESS 섞인 모델의 전체 LCOE 는
    분모 정의가 성립하지 않는다(v0.3 정정). 모델 전체 비교는 NPV·회수기간으로.

    «분모를 명시하면 낼 수 있다» 는 우회로는 v1.6 에서 닫혔다 — 되살리지 말 것.
    이 함수는 항상 ``None`` 을 반환하며, 그것이 곧 검증 통과다.
    """
    return None


def household_saving(annual_saving_won: Money, household_count: int) -> Money:
    """가구당 월 절감액 — 원/호·월 (FR-703-AC1.household-saving).

    오라클: 순위 1 (단순 나눗셈).
    """
    if household_count <= 0:
        raise ValueError(
            f"가구 수는 1 이상이어야 합니다: {household_count}. "
            "0 가구면 가구당 절감액이 정의되지 않는다"
        )
    monthly = int(annual_saving_won) / 12 / household_count
    return to_won(monthly)


def self_consumption_rate(
    self_consumed_kwh: float, total_generation_kwh: float
) -> float:
    """연간 자가소비율(%) — FR-703-AC1.self-consumption.

    오라클: 순위 1. 0~1 소수로 반환(표시측에서 % 변환).
    """
    if total_generation_kwh <= 0:
        return 0.0
    rate = self_consumed_kwh / total_generation_kwh
    return max(0.0, min(1.0, rate))


def supply_duty_rate(
    excess_generation_kwh: float, required_supply_kwh: float
) -> float:
    """초과발전량 우선공급 의무 충족률 — FR-703-AC1.supply-duty.

    **현행 기준값(70%)은 규제 프로파일(FR-504)이 들고 있으며 이 함수에 고정하지
    않는다.** 0~1 소수(1.0 = 100% 충족). 음수면 0, 초과면 1 로 클램프.
    """
    if required_supply_kwh <= 0:
        return 0.0
    return max(0.0, min(1.0, excess_generation_kwh / required_supply_kwh))


def fiscal_pv(
    direct_subsidy_won: Money,
    loan_interest_subsidy_pv_won: Money,
    other_fiscal_cost_pv_won: Money = ZERO,
) -> Money:
    """정부 재정 부담 현가 — FR-703-AC1.fiscal-pv.

    직접 보조금 + 융자 이차보전 현가 + 기타 재정 비용. **타 사업 국비은 제외**
    (FR-704-AC6 — 본 사업 국비만 분모에).
    """
    return Money(direct_subsidy_won + loan_interest_subsidy_pv_won + other_fiscal_cost_pv_won)
