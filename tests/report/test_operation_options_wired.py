"""**개선 방안을 표현할 통로 넷이 실행까지 간다** — R71/WP-6.

`.orch/R71/result_5.md` 가 실측한 대로, 러너 `run_single_case_e2e` 는 인자를
스무 개 넘게 받는데 **시나리오가 닿는 것은 아홉뿐**이었다. 닿지 않는 것 중
개선 폭이 가장 큰 넷이 이 파일의 대상이다:

    cp_price_won_per_kw_month   ← 대장 `benefit.cp_price`
    nwas_price_won_per_kwh      ← 대장 `benefit.nwas_price`
    ess_operating_mode          ← 시나리오 `operation_options`
    pv_allocation_priority      ← 시나리오 `operation_options`

## ★★ 이 파일이 실제로 고치는 것 — **대장이 적어 둔 문장이 거짓이었다**

`docs/assumptions.yaml` 의 `benefit.cp_price`·`benefit.nwas_price` 는
`applicable_scope` 에 *「실행 경로가 이 값을 … 단가로 읽는다」* 고 쓴다. 그런데
리포트 경로는 그 값을 러너에 **넘기지 않았고**(`grep cp_price_won_per_kw_month
core/report/case_report.py` → 0건), 그래서 대장을 아무리 고쳐도 `CP` 편익은
0원이었다 — 「선언·계산은 있는데 읽는 쪽이 없다」의 또 한 사례다.
`test_raising_the_ledger_cp_price_lights_up_the_cp_benefit` 가 그 문장을
**참으로 만든 것**을 잰다.

## ⚠ 「안 준 실행이 종전과 같다」의 정본은 여기가 아니다

골든 회귀(`tests/golden/test_regression_scenarios.py`)와
`scripts/verify_ladder.py check --deep` 가 그것을 잰다 — 골든 셋에
`operation_options` 필드가 없으므로 그 회귀가 통째로 이 축의 불변을 잰다.
다만 **「빈 매핑·명시 기본값 = 종전」** 한 가지는 골든이 재지 못하므로(그
실행은 필드를 «적은» 실행이다) 여기서 함께 본다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.assumption.scenario_overrides import ASSUMPTION_OVERRIDES_FIELD
from core.casegrid.ledger_levels import OPERATION_OPTIONS_FIELD
from core.contracts.validation import ValidationError
from core.report.case_influences import CONCLUSION_METRIC
from core.report.case_report import (
    CP_PRICE_LEDGER_KEY,
    NWAS_PRICE_LEDGER_KEY,
    CaseReport,
    build_case_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"


def _report(
    operation_options: object | None = None,
    *,
    ledger_prices: dict[str, float] | None = None,
) -> CaseReport:
    """골든 시나리오 + 통로 넷 → 리포트 하나.

    ⚠ **골든 픽스처를 고치지 않는다** — `test_design_capacity_wired.py::_report`
    와 같은 모양으로 `tempfile` 안에만 쓴다.

    ⚠ **단가는 새 필드가 아니라 `assumption_overrides` 로 준다** — 그것이 이
    WP 의 판정이다(단가는 **값**이고 대장이 그 소유자다). 통로를 또 내면 둘이
    되고, 그때 어느 것이 이겼는지 산출물에서 알 수 없다.
    """
    fields: dict[str, Any] = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    if operation_options is not None:
        fields[OPERATION_OPTIONS_FIELD] = operation_options
    if ledger_prices:
        fields[ASSUMPTION_OVERRIDES_FIELD] = [
            {"key": key, "value": value, "reason": "R71/WP-6 배선 확인"}
            for key, value in ledger_prices.items()
        ]
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / _GOLDEN.name
        path.write_text(
            yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return build_case_report(path, assumptions_path=_ASSUMPTIONS)


def _npv(report: CaseReport) -> float:
    return float(report.metrics[CONCLUSION_METRIC])


def _benefits(report: CaseReport) -> dict[str, int]:
    """편익 갈래 → 1년차 금액(원). **배선의 증거는 여기 있다.**

    결론축만 보면 「값을 나르기만 하고 다른 데서 상쇄됐다」와 구별되지 않는다.
    """
    return {line.tag: line.annual_won for line in report.basis.benefits}


def test_writing_the_deployment_defaults_changes_nothing() -> None:
    """① **적지 않으면 종전과 같다** — 배포 기본값을 명시로 적어도 같은 결과다.

    이 두 실행이 갈리면 통로가 값을 나르는 것이 아니라 **다른 경로를 태우고**
    있다는 뜻이고, 그때 골든 불변은 「안 적었으니 안 지났다」로만 지켜진다.
    """
    baseline = _report()
    explicit = _report({"ess_operating_mode": "자가소비 우선", "pv_allocation_priority": "집 우선"})
    assert _npv(explicit) == pytest.approx(_npv(baseline), abs=1.0)
    assert _benefits(explicit) == _benefits(baseline)


def test_an_empty_mapping_is_the_same_as_not_writing_it() -> None:
    """① 빈 매핑도 **「적지 않았다」와 같다** — 두 인자가 `None` 으로 간다."""
    assert _npv(_report({})) == pytest.approx(_npv(_report()), abs=1.0)


def test_choosing_battery_first_moves_the_conclusion() -> None:
    """② ★★★ **배분 우선순위가 실행에 닿는다** — 결론축이 실제로 움직인다.

    `.orch/R71/result_5.md` §4 (아): 「배터리 우선」이 잉여판매·REC 를 **한꺼번에
    살린다**(Δ npv +322,053원). 결론축만 보면 「나르기만 했다」와 구별되지 않아
    편익 갈래까지 본다.
    """
    baseline, moved = _report(), _report({"pv_allocation_priority": "배터리 우선"})
    assert _npv(moved) != pytest.approx(_npv(baseline), abs=1.0), (
        f"「배터리 우선」을 골라도 결론축이 {_npv(baseline):,.0f}원 그대로다 — "
        "operation_options 가 러너에 닿지 않았다"
    )
    assert _benefits(baseline)["SurplusSale"] == 0
    assert _benefits(moved)["SurplusSale"] > 0, "잉여판매가 서지 않았다"
    assert _benefits(moved)["REC"] > 0, "REC 가 서지 않았다"


def test_choosing_semi_central_dispatch_turns_off_peak_shaving() -> None:
    """② ★★ **운전 방법이 실행에 닿는다** — 계통 급전을 고르면 사용자 운전
    편익(`PeakShaving`)이 **0 이 된다.**

    방전 시점을 사업자가 정하지 못하는 구조이므로 피크저감이 성립하지 않는다
    (`docs/decisions-2026-08-31-R48.md` §2). 단가가 0원인 동안에도 **이 축은
    움직인다** — 그래서 단가와 따로 잰다.
    """
    assert _benefits(_report())["PeakShaving"] > 0
    assert _benefits(_report({"ess_operating_mode": "준중앙급전 등록"}))["PeakShaving"] == 0


def test_raising_the_ledger_cp_price_lights_up_the_cp_benefit() -> None:
    """④ ★★★ **대장이 적어 둔 문장이 이제 참이다.**

    `benefit.cp_price` 를 `assumption_overrides` 로 올리고 운전 방법을 「준중앙
    급전 등록」으로 두면 `CP` 편익이 **0 이 아니게 된다.** 이 배선이 없던 동안
    대장의 `applicable_scope` 는 *「실행 경로가 이 값을 … 읽는다」* 라고 적으면서
    실제로는 읽지 않았다.
    """
    lit = _report(
        {"ess_operating_mode": "준중앙급전 등록"},
        ledger_prices={CP_PRICE_LEDGER_KEY: 10_000.0},
    )
    assert _benefits(lit)["CP"] > 0, "대장 단가를 올렸는데 CP 편익이 0원이다"
    assert _npv(lit) > _npv(_report({"ess_operating_mode": "준중앙급전 등록"})), (
        "CP 단가가 결론축을 움직이지 않았다 — 금액만 인쇄되고 계산에 안 들어갔다"
    )


def test_the_cp_price_alone_does_nothing_without_the_operating_mode() -> None:
    """④ **넷이 한 묶음이다** — 단가만 올리면 `CP` 는 켜지지 않는다.

    운전 방법이 「자가소비 우선」이면 그 편익이 `enabled=False` 이기 때문이며,
    그 조합을 **예외 없이** 지나간다는 것이 이 시험이 잡는 함정이다(대장만
    고치고 「반영됐다」로 읽는 자리).
    """
    only_price = _report(ledger_prices={CP_PRICE_LEDGER_KEY: 10_000.0})
    assert _benefits(only_price)["CP"] == 0
    assert _npv(only_price) == pytest.approx(_npv(_report()), abs=1.0)


def test_the_nwas_price_reaches_the_runner_even_though_the_quantity_is_zero() -> None:
    """④ `benefit.nwas_price` 도 **같은 통로로 닿는다** — 다만 지금 구성에서는
    계통 방전 수량이 0kWh 라 금액이 0원이다(`.orch/R71/result_5.md` §4 마).

    ⚠ **그 0 을 「배선이 없다」로 읽지 않기 위해** 여기 적어 둔다: 단가를 올린
    실행이 **거부 없이** 지나가고 `NWAs` 갈래가 산출물에 서 있다는 것이 이
    시험이 잡는 전부다. 수량이 서는 날(ⓑ)은 이 단언이 바뀐다.
    """
    lit = _report(
        {"ess_operating_mode": "계통 방전"},
        ledger_prices={NWAS_PRICE_LEDGER_KEY: 100.0},
    )
    assert "NWAs" in _benefits(lit)
    assert _benefits(lit)["PeakShaving"] == 0, "계통 방전인데 피크저감이 남아 있다"


@pytest.mark.parametrize(
    "value",
    [
        {"ess_charge_source": "계통"},
        {"ess_operating_mode": "GRID_DISCHARGE"},
        "준중앙급전 등록",
    ],
    ids=["모르는 키", "열거 이름", "매핑이 아니다"],
)
def test_a_bad_operation_option_is_refused_with_three_elements(value: object) -> None:
    """③ 조용히 무시되지 않고 **3요소로** 거부된다 (`NFR-303`) — 배선 경로에서.

    함수 단위 확인은 `tests/casegrid/test_ledger_levels.py` 가 하고, 여기서는
    **리포트 경로가 그 거부를 지나는지**를 본다(해석이 호출부로 새면 함수만
    초록불이고 실행은 조용히 무시한다).
    """
    with pytest.raises(ValidationError) as caught:
        _report(value)
    error = caught.value
    assert error.field == "operation.options"
    assert error.reason.strip()
    assert "준중앙급전 등록" in error.action
