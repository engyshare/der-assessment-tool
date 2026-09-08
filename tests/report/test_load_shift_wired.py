"""**부하 이동이 리포트까지 간다** — 대장 → 러너 → 스윕 → 산출물 (R64/WP-7).

사용자 요구 2 의 남은 절반(「AI 가전」)이 성립하려면 넷이 함께 서야 한다:

    ① 대장이 정한 비율이 **본 실행**의 하루 모양을 바꾼다
    ② **스윕**(5절 민감도 · 6절 용량 검토)도 같은 하루로 돈다
    ③ 산출물이 **얼마를 옮길 수 있다고 보고 얼마나 옮겼는지**를 인쇄한다
    ④ **하지 않은 것**(정산금 갈래)을 붙임 8 이 신고한다

②가 빠지면 본문 4절은 옮긴 하루인데 5·6절은 옮기지 않은 하루가 되고, **두 절
모두 자기 기준에서는 매끈하므로 아무 검사도 걸리지 않는다** — 이 저장소가
형상(R37)·기준선 갈래(R60)·REC(R52)·가구 수(R64/WP-1)·기기 부하(R64/WP-2)에서
다섯 번 밟은 형태이며, 그래서 그 다섯과 **같은 방식**으로 붙든다.

## ★★★ 이 파일이 가장 먼저 붙드는 것 — **총량 불변**

부하를 옮기는 축이므로 연간 부하 총량이 움직이면 그것은 이 라운드가 **대장이
정한 부하를 바꾼 것**이고, 그때 결론은 다른 사업의 것이 된다. 그 성질을
실물 자산(계절 넷)으로 잰다 — 하루 한 벌 수준의 성질은
`tests/casegrid/test_load_shift.py` 가 잰다.

## ⚠ 값을 리터럴로 박지 않는다

기대 비율은 **대장에서 읽어** 만든다. 박으면 대장 값이 바뀌는 날 이 검사가
조용히 낡는다 — `tests/casegrid/test_appliance_load.py` 머리말의 같은 판단.

## ⚠ `req()` 마커를 달지 않았다

사유는 `tests/casegrid/test_load_shift.py` 머리말이 갖는다.
"""
from __future__ import annotations

import dataclasses
import math
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from core.assumption.provider import AssumptionSet
from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map, required_scalar
from core.casegrid.load_shift import (
    DR_SHIFT_NOTHING_MOVED,
    DR_SHIFTABLE_SHARE_LEDGER_KEY,
)
from core.casegrid.profiles import load_daily_shapes
from core.contracts.validation import ValidationError
from core.report.appendix_sections import LOAD_SHIFT_TABLE, appendix_section
from core.report.case_influences import CONCLUSION_METRIC
from core.report.case_report import CaseReport, build_case_report
from core.report.unreflected import (
    DIRECTION_FAVORABLE,
    JUDGED_METHOD,
    build_unreflected,
    unreflected_section,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"
_LOAD = "e2e-load"
_PV = "e2e-pv"


def _ledger_share() -> float:
    """대장이 정한 비율. **여기에 수를 적지 않는다** — 대장이 정본이다."""
    provider = AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))
    return required_scalar(
        provider, DR_SHIFTABLE_SHARE_LEDGER_KEY, note="이 검사"
    )


