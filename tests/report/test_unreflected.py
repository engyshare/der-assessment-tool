"""**미반영 항목**을 재어 싣는가 — 「1차 의견」 6 의 절충안 (R33).

의견은 *「미반영 사항은 붙임으로 별도 기재」* 였고 절반만 받았다. 전부 붙임으로
내리면 본문의 순현재가치가 **확정 수치로** 읽히기 때문이다 — 남은 항목의 방향이
서로 반대다(교체비는 악화, 잔존가치는 개선).

    본문 3.4   항목명 + 방향        ← 결과와 같은 자리
    붙임 8     크기 · 사유 · 해소   ← 본문을 늘리지 않는다

    ★ 항목을 **재어** 만든다              ← 문장으로 박으면 구성이 바뀔 때 틀린다
    ★ 방향을 **지어내지 않는다**          ← 배선되지 않은 인자는 잴 수 없다
    ★ 계통 수전이 있으면 구매 비용 미계상 ← 표를 내고서야 드러난 것
    양식 0절 — 해설을 싣지 않는다
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from core.report.case_report import build_case_report
from core.report.narrative import render_markdown
from core.report.unreflected import (
    DIRECTION_ADVERSE,
    DIRECTION_FAVORABLE,
    DIRECTION_UNKNOWN,
    JUDGED_MEASURED,
    build_unreflected,
    unreflected_direction_tally,
    unreflected_rows,
    unreflected_section,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report():
    return build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )


def test_replacement_item_appears_only_when_a_resource_outlives_nothing() -> None:
    """★ 교체비 항목이 **수명과 분석기간을 견주어** 나타나고 사라진다.

    「ESS 는 교체비가 빠졌다」로 박아 두면 수명 25년 ESS 를 쓰는 날 리포트가
    틀린 항목을 계속 인쇄한다. 여기서는 분석기간을 **자원 수명보다 짧게**
    바꾼 리포트에서 그 행이 사라지는지 본다 — 사라지지 않으면 판정이 아니라
    문장인 것이다.
    """
    report = _report()
    basis = report.basis
    shortest = min(r.lifetime_years for r in basis.resources)

    assert any(i.label == "교체비" for i in build_unreflected(report)), (
        "지금 구성(ESS 17년 < 분석기간 20년)에서 교체비 행이 없다"
    )

    # 분석기간을 가장 짧은 수명보다 짧게 두면 교체 대상이 사라진다.
    shortened = replace(report, basis=replace(basis, horizon_years=shortest - 1))
    labels = [item.label for item in build_unreflected(shortened)]
    assert "교체비" not in labels, (
        "분석기간 안에 수명이 끝나는 자원이 없는데 교체비 행이 남았다"
    )
    assert "잔존가치" in labels, (
        "분석기간보다 수명이 긴 자원이 생겼는데 잔존가치 행이 없다"
    )


def test_replacement_and_salvage_point_in_opposite_directions() -> None:
    """★ **방향이 갈린다는 사실**이 절충안의 근거다.

    둘 다 「미반영」이지만 하나는 결과를 좋게, 하나는 나쁘게 만든다. 방향을
    적지 않고 항목만 나열하면 검토자는 그것을 한쪽 방향의 여유로 읽는다.
    """
    items = {item.label: item for item in build_unreflected(_report())}
    assert items["교체비"].direction == DIRECTION_ADVERSE
    assert items["잔존가치"].direction == DIRECTION_FAVORABLE


def test_unread_variable_gets_no_invented_direction() -> None:
    """★ 배선되지 않은 인자의 방향을 **지어내지 않는다.**

    반영했을 때의 이동을 계산할 수 없으므로 방향은 `방향 미측정` 이어야 한다.
    대장 값의 부호로 짐작한 것을 방향 칸에 적으면 그 짐작이 **리포트의
    진술**이 된다.
    """
    report = _report()
    assert report.unread_variables, (
        "미배선 인자가 없다 — 전제가 바뀌었다면 이 검사를 갱신할 것"
    )
    items = build_unreflected(report)
    for entry in report.unread_variables:
        item = next(i for i in items if entry.variable in i.label)
        assert item.direction == DIRECTION_UNKNOWN, (
            f"{entry.variable}: 잴 수 없는 방향을 적었다 — {item.direction}"
        )
        assert "0원" in item.magnitude, "측정된 변동폭이 크기 칸에 없다"


def test_the_grid_purchase_is_now_a_cost_row_and_leaves_the_unreflected_table() -> None:
    """★★ **계통에서 산 전력이 값을 갖는다** (R34 · 사용자 판정).

    R33 은 이 항목을 붙임 8 에 「반영 시 결과 악화 · 금액 미정량」으로 실었다.
    R34 에 한계단가(`tariff.hv_single_contract.energy_only`)를 대장에 세우고
    비용 행을 배선했으므로, 이제 **미반영 표에서 사라지고 붙임 4 의 비용
    항목으로 옮겨가야 한다.** 사라지지 않으면 같은 사실이 두 곳에 실린다.
    """
    report = _report()
    imported = sum(hour.grid_import for hour in report.dispatch_hours)
    assert imported, "이 구성은 대표일에 계통 수전을 가져야 한다 (ESS 심야 충전)"

    (row,) = [line for line in report.basis.costs if line.tag == "GridPurchase"]
    assert row.annual_won > 0, (
        f"수전이 {imported:,.2f}kWh/일 인데 구매 비용이 {row.annual_won}원이다 — "
        "행은 있고 값이 없으면 프로포마에서 「사 온 것이 없다」와 구별되지 않는다"
    )
    assert f"{imported:,.2f}kWh" in row.formula, "산식에 측정 수량이 없다"
    assert f"{report.basis.grid_purchase_price_won_per_kwh:,.0f}원/kWh" in row.formula, (
        "산식에 단가가 없다 — 수량과 단가 중 어느 쪽이 틀렸는지 가릴 수 없다"
    )

    assert not [
        i for i in build_unreflected(report) if i.label == "계통 전력 구매 비용"
    ], "비용 행이 있는데 미반영 항목으로도 실린다 — 같은 사실이 두 곳에 있다"


def test_grid_purchase_without_a_cost_row_is_reported_as_adverse() -> None:
    """★★ **비용 행을 없애면 다시 「악화」로 드러나는가** (R33 이 찾은 결함).

    종전 판정은 *「가구 부하가 없으므로 구매 자체가 없다」* 였다. 붙임 7 을
    실제로 내 보니 ESS 가 심야에 충전하고 그 전력이 **계통에서 들어온다** —
    부하가 없어도 구매는 일어난다. 값 없이 쓴 전력이 있으면 방향은 「불명」이
    아니라 **악화**다.

    ⚠ 판정 조건이 「수전이 0인가」이면 이 결함을 놓친다. 조건은 **수전이
    있는데 비용 행이 없는가**여야 한다.

    ⚠ **R34 에 배선됐는데도 이 검사를 남긴다.** 비용 행을 만드는 것은 러너의
    세 줄이고, 그것이 조건부가 되거나 다른 진입점이 생기면 같은 상태가 다시
    만들어진다 — 그때 순현재가치는 **조용히 좋아진다**. 그래서 행을 거둔
    리포트를 만들어 판정이 살아 있는지 본다.
    """
    report = _report()
    imported = sum(hour.grid_import for hour in report.dispatch_hours)
    without = replace(
        report,
        basis=replace(
            report.basis,
            costs=tuple(
                line for line in report.basis.costs if line.tag != "GridPurchase"
            ),
            annual_cost_won=sum(
                line.annual_won
                for line in report.basis.costs
                if line.tag != "GridPurchase"
            ),
        ),
    )

    item = next(
        i for i in build_unreflected(without) if i.label == "계통 전력 구매 비용"
    )
    assert item.direction == DIRECTION_ADVERSE, (
        f"대표일 계통 수전이 {imported:,.2f}kWh 인데 방향이 "
        f"{item.direction} 이다 — 값 없이 쓴 전력은 비용이다"
    )
    assert f"{imported:,.2f}kWh" in item.magnitude, "측정 수량이 없다"


def test_body_carries_only_the_name_and_direction() -> None:
    """★ 본문 3.4 는 **이름과 방향만** — 크기·사유는 붙임 8.

    전부 본문에 두면 4~5쪽을 넘고, 전부 붙임으로 내리면 본문의 순현재가치가
    확정 수치로 읽힌다. 절충안이 성립하는지는 **두 자리가 서로 다른 것을
    싣는가**로 판정된다.
    """
    report = _report()
    items = build_unreflected(report)
    text = render_markdown(report)
    body = text[text.index("### 3.4 이 평가가 하지 않은 것") : text.index("## 4. 평가 결과")]
    detail = text[text.index("## 붙임 8. 미반영 항목") : text.index("## 붙임 9.")]

    for item in items:
        assert item.label in body, f"{item.label}: 본문 3.4 에 없다"
        assert item.direction in body, f"{item.label}: 방향이 본문에 없다"
        assert item.magnitude not in body, (
            f"{item.label}: 크기가 본문에 실렸다 — 붙임으로 내려야 한다"
        )
        assert item.magnitude in detail, f"{item.label}: 크기가 붙임 8 에 없다"
        assert item.resolves_when in detail, f"{item.label}: 해소 조건이 없다"


def test_summary_carries_the_tally_with_directions() -> None:
    """요약이 **건수와 방향 내역**을 함께 싣는다.

    건수만 적으면 방향이 갈린다는 사실이 사라지고, 그러면 본문의 한 수가
    확정 수치로 읽힌다 — 이 절충안이 막으려던 상태 그대로다.
    """
    report = _report()
    items = build_unreflected(report)
    tally = unreflected_direction_tally(items)
    summary = render_markdown(report)
    summary = summary[summary.index("## 1. 요약") : summary.index("## 2. 평가 개요")]

    assert tally in summary, "요약의 미반영 칸이 방향 내역을 싣지 않는다"
    assert str(len(items)) in tally
    assert "붙임 8" in tally, "전문의 자리를 가리키지 않는다"


def test_measured_and_authored_items_are_distinguished() -> None:
    """★ **매 실행 재확인되는 사실**과 **적어 둔 문장**을 갈라 적는다.

    갈라 두지 않으면 둘이 같은 무게로 읽힌다 — 「이번에 확인된 것」과 「원래
    그런 것」은 검토자에게 다른 정보다.
    """
    items = build_unreflected(_report())
    assert any(i.measured for i in items), "재어 판정한 항목이 하나도 없다"
    assert any(not i.measured for i in items), "방법의 한계 항목이 사라졌다"
    rows = unreflected_rows(items)
    assert any(JUDGED_MEASURED in row for row in rows), "판정 열이 표에 없다"


def test_section_carries_no_reading_instructions() -> None:
    """★ **해설을 싣지 않는다** (양식 0절)."""
    section = unreflected_section(build_unreflected(_report()))
    quoted = [line for line in section if line.startswith(">")]
    assert not quoted, f"해설 인용문이 남았다: {quoted[:2]}"
    for banned in ("읽지 말", "읽힌다", "말 것"):
        offenders = [line for line in section if banned in line]
        assert not offenders, f"독법 지시가 남았다({banned}): {offenders[:2]}"


def test_empty_item_list_says_none_rather_than_printing_an_empty_table() -> None:
    """항목이 없으면 **없다고 적는다** — 빈 표는 「빠뜨림」과 구별되지 않는다."""
    lines = unreflected_section(())
    text = "\n".join(lines)
    assert "없음" in text
    assert "|---" not in text, "빈 표를 그렸다"
    assert unreflected_direction_tally(()) == "없음"
    assert unreflected_rows(()) == ["| 없음 | — | — |"]


def test_flat_generation_profile_is_measured_not_asserted() -> None:
    """★★ **일중 발전 곡선이 평탄하다** — 붙임 7 을 눈으로 읽고서야 드러났다.

    표에 **00~01시 태양광 0.45kWh** 가 실려 있었다. 야간 발전이다. 러너가 PV 에
    이용률 하나만 주어 하루 발전량을 24스텝에 균등 배분한 결과이며 실물의 일사
    곡선이 아니다. 드러내지 않으면 검토자는 **야간 태양광 발전을 사실로 읽는다.**

    ⚠ 「PV 가 평탄하다」를 문장으로 박으면 일사 시계열을 바인딩하는 날 그 문장이
    틀린 채로 계속 인쇄된다. 여기서는 **곡선을 주입해 행이 사라지는지** 본다 —
    사라지지 않으면 판정이 아니라 문장인 것이다.
    """
    report = _report()
    hours = report.dispatch_hours
    item = next(
        (i for i in build_unreflected(report) if i.label.startswith("일중 발전 프로파일")),
        None,
    )

    generators = [
        name
        for name in hours[0].per_resource
        if all(hour.per_resource[name] >= 0.0 for hour in hours)
        and max(hour.per_resource[name] for hour in hours) > 0.0
    ]
    flat = [
        name
        for name in generators
        if len({round(hour.per_resource[name], 9) for hour in hours}) == 1
    ]
    if not flat:
        assert item is None, "곡선이 있는데 평탄으로 보고했다"
        return

    assert item is not None, (
        f"발전 자원 {flat} 이 전 스텝 동일 출력인데 붙임 8 에 행이 없다"
    )
    assert item.direction == DIRECTION_UNKNOWN, (
        "발전을 주간으로 옮기면 송전(편익)과 수전(비용)이 함께 늘어난다 — "
        f"한쪽만 보고 방향을 {item.direction} 로 단정했다"
    )
    covered = sum(
        sum(hour.per_resource[name] for name in flat)
        for hour in hours
        if hour.grid_import > 0.0
    )
    assert f"{covered:,.2f}kWh/일" in item.magnitude, (
        f"수전 스텝에 실린 발전량({covered:,.2f}kWh)이 크기 칸에 없다"
    )


def test_a_shaped_generation_profile_removes_the_row() -> None:
    """★ **곡선을 주입하면 행이 사라진다** — 판정이지 문장이 아님을 고정한다.

    지금 대장·러너로는 평탄한 운전만 나오므로, 이 검사가 없으면 *「평탄 자원이
    있는가」* 대신 *「PV 가 있는가」* 로 구현해도 오늘은 초록불이다. 그때 일사
    시계열이 배선되는 날 리포트는 **없는 결함을 계속 인쇄한다.**
    """
    report = _report()
    hours = report.dispatch_hours
    name = next(
        name
        for name in hours[0].per_resource
        if all(hour.per_resource[name] >= 0.0 for hour in hours)
    )
    total = sum(hour.per_resource[name] for hour in hours)
    # 총량은 그대로 두고 **주간 절반에만** 실어 곡선을 만든다.
    half = len(hours) // 2
    shaped = tuple(
        replace(
            hour,
            per_resource={
                **hour.per_resource,
                name: (total / half if half <= index < half * 2 else 0.0),
            },
        )
        for index, hour in enumerate(hours)
    )
    curved = replace(report, dispatch_hours=shaped)

    assert not [
        i
        for i in build_unreflected(curved)
        if i.label.startswith("일중 발전 프로파일")
    ], "곡선을 주입했는데도 평탄 항목이 남았다 — 자원 이름으로 판정하고 있다"
