"""잉여 판매단가가 **대장에서** 러너에 닿는가 — NFR-202 · R35.

R34 까지 이 단가는 러너 안의 리터럴이었다:

    settlement_streams = (SurplusSale(sale_price_won_per_kwh=120.0),)

그 상태의 나쁜 점은 **셋**이며, 이 파일이 셋을 각각 붙든다.

    ① 대장이 정본이 아니었다        → 대장을 고쳐도 러너는 옛 단가로 계산한다
    ② 어느 케이스 축에도 없었다      → 영향도 표(5.1)에 오르지 못한다.
                                     리터럴은 흔들 수 없으므로 *영향이 없는 것과
                                     같은 모양*으로 보인다 — R33 이
                                     `tariff_escalation` 에서 만난 형태다
    ③ 구매 단가와 **우연히 같았다**  → 심야에 사서 주간에 파는 이 구성에서 두
                                     단가가 같으면 차익거래는 왕복효율 손실만큼
                                     정확히 순손실이다. 「저장장치를 키우면
                                     좋아지는가」의 답이 그 우연 위에 서 있었다

## ⚠ `NFR-202` 검사가 이 리터럴을 잡지 못했다

`check_hardcoded_params` 의 판정이 |값| ≥ 1,000 만 보므로 120 은 사각지대였다
(`status.md` 「미해결」의 그 행). 즉 이 파일은 **검사가 볼 수 없던 자리**를 코드
쪽에서 없앤 뒤, 그 자리가 되살아나는 것을 대신 붙드는 장치다.

## 왜 기대 금액을 이 파일에 적지 않는가

적으면 그것이 대장의 사본이 되고, 대장을 고칠 때 여기가 따라오지 않아도 아무
일이 없다. 그래서 **대장을 다시 읽어** 대조하고, 수량은 러너가 돌려준 운전
결과에서 가져온다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml  # type: ignore[import-untyped]

from core.casegrid.e2e_runner import DAYS_PER_YEAR, run_single_case_e2e
from core.casegrid.ledger_levels import (
    build_level_map,
    design_levels,
    ledger_backed_variables,
)
from core.casegrid.models import CaseOutcome
from core.contracts.units import to_won
from core.valuestream.settlement import SURPLUS_SALE_KEY, TARIFF_KEY


def _annualised(daily_surplus_kwh: float, price: float) -> int:
    """대표일 잉여를 연간 금액으로 — **러너와 같은 순서로** 곱한다.

    `to_won()` 을 쓰는 이유는 반올림이 그 경계에서 한 번 일어나기 때문이다
    (`units.to_won` 독스트링 — 사사오입, 원 단위). 여기서 `int(...)` 로 잘라
    버리면 최대 365원이 어긋나고, 그것은 배선 결함이 아니라 **이 검사가 규약을
    베껴 적다 틀린 것**이다.
    """
    return int(float(to_won(daily_surplus_kwh * price)) * DAYS_PER_YEAR)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS_YAML = _REPO_ROOT / "docs" / "assumptions.yaml"

_SURPLUS_TAG = "SurplusSale"
_VARIABLE = "surplus_sale_price"

#: 분석기간 탐침값 — 이 파일의 관심이 아니다(소유자는 `AssumptionSet`).
_PROBE_HORIZON = 18


def _level_map(surplus_sale_price: float) -> dict[str, Mapping[str, float]]:
    """판매단가만 흔드는 최소 수준표.

    구매 단가를 **다른 수**로 고정하는 것이 요점이다 — 같은 수로 두면 이 파일이
    R35 가 없앤 「두 단가가 우연히 같다」를 검사 안에서 되살린다.
    """
    return {
        "pv_unit_cost": MappingProxyType({"base": 1_600_000.0}),
        "ess_unit_cost": MappingProxyType({"base": 400_000.0}),
        "discount_rate": MappingProxyType({"base": 0.045}),
        "grid_purchase_price": MappingProxyType({"base": 100.0}),
        _VARIABLE: MappingProxyType({"base": surplus_sale_price}),
        # 교체 실질 추세 — 러너가 요구한다(R42). **0 은 중립값**이며 이 파일의
        # 관심이 아니다: 0 이면 명목 교체단가가 물가 계수만 탄다.
        "replacement_real_trend": MappingProxyType({"base": 0.0}),
        **design_levels(),
    }


def _surplus_won(outcome: CaseOutcome) -> int:
    lines = [line for line in outcome.basis.benefits if line.tag == _SURPLUS_TAG]
    assert len(lines) == 1, (
        f"잉여판매 편익 항목이 {len(lines)}개다 — 구조를 주지 않은 기본 경로는 "
        "잉여판매 하나를 갖는다"
    )
    return lines[0].annual_won


@pytest.mark.req("NFR-202-M1")
def test_the_runner_refuses_to_run_without_a_sale_price() -> None:
    """★★★ 수준표에서 빼면 **거부한다** — 기본값이 없다.

    이것이 리터럴로 되돌아가는 것을 막는 래칫이다. 기본값을 하나 두면 수준표에서
    이 변수를 빼도 러너가 옛 단가로 계속 계산하고, **그 어긋남은 NPV 를 바꾸면서
    아무 예외도 내지 않는다** — `horizon_years`(R31)·`grid_purchase_price`(R34)에서
    같은 판단을 내렸다.
    """
    incomplete = _level_map(110.0)
    del incomplete[_VARIABLE]

    with pytest.raises(ValueError) as excinfo:
        run_single_case_e2e({}, level_map=incomplete, horizon_years=_PROBE_HORIZON)

    assert _VARIABLE in str(excinfo.value), (
        f"어느 변수가 없어서 멈췄는지 말하지 않는다 — {excinfo.value}"
    )


@pytest.mark.req("FR-703-AC1.npv")
def test_the_sale_price_reaches_the_npv() -> None:
    """★★★ 단가를 올리면 **NPV 가 커진다** — 편익이 버려지지 않는다.

    방향까지 보는 이유는 구매 단가 쪽과 같다: 부호가 뒤집혀 판매가 비용으로
    들어가도 「달라진다」만 보는 검사는 통과한다(R32 가 관리 수수료에서 실제로
    밟은 형태다).
    """
    cheap = run_single_case_e2e(
        {}, level_map=_level_map(0.0), horizon_years=_PROBE_HORIZON
    )
    dear = run_single_case_e2e(
        {}, level_map=_level_map(200.0), horizon_years=_PROBE_HORIZON
    )

    assert dear.metrics["npv"] > cheap.metrics["npv"], (
        f"판매단가를 0 → 200원/kWh 로 올렸는데 NPV 가 "
        f"{cheap.metrics['npv']:,.0f}원 → {dear.metrics['npv']:,.0f}원 이다 — "
        "단가가 편익에 닿지 않고 버려졌거나, 부호가 뒤집혀 비용으로 들어갔습니다"
    )


@pytest.mark.req("FR-1001-AC3")
def test_the_benefit_is_the_measured_surplus_times_the_price() -> None:
    """★ 양성 짝 — **측정한 잉여량 × 단가 × 365** 가 그 항목에 실린다.

    위 검사만 두면 「단가를 아무 데나 곱하는」 구현도 방향은 맞출 수 있다. 손계산
    상수를 적지 않는 이유는 그것이 디스패치 규칙의 사본이 되어 규칙이 바뀔 때
    함께 틀리기 때문이다 — 수량은 러너가 돌려준 운전 결과에서 읽는다.
    """
    price = 90.0
    outcome = run_single_case_e2e(
        {}, level_map=_level_map(price), horizon_years=_PROBE_HORIZON
    )

    daily_surplus_kwh = sum(max(0.0, e) for e in outcome.dispatch.grid_export)
    assert daily_surplus_kwh > 0, (
        "대표일 잉여가 0이다 — 이 구성은 전량 판매(자가소비율 0%)이므로 잉여를 "
        "가져야 하며, 0이면 이 검사가 「수량이 0이라 금액도 0」을 보게 되어 "
        "단가가 닿는지를 재지 못한다"
    )

    assert _surplus_won(outcome) == _annualised(daily_surplus_kwh, price), (
        f"대표일 잉여 {daily_surplus_kwh:,.2f}kWh · 단가 {price:,.0f}원/kWh 인데 "
        f"{_surplus_won(outcome):,}원이 실렸다 — 연간화(×{DAYS_PER_YEAR})가 "  # noqa: RUF001
        "빠졌거나 두 번 곱해졌거나, 단가가 러너까지 닿지 않았습니다"
    )


@pytest.mark.req("NFR-202-M1")
def test_the_deploy_path_prices_the_surplus_from_the_ledger() -> None:
    """★★★ 배포 경로가 **대장 값**으로 잰다 — 기대 금액을 여기 적지 않는다.

    위 셋은 단가가 *러너까지* 닿는지만 본다. 러너에 닿는 수가 대장에서 온
    것인지는 별개이며, `_LEDGER_VARS` 에서 이 줄이 빠지거나 다른 키를 가리키면
    위 셋은 **전건 초록불**이다(탐침 수준표를 쓰므로 대장을 읽지 않는다).

    그래서 여기서는 실물 대장으로 수준표를 만들어 돌리고, **대장을 다시 읽어**
    같은 수가 편익에 쓰였는지 본다.
    """
    level_map = build_level_map(_ASSUMPTIONS_YAML)
    outcome = run_single_case_e2e(
        {}, level_map=level_map, horizon_years=_PROBE_HORIZON
    )

    ledger_key = ledger_backed_variables().get(_VARIABLE)
    assert ledger_key is not None, (
        f"{_VARIABLE!r} 가 대장 항목과 이어져 있지 않다 — 리터럴로 되돌아갔거나 "
        "모형 파라미터로 옮겨졌습니다"
    )
    items = {
        item["key"]: item
        for item in yaml.safe_load(
            _ASSUMPTIONS_YAML.read_text(encoding="utf-8")
        )["assumptions"]
    }
    ledger_price = float(items[ledger_key]["sensitivity"]["base"])

    daily_surplus_kwh = sum(max(0.0, e) for e in outcome.dispatch.grid_export)
    assert _surplus_won(outcome) == _annualised(daily_surplus_kwh, ledger_price), (
        f"대장 {ledger_key} = {ledger_price:,.0f}원/kWh 인데 편익에 실린 수는 "
        f"{_surplus_won(outcome):,}원이다 — 러너가 대장이 아닌 다른 단가로 "
        "잉여를 값하고 있습니다"
    )


@pytest.mark.req("NFR-202-M1")
def test_the_default_path_prices_the_surplus_like_the_surplus_structure() -> None:
    """★★★ **어느 대장 항목인가**를 붙든다 — 위 검사가 놓친 자리.

    ## 왜 이 검사가 따로 필요한가 (R35 · 변이 3 이 ★초록불이었다)

    `test_the_deploy_path_prices_the_surplus_from_the_ledger` 는 대장 키를
    `ledger_backed_variables()` 에서 **읽어** 온다. 그래서 `_LEDGER_VARS` 의 그
    줄을 `tariff.hv_single_contract.avg`(약관요금 150원/kWh)로 바꾸는 변이가
    **아무 검사도 빨간불로 만들지 않았다** — 검사가 자기가 검사할 대상을 따라가
    「러너는 표가 말하는 키를 쓴다」만 확인했기 때문이다. 참이지만 공허하다.

    그 변이가 통과하면 잉여를 **소매가로 파는 사업**이 되고, 그 순간 사는 값과
    파는 값이 같은 대장 줄에 묶여 저장장치 차익거래가 항상 본전이 된다. 금액은
    그럴듯하고 아무 예외도 나지 않는다.

    ## 무엇에 대고 맞추는가 — **사본을 만들지 않는다**

    키를 여기 리터럴로 적으면 대장 키를 옮길 때 두 곳을 고쳐야 한다. 그래서
    `settlement.py` 의 상수에 대고 맞춘다: 조립기가 「잉여 직거래」 구조에 쓰는
    바로 그 항목이며, **구조를 주지 않은 기본 경로도 잉여를 파는 것**이므로 같은
    항목이어야 한다. 그 상수가 정본이고 이 검사는 그것을 가리킨다.
    """
    keys = ledger_backed_variables()
    assert keys[_VARIABLE] == SURPLUS_SALE_KEY, (
        f"기본 경로가 {keys[_VARIABLE]!r} 로 잉여를 값한다 — 「잉여 직거래」 "
        f"조립기가 쓰는 {SURPLUS_SALE_KEY!r} 와 달라졌습니다. 두 자리가 같은 "
        "판매를 다른 단가로 세면 구조 비교(FR-202)가 구조의 차이가 아니라 "
        "배선의 차이를 재게 됩니다"
    )
    assert keys[_VARIABLE] != TARIFF_KEY, (
        f"기본 경로가 약관요금({TARIFF_KEY})으로 잉여를 판다 — 그것은 상계거래가 "
        "**회피한 요금**으로 쓰는 값이며, 판매단가로 쓰면 소매가로 파는 사업이 "
        "됩니다"
    )


@pytest.mark.req("NFR-202-M1")
def test_the_two_prices_are_separate_ledger_items() -> None:
    """★★ 사는 단가와 파는 단가가 **다른 항목**에서 온다.

    한쪽 키로 둘을 가리키면 대장을 고칠 때 둘이 함께 움직이고, 그 순간 저장장치
    차익거래의 손익이 **대장 한 줄에 매인다** — R35 가 없앤 「우연히 같다」가
    이번에는 *구조적으로* 같아지는 것이며 더 나쁘다(우연은 실측하면 드러나지만
    구조는 드러나지 않는다).

    ⚠ **값의 크기를 단언하지 않는다.** 「판매가 구매보다 싸다」는 지금 실측이지
    도메인 규칙이 아니다 — 대장의 두 범위(80~150 · 80~170)가 겹치므로 단언하면
    검사가 없는 규칙을 발명하게 된다.
    """
    keys = ledger_backed_variables()
    assert keys[_VARIABLE] != keys["grid_purchase_price"], (
        f"두 변수가 같은 대장 키({keys[_VARIABLE]})를 가리킨다 — 사는 값과 파는 "
        "값이 한 줄로 묶였습니다"
    )


@pytest.mark.req("NFR-202-M1")
def test_the_appendix_formula_carries_the_price_and_the_quantity() -> None:
    """★★★ **붙임 4 의 산식이 그 단가를 싣는다** (R36).

    R35 ① 은 이 단가를 대장으로 올려 **영향도 1위**임을 실측했다. 그런데 그 값이
    **붙임 4 어디에도 없었다** — 편익 산식이 `대표일 1,771원 × 365일` 이라 곱해서
    나온 금액만 있고 무엇에 얼마를 곱했는지가 없었다. 비용 쪽은 같은 자리에
    `대표일 수전 6.19kWh × 365일 × 120원/kWh` 로 갈라 적는다.

    ★ **수량과 단가를 함께 본다.** 단가만 보면 산식이 단가를 적어 두고 수량은
    엉뚱한 것을 실어도 통과한다 — 그 둘의 **곱이 실린 금액과 맞는가**까지
    본다(R35 ② 가 「거리만 보는 검사는 거짓 문장을 통과시킨다」에서 세운 형태).
    """
    price = 137.0
    outcome = run_single_case_e2e(
        {}, level_map=_level_map(price), horizon_years=_PROBE_HORIZON
    )
    line = next(x for x in outcome.basis.benefits if x.tag == _SURPLUS_TAG)

    assert f"{price:,.0f}원/kWh" in line.formula, (
        f"붙임 4 의 잉여판매 산식에 판매단가가 없다 — 「{line.formula}」\n"
        "영향도 1위 인자의 값이 리포트 어디에도 없으면, 검토자는 그 금액이 왜 "
        "그 금액인지 확인할 수 없습니다"
    )

    quantity = _quantity_kwh(line.formula)
    assert _annualised(quantity, price) == pytest.approx(line.annual_won, rel=1e-3), (
        f"산식에 실린 수량과 단가의 곱이 실린 금액과 다르다 — "
        # RUF001: 실패 메시지가 산식 문면과 같은 모양이어야 대조가 된다.
        f"「{line.formula}」\n{quantity:,.2f}kWh × {price:,.0f}원/kWh × "  # noqa: RUF001
        f"{DAYS_PER_YEAR}일 ≠ {line.annual_won:,}원"
    )


def _quantity_kwh(formula: str) -> float:
    """산식 문면에서 **대표일 수량**을 읽는다.

    ⚠ 문면을 파싱하는 검사는 표기를 조금 다듬어도 깨진다. 그래도 이 자리에서는
    파싱이 옳다 — 재는 것이 *「검토자가 **읽는 그 수**가 금액과 맞는가」* 이기
    때문이다. 구현에서 수량을 다시 받아 오면 **리포트에 실제로 인쇄된 수**가
    아니라 그것을 만든 값을 검산하게 되고, 그 사이의 어긋남이 그대로 남는다.
    """
    match = re.search(r"([\d,]+\.\d+)kWh", formula)
    assert match, f"산식에서 kWh 수량을 못 읽었다 — 「{formula}」"
    return float(match.group(1).replace(",", ""))
