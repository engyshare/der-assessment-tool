"""**자립 역산**(경우 「가」) — R55/WP-1.

검토서(`docs/적정용량-산출방법-검토.md`) §1 이 확인한 결손 — 대장에 연간
사용량은 있으나 그것을 용량으로 뒤집는 산식이 없었다 — 을 `core/report/
sizing.py` 가 채웠는지를 잰다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.ledger_levels import build_level_map, design_variables
from core.contracts.units import HOURS_PER_YEAR
from core.contracts.validation import ValidationError
from core.der.pv import PV
from core.report.case_report import build_case_report
from core.report.narrative import render_markdown
from core.report.sizing import (
    MONTHS_PER_YEAR,
    USER_EXAMPLE_MONTHLY_KWH,
    build_self_sufficiency_sizing,
    required_pv_capacity_kw,
    self_sufficiency_section,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def test_the_inverse_closes_the_oracle_round_trip() -> None:
    """★ **오라클 왕복** — `PV` 를 실제로 세워 얻은 발전량을 역산하면 원래
    용량으로 돌아오고, 그 용량으로 다시 `PV` 를 세우면 발전량이 닫힌다.

    ★ 오라클 수(1kW·8760h·0.15 → 1,314.0kWh)를 이 파일에 베껴 적지 않는다 —
    `PV` 를 불러 얻는다.
    """
    capacity_factor = 0.15
    oracle_pv = PV(name="oracle", capacity_kw=1.0, capacity_factor=capacity_factor)
    oracle_kwh = oracle_pv.annual_generation_kwh(year=1)

    required_kw = required_pv_capacity_kw(
        annual_load_kwh=oracle_kwh, capacity_factor=capacity_factor
    )
    assert required_kw == pytest.approx(1.0)

    roundtrip_pv = PV(name="roundtrip", capacity_kw=required_kw, capacity_factor=capacity_factor)
    assert roundtrip_pv.annual_generation_kwh(year=1) == pytest.approx(oracle_kwh)


def test_ledger_levels_yield_three_monotonic_capacities() -> None:
    """★ **대장에서 읽는다 — 수를 베끼지 않는다.**

    `build_level_map()` 이 낸 `household_load_annual_kwh` 세 수준으로 역산하면
    부하가 커지는 순서(`low`→`base`→`high`)로 용량도 커지고, 세 점이 다 나온다.
    ⚠ 2,700·3,600·4,800 을 리터럴로 적지 않는다 — 대장이 바뀌면 이 검사가
    조용히 낡는다.
    """
    load_levels = build_level_map(_ASSUMPTIONS)["household_load_annual_kwh"]
    sizing = build_self_sufficiency_sizing(
        load_levels=load_levels,
        capacity_factor=0.15,
        capacity_factor_source="시험 탐침값",
        search_low_kw=0.0,
        search_high_kw=1_000.0,
    )

    assert [p.source_label for p in sizing.points] == ["대장 low", "대장 base", "대장 high"]
    capacities = [p.required_capacity_kw for p in sizing.points]
    assert capacities == sorted(capacities), "부하가 커지는데 역산 용량이 단조가 아니다"
    assert len(set(capacities)) == 3, "세 점 중 일부가 같은 값이다"


def test_a_reference_load_beyond_the_search_range_is_kept_not_dropped() -> None:
    """★ **탐색 구간 밖을 「밖이다」로 싣는다** — 구간을 넓히지 않는다.

    `design_variables()` 에서 읽은 `pv_capacity_kw` 의 `low`·`high` 를 그대로
    탐색 구간으로 넘기고, 상한을 확실히 넘는 참고 부하 하나를 더한다. 그 점이
    표(`points`)에서 사라지지 않고 `within_search_range=False` 로 남는지 본다.
    """
    variable = next(v for v in design_variables() if v.name == "pv_capacity_kw")
    capacity_factor = 0.15

    # 구간 경계에 정확히 닿도록 부하를 지어 low·base·high 셋 다 구간 «안»에
    # 들게 하고, 참고 부하 하나만 상한의 두 배를 주어 확실히 «밖»으로 만든다.
    within_low_kwh = variable.low * HOURS_PER_YEAR * capacity_factor
    within_mid_kwh = (variable.low + variable.high) / 2 * HOURS_PER_YEAR * capacity_factor
    within_high_kwh = variable.high * HOURS_PER_YEAR * capacity_factor
    beyond_kwh = variable.high * HOURS_PER_YEAR * capacity_factor * 2.0

    sizing = build_self_sufficiency_sizing(
        load_levels={"low": within_low_kwh, "base": within_mid_kwh, "high": within_high_kwh},
        capacity_factor=capacity_factor,
        capacity_factor_source="시험 탐침값",
        search_low_kw=variable.low,
        search_high_kw=variable.high,
        reference_loads=[("참고", beyond_kwh)],
    )

    assert len(sizing.points) == 4, "참고 부하 점이 표에서 사라졌다"
    for point in sizing.points[:3]:
        assert point.within_search_range, f"{point.source_label}: 구간 안인데 밖으로 나왔다"
    beyond_point = sizing.points[-1]
    assert beyond_point.source_label == "참고"
    assert not beyond_point.within_search_range, "상한을 넘는 점이 구간 안으로 세어졌다"


def test_the_user_example_load_is_about_twice_the_ledger_base_load() -> None:
    """★ **사용자 예시와 대장 base 가 두 배 다르다** — 검토서 §7 의 물음을
    수로 세우는 자리다. 대신 정하지 않는다 — 둘 다 역산해 나란히 낸다.
    """
    load_levels = build_level_map(_ASSUMPTIONS)["household_load_annual_kwh"]
    capacity_factor = 0.15
    sizing = build_self_sufficiency_sizing(
        load_levels=load_levels,
        capacity_factor=capacity_factor,
        capacity_factor_source="시험 탐침값",
        search_low_kw=0.0,
        search_high_kw=1_000.0,
        reference_loads=[("사용자 예시", USER_EXAMPLE_MONTHLY_KWH * MONTHS_PER_YEAR)],
    )

    base_point = next(p for p in sizing.points if p.source_label == "대장 base")
    example_point = next(p for p in sizing.points if p.source_label == "사용자 예시")
    ratio = example_point.required_capacity_kw / base_point.required_capacity_kw
    assert ratio == pytest.approx(2.0, rel=0.05), (
        f"사용자 예시 용량이 대장 base 의 두 배 근처가 아니다 (비율 {ratio:.3f})"
    )


def test_validation_errors_carry_field_reason_and_action() -> None:
    """★ **검증 셋** — 네 조건 모두 `ValidationError` 가 나고, `as_dict()` 의
    `field`·`reason`·`action` 이 셋 다 비어 있지 않은지 본다 (NFR-303).
    """
    with pytest.raises(ValidationError) as bad_capacity_factor:
        required_pv_capacity_kw(annual_load_kwh=1_000.0, capacity_factor=1.5)
    with pytest.raises(ValidationError) as bad_annual_load:
        required_pv_capacity_kw(annual_load_kwh=0.0, capacity_factor=0.15)
    with pytest.raises(ValidationError) as missing_level:
        build_self_sufficiency_sizing(
            load_levels={"low": 100.0, "base": 200.0},
            capacity_factor=0.15,
            capacity_factor_source="시험 탐침값",
            search_low_kw=0.0,
            search_high_kw=10.0,
        )
    with pytest.raises(ValidationError) as inverted_search_range:
        build_self_sufficiency_sizing(
            load_levels={"low": 100.0, "base": 200.0, "high": 300.0},
            capacity_factor=0.15,
            capacity_factor_source="시험 탐침값",
            search_low_kw=10.0,
            search_high_kw=1.0,
        )

    for excinfo, expected_field in (
        (bad_capacity_factor, "pv.capacity_factor"),
        (bad_annual_load, "load.household.annual"),
        (missing_level, "load.household.annual"),
        (inverted_search_range, "pv.capacity_kw"),
    ):
        payload = excinfo.value.as_dict()
        assert payload["field"] == expected_field
        assert payload["reason"], f"{expected_field}: reason 이 비어 있다"
        assert payload["action"], f"{expected_field}: action 이 비어 있다"


def test_the_report_appendix_carries_the_self_sufficiency_section() -> None:
    """★ **붙임 10 에 실린다 — 본문에는 없다** (R55/WP-2 지시문 5절 6번 · WP-2-fix).

    본문 분량 예산(219줄 — `test_body_stays_within_the_form_length_budget`)을
    다시 밀지 않으려고 이 소절은 붙임 10 으로 옮겨졌다. 소제목과 역산 용량
    값이 `appendix` 안에는 있고 `body` 안에는 없는지 본다. 값은
    `report.self_sufficiency` 에서 꺼내지 리터럴로 박지 않는다 — 대장이
    바뀌면 이 검사도 함께 값을 바꿔 읽는다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    body, appendix = render_markdown(report).split("# 붙임", 1)

    assert "경우 「가」" in appendix, "소제목이 붙임에 없다"
    assert "경우 「가」" not in body, "소제목이 본문에 남아 있다"
    for point in report.self_sufficiency.points:
        capacity_text = f"{point.required_capacity_kw:.2f}"
        assert capacity_text in appendix, (
            f"{point.source_label} 의 역산 용량이 붙임에 없다"
        )
        assert capacity_text not in body, (
            f"{point.source_label} 의 역산 용량이 본문에 남아 있다"
        )