def _report(share: float | None = None, **fields_given: object) -> CaseReport:
    """골든 시나리오를 그대로, 또는 **비율만 오버라이드해** 돌린다.

    ⚠ **골든 픽스처를 고치지 않는다.** 읽기만 하고 쓰는 곳은
    `tempfile.TemporaryDirectory()` 안이다 — `app/services/ui_run.py::
    run_ui_case` 가 배포 경로에서 하는 것과 같은 모양이며, 그래야 이 검사가
    사용자가 실제로 지나는 통로(**전용 필드가 아니라 대장 오버라이드**)를 잰다.
    """
    fields: dict[str, Any] = yaml.safe_load(_GOLDEN.read_text(encoding="utf-8")) or {}
    fields.update(fields_given)
    if share is not None:
        fields["assumption_overrides"] = [
            {
                "key": DR_SHIFTABLE_SHARE_LEDGER_KEY,
                "value": share,
                "reason": "이 검사가 축을 흔든다",
            }
        ]
    with tempfile.TemporaryDirectory() as workspace:
        path = Path(workspace) / _GOLDEN.name
        path.write_text(
            yaml.safe_dump(fields, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return build_case_report(path, assumptions_path=_ASSUMPTIONS)


def _annual(report: CaseReport, resource: str) -> float:
    """계절 합으로 낸 그 자원의 연간 전력량(부호 규약 그대로)."""
    return math.fsum(
        season.per_resource_annual_kwh.get(resource, 0.0) for season in report.seasons
    )


def _moved(report: CaseReport) -> float:
    return math.fsum(season.load_shift_annual_kwh for season in report.seasons)


def test_the_deployed_default_actually_moves_load() -> None:
    """★★★ **기본 실행이 이 갈래를 켜고 돈다** — 꺼져 있으면 요구 2 를 못 만족한다.

    대장이 값을 갖고(`track: assume`) 그 값이 0 이 아니므로, 골든 시나리오를
    그대로 돌린 실행에서 **실제로 옮긴 몫이 0 보다 크다.** 갈래만 만들고
    기본값을 0 으로 두면 그것은 사용자의 요구 범위를 우리가 줄인 것이다.
    """
    report = _report()
    assert report.dr_shiftable_share_pct == pytest.approx(_ledger_share())
    assert report.dr_shiftable_share_pct > 0.0, (
        "대장 비율이 0 이다 — 기본 실행이 부하를 옮기지 않으면 요구 2 의 "
        "「AI 가전」이 반영되지 않는다"
    )
    assert _moved(report) > 0.0, (
        f"비율 {report.dr_shiftable_share_pct}% 인데 옮긴 몫이 0 이다 — "
        "배선이 계산에 닿지 않았다"
    )


def test_moving_the_load_does_not_move_the_totals() -> None:
    """★★★ **연간 부하·발전 총량이 한 kWh 도 안 움직인다** (판정 ①).

    옮기는 것이지 더하거나 빼는 것이 아니다. 총량이 움직이면 결론이 대장이
    정한 부하가 아닌 것 위에 서고, 그 어긋남은 아무 예외도 내지 않는다.
    """
    still = _report(share=0)
    moved = _report()
    assert _moved(still) == 0.0

    load_before, load_after = -_annual(still, _LOAD), -_annual(moved, _LOAD)
    assert load_after == pytest.approx(load_before, abs=1e-6), (
        f"연간 부하가 {load_before:,.6f} → {load_after:,.6f} 로 움직였다"
    )
    pv_before, pv_after = _annual(still, _PV), _annual(moved, _PV)
    assert pv_after == pytest.approx(pv_before, abs=1e-6), (
        f"연간 발전이 {pv_before:,.6f} → {pv_after:,.6f} 로 움직였다"
    )
    # ★ 설비를 안 바꾼다 — 초기투자가 그대로여야 한다
    assert (
        moved.basis.initial_investment_won == still.basis.initial_investment_won
    )


def test_the_conclusion_axis_actually_moves() -> None:
    """★★★ 비율을 흔들면 **결론축이 실제로 움직인다.**

    이 단언이 없으면 아래 검사들은 *「값을 나르기만 하고 계산에 안 쓴다」* 로도
    통과한다 — 이 저장소가 반복해 만난 「표시만 하는 구현」이다.

    ⚠ **방향을 단언하지 않는다.** 옮기면 계통 수전(비용)이 줄지만 잉여 판매·
    REC 도 함께 줄고 부하가 평탄해져 첨두 절감도 준다 — 순효과의 부호는 단가와
    계절별 잉여가 정하는 값이며 이 검사가 정할 것이 아니다.
    """
    still = float(_report(share=0).metrics[CONCLUSION_METRIC])
    moved = float(_report().metrics[CONCLUSION_METRIC])
    assert moved != pytest.approx(still, abs=1.0), (
        f"비율을 0 → {_ledger_share()}% 로 올렸는데 결론축이 그대로다 "
        f"({still:,.0f}원) — 부하 이동이 계산에 들어가지 않았다"
    )


def test_more_shiftable_share_moves_more_until_the_surplus_caps_it() -> None:
    """★★ 비율을 올리면 옮긴 몫이 늘고, **그 날 잉여에서 멈춘다** (판정 ②).

    포화가 이 축의 성질이다 — 대장의 `impact_note` 가 *「비율에 비례하지
    않는다」* 로 적은 그 사실이며, 적어만 두고 재지 않으면 문면이 낡는다.

    ## ★ 상한은 **그 날의 잉여**다 — 그리고 50% 에서 이미 걸린다

    옮길 수 있는 몫은 *「옮겨 갈 자리에 남은 태양광 잉여」* 가 정한다. 비율은
    **옮길 후보**를 늘릴 뿐이므로 후보가 잉여를 넘어서는 순간 옮긴 몫이 멈춘다
    — 실측(R67/WP-N1d · 골든 무보조)에서 **50% 와 100% 가 같은 수**다:

        share  5%   2,900.225608538557 kWh
        share 50%  10,474.151920363418 kWh   ← 여기서 이미 잉여 상한
        share 100% 10,474.151920363418 kWh

    ⚠ **그 정체를 「같아도 된다」로 적지 않는다** (`small < big <= full`). 그러면
    우연히 같아도 통과하고, *「상한에 걸렸다」* 는 이 축의 성질이 무감시가 된다.
    ⇒ **정체를 «측정된 주장»으로 적는다** — 50% 에서 상한에 **걸려야** 한다.
    ⚠ 100% 가 다시 늘면 이 검사가 빨간불이 된다. 그때는 완화하지 말고 **왜 그
    날 잉여를 넘어 옮길 수 있게 됐는지**를 보라(잉여가 늘었거나 상한이 풀렸다).
    """
    small, big, full = _moved(_report(share=5)), _moved(_report(share=50)), _moved(
        _report(share=100)
    )
    assert small < big, f"5% → 50% 에서 옮긴 몫이 늘지 않았다: {small} · {big}"
    assert big == pytest.approx(full), (
        f"50% 에서 이미 그 날 잉여 상한에 걸려야 한다 — 50% {big} · 100% {full} "
        "가 갈렸다. 완화하지 말고 잉여가 늘었는지 상한이 풀렸는지 보라"
    )
    assert full < 20.0 * small, (
        f"비율을 20배 올렸는데 옮긴 몫이 {full / small:.1f}배다 — 잉여 상한이 "
        "이동량을 자르지 않고 있다"
    )


def test_the_sweep_runs_on_the_same_day_as_the_body() -> None:
    """★★★ **5·6절의 스윕도 같은 하루로 돈다** — 두 절이 다른 사업을 그리지 않는다.

    ## 어떻게 재는가 — 「읽지 않는 인자」가 스윕의 **기준선**을 드러낸다

    `unread_by_pipeline` 인 인자는 끝에서 끝까지 흔들어도 결론축이 0원
    움직인다. 그러므로 그 인자의 `npv_low`·`npv_high` 는 **스윕의 기준선 그
    자체**이며, 스윕이 옮기지 않은 하루로 돌면 그 값이 본문의 결론과 갈린다.
    `tests/report/test_appliance_load_wired.py` 가 기기 부하 축에서 같은 방법을
    쓴다.
    """
    report = _report()
    conclusion = float(report.metrics[CONCLUSION_METRIC])
    unread = [entry for entry in report.influences if entry.unread_by_pipeline]
    assert unread, (
        "파이프라인이 읽지 않는 인자가 0건이다 — 이 검사가 0회 순회로 통과한다"
    )
    for entry in unread:
        assert entry.npv_low == pytest.approx(conclusion, abs=1.0), (
            f"`{entry.variable}` 의 스윕 기준선이 {entry.npv_low:,.0f}원인데 "
            f"본문 결론은 {conclusion:,.0f}원이다 — 스윕이 옮기지 않은 하루로 "
            "돌고 있다"
        )
        assert entry.npv_high == pytest.approx(conclusion, abs=1.0)


def test_the_appendix_prints_the_share_and_what_actually_moved() -> None:
    """★★★ 붙임 1 이 **비율과 실제로 옮긴 몫을 함께** 싣는다 (판정 ⑥ ①②).

    비율만 적으면 *「10% 라고 했으니 10% 가 옮겨졌다」* 로 읽힌다 — 실제
    이동량은 그 날 잉여가 자른다.
    """
    report = _report()
    lines = appendix_section(report)
    assert any(LOAD_SHIFT_TABLE in line for line in lines), (
        f"붙임 1 에 「{LOAD_SHIFT_TABLE}」 표가 없다"
    )
    assert any(
        f"{report.dr_shiftable_share_pct:,.1f}" in line for line in lines
    ), "붙임 1 이 이 실행의 비율을 인쇄하지 않는다"
    assert any(f"{_moved(report):,.1f} kWh/년" in line for line in lines), (
        "붙임 1 이 실제로 옮긴 몫을 인쇄하지 않는다"
    )
    # ★ 판정 ⑥ — 셋을 글자로 적는다
    text = "\n".join(lines)
    assert "기기별 목록이 아니다" in text, "① 총량의 비율이라는 사실이 없다"
    assert "가정값이다" in text, "② 비율이 가정값이라는 사실이 없다"
    assert "정산금" in text, "③ 정산금 갈래를 하지 않는다는 사실이 없다"
    # ★ 계절마다 한 줄 — 옮긴 몫이 0 이어도 줄을 지우지 않는다
    for season in report.seasons:
        assert any(line.startswith(f"| {season.name} |") for line in lines), (
            f"붙임 1 에 계절 「{season.name}」 줄이 없다"
        )


def test_a_season_with_nowhere_to_move_says_so_in_words() -> None:
    """★★★ **옮긴 몫이 0 인 계절을 글자로 말한다** — 빈칸으로 두지 않는다.

    ⚠ **배포 자산에서는 네 계절 모두 옮긴다**(비율 10% 에서는 잉여가 아니라
    비율이 이동량을 자른다). 그러나 잉여가 마르는 자산·구성은 언제든 오며
    (겨울 하루의 잉여는 3.25kWh 뿐이다), 그때 표가 0 을 빈칸으로 두면 검토자가
    *「그 계절에는 옮길 곳이 없었다」* 와 *「그 계절이 아예 없다」* 를 가릴 수
    없다. 그래서 **그 하루를 만들어** 문면을 잰다.
    """
    report = _report()
    dry = dataclasses.replace(
        report,
        seasons=tuple(
            dataclasses.replace(season, load_shift_annual_kwh=0.0)
            for season in report.seasons
        ),
    )
    lines = appendix_section(dry)
    printed = [line for line in lines if DR_SHIFT_NOTHING_MOVED in line]
    assert len(printed) == len(report.seasons) + 1, (
        f"「{DR_SHIFT_NOTHING_MOVED}」가 {len(printed)}줄이다 — 계절 "
        f"{len(report.seasons)}줄과 연간 합 한 줄에 모두 서야 한다"
    )


def test_a_run_without_seasons_says_the_operation_did_not_stand() -> None:
    """★★ **계절 형상이 없는 실행**은 「0 kWh」가 아니라 그 사실을 적는다.

    형상 자산 없이 도는 실행(케이스 그리드·성능 측정)에서는 「잉여가 있는
    시각」이라는 개념 자체가 서지 않는다 — `0 kWh` 로 적으면 「옮길 곳이
    없었다」로 읽힌다.
    """
    lines = appendix_section(dataclasses.replace(_report(), seasons=()))
    assert any("옮기는 연산이 서지 않았다" in line for line in lines)
    assert not any(line.startswith("| 봄 |") for line in lines)


def test_the_settlement_branch_is_reported_as_unreflected() -> None:
    """★★★ **하지 않은 것을 붙임 8 이 신고한다** (판정 ⑥ ③ · 사용자 판정 §5).

    사용자가 고른 것은 (가) 자가소비 최적화 하나이고 정산금 갈래는 하지
    않는다. ⛔ 크기를 추정하지 않는 이유는 참고자료의 결함 1 이 그 형태였기
    때문이다 — *「★ V2G 시장 미개설, 1~2만원/일 범위 중간값」* 이라 적힌 수익이
    편익의 57.7% 를 차지하고 빼면 결론의 부호가 뒤집힌다.
    """
    items = build_unreflected(_report())
    matched = [item for item in items if "수요반응 정산금" in item.label]
    assert len(matched) == 1, (
        f"붙임 8 에 수요반응 정산금 항목이 {len(matched)}건이다"
    )
    item = matched[0]
    assert item.direction == DIRECTION_FAVORABLE
    assert item.judged == JUDGED_METHOD, (
        "이 결손은 이 실행의 값이 아니라 매핑이 없다는 사실에서 온다 — "
        "「매 실행 측정」으로 적으면 구성을 바꾸면 사라지는 것처럼 읽힌다"
    )
    assert "미정량" in item.magnitude, "크기를 추정하지 않았다는 사실이 없다"
    assert "FR-401-AC2.DemandResponse" in item.reason
    text = "\n".join(unreflected_section(items))
    assert "수요반응 정산금" in text


def test_a_share_outside_the_axis_is_refused_at_one_place() -> None:
    """★★ 오버라이드로 들어온 값도 **같은 자리에서** 판정된다 (`NFR-303`).

    오버라이드 관문은 **형만** 맞대어 보므로(`scenario_overrides._kind`) 범위
    밖의 수가 계산까지 올 수 있다. 거부 문면이 층마다 생기지 않게
    `resolve_shiftable_share` 하나가 진다.
    """
    with pytest.raises(ValidationError, match="옮길 수 있는 가전 부하 비율"):
        _report(share=150)


def test_a_run_without_a_load_total_is_untouched_by_the_share() -> None:
    """★★ **부하를 세우지 않은 실행은 옮길 것이 없다** — 비율이 있어도 같다.

    총량을 주지 않은 실행(케이스 그리드·성능 측정)에서는 부하 자원이 서지
    않으므로 옮길 하루가 없다. 그때 비율이 무언가를 바꾸면 그것은 **부하 없이
    부하를 옮긴 것**이다.
    """
    levels = build_level_map(_ASSUMPTIONS)
    shapes = load_daily_shapes()
    still = run_single_case_e2e(
        {}, level_map=levels, horizon_years=20, daily_shapes=shapes
    )
    asked = run_single_case_e2e(
        {}, level_map=levels, horizon_years=20, daily_shapes=shapes,
        dr_shiftable_share_pct=_ledger_share(),
    )
    assert list(asked.dispatch.grid_export) == list(still.dispatch.grid_export)
    assert list(asked.dispatch.grid_import) == list(still.dispatch.grid_import)
    assert all(season.load_shift_annual_kwh == 0.0 for season in asked.seasons)


def test_the_extra_appliances_do_not_join_the_shiftable_denominator() -> None:
    """★★ 히트펌프를 얹어도 **총량 불변**은 그대로다 — 분모만 좁아진다.

    분모가 가전뿐이라는 성질 자체는 `tests/casegrid/test_load_shift.py::
    test_the_denominator_is_the_appliance_load_only` 가 하루 한 벌로 잰다.
    여기서는 그 좁힘이 **실물 경로에서 총량을 깨지 않는가**를 본다 — 추가
    기기가 들어오면 부하가 커져 잉여가 줄고, 그 상호작용이 이 자리를 지난다.
    """
    from core.casegrid.appliance_load import HEATPUMP_LOAD_FIELD

    still = _report(share=0, **{HEATPUMP_LOAD_FIELD: 900.0})
    moved = _report(**{HEATPUMP_LOAD_FIELD: 900.0})
    assert -_annual(moved, _LOAD) == pytest.approx(-_annual(still, _LOAD), abs=1e-6)
    assert _moved(moved) > 0.0
