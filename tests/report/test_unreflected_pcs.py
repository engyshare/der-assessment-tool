"""★ **PCS 교체비 누락을 산출물이 «말하는가»** — R66/WP-2-fix.

## 무엇이 어긋나 있었는가

R66/WP-2 가 초기투자에 `PCS 단가 × 정격출력` 항을 세우면서 **그 설비의 수명은
세우지 않았다**(`ESS(pcs_lifetime=None)` · 소규모 PCS 내용연수 자료가 국내에
없다). 그 누락은 **비용 누락**이라 결론을 **좋은 쪽으로** 기울인다.

그 사실이 저장소 안에는 적혀 있었다 — 골든의 R66 블록 ·
`core/casegrid/ess_build.py::_case_ess_spec` 독스트링 · `.orch/R66/result_2.md`.
**그런데 리포트가 말하지 않았다.** 즉 *심의자가 「PCS 교체비가 빠져 있다」를 읽을
자리가 없었다* — 이 저장소가 반복해 경계해 온 *「선언과 구현이 갈린」* 형태의
표시층 판본이며, R40 ② 가 잡은 비대칭의 **반대 방향**이다.

## 이 파일이 재는 것 다섯

    ⓐ 붙임 8 에 항목이 **선다** — 라벨·방향·크기·사유·해소 칸이 비어 있지 않다
    ⓑ ★ PCS 수명이 켜지면 **사라진다**            ← 이 파일의 핵심
    ⓒ 본문 3.4 와 붙임 8 **양쪽**에 인쇄된다
    ⓓ 크기 칸의 단가가 **대장에서 온다** (리터럴 사본이 아니다)
    ⓔ ★ 2.1 자원 표가 **자기 취득비를 설명한다**  ← WP-2 가 깨 두었던 자리

**ⓑ 가 핵심이다.** `core/report/unreflected.py::_replacement_items` 가
*「배선이 들어오면 참인 조건 위에서 거짓을 계속 인쇄한다」* 를 경고한 바로 그
자리이며, 수명이 켜지는 날 이 항목이 남아 있으면 붙임 8 이 **이미 계상된 비용을
미반영으로** 싣는다.

**ⓔ 가 WP-2 의 별 결함이었다.** 그 라운드 뒤 2.1 표는 `500,000원/kWh` 를
인쇄하면서 같은 행의 취득비를 `105,000,000원`으로 적었다 — 500,000 × 200 kWh 는
100,000,000 이므로 **표에 적힌 단가·용량으로 초기투자를 되짚을 수 없었다.**

⚠ **금액 오라클을 대장에서 베끼지 않는다.** 아래 단정은 전부 `report` 가 들고 온
값(대장 행·용량 검토·자원 행)에서 **지어** 대조한다 — 리터럴로 적으면 대장이
바뀔 때 이 파일만 낡고, 그 상태는 아무것도 붙들지 않는다.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from core.casegrid.models import ONE_OFF_REPLACEMENT, OneOffLine
from core.report.case_report import build_case_report
from core.report.narrative import render_markdown
from core.report.unreflected import (
    DIRECTION_ADVERSE,
    JUDGED_MEASURED,
    build_unreflected,
    unreflected_rows,
)
from core.report.unreflected_pcs import (
    LABEL_PCS_REPLACEMENT,
    PCS_PRICE_LEDGER_KEY,
    pcs_replacement_gap,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"

#: 시스템 단가와 PCS 몫이 선 대장 자리 — `PCS_PRICE_LEDGER_KEY` 와 함께
#: 배터리 단가를 짓는다(`core/casegrid/ess_build.py::_case_ess_spec` 의 식).
_ESS_PRICE_KEY = "capex.ess.new"
_PCS_SHARE_KEY = "capex.ess.pcs_share_of_system"

#: 설계 변수 이름 — 용량 검토(4.4)가 「이 실행이 실제로 쓴 값」을 이 키로 낸다.
_ESS_CAPACITY_VAR = "ess_capacity_kwh"


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def _ledger(report) -> dict[str, float]:
    return {row.key: float(row.value) for row in report.assumptions}


def _pcs_item(report):
    found = [i for i in build_unreflected(report) if i.label == LABEL_PCS_REPLACEMENT]
    return found[0] if found else None


def _with_a_part_replacement(report):
    """PCS 교체가 **계상된** 리포트 — 수명이 켜진 뒤의 모습.

    ⚠ **`ess_build` 를 건드려 실제로 켜지 않는다.** 그 통로는 대장 → 러너 →
    조립기를 지나므로 실행을 한 번 더 돌려야 하고(붙임 8 검사 하나에 전건
    재계산이 붙는다), 무엇보다 **이 검사가 재려는 것은 판정 재료**다 —
    *「본체 수명으로 설명되지 않는 교체 연차가 있으면 항목이 사라지는가」*.
    그래서 그 연차 하나를 흐름 목록에 실어 판정이 갈리는지 본다
    (`tests/report/conftest.py::with_variable_om_row` 가 비용 행 하나로 같은
    일을 한다).

    ★ **11년차를 고른 것은 실측이다** — `pcs_lifetime=10` 을 실제로 켜면
    계상되는 ESS 교체 연차가 `[11, 18]` 이 된다(본체 17년 → 18년차 · PCS 10년
    → 11년차). 금액은 0 으로 둔다: 재는 것은 *판정이 연차를 보는가* 이고,
    금액을 넣으면 프로포마 항등식까지 함께 움직여 무엇이 판정을 뒤집었는지가
    흐려진다.
    """
    basis = report.basis
    owner = next(
        line.resource_name for line in basis.one_off_flows if line.tag.startswith("ESS")
    )
    return replace(
        report,
        basis=replace(
            basis,
            one_off_flows=(
                *basis.one_off_flows,
                OneOffLine(
                    tag="ESSReplacement",
                    label="ESSReplacement 교체비 (11년차)",
                    kind=ONE_OFF_REPLACEMENT,
                    year=11,
                    amount_won=0,
                    resource_name=owner,
                    formula="판정 확인용",
                ),
            ),
        ),
    )


# ── ⓐ 붙임 8 에 항목이 선다 ──────────────────────────────────────────

@pytest.mark.req("FR-104-AC4")
def test_the_pcs_replacement_gap_is_printed_with_a_size() -> None:
    """칸 여섯이 **전부** 차 있다 — 특히 크기 칸이다.

    `UnreflectedItem` 독스트링이 *「**크기를 모르면 「미정량」이라 적는다** —
    빈칸으로 두면 「작다」로 읽힌다」* 를 규약으로 둔다. 우리는 이 결손의 크기를
    **쟀으므로**(10년 가정에서 무보조 순현재가치 −18,778,570원 · 재현
    `.orch/R66/probe/pcs_wiring.py` ③) 그 어림을 적는다.
    """
    item = _pcs_item(_report())
    assert item is not None, (
        "붙임 8 에 「PCS 교체비」 항목이 없다 — 초기투자에는 PCS 가 섰는데 "
        "20년 동안 한 번도 갱신하지 않는 사실을 심의자가 읽을 자리가 없다"
    )
    assert item.direction == DIRECTION_ADVERSE, (
        f"방향이 {item.direction} 이다 — 교체비를 세지 않으면 비용이 작아지므로 "
        "지금 수치는 낙관 쪽이고, 그 사실을 붙임 8 이 말해야 한다"
    )
    assert item.judged == JUDGED_MEASURED, (
        "「방법의 한계」로 실린다 — 이 항목은 «초기투자에 PCS 가 있는가»와 "
        "«그 설비의 교체가 계상됐는가»를 매 실행 재어 판정한다"
    )
    for name in ("magnitude", "reason", "resolves_when"):
        assert getattr(item, name).strip(), f"{name} 칸이 비어 있다"
    assert "10년" in item.magnitude, (
        "크기 칸이 **어느 수명을 가정한 어림인지** 말하지 않는다 — 가정을 밝히지 "
        "않은 수는 검토자에게 「확보된 값」으로 읽힌다"
    )
    assert "미정량" not in item.magnitude, (
        "크기를 「미정량」으로 적었다 — 이 결손은 쟀다(10년 가정 · 실측 -18,778,570원)"
    )


# ── ⓑ ★ 수명이 켜지면 사라진다 ───────────────────────────────────────

@pytest.mark.req("FR-104-AC4")
def test_a_part_replacement_year_removes_the_row() -> None:
    """★★★ **배선이 들어오면 이 항목이 사라진다** — 그것을 여기서 붙든다.

    `_replacement_items` 독스트링이 경고한 형태가 이것이다: *「배선이 들어오면
    참인 조건 위에서 거짓을 계속 인쇄한다」*. 판정이 연차를 보지 않으면 PCS
    수명을 켠 날 붙임 8 이 **이미 계상된 교체비를 미반영으로** 싣게 되고, 그
    상태는 아무 예외도 내지 않는다.

    판정 재료는 **연차의 나머지**다 — 부품 재취득은 `수명 + 1` 부터 수명마다
    서므로 본체 수명 `L` 로 설명되는 연차는 `year % L == 1` 이다(본체 17년 →
    18년차 ✓). PCS 10년이 켜지면 11년차가 생기고 `11 % 17 = 11` 이라 그 식을
    만족하지 않는다.
    """
    report = _report()
    assert _pcs_item(report) is not None, "전제가 바뀌었다 — 이 구성에 이미 항목이 없다"

    assert pcs_replacement_gap(_with_a_part_replacement(report)) is None, (
        "본체 수명으로 설명되지 않는 교체 연차를 실었는데도 결손이 남는다 — "
        "판정이 연차를 보지 않는다(이 상태에서는 PCS 수명을 켜도 붙임 8 이 "
        "거짓을 계속 인쇄한다)"
    )
    assert _pcs_item(_with_a_part_replacement(report)) is None, (
        "판정은 갈렸는데 붙임 8 의 행이 남는다 — 집합체가 이 판정을 읽지 않는다"
    )


@pytest.mark.req("FR-104-AC4")
def test_the_row_needs_the_ledger_price_to_stand() -> None:
    """대장에 PCS 단가가 없으면 서지 않는다 — **없는 설비의 교체비를 세지 않는다.**

    ⚠ 이것은 「통과시키기 위한 가드」가 아니다. 그 단가가 없는 저장소 상태
    (R66/WP-1 이전)에서는 초기투자에 PCS 항 자체가 없으므로 *「사기는 했는데
    교체가 없다」* 가 성립하지 않는다 — 그때의 결손은 **대장 축이 비었다**는
    다른 항목의 몫이다(`_unread_items`).
    """
    report = _report()
    stripped = replace(
        report,
        assumptions=tuple(
            row for row in report.assumptions if row.key != PCS_PRICE_LEDGER_KEY
        ),
    )
    assert pcs_replacement_gap(stripped) is None


# ── ⓒ 본문과 붙임 양쪽에 인쇄된다 ────────────────────────────────────

@pytest.mark.req("FR-104-AC4")
def test_the_label_reaches_both_the_body_and_the_appendix() -> None:
    """절충안대로 **본문 3.4 에는 이름·방향**, 붙임 8 에는 크기·사유가 실린다.

    한쪽만 서면 결손이 결과와 함께 읽히지 않거나(본문 누락), 크기를 물을 자리가
    사라진다(붙임 누락).
    """
    report = _report()
    items = build_unreflected(report)
    body = "\n".join(unreflected_rows(items))
    assert LABEL_PCS_REPLACEMENT in body, "본문 3.4 표에 항목명이 없다"

    text = render_markdown(report)
    assert text.count(LABEL_PCS_REPLACEMENT) >= 2, (
        f"렌더 문면에 「{LABEL_PCS_REPLACEMENT}」가 한 번만 나온다 — 본문 3.4 와 "
        "붙임 8 양쪽에 서야 한다"
    )
    appendix = text[text.index("# 붙임"):]
    assert LABEL_PCS_REPLACEMENT in appendix, "붙임 8 에 항목이 없다"


# ── ⓓ 크기 칸의 단가가 대장에서 온다 ─────────────────────────────────

@pytest.mark.req("NFR-202-M1")
def test_the_size_quotes_the_ledger_and_not_a_copy() -> None:
    """단가를 **대장에서 읽어** 싣는다 — 리터럴로 박으면 대장이 바뀔 때 낡는다.

    R59b §3 이 금지한 형태이며, 여기서는 대장 값을 바꿔 문면이 **따라오는지**로
    잰다. 따라오지 않으면 그 수는 사본이다.
    """
    report = _report()
    item = _pcs_item(report)
    assert item is not None
    quoted = f"{_ledger(report)[PCS_PRICE_LEDGER_KEY]:,.0f}"
    assert quoted in item.magnitude, "크기 칸이 대장 단가를 인용하지 않는다"

    moved = replace(
        report,
        assumptions=tuple(
            replace(row, value=999_999) if row.key == PCS_PRICE_LEDGER_KEY else row
            for row in report.assumptions
        ),
    )
    gap = pcs_replacement_gap(moved)
    assert gap is not None
    assert "999,999" in gap["magnitude"], (
        "대장 단가를 고쳤는데 크기 칸이 옛 수를 그대로 인쇄한다 — 그 수는 사본이다"
    )


# ── ⓔ ★ 2.1 자원 표가 자기 취득비를 설명한다 ────────────────────────

@pytest.mark.req("FR-1001-AC2")
def test_the_resource_table_explains_its_own_acquisition_cost() -> None:
    """★★ **표에 적힌 단가·용량으로 초기투자를 되짚을 수 있다** (R66/WP-2-fix).

    R66/WP-2 뒤 이 칸은 `500,000원/kWh`(대장의 **시스템** 단가)를 인쇄하면서
    같은 행의 취득비를 `105,000,000원`으로 적었다 — 500,000 × 200 kWh 는
    100,000,000 이므로 **되짚기가 성립하지 않았다.** 배터리에 실제로 곱해지는
    것은 `시스템 단가 × (1 − PCS 몫)` 이고, 남은 5,000,000원은 `PCS 단가 ×
    정격출력` 이다.

    ⚠ **기대값을 여기 적지 않는다** — 대장 행과 용량 검토에서 **지어** 대조한다.
    ⚠⚠ 마지막 단정이 요점이다: 되짚어 남은 몫을 PCS 단가로 나누면 **정수 kW**
    가 떨어져야 한다. 그것이 *「두 축이 각각 무엇에 곱해졌는가」* 를 표가 실제로
    설명한다는 뜻이다 — 문면만 맞추고 수가 안 맞는 상태를 이 단정이 잡는다.
    """
    report = _report()
    price = _ledger(report)
    battery_unit = price[_ESS_PRICE_KEY] * (1.0 - price[_PCS_SHARE_KEY] / 100.0)
    pcs_unit = price[PCS_PRICE_LEDGER_KEY]
    capacity_kwh = {
        finding.variable: finding.used_value for finding in report.capacity_review
    }[_ESS_CAPACITY_VAR]

    (ess,) = [line for line in report.basis.resources if "저장장치" in line.kind]
    assert f"{battery_unit:,.0f}원/kWh" in ess.unit_capex, (
        f"단가 칸({ess.unit_capex!r})이 배터리 단가를 말하지 않는다 — 대장의 "
        "시스템 단가를 그대로 적으면 그 수로는 취득비가 되짚어지지 않는다"
    )
    assert f"{pcs_unit:,.0f}원/kW" in ess.unit_capex, (
        f"단가 칸({ess.unit_capex!r})에 PCS 원/kW 항이 없다 — 그러면 심의자가 "
        "초기투자의 5,000,000원이 어디서 왔는지 물을 자리가 없다"
    )

    residual = ess.capex_won - battery_unit * capacity_kwh
    assert residual > 0.0, (
        f"취득비({ess.capex_won:,})에서 배터리 몫을 빼도 남는 것이 없다 — "
        "PCS 항이 초기투자에 서지 않았다"
    )
    power_kw = residual / pcs_unit
    assert power_kw == pytest.approx(round(power_kw)), (
        f"되짚은 정격출력이 {power_kw!r} kW 다 — 표의 두 단가로 취득비가 "
        "설명되지 않는다(어느 축이 무엇에 곱해졌는지 갈렸다)"
    )