def test_the_capacity_factor_source_prints_as_a_source_constant_not_ledger() -> None:
    """★ **이용률의 출처가 「소스 상수」로 붙임에 인쇄된다** (R55/WP-2 지시문 5절 7번 · WP-2-fix).

    문면에 `PV_CAPACITY_FACTOR` 와 「대장」이라는 말이 함께 있고, 그 일치를
    근거로 쓸 수 없다는 경고가 있는지 본다 — 「좋아 보이는 수를 근거처럼
    인쇄하지 않는다」를 지키는 검사다. 이 소절은 **붙임**에 있다(WP-2-fix).
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    _body, appendix = render_markdown(report).split("# 붙임", 1)

    assert "PV_CAPACITY_FACTOR" in appendix
    assert "대장" in appendix
    assert "근거로 쓸 수 없다" in appendix


def test_a_point_outside_the_range_says_which_side_it_fell_off() -> None:
    """★ **「구간 밖」을 한 말로 뭉개지 않는다** — 상한 초과와 하한 미만은
    검토자에게 **반대 방향의 조치**를 요구한다.

    상한을 넘었다는 것은 *「이 부하를 자립으로 덮으려면 탐색 구간을 넓혀야
    한다」* 이고, 하한에 못 미쳤다는 것은 *「구간을 그만큼 크게 잡을 이유가
    없다」* 이다. 한 문면으로 둘을 인쇄하면 어느 쪽이든 거짓말이 된다
    (`capacity.py` 의 「두 갈래를 미리 밝힌다」와 같은 태도).
    """
    capacity_factor = 0.15
    low_kw, high_kw = 2.0, 3.0
    below_kwh = low_kw * HOURS_PER_YEAR * capacity_factor / 2.0
    inside_kwh = (low_kw + high_kw) / 2 * HOURS_PER_YEAR * capacity_factor
    above_kwh = high_kw * HOURS_PER_YEAR * capacity_factor * 2.0

    sizing = build_self_sufficiency_sizing(
        load_levels={"low": below_kwh, "base": inside_kwh, "high": above_kwh},
        capacity_factor=capacity_factor,
        capacity_factor_source="시험 탐침값",
        search_low_kw=low_kw,
        search_high_kw=high_kw,
    )
    text = "\n".join(self_sufficiency_section(sizing))

    assert f"아니오 — 구간 하한 {low_kw:g}kW 미만" in text
    assert f"아니오 — 구간 상한 {high_kw:g}kW 초과" in text


def test_without_a_reference_load_no_mismatch_line_is_invented() -> None:
    """★ **비교 대상이 없으면 「어긋남」 줄을 짓지 않는다.**

    어긋남 줄은 대장 `base` 와 참고 부하를 **나란히** 놓는 줄이다. 참고
    부하가 없는데도 그 줄을 인쇄하면 비교되지 않은 것이 비교된 것처럼 읽힌다.
    """
    sizing = build_self_sufficiency_sizing(
        load_levels={"low": 2_700.0, "base": 3_600.0, "high": 4_800.0},
        capacity_factor=0.15,
        capacity_factor_source="시험 탐침값",
        search_low_kw=1.0,
        search_high_kw=9.0,
    )
    lines = self_sufficiency_section(sizing)

    assert not [line for line in lines if line.startswith("- 어긋남")]
    assert len([line for line in lines if line.startswith("| 대장 ")]) == 3
