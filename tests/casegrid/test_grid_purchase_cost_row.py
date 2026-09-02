"""계통 전력 구매 행이 **금액 0에서도 실리는가** — 「0원 행」 규약 (R34).

R34 가 구매 비용을 배선하며 러너에 규약 하나를 함께 적었다:

    ⚠ **행을 조건부로 만들지 않는다** — 수전이 0이어도 0원 행을 싣는다.

`if annual_purchase_won:` 한 줄이면 그 규약이 깨지는데 **아무것도 빨간불이 되지
않는다.** 금액이 0인 행을 빼도 합계·NPV·회수기간이 전부 그대로이기 때문이다.
그래서 이 파일은 금액이 아니라 **행의 존재**를 붙든다.

## 왜 그 한 줄이 위험한가

프로포마에서 「수전이 없어서 0원」과 「행이 없어서 0원」은 **똑같이 보이는데 뜻이
정반대**다 — 하나는 측정이고 하나는 누락이다. 그리고 붙임 8 의 판정 조건이
**「수전이 있는데 비용 행이 없는가」**이므로, 행이 조건부로 사라지는 구현에서는
*값 없이 쓴 전력*이 다시 생겨도 미반영 표가 그것을 잡지 못하는 조합이 만들어질
수 있다 — R33 이 실제로 밟았던 상태다(`tests/report/test_unreflected.py`).

## 왜 **단가 0** 으로 재는가 — 수량 0인 케이스는 만들 수 없다 (실측)

이 파이프라인에서 수전을 0으로 만들 방법이 없다. 부하를 주지 않아도 저장장치가
심야에 계통에서 충전하고(대표일 6.19kWh · 실측), 저장장치를 없애려고 용량을
0으로 두면 **자원이 거부한다**(`ess.capacity_kwh — 0보다 커야 합니다`). 남는
길이 한계단가를 0으로 두는 것이고, 금액 0을 만드는 목적에는 그것으로 충분하다.

⚠ **프로포마 행 쪽은 밖에서 볼 수 없다.** `CaseOutcome` 은 현금흐름 행을 내지
않으므로, 0원 행을 프로포마에서 빼도 지표가 한 자리도 움직이지 않는다. 이 파일이
붙드는 것은 **밖으로 나오는 절반**(`basis.costs`)이고 그것이 붙임 4 의 비용 항목
표와 붙임 8 의 판정이 읽는 자리다.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import pytest

from core.casegrid.e2e_runner import DAYS_PER_YEAR, run_single_case_e2e
from core.casegrid.ledger_levels import design_levels
from core.casegrid.models import CaseOutcome, CostLine
from core.der.ess import ESSChargeSource

_GRID_PURCHASE_TAG = "GridPurchase"

#: 분석기간 탐침값 — 이 파일의 관심이 아니다(소유자는 `AssumptionSet`).
_PROBE_HORIZON = 18


def _level_map(grid_purchase_price: float) -> dict[str, Mapping[str, float]]:
    """대장을 읽지 않는다 — 이 파일이 보는 것은 금액이 아니라 **행의 존재**다.

    단가만 인자로 받는 이유는 그것이 이 파일이 흔드는 유일한 값이어서다. 나머지는
    러너가 요구하는 최소 구성이며(기본값을 두지 않는 것이 규칙) 대장값과 같을
    필요가 없다.
    """
    return {
        "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
        "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
        "discount_rate": MappingProxyType({"base": 0.045}),
        "grid_purchase_price": MappingProxyType({"base": grid_purchase_price}),
        # 잉여 판매단가 — 러너가 요구한다(R35). 이 파일이 흔드는 값이 아니므로
        # 고정하되 **구매 단가와 다른 수**로 둔다: 같게 두면 단가를 0·200 으로
        # 흔드는 아래 검사들이 *판매* 단가도 함께 움직인 것처럼 읽힌다.
        "surplus_sale_price": MappingProxyType({"base": 90.0}),
        # 교체 설비단가의 실질 추세 — 러너가 요구한다(R42 에 스윕 축으로 올렸다).
        # **0 은 대장의 사본이 아니라 중립값이다** — 0 이면 명목 교체단가가 물가
        # 계수만 타므로 이 축을 흔들지 않는 것과 같다. 이 파일은 그 축을 재지
        # 않으므로 중립을 고른다(대장의 base 가 바뀌어도 여기는 따라오지 않아야
        # 한다 — 따라오면 이 파일이 대장의 사본을 갖게 된다).
        "replacement_real_trend": MappingProxyType({"base": 0.0}),
        # PV 설비단가 중 인버터 몫 — 러너가 요구한다(R43 에 스윕 축으로 올렸다).
        # **대장의 15 와 다른 수를 일부러 쓴다** — 같은 수를 쓰면 이 파일이 대장의
        # 사본을 하나 갖게 되고, 대장이 바뀔 때 여기가 따라오지 않아도 아무 일이
        # 없다(위 두 단가와 같은 규약이다). 이 파일은 이 축을 재지 않는다.
        "pv_inverter_share": MappingProxyType({"base": 0.11}),
        # 첨두 기본요금 단가 — 러너가 요구한다(R43 에 대장·스윕 축으로 올렸다).
        # **대장의 8,320 과 다른 수를 일부러 쓴다** — 같은 수를 쓰면 이 파일이
        # 대장의 사본을 하나 갖게 되고, 대장이 바뀔 때 여기가 따라오지 않아도
        # 아무 일이 없다(위 단가들과 같은 규약이다). 이 파일은 이 축을 재지 않는다.
        "demand_charge": MappingProxyType({"base": 7_700.0}),
        # 고정 O&M 둘 — 러너가 요구한다(R51/WP-2 에 스윕 축으로 올렸다). **대장의
        # 100,000 과 다른 수를 일부러 쓴다** — 위 단가들과 같은 규약이다.
        "pv_fixed_om": MappingProxyType({"base": 70_000.0}),
        "ess_fixed_om": MappingProxyType({"base": 65_000.0}),
        # ESS 교체 단가 — 러너가 요구한다(R52/WP-6 에 스윕 축으로 올렸다).
        # **대장과 다른 수를 일부러 쓴다.**
        "ess_replacement": MappingProxyType({"base": 350_000.0}),
        **design_levels(),
    }


def _purchase_line(outcome: CaseOutcome) -> CostLine:
    lines = [c for c in outcome.basis.costs if c.tag == _GRID_PURCHASE_TAG]
    assert len(lines) == 1, (
        f"계통 전력 구매 비용 항목이 {len(lines)}개다 — 「0원 행」 규약대로라면 "
        "금액과 무관하게 **정확히 하나**여야 한다. 행이 조건부가 되면 "
        "프로포마에서 「사 온 것이 없다」와 「세지 않았다」가 구별되지 않는다"
    )
    return lines[0]


@pytest.mark.req("FR-1001-AC3")
def test_the_purchase_row_survives_a_zero_amount() -> None:
    """★★★ 금액이 0이어도 행이 실린다 — 조건부가 아니다.

    한계단가를 0으로 두면 구매 금액이 0이 된다. 이때 행이 사라지는 구현은
    **지표를 한 자리도 바꾸지 않으므로** 다른 어떤 검사도 빨간불이 되지 않는다.

    ⚠ **`ess_charge_source=GRID` 를 명시로 강제한다** (R48 판정 A-8 이후).
    기본값은 `PV_SURPLUS` 이고 그 아래서는 대표일 수전이 정당하게 0 일 수
    있다(심야 계통충전이 바로 R48 이 없앤 것이다) — 그러면 이 검사가 재려는
    「0원 행이 조건부로 사라지는가」와 「수량이 0이라 금액도 0인가」가
    구별되지 않는다. `GRID` 로 고정해 **결정적으로 0 아닌 수전**을 만든다.
    """
    outcome = run_single_case_e2e(
        {}, level_map=_level_map(0.0), horizon_years=_PROBE_HORIZON,
        ess_charge_source=ESSChargeSource.GRID,
    )

    line = _purchase_line(outcome)
    assert line.annual_won == 0, (
        f"단가 0인데 구매 비용이 {line.annual_won:,}원이다 — 단가가 러너까지 "
        "닿지 않고 어딘가에 박힌 수가 쓰이고 있습니다"
    )
    assert sum(outcome.dispatch.grid_import) > 0, (
        "대표일 수전이 0이다 — charge_source=GRID 로 고정했는데도 0이면 이 "
        "검사가 「수량이 0이라 금액도 0」을 보게 되어 규약을 재지 못한다"
    )


@pytest.mark.req("FR-703-AC1.npv")
def test_the_purchase_price_reaches_the_npv() -> None:
    """★★★ 단가를 올리면 **NPV 가 줄어든다** — 프로포마 행이 버려지지 않는다.

    `basis.costs` 를 보는 위 검사들은 **항목 표**만 붙든다. 러너에는 자리가
    둘이고(프로포마 행 · 비용 항목), 프로포마 쪽 `energy_purchase_row(...)`
    호출을 통째로 지워도 항목 표는 그대로다 — 그때 순현재가치는 **조용히
    좋아진다.** 실측하니 그 변이는 리포트·케이스 스위트 전건에서 우연히
    빨간불이었을 뿐이고(전환 인자 검사 둘이 값이 움직여 깨졌다), **구매 비용을
    이름으로 붙드는 검사는 하나도 없었다**(2026-08-17 · 변이 1).

    방향까지 보는 이유: 부호가 뒤집혀 구매가 편익으로 들어가도 「달라진다」는
    통과한다 — R32 가 관리 수수료에서 실제로 밟은 형태다.

    ⚠ **`ess_charge_source=GRID` 를 명시로 강제한다** — 위 검사와 같은 이유다.
    """
    free = run_single_case_e2e(
        {}, level_map=_level_map(0.0), horizon_years=_PROBE_HORIZON,
        ess_charge_source=ESSChargeSource.GRID,
    )
    dear = run_single_case_e2e(
        {}, level_map=_level_map(200.0), horizon_years=_PROBE_HORIZON,
        ess_charge_source=ESSChargeSource.GRID,
    )

    assert dear.metrics["npv"] < free.metrics["npv"], (
        f"한계단가를 0 → 200원/kWh 로 올렸는데 NPV 가 {free.metrics['npv']:,.0f}원 "
        f"→ {dear.metrics['npv']:,.0f}원 이다 — 구매 비용이 프로포마에 닿지 않고 "
        "버려졌거나, 부호가 뒤집혀 편익으로 들어갔습니다"
    )


@pytest.mark.req("FR-1001-AC3")
def test_the_cost_total_and_the_itemised_lines_agree() -> None:
    """★★ 합계와 항목이 **같은 수를 말한다** (`CaseBasis.costs` 독스트링).

    합계(`annual_cost_won`)는 **프로포마 행**에서 세고 항목(`costs`)은 러너가
    따로 짓는다. 두 자리가 갈리는 것이 R34 가 이 필드를 나눠 담은 이유이며,
    어긋남 자체가 결함이다 — 한쪽에서 행이 사라지면 리포트의 「1년차 운영비」와
    붙임 4 의 항목 표가 **서로 다른 사업을 말하게 된다.**
    """
    outcome = run_single_case_e2e(
        {}, level_map=_level_map(120.0), horizon_years=_PROBE_HORIZON
    )

    itemised = sum(line.annual_won for line in outcome.basis.costs)
    assert outcome.basis.annual_cost_won == itemised, (
        f"운영비 합계 {outcome.basis.annual_cost_won:,}원과 항목 합 "
        f"{itemised:,}원이 다르다 — 프로포마 행과 비용 항목 중 한쪽에만 있는 "
        "비용이 있습니다"
    )


@pytest.mark.req("FR-1001-AC3")
def test_the_row_still_measures_the_purchase_when_the_price_is_real() -> None:
    """★ 양성 짝 — 단가가 있으면 **측정한 수량 × 단가**가 그 행에 실린다.

    위 검사만 두면 「무엇이든 0원 행 하나를 넣는」 구현도 통과한다. 여기서는
    러너가 돌려준 운전 결과에 대고 금액을 맞춰 본다 — 손계산 상수를 적지 않는
    이유는 그것이 디스패치 규칙의 사본이 되어 규칙이 바뀔 때 함께 틀리기
    때문이다.
    """
    price = 100.0
    outcome = run_single_case_e2e(
        {}, level_map=_level_map(price), horizon_years=_PROBE_HORIZON
    )

    daily_kwh = sum(outcome.dispatch.grid_import)
    line = _purchase_line(outcome)

    assert line.annual_won == int(daily_kwh * DAYS_PER_YEAR * price), (
        f"대표일 수전 {daily_kwh:,.2f}kWh · 단가 {price:,.0f}원/kWh 인데 "
        f"{line.annual_won:,}원이 실렸다 — 연간화(×{DAYS_PER_YEAR})가 빠졌거나 "  # noqa: RUF001
        "두 번 곱해졌습니다"
    )
    assert f"{daily_kwh:,.2f}kWh" in line.formula, "산식에 측정 수량이 없다"
    assert f"{price:,.0f}원/kWh" in line.formula, (
        "산식에 단가가 없다 — 수량과 단가 중 어느 쪽이 틀렸는지 가릴 수 없다"
    )
