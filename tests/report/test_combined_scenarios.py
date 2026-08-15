"""**함께 움직이는 인자를 함께 흔들었는가** — 검토 「1차 의견」 1 (R33).

의견의 물음은 한 줄이었다 — *「ESS, PV 단가가 같이 움직여도 동일한 결과가
나오는가?」* 그리고 저장소는 이미 **아니다**라고 판정해 두고 있었다:
`quick_preset_grid()` 가 설비단가 넷을 `equipment_cost_bundle` 한 축으로 묶어
흔든다. **케이스 그리드는 결합으로 보는데 리포트의 민감도만 독립**이었고, 그
어긋남은 *「PV 18% · ESS 17% 가 각각 내려가야 한다」* 로 읽혀 **사업에 불리한
쪽으로** 틀렸다.

    묶음이 케이스 그리드 선언에서 온다      ← 리포트가 따로 묶으면 탐색과 보고가 갈린다
    ★ 결합 행이 실제 실행 결과다            ← 단독 합으로 채워 넣으면 통과하면 안 된다
    ★ 상호작용을 **재고** 있다              ← 「더해진다」를 상수로 단정하면 배선 후 틀린다
    본문이 단독 기여임을 말한다             ← 말하지 않으면 각각 달성할 조건으로 읽힌다
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.grid import coupled_variable_sets
from core.casegrid.ledger_levels import build_level_map
from core.report.case_report import (
    CONCLUSION_METRIC,
    PLAN_VARIANT,
    build_case_report,
)
from core.report.combined import build_coupled_sweeps
from core.report.narrative import render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report(name: str = "scenario_unsubsidized"):
    return build_case_report(_GOLDEN / f"{name}.yaml", assumptions_path=_ASSUMPTIONS)


@pytest.mark.req("FR-801-AC7.quick", "FR-1002-AC2")
def test_bundles_come_from_the_case_grid_declaration() -> None:
    """묶음은 **케이스 그리드가 선언한 것**이며 리포트가 만들지 않는다.

    리포트가 제 손으로 묶으면 그리드가 묶음을 바꾼 날 두 산출물이 서로 다른
    사업을 그리고, 그 어긋남은 **어느 쪽도 빨간불을 내지 않는다** — 리포트가
    독립으로 그리고 있던 종전 상태가 정확히 그 모양이었다.
    """
    report = _report()
    declared = coupled_variable_sets()
    level_map = build_level_map(_ASSUMPTIONS)

    assert report.coupled_sweeps, (
        "결합 시나리오가 비어 있다 — 이 수준표에는 equipment_cost_bundle 의 "
        "구성원이 둘 이상 있다"
    )
    for sweep in report.coupled_sweeps:
        assert sweep.bundle in declared, (
            f"리포트가 케이스 그리드에 없는 묶음 {sweep.bundle!r} 을 만들었다"
        )
        expected = tuple(
            name for name in declared[sweep.bundle] if name in level_map
        )
        assert sweep.variables == expected, (
            f"{sweep.bundle}: 구성원이 선언과 다르다 — 선언 {expected} · "
            f"리포트 {sweep.variables}"
        )
        assert len(sweep.variables) >= 2, "구성원이 하나면 결합이 아니다"


@pytest.mark.req("FR-1002-AC2", "FR-1002-AC4")
def test_combined_rows_are_real_pipeline_runs() -> None:
    """★ **결합 행을 파이프라인으로 다시 돌려 같은 수가 나오는지 본다.**

    이 검사가 없으면 결합 행을 **단독 효과의 합으로 채워 넣는** 구현이
    통과한다. 지금 구성에서는 두 값이 우연히 같으므로 표를 눈으로 보아도
    구별되지 않고, 요금 인상률이 배선되는 날 조용히 틀린 수가 실린다.
    """
    report = _report()
    level_map = build_level_map(_ASSUMPTIONS)
    horizon = report.basis.horizon_years

    for sweep in report.coupled_sweeps:
        for point in sweep.points:
            assignment = {
                name: float(level_map[name]["base" if point.is_base else point.level])
                for name in point.moved
            }
            expected = _conclusion_at(level_map, assignment, horizon)
            assert point.npv == pytest.approx(expected, abs=1.0), (
                f"{sweep.bundle} / {point.moved} @ {point.level}: 표의 "
                f"{point.npv:,.0f}원 과 실제 실행 {expected:,.0f}원 이 다르다"
            )
            assert point.delta_won == pytest.approx(
                point.npv - sweep.base_npv, abs=1.0
            ), "기준 대비 증분이 표의 두 수와 맞지 않는다"


def _conclusion_at(level_map, assignment, horizon: int) -> float:
    probe = {name: dict(levels) for name, levels in level_map.items()}
    for variable, value in assignment.items():
        probe[variable] = {**probe[variable], "base": value}
    outcome = run_single_case_e2e({}, level_map=probe, horizon_years=horizon)
    return float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])


@pytest.mark.req("FR-1002-AC4")
def test_moving_together_goes_farther_than_moving_alone() -> None:
    """함께 움직인 폭이 **어느 단독 폭보다도 크다.**

    이것이 성립하지 않으면 결합 표를 실을 이유가 없다 — 단독 표가 이미 최악을
    보여 준 것이 되기 때문이다. 성립한다는 것은 곧 **단독 표만 실은 리포트가
    변동 범위를 과소평가한다**는 뜻이다.
    """
    report = _report()
    for sweep in report.coupled_sweeps:
        for level in ("low", "high"):
            singles = [
                point
                for point in sweep.points
                if point.level == level and not point.is_combined
            ]
            combined = next(
                point
                for point in sweep.points
                if point.level == level and point.is_combined
            )
            assert singles, f"{sweep.bundle}: {level} 단독 행이 없다"
            assert abs(combined.delta_won) > max(
                abs(point.delta_won) for point in singles
            ), (
                f"{sweep.bundle} @ {level}: 함께 움직인 폭이 단독 폭을 넘지 "
                "않는다 — 결합 실행이 실제로 여럿을 옮기고 있는지 확인할 것"
            )


@pytest.mark.req("FR-1002-AC2")
def test_interaction_is_measured_not_assumed() -> None:
    """★★ **「단독 효과를 더하면 결합 효과」를 코드가 단정하지 않는다.**

    지금은 설비단가가 `t=0` CAPEX 로만 들어가 정확히 더해진다. 그래서 잔차를
    **0 으로 적어 두어도** 실물 리포트는 오늘 옳게 보이고, 요금 인상률이 편익
    시계열에 배선되는 날 리포트는 **여전히 「정확히 더해진다」고 말하면서 틀린
    수를 싣는다.**

    그 미래를 지금 재현한다 — 인자들이 **서로 곱해지는** 탐침을 주고, 잔차가
    0 이 아니라 실제 값으로 나오는지 본다.
    """
    level_map = {
        "a": {"low": 1.0, "base": 2.0, "high": 3.0},
        "b": {"low": 1.0, "base": 2.0, "high": 3.0},
    }

    def multiplicative(assignment) -> float:
        """곱으로 섞이는 모형 — 단독 합과 결합이 갈린다."""
        values = {"a": 2.0, "b": 2.0, **dict(assignment)}
        return values["a"] * values["b"] * 1_000_000.0

    sweeps = build_coupled_sweeps(
        level_map=level_map,
        probe=multiplicative,
        scales={},
        base_npv=multiplicative({}),
        bundles={"synthetic": ("a", "b")},
    )
    assert len(sweeps) == 1
    sweep = sweeps[0]
    # 기준 4,000,000 · 단독 low 각 2,000,000(Δ −2,000,000 씩) ·
    # 동반 low 1,000,000(Δ −3,000,000). 잔차 = −3,000,000 + 4,000,000 = +1,000,000.
    assert sweep.interaction_won["low"] == pytest.approx(1_000_000.0), (
        f"곱으로 섞이는 모형인데 잔차가 {sweep.interaction_won['low']:,.0f}원 이다 "
        "— 잔차를 재지 않고 0 으로 적고 있다"
    )
    assert not sweep.additive, (
        "잔차가 0 이 아닌데 「정확히 더해진다」로 판정했다 — 리포트가 근거 "
        "없이 단정하게 된다"
    )


@pytest.mark.req("FR-1002-AC2", "FR-1002-AC4")
def test_body_says_the_single_variable_table_is_a_solo_contribution() -> None:
    """본문이 **단독 기여임을 말하고** 결합 표를 5.1 안에 싣는다.

    말하지 않으면 검토자는 임계값 두 줄을 *「각각 달성해야 하는 조건」* 으로
    읽는다 — 그것이 이 의견이 지적한 오독이며, 표를 잘 그려서가 아니라
    **문장으로** 막아야 한다.
    """
    text = render_markdown(_report())

    flip = text.index("### 5.1 불확실 인자")
    combined = text.index("#### 함께 움직일 때 — 결합 시나리오")
    policy = text.index("### 5.2 정책 설정값")
    assert flip < combined < policy, "결합 표가 5.1 안에 있지 않다"
    assert "단독 기여" in text[flip:policy], (
        "5.1 이 1변수 스윕을 「단독 기여」로 밝히지 않는다"
    )
    assert "각각을 달성해야 하는 조건이 아니다" in text[flip:policy]
    # 「더해진다」는 **잰 결과**로만 적는다. 문면이 사라지면 부기가 판정을
    # 하지 않고 넘어간 것이다.
    assert "잔차" in text[combined:policy]


@pytest.mark.req("FR-1002-AC4")
def test_summary_carries_the_combined_case_not_only_the_solo_ones() -> None:
    """★ **요약(1절)이 결합 결과를 함께 말한다.**

    심의위원은 1절만 읽고 판단의 뼈대를 잡는다(양식). 요약에 단독 기여만
    실으면 *「PV 와 ESS 가 각각 18%·17% 내려가야 한다」* 로 읽히고, 그것은
    **사업을 실제보다 어렵게** 그린다 — 5.1 에 결합 표를 넣고도 요약을 그대로
    두면 이 의견은 절반만 닫힌다.

    ⚠ 요약이 **제 손으로 계산하지 않았는지**도 함께 본다. 요약의 수는 5.1 의
    결합 행에서 그대로 와야 하며, 갈라지면 두 표를 대조할 때에야 드러난다.
    """
    report = _report()
    text = render_markdown(report)
    summary = text[text.index("## 1. 요약") : text.index("## 2. 평가 개요")]

    recovering = [
        point
        for sweep in report.coupled_sweeps
        for point in sweep.points
        if point.is_combined and point.recovers
    ]
    assert recovering, (
        "이 시나리오는 동반 이동에서 회수되는 행을 가져야 한다 "
        "(전제가 바뀌었다면 갱신할 것)"
    )
    assert "함께" in summary, "요약이 결합 결과를 말하지 않는다"
    for point in recovering:
        assert f"{point.npv:,.0f}원" in summary, (
            f"요약의 수가 5.1 결합 행({point.npv:,.0f}원)과 다르다 — 요약이 "
            "스스로 계산하고 있다"
        )
