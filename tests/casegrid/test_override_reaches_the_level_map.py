"""사용자가 고친 값이 **수준표를 거쳐 러너에 닿는가** — `FR-602-AC1` · `NFR-202`.

## 무엇이 틀려 있었나 (R63 V2 브라우저 검수 D10)

`build_case_report()` 는 **통로를 둘** 갖고 있었다:

    provider  = apply_scenario_overrides(provider, …)   ← 오버라이드가 얹힌다
    level_map = build_level_map(assumptions_path)       ← 파일에서 다시 읽는다

러너가 단가·요금·할인율을 받는 자리는 `provider` 가 아니라 `level_map` 이다
(`core/casegrid/e2e_runner.py::run_single_case_e2e(level_map=…)`). 그래서
`capex.pv.rooftop` 을 1,600,000 → 1,500,000 으로 고쳐도 결론축은 **1원도 움직이지
않았고**, 그런데도 붙임 1 의 「기준 전제 대비 변경 항목」은 그 두 값을 나란히
인쇄했다 — `core/assumption/scenario_overrides.py` 머리말이 *「화면은 고친 값을
인쇄하고 수는 옛 값으로 돈다」* 로 「가장 나쁘다」고 지목한 바로 그 상태다.

실측(오케스트레이터 · `.orch/R63/WP-FIX2.md` §A-1)으로 대장 39항목 중 축을
움직인 것은 **셋뿐**이었다 — `benefit.rec_price`·`benefit.rec_weight_pv`(둘 다
`provider.get()` 직독 갈래)와 `analysis.period_years`. `_LEDGER_VARS` 12축은
**전건 Δ = 0** 이었다.

## 이 파일이 갈라서 붙드는 두 가지

    ① 사용자가 값을 고치면 축이 **움직인다**       ← 고치는 목표
    ② 오버라이드가 없으면 축이 **안 움직인다**     ← 고치면서 깨면 안 되는 것

②를 함께 재지 않으면 ①을 통과시키는 가장 싼 방법이 *「수준표를 아무 값으로나
다시 짓기」* 가 된다. 기본값 실행의 결론축(무보조 `npv`)은 이 저장소의 회귀
기준이며 **골든 픽스처가 그 정본**이다 — 그래서 여기서 수를 리터럴로 적지 않고
`fixtures/golden/scenario_unsubsidized.yaml` 을 다시 읽어 대조한다. 리터럴로
적으면 그것이 사본이 되고, 골든을 고치는 날 이 파일이 따라오지 않아도 조용하다.

## ⚠ 「기준」 수준 하나만 바꾼다 — 재서 정했다

대장에서 `sensitivity` 를 가진 25항목을 실측한 결과 **전건에서 `base == value`**
이고(어긋난 항목 0건), `low`·`high` 는 기준값의 **일정한 배수가 아니다**:
`capex.pv.rooftop` 은
±20%(그 항목 `derivation_method` 가 *「FR-801 결합 집합의 기본 3수준과 같은
폭」* 이라 적는다), `load.household.annual` 은 0.75·1.33(서로 다른 조사 두 건),
`tariff.hv_single_contract.energy_only` 는 150−30·120−38·190−19 로 **각각 따로
유도**된다. 즉 세 수준은 규칙으로 생성된 것이 아니라 **항목마다 따로 조사된
띠**이며, 사용자가 고친 값이 그 띠를 함께 끌고 가야 할 근거가 대장에 없다.

⇒ **오버라이드는 `base` 한 자리에 얹고 `low`·`high` 는 대장 것을 남긴다.**
그 결과 5.1 영향도 스윕의 폭은 여전히 대장이 조사한 폭이다 — 사용자가 자기
단가를 넣어도 *「그 단가가 얼마나 틀릴 수 있는가」* 는 대장이 말한다.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.casegrid.ledger_levels import build_level_map, ledger_backed_variables
from core.report.case_report import build_case_report

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"

#: 사용자 문면이 든 다섯 중 **둘**이 이 키에 걸려 있다 — *「설비별 단가」*·
#: *「전기요금」* (`docs/decisions-2026-09-05-R63.md` §1).
_PV_UNIT_COST = "capex.pv.rooftop"
_GRID_PRICE = "tariff.hv_single_contract.energy_only"


def _ledger_items() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    return {item["key"]: item for item in data["assumptions"]}


def _plain(level_map: Mapping[str, Mapping[str, float]]) -> dict[str, dict[str, float]]:
    """읽기 전용 매핑을 견줄 수 있는 보통 사전으로 편다."""
    return {name: dict(levels) for name, levels in level_map.items()}


def _golden_npv() -> float:
    """골든 픽스처가 선언한 무보조 `npv` — **여기 수를 적지 않는다.**

    회귀 기준의 정본은 `fixtures/golden/scenario_unsubsidized.yaml` 이고
    `tests/golden/test_regression_scenarios.py` 가 같은 자리를 읽는다. 이
    파일이 자기 리터럴을 들면 정본이 둘이 되고, 골든을 옮기는 날 한쪽만
    고쳐진 상태를 아무도 보지 않는다.
    """
    case = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8"))
    return float(case["expected_values"]["npv_won"])


def _npv(tmp_path: Path, overrides: list[dict[str, Any]] | None) -> float:
    """골든 시나리오를 **실행 경로 그대로** 돌려 결론축을 낸다."""
    body = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8"))
    if overrides is not None:
        body["assumption_overrides"] = overrides
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    return float(build_case_report(path, assumptions_path=_ASSUMPTIONS).metrics["npv"])


# ── ① 인자를 안 주면 종전과 **같은 표**다 — 기존 호출부가 안 깨진다 ──────


def test_the_table_is_unchanged_when_no_override_is_given() -> None:
    """`build_level_map(path)` 은 종전 그대로다 — 호출부 20여 곳이 그 꼴이다.

    새 인자를 필수로 만들면 그 호출부가 전부 값을 지어내야 하고, 지어낸 값이
    곧 사본이 된다. `None` 과 빈 사전이 **같은 표**를 내는 것도 함께 잰다 —
    `AssumptionSet.get_overrides()` 는 오버라이드가 없을 때 빈 매핑을 주므로,
    그 둘이 갈리면 기본값 실행이 통로가 생기기 전과 다른 표로 돈다.
    """
    plain = _plain(build_level_map(_ASSUMPTIONS))

    assert _plain(build_level_map(_ASSUMPTIONS, overrides=None)) == plain
    assert _plain(build_level_map(_ASSUMPTIONS, overrides={})) == plain


# ── ② 오버라이드는 「기준」 한 자리에만 얹힌다 ───────────────────────────


@pytest.mark.req("FR-602-AC1")
def test_an_override_moves_the_base_level_and_leaves_the_band_alone() -> None:
    """고친 값이 `base` 에 앉고 `low`·`high` 는 **대장 것**으로 남는다.

    띠를 함께 끌고 가지 않는 근거는 이 파일 머리말에 있다 — 세 수준은 규칙이
    아니라 항목마다 따로 조사된 폭이다.
    """
    ledger = _ledger_items()[_PV_UNIT_COST]["sensitivity"]
    mine = 1_500_000.0

    levels = build_level_map(_ASSUMPTIONS, overrides={_PV_UNIT_COST: mine})[
        "pv_unit_cost"
    ]

    assert levels["base"] == pytest.approx(mine), "고친 값이 기준 수준에 안 앉았다"
    assert levels["low"] == pytest.approx(float(ledger["low"]))
    assert levels["high"] == pytest.approx(float(ledger["high"]))


def test_only_the_overridden_variable_moves() -> None:
    """한 키를 고쳐도 **나머지 축은 그대로**다 — 표를 다시 짓지 않는다."""
    before = _plain(build_level_map(_ASSUMPTIONS))
    after = _plain(build_level_map(_ASSUMPTIONS, overrides={_PV_UNIT_COST: 1_500_000}))

    moved = [name for name in before if before[name] != after[name]]
    assert moved == ["pv_unit_cost"], f"함께 움직인 축이 있다 — {moved}"


@pytest.mark.req("NFR-202-M1")
def test_an_override_goes_through_the_same_unit_scale() -> None:
    """`%/년` 항목은 오버라이드도 **비율로 환산**된다 — 환산이 한 자리다.

    환산을 빠뜨리면 「2.5% 대신 250%」가 아니라 **그럴듯한 큰 수**가 나오고,
    그것이 옆 파일(`test_ledger_levels.py` 의
    `test_percent_per_year_is_converted_once`)이 대장 값에 대해 이미 붙들고
    있는 사실이다. 오버라이드가 그 자리를 우회하면 같은 축에 환산된 값과
    안 된 값이 섞인다.
    """
    levels = build_level_map(
        _ASSUMPTIONS, overrides={"escalation.electricity_tariff": 5.0}
    )["tariff_escalation"]

    assert levels["base"] == pytest.approx(0.05), "퍼센트가 그대로 들어왔다"


def test_a_key_that_is_not_a_sweep_axis_leaves_the_table_alone() -> None:
    """축이 아닌 키는 표를 **건드리지 않는다** — 거부하지도 않는다.

    `tax.vat_rate` 는 대장에 있으나 아무도 읽지 않고(`core/contracts/der.py`),
    `benefit.rec_price` 는 `provider.get()` 직독 갈래로 실행에 닿는다. 둘 다
    수준표의 축이 아니므로 여기서 할 일이 없다 — 그렇다고 거부하면 정당한
    오버라이드가 막힌다. **어느 키가 실제로 먹는지는 실행마다 다르며 그 목록을
    여기 박으면 낡는다**(`scenario_overrides.py` 머리말의 같은 판단).
    """
    before = _plain(build_level_map(_ASSUMPTIONS))
    after = _plain(
        build_level_map(
            _ASSUMPTIONS, overrides={"tax.vat_rate": 0.2, "benefit.rec_price": 140}
        )
    )

    assert after == before
    assert "tax.vat_rate" not in set(ledger_backed_variables().values())


def test_a_non_numeric_override_on_a_sweep_axis_is_refused() -> None:
    """축 값이 수가 아니면 **여기서 멈춘다** — 표 깊은 곳에서 터지지 않게.

    ⚠ **이 갈래는 배포 경로로는 닿지 않는다.** 시나리오에서 들어온 값은
    `resolve_assumption_overrides` 가 이미 대장 값과 **형을 맞대어** 걸렀고,
    수준표의 축은 전건이 수 항목이다. 붙드는 것은 그 관문을 **거치지 않고**
    이 함수를 직접 부르는 자리(시험·계측 스크립트가 20여 곳에서 그렇게
    부른다)이며, 없으면 같은 입력이 `float()` 에서 맨 `TypeError` 로 터져
    「어느 항목이·왜·어떻게」가 없는 오류가 된다.
    """
    with pytest.raises(ValueError) as caught:
        build_level_map(_ASSUMPTIONS, overrides={_PV_UNIT_COST: "비싸다"})

    message = str(caught.value)
    assert _PV_UNIT_COST in message, "어느 항목인지 말하지 않는다"
    assert "수" in message, "왜 거부됐는지 말하지 않는다"


# ── ③ ★★ 실행 경로 — 갈라서 단정한다 ────────────────────────────────────


def test_a_run_without_overrides_still_lands_on_the_golden_conclusion(
    tmp_path: Path,
) -> None:
    """★★★ **오버라이드가 없으면 결론축이 움직이지 않는다.**

    이 라운드가 지키기로 한 수이며(`docs/decisions-2026-09-05-R63.md` §1 —
    *「움직이면 그것이 새 결함이다」*), 위 ①의 「같은 표」와 짝을 이룬다. 수는
    골든 픽스처에서 읽는다 — 사유는 `_golden_npv()` 독스트링.
    """
    assert _npv(tmp_path, None) == pytest.approx(_golden_npv())


@pytest.mark.req("FR-602-AC1")
def test_a_cheaper_pv_unit_cost_raises_the_conclusion(tmp_path: Path) -> None:
    """★★★ **D10 재현** — 설비 단가를 낮추면 결론축이 **올라야** 한다.

    V2 가 브라우저로 눌러 본 그 조작이다(`.orch/R63/result_V2.md` §2 D10):
    설정 화면에서 `capex.pv.rooftop` 을 1,600,000 → 1,500,000 으로 고쳐
    저장하고 그 설정을 시나리오에 붙여 실행했더니 `npv` 가 −11,552,270 에서
    **1원도 움직이지 않았다.**

    ⚠ **방향과 부호를 단정한다** — 「움직인다」만 재면 배선을 거꾸로 걸어도
    통과한다. 단가가 내려가면 CAPEX 가 줄고 `npv` 는 **올라간다.**
    """
    base = _npv(tmp_path, None)

    cheaper = _npv(
        tmp_path,
        [{"key": _PV_UNIT_COST, "value": 1_500_000, "reason": "2026년 견적"}],
    )

    assert cheaper > base, (
        f"설비 단가를 낮췄는데 결론축이 오르지 않았다 — {base:,.0f} → {cheaper:,.0f}"
    )


@pytest.mark.req("FR-602-AC1")
def test_a_dearer_grid_energy_price_lowers_the_conclusion(tmp_path: Path) -> None:
    """★★★ **전기요금도 움직인다** — 사용자 문면이 든 다섯 중 둘째다.

    `tariff.hv_single_contract.energy_only` 는 저장장치가 계통에서 받아 오는
    전력의 한계단가다(`ledger_levels.py` 의 `grid_purchase_price` 주석).
    비싸지면 그 구매 비용이 늘어 `npv` 는 **내려간다** — V2 실측에서는
    200원/kWh 로 올려도 Δ = 0 이었다.
    """
    base = _npv(tmp_path, None)

    dearer = _npv(tmp_path, [{"key": _GRID_PRICE, "value": 200, "reason": "계약 갱신"}])

    assert dearer < base, (
        f"전기요금을 올렸는데 결론축이 내려가지 않았다 — {base:,.0f} → {dearer:,.0f}"
    )
