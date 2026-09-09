"""**자립 역산**(경우 「가」) — R55/WP-1.

검토서(`docs/적정용량-산출방법-검토.md`) §1 이 확인한 결손 — 대장에 연간
사용량은 있으나 그것을 용량으로 뒤집는 산식이 없었다 — 을 `core/report/
sizing.py` 가 채웠는지를 잰다.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from core.casegrid.ledger_levels import (
    build_level_map,
    design_variables,
    ledger_backed_variables,
)
from core.contracts.units import HOURS_PER_YEAR
from core.contracts.validation import ValidationError
from core.der.pv import PV
from core.report.case_report import build_case_report
from core.report.narrative import render_markdown
from core.report.sizing import (
    MONTHS_PER_YEAR,
    USER_EXAMPLE_MONTHLY_KWH,
    SelfSufficiencySizing,
    base_level_point,
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


def test_the_capacity_factor_source_prints_the_ledger_key_it_actually_read() -> None:
    """★ **이용률의 출처가 「대장 키」로 붙임에 인쇄된다** (R67/WP-N2).

    ## 이 검사가 뒤집혔다 — 뒤집힌 것이 요점이다

    R55/WP-2-fix 까지 이 자리는 *「출처가 **소스 상수**로 인쇄된다」* 를 붙들었고
    문면에 `e2e_runner` 의 상수 이름이 있는지 보았다. R67/WP-N2 가 그 상수를
    대장(`capacity_factor.pv_rooftop`)으로 옮겼으므로 **그 단언은 이제 거짓을
    지킨다** — 사용자 판정 R67 §2(*「모든 수치는 추후 변경 가능」*)와
    `docs/decisions-2026-09-08-R67b.md` §3-4 가 그 이동을 지시했다.

    ⚠ **느슨하게 하지 않았다** — 지키는 것을 바꿨다: ⓐ 인쇄되는 키가 **이
    실행이 실제로 읽은 그 키**인가(대장을 다시 읽어 대조한다 · 문자열을 여기
    베끼지 않는다) ⓑ *「그 값이 옳다는 근거는 없다」* 는 경고가 **남아 있는가**.
    ⓑ 를 지우면 대장으로 옮긴 것이 값의 신뢰도를 올린 것처럼 읽힌다 — 대장
    항목 자신이 `confidence: 가정` · `source: null` 이다.
    """
    report = build_case_report(
        _GOLDEN / "scenario_unsubsidized.yaml", assumptions_path=_ASSUMPTIONS
    )
    _body, appendix = render_markdown(report).split("# 붙임", 1)
    ledger_key = ledger_backed_variables()["pv_capacity_factor"]

    assert ledger_key in appendix, (
        f"이용률의 대장 키 {ledger_key!r} 가 붙임에 없다 — 출처 문면이 실행이 "
        "읽은 자리를 가리키지 않는다"
    )
    assert report.self_sufficiency.capacity_factor == pytest.approx(
        build_level_map(_ASSUMPTIONS)["pv_capacity_factor"]["base"]
    ), "역산이 대장의 값을 쓰지 않았다 — 출처 문면만 대장을 가리킨다"
    assert "근거로 쓸 수 없다" in appendix, (
        "「그 값이 옳다는 근거는 없다」 경고가 사라졌다 — 대장 등재가 신뢰도를 "
        "올린 것처럼 읽힌다"
    )


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


# ── R65/WP-2c — **이 역산이 답하는 사업이 본문과 같은가** ──────────────────────
#
# ⚠ 이 절이 없어 CI 의 게이트 ②(NFR-105 · 테스트 동반)가 빨간불이었다.
# `core/report/sizing.py` 가 배수를 받도록 바뀌었는데 **그것을 재는 시험이
# 함께 오지 않았다** — 그 게이트는 `pull_request` 에서만 돌아 로컬 전건이
# 초록불이어도 드러나지 않는다(`CLAUDE.md` 「로컬 초록불 ≠ CI 초록불」).


def _scaling_inputs() -> tuple[dict[str, float], float, float, float]:
    """배수 시험 셋이 함께 쓰는 입력 — **수를 세 곳에 베끼지 않는다.**"""
    variable = next(v for v in design_variables() if v.name == "pv_capacity_kw")
    capacity_factor = 0.15
    base_kwh = variable.low * HOURS_PER_YEAR * capacity_factor
    load_levels = {"low": base_kwh * 0.8, "base": base_kwh, "high": base_kwh * 1.2}
    return load_levels, capacity_factor, variable.low, variable.high


def test_the_site_size_multiplies_both_the_load_and_the_search_band() -> None:
    """★★ **부하와 탐색 구간이 «같은» 배수를 탄다** (R65/WP-2c).

    한쪽만 곱하면 이 표가 본문과 다른 사업을 그린다 — 본문 4절은 20호면
    60 kW 로 도는데 이 역산이 「1~9 kW 구간」과 한 호 부하로 답하던 것이
    R65 가 닫은 어긋남이다. ⛔ 띠의 **수**(`low`·`high`)를 고친 것이 아니라
    **곱한 것**이므로, 여기서도 `design_variables()` 에서 읽어 곱해 견준다.
    """
    load_levels, capacity_factor, low_kw, high_kw = _scaling_inputs()
    count = 20

    sizing = build_self_sufficiency_sizing(
        load_levels=load_levels,
        capacity_factor=capacity_factor,
        capacity_factor_source="시험 탐침값",
        search_low_kw=low_kw,
        search_high_kw=high_kw,
        household_count=count,
    )

    assert sizing.household_count == count
    assert sizing.search_low_kw == pytest.approx(low_kw * count), "탐색 하한이 한 호분이다"
    assert sizing.search_high_kw == pytest.approx(high_kw * count), "탐색 상한이 한 호분이다"
    for point, level in zip(sizing.points, ("low", "base", "high"), strict=True):
        assert point.annual_load_kwh == pytest.approx(load_levels[level] * count), (
            f"{level}: 부하가 단지 규모로 곱해지지 않았다"
        )


def test_the_appliance_load_is_added_before_the_site_size_multiplies() -> None:
    """★★★ **더한 «뒤에» 곱한다 — 차례가 뜻을 정한다** (R65/WP-2c).

    대장 `load.household.annual` 은 *「추가 전력사용기기가 없는 가구 기준」*
    이고 본문은 `(annual + 기기) × 호수` 로 총량을 낸다
    (`core/casegrid/seasonal_dispatch.py::_load_total_kwh`). 곱한 뒤에 더하면
    기기 부하가 **한 호분만** 들어와 이 표의 「필요 용량」이 본문이 실제로
    감당해야 하는 것보다 **작게** 나온다 — 그 어긋남은 아무 예외도 내지 않는다.
    """
    load_levels, capacity_factor, low_kw, high_kw = _scaling_inputs()
    count, extra = 20, 5_459.0

    sizing = build_self_sufficiency_sizing(
        load_levels=load_levels,
        capacity_factor=capacity_factor,
        capacity_factor_source="시험 탐침값",
        search_low_kw=low_kw,
        search_high_kw=high_kw,
        reference_loads=[("참고", load_levels["base"])],
        extra_appliance_load_kwh=extra,
        household_count=count,
    )

    base_point = sizing.points[1]
    added_then_scaled = (load_levels["base"] + extra) * count
    scaled_then_added = load_levels["base"] * count + extra
    assert base_point.annual_load_kwh == pytest.approx(added_then_scaled)
    assert base_point.annual_load_kwh != pytest.approx(scaled_then_added), (
        "곱한 뒤에 더했다 — 기기 부하가 한 호분만 들어왔다"
    )

    # ⚠ 참고 부하(사용자 예시)에도 **같은** 처리를 한다. 두 부하를 나란히 놓고
    # 「어느 쪽이 맞는가」를 묻는 것이 이 표의 목적인데, 한쪽만 곱하면 그 물음이
    # 규모 차이로 덮인다.
    assert sizing.points[-1].annual_load_kwh == pytest.approx(added_then_scaled), (
        "참고 부하만 한 호분으로 남아 대장 점과 규모가 갈렸다"
    )


def test_an_unspecified_site_size_is_unchanged_to_the_last_element() -> None:
    """★ **미지정이면 이 두 인자가 생기기 전과 원소 하나까지 같다.**

    배수가 `1` 이고 기기 부하가 `0` 이므로 **인자를 주지 않은 호출과 같은
    객체**가 나와야 한다. 이것이 참이라야 「움직인 것은 값이지 배선이 아니다」
    가 성립한다.
    """
    load_levels, capacity_factor, low_kw, high_kw = _scaling_inputs()
    common = {
        "load_levels": load_levels,
        "capacity_factor": capacity_factor,
        "capacity_factor_source": "시험 탐침값",
        "search_low_kw": low_kw,
        "search_high_kw": high_kw,
        "reference_loads": [("참고", load_levels["base"])],
    }

    before = build_self_sufficiency_sizing(**common)
    after = build_self_sufficiency_sizing(
        **common, household_count=None, extra_appliance_load_kwh=0.0
    )

    assert after == before, "미지정 실행이 배선 전과 달라졌다"
    assert all("호" not in point.source_label for point in after.points), (
        "미지정인데 점 이름에 단지 규모가 붙었다"
    )


# ── R67/WP-N2 — 이용률이 **대장에서** 오는가 · 그리고 축은 움직이지 않았는가 ──
#
# 판정 `docs/decisions-2026-09-08-R67b.md` §3-4 가 지목한 결손: 역산 **전체가**
# 이용률에 반비례하는데 그 값이 소스 상수라 사용자가 바꿀 통로가 없었다.


def _report_with_capacity_factor(value: float | None):
    """대장 **오버라이드**로 이용률을 흔들어 돌린다.

    ⚠ **리터럴이나 전용 인자로 흔들지 않는다** — 사용자가 실제로 지나는 통로가
    대장 오버라이드이고(`app/services/ui_run.py::run_ui_case`), 그 통로를 재지
    않으면 *「대장에 올렸다」* 가 화면에서 참인지 알 수 없다. 관용구는
    `tests/report/test_load_shift_wired.py::_report` 와 같다.
    ⚠ **골든 픽스처를 고치지 않는다** — 쓰는 곳은 임시 디렉터리 안이다.
    """
    scenario = _GOLDEN / "scenario_unsubsidized.yaml"
    fields: dict[str, object] = (
        yaml.safe_load(scenario.read_text(encoding="utf-8")) or {}
    )
    if value is not None:
        fields["assumption_overrides"] = [
            {
                "key": ledger_backed_variables()["pv_capacity_factor"],
                "value": value,
                "reason": "이 검사가 축을 흔든다",
            }
        ]
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / scenario.name
        path.write_text(
            yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return build_case_report(path, assumptions_path=_ASSUMPTIONS)


def _base_point(report) -> float:
    """대장 base 부하의 역산 용량(kW) — 점 이름으로 찾는다."""
    return next(
        point.required_capacity_kw
        for point in report.self_sufficiency.points
        if point.source_label.startswith("대장 base")
    )


def test_shaking_the_capacity_factor_in_the_ledger_moves_the_back_calculation() -> None:
    """★★★ **대장에서 이용률을 바꾸면 역산의 답이 따라 움직인다** (R67/WP-N2).

    이것이 이 이동의 요점이다 — 종전에는 소스 상수였으므로 사용자가 무엇을
    고쳐도 147.23 kW 가 그대로 나왔다. **두 점 이상**을 재고, 방향까지 본다:
    필요 용량은 이용률에 **반비례**하므로 이용률을 올리면 필요 용량이 줄어야
    한다. 부호만 맞고 크기가 틀리는 배선(예: 비례로 걸린 경우)을 잡기 위해
    **곱까지** 대조한다.

    ⚠ **기대값을 여기 적지 않는다** — `연간 부하 ÷ (8,760h × 이용률)` 이
    `required_pv_capacity_kw` 의 정의이므로, 같은 부하에서 두 점의 곱
    (`용량 × 이용률`)이 같아야 한다. 리터럴을 적으면 대장 폭이 바뀌는 날
    이 검사만 낡는다.
    """
    levels = build_level_map(_ASSUMPTIONS)["pv_capacity_factor"]
    low, high = float(levels["low"]), float(levels["high"])
    assert low < high, f"대장 감도 폭이 서지 않았다 — {dict(levels)}"

    at_low = _report_with_capacity_factor(low)
    at_high = _report_with_capacity_factor(high)

    assert at_low.self_sufficiency.capacity_factor == pytest.approx(low)
    assert at_high.self_sufficiency.capacity_factor == pytest.approx(high)

    kw_low, kw_high = _base_point(at_low), _base_point(at_high)
    assert kw_low > kw_high, (
        f"이용률 {low} → {kw_low:.2f}kW · {high} → {kw_high:.2f}kW 다 — "
        "이용률을 올렸는데 필요 용량이 줄지 않았다(반비례가 아니다)"
    )
    assert kw_low * low == pytest.approx(kw_high * high, rel=1e-9), (
        "두 점의 `용량 * 이용률` 이 다르다 — 역산이 이용률에 반비례로 걸리지 "
        "않았다(부하가 함께 움직였을 수도 있다)"
    )


def test_the_default_ledger_run_leaves_the_conclusion_axis_where_it_was() -> None:
    """★★ **값을 옮겼을 뿐이므로 결론축이 움직이지 않는다** (R67/WP-N2 조건).

    사용자 판정 R67 §2 는 *「현재 설정된 값을 사용하되」* 이므로 이 이동은
    **같은 값을 같은 자리로** 옮기는 일이다. 축이 움직이면 배선이 틀린 것이다.

    ⚠ **기대값을 이 파일에 베끼지 않는다** — 골든 픽스처의 `expected_values`
    를 읽어 대조한다.
    ⚠ **`tests/golden` 과 겹치는 것을 숨기지 않는다.** 그쪽도 같은 수를 붙들며,
    이용률 `base` 를 고치는 라운드는 두 검사가 함께 빨간불이 된다. 이 검사가
    더하는 것은 **사유의 이름**이다: 실패 문면이 *「이용률을 대장으로 옮긴
    것이 축을 움직였다」* 를 가리키므로 다음 사람이 어디를 볼지 안다.
    """
    scenario = _GOLDEN / "scenario_unsubsidized.yaml"
    expected = yaml.safe_load(scenario.read_text(encoding="utf-8"))["expected_values"]
    report = _report_with_capacity_factor(None)

    assert report.metrics["npv"] == pytest.approx(float(expected["npv_won"])), (
        f"대장 기본값으로 돈 실행의 결론축이 {report.metrics['npv']:,.0f}원이다 "
        f"— 골든은 {float(expected['npv_won']):,.0f}원이다. 이용률을 대장으로 "
        "옮긴 배선이 값을 함께 바꿨는지 보라(같은 값을 같은 자리로 옮기는 "
        "일이었다)"
    )


def test_the_base_level_point_is_picked_by_name_not_by_position() -> None:
    """★★ **기준 수준(`base`) 점을 고르는 규칙의 정본** (R68/WP-2 부수 정리).

    이 규칙이 `_mismatch_lines` 안의 사적 상수로만 있어서, R68/WP-1 이 붙임 10 의
    「진단 용량」 칸을 세울 때 `core/casegrid/ledger_levels.py::LEVEL_NAMES` 로
    **같은 규칙을 다시 썼다** — 사본이 하나 생겼다. 지금은 두 자리가 이 접근자
    하나를 부른다.

    ⚠ **차례를 세어 고르지 않는다.** 그 사실을 이 검사가 실물로 붙든다: 부하
    수준 셋의 `source_label` 에서 `base` 를 찾아 그 점과 같은지 대조하며,
    「둘째 점」을 기대하지 않는다.
    """
    load_levels = build_level_map(_ASSUMPTIONS)["household_load_annual_kwh"]
    sizing = build_self_sufficiency_sizing(
        load_levels=load_levels,
        capacity_factor=0.15,
        capacity_factor_source="시험 탐침값",
        search_low_kw=0.0,
        search_high_kw=1_000.0,
    )
    picked = base_level_point(sizing)
    assert picked is not None, "대장 세 수준이 다 있는데 기준 점을 못 골랐다"
    expected = next(p for p in sizing.points if p.source_label.endswith("base"))
    assert picked is expected, (
        f"기준 점을 이름으로 고르지 않았다 — 고른 것은 {picked.source_label!r}, "
        f"이름으로 찾은 것은 {expected.source_label!r}"
    )


def test_a_sizing_without_that_point_says_so_instead_of_inventing_one() -> None:
    """★ 점이 모자라면 **`None`** 이다 — 부르는 쪽이 그 사실을 글자로 적는다.

    ⚠ 빈 점을 지어내면 붙임 10 의 「진단 용량」 칸이 **아무 예외 없이 거짓
    수치**를 인쇄한다(`_pv_diagnostic_cell` 의 「역산한 점이 없다」가 그 자리다).
    """
    empty = SelfSufficiencySizing(
        points=(),
        capacity_factor=0.15,
        capacity_factor_source="시험 탐침값",
        search_low_kw=0.0,
        search_high_kw=1.0,
        household_count=None,
        extra_appliance_load_kwh=0.0,
    )
    assert base_level_point(empty) is None
