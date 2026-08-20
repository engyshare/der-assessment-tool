"""골든 3종 회귀 스냅숏 — **이 파일이 무엇을 재고 무엇을 못 재는가.**

정본은 작업목록 16.4 다: *「가정값 위의 골든은 회귀 테스트이지 정확도 테스트가
아니다. … 이 3종이 통과한다는 것은 «계산이 어제와 같다» 는 뜻이지 «계산이 맞다»
는 뜻이 아니다.」* 아래 대조가 초록불인 것은 그 뜻이며, 그 이상을 주장하지 않는다.

## ① 이 골든이 넘기는 현금흐름의 모양 — 편익 **한 행**, 비용 행 없음

`_reference_metrics()` 와 `_scenario_metrics()` 는 둘 다 `benefit_row` 하나만
세운다. 한 해에 행이 하나뿐이므로 **행 단위 순회와 연 단위 순회가 같은 목록을
낸다** — 그래서 `payback_simple` 이 R38 까지 한 해의 행을 합치지 않고 한 걸음씩
세고 있었는데도 세 시나리오가 전건 초록불이었다. **이 골든은 그 결함의 파수꾼이
아니다.** 그 자리를 보는 검사는 `tests/cba/test_indicators.py` 와
`tests/cba/test_metrics.py` 의 「한 해에 행이 여럿」 구획에 있다.

## ② 실행 경로의 모양은 다르다 — 여기가 재는 것이 아니다

실물은 `core/casegrid/e2e_runner.py::net_operating_flows()` 를 지나며 **편익
1행 + 부호를 뒤집은 비용 여러 행**(`PVFixedOM`·`ESSFixedOM`·`GridPurchase`·
정산 수수료)을 만든다. 그 경계를 붙드는 것은 `tests/casegrid/test_e2e_cost_sign.py`
다. 즉 **두 모양이 갈려 있고, 갈린 자리를 각각 다른 검사가 붙든다.** 이 갈림
자체는 조항 위반이 아니다(위 16.4) — 다만 이 파일의 초록불을 「실행 경로가
맞다」로 읽으면 안 된다.

## ③ 왜 아직 옮기지 않는가 — 옮기는 조건

모양을 옮기면 `fixtures/golden/*.yaml` 의 `expected_values` 6개가 전부 바뀌고,
무보조 시나리오의 `npv` 는 **부호가 뒤집힌다**(R38 실측. 단 `GridPurchase` 와
정산 수수료 행을 채우지 못했으므로 그 실측은 변화폭의 **하한**이다). 「어제와
같다」를 재는 자리의 기준점을 흔드는 일이므로 **한 번만** 해야 한다. 그런데 지금
골든 안에는 `GridPurchase` 단가도 정산 구조도 없고, 교체비·잔존가치 배선이 비용
행을 더 늘린다 — 지금 옮기면 옛 모양을 **또 다른 잠정 모양**으로 바꾸는 것이다.

→ **옮기는 시점은 그 배선이 끝나 비용 행 구성이 확정된 뒤이며, 그때 위 6개를
함께 재산출한다.** 세 yaml 머리글이 같은 조건을 가리킨다.

## ④ 세 yaml 이 선언한 출처는 위 두 수를 낼 수 없다 — 별개 축, 고치지 않았다

세 yaml 은 오라클 순위 3(외부 공표 실적)과 출처 파일
`tests/integration/test_wave2_end_to_end.py` 를 선언한다. 그 파일을 열어 보면
**회수기간을 아예 계산하지 않고**, `npv` 에도 수치 단언이 없다(형과 정수 여부만
본다). 게다가 행 구성이 편익 1행 + 고정 O&M 2행이며 `total_row()` 로 합쳐
넘긴다 — 위 ①과 다른 모양이다. 즉 **선언된 출처는 세 yaml 의 두 수를 낼 수
없다.**

이것은 ①~③의 「모양」 축과 다른 **정박** 축이며, 정본이 이미 유예해 둔 자리다
(작업목록 16.1b ④ — Q-4·Q-5 회신이 §13.3 판정을 연다). 기계로 적어 둔 자리는
`tests/ci/test_performance_and_golden.py` 의
`test_repo_golden_files_are_readable_and_declare_an_oracle_rank_and_source`
독스트링이다. 순위·출처 필드는 주석이 아니라 파서가 읽는 값이므로 R38-C2 는
**값을 고치지 않고 사실만 남겼다.**
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from core.cba.metrics import npv, payback_simple
from core.cba.proforma import benefit_row
from core.contracts.der import DispatchContext, DispatchResult
from core.contracts.units import Money
from core.der.ess import ESS, ESSOperatingMode
from core.der.pv import PV, OperatingMode
from core.engine.rule_based import RuleBasedEngine
from core.incentive.schemas import IncentiveScheme
from core.valuestream import PeakShaving, SurplusSale

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
DISCOUNT_RATE = 0.045
HORIZON_YEARS = 20
HOURS_PER_DAY = 24
DAYS_PER_YEAR = 365


def _load_case(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path.name} is not a mapping"
    return loaded


def _expected_values(case: dict[str, Any]) -> dict[str, float]:
    expected = case.get("expected_values")
    if not isinstance(expected, dict):
        return {}
    return {
        key: float(value)
        for key, value in expected.items()
        if isinstance(value, (int, float))
    }


def _reference_metrics() -> dict[str, float]:
    pv = PV(
        name="integration-pv",
        capacity_kw=3.0,
        capacity_factor=0.15,
        unit_capex_won_per_kw=1_500_000,
        fixed_om_won_per_year=100_000,
        escalation_rate=0.02,
        self_consumption_ratio=0.0,
        operating_mode=OperatingMode.FULL_EXPORT,
    )
    ess = ESS(
        name="integration-ess",
        capacity_kwh=10.0,
        power_kw=5.0,
        rte_pct=90.0,
        soc_min_pct=10.0,
        soc_max_pct=90.0,
        cycle_life=6_000,
        calendar_life=20,
        eol_soh_pct=80.0,
        cycles_per_year=365.0,
        operating_mode=ESSOperatingMode.PEAK_SHAVING,
        capex_unit_won_per_kwh=500_000,
        fixed_om_won_per_year=100_000,
    )

    ctx = DispatchContext(steps=HOURS_PER_DAY, dt=3_600, year=1)
    dispatch = RuleBasedEngine().run([pv, ess], ctx)
    grid_export_result = DispatchResult(
        electric=list(dispatch.grid_export),
        heat=[0.0] * ctx.steps,
        cool=[0.0] * ctx.steps,
        fuel=[0.0] * ctx.steps,
    )

    surplus = SurplusSale(sale_price_won_per_kwh=120.0).annual_value(
        grid_export_result, year=1
    )
    peak = PeakShaving(
        monthly_peak_reduction_kw=[ess.reducible_peak_kw(year=1)] * 12,
        demand_charge_won_per_kw_month=8_320.0,
    ).annual_value(grid_export_result, year=1)
    annual_benefit = Money(surplus * DAYS_PER_YEAR + peak)

    base_capex = Money(int(pv.capex(year=1) + ess.capex(year=1)))
    # ⚠ **편익 한 행. 비용 행이 없다.** 이 모양이 무엇을 못 재는지와 언제
    # 옮기는지는 **모듈 독스트링이 정본이다** — 여기에 다시 적지 않는다(같은
    # 사실이 두 곳에 있으면 한쪽만 고쳐진다).
    rows = [
        benefit_row(
            "annual_benefit",
            {year: int(annual_benefit) for year in range(1, HORIZON_YEARS + 1)},
        )
    ]

    return {
        "annual_benefit_won": float(int(annual_benefit)),
        "base_capex_won": float(int(base_capex)),
        "npv_won": float(int(npv(base_capex, rows, DISCOUNT_RATE))),
        "payback_period_years": float(payback_simple(base_capex, rows)),
    }


def _scenario_metrics(subsidy_rate: float) -> dict[str, float]:
    metrics = _reference_metrics()
    base_capex = int(metrics["base_capex_won"])
    annual_benefit = int(metrics["annual_benefit_won"])

    scheme = IncentiveScheme(
        subsidy_rate=subsidy_rate,
        loan_rate=0.0,
        loan_interest=0.0,
        loan_grace_years=0,
        loan_repayment_years=0,
        loan_repayment_type="\uc6d0\ub9ac\uae08\uade0\ub4f1",
        tax_credit_rate=0.0,
        sponsor="\uad6d\ube44",
    )
    equity = scheme.calculate_financing(base_capex)["equity"]
    initial_investment = Money(int(equity))
    # ⚠ 여기도 **편익 한 행**이다. 그리고 **실제로 대조에 쓰이는 것은 이쪽이다**
    # — 아래 회귀 검사와 `tests/acceptance2/test_17_7_dod7.py` 가 부르는 함수가
    # 이 함수다. 이 모양이 못 재는 것은 모듈 독스트링 ①·②를 볼 것.
    rows = [
        benefit_row(
            "annual_benefit",
            {year: annual_benefit for year in range(1, HORIZON_YEARS + 1)},
        )
    ]

    return {
        "npv_won": float(int(npv(initial_investment, rows, DISCOUNT_RATE))),
        "payback_period_years": float(payback_simple(initial_investment, rows)),
    }


def _compare(path: Path, expected: dict[str, float], actual: dict[str, float]) -> None:
    for key, expected_value in expected.items():
        assert key in actual, f"{path.name}: missing actual value for {key}"
        if key == "npv_won":
            assert actual[key] == expected_value, (
                f"{path.name}: {key} expected {expected_value}, actual {actual[key]}"
            )
        else:
            assert actual[key] == pytest.approx(expected_value, rel=1e-3, abs=1e-3), (
                f"{path.name}: {key} expected {expected_value}, actual {actual[key]}"
            )


# `FR-1103-AC1` 을 함께 붙인 이유 (R17):
#
# 조항은 *「GitHub Actions 에서 pytest·ruff·**골든 시나리오 3종 수치 회귀**
# 통과 시에만 머지」* 다. **그 「수치 회귀」를 실제로 하는 것이 이 테스트다** —
# 계산값을 `expected_values` 와 대조한다. 그런데 마커가 `NFR-104-M1` 뿐이어서
# `FR-1103-AC1` 은 `tests/acceptance2/test_17_7_dod7.py` 의 **간접 확인**들로만
# 매핑돼 있었고, 그중 여럿이 *「파일이 있는지」·「필드가 있는지」* 수준이었다.
# 즉 **조항이 요구한 실검증은 존재했는데 그 조항이 그것을 가리키지 않았다.**
@pytest.mark.req("NFR-104-M1", "FR-1103-AC1")
@pytest.mark.parametrize("path", sorted(GOLDEN_DIR.glob("scenario_*.yaml")))
def test_golden_scenarios_match_current_regression_snapshot(path: Path) -> None:
    case = _load_case(path)
    expected = _expected_values(case)
    if not expected:
        print(f"SKIP {path.name}: expected_values are all null")
        pytest.skip(f"{path.name}: expected_values are all null")

    actual = _scenario_metrics(float(case["subsidy_rate"]))
    _compare(path, expected, actual)
