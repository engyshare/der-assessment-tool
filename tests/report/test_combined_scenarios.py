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
from core.report.appendix_sections import UNREAD_BY_PIPELINE, influence_section
from core.report.case_report import (
    CONCLUSION_METRIC,
    PLAN_VARIANT,
    build_case_report,
)
from core.report.combined import build_coupled_sweeps
from core.report.narrative import SOLO_SWEEP, render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report(name: str = "scenario_unsubsidized", assumptions: Path | None = None):
    return build_case_report(
        _GOLDEN / f"{name}.yaml", assumptions_path=assumptions or _ASSUMPTIONS
    )


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
def test_body_marks_the_single_variable_table_as_a_solo_sweep() -> None:
    """본문이 **산출 방법을 열로 적고** 결합 표를 5.1 안에 싣는다.

    ⚠ 종전 이 검사는 *「각각을 달성해야 하는 조건이 아니다」* 라는 **해설
    문장**을 찾았다. 양식 0절이 해설을 금지한 뒤로는 같은 사실을 `산출` 열의
    `1변수 스윕` 라벨과 **바로 아래 결합 표**가 나른다.

    막으려는 오독은 그대로다 — 임계값 두 줄을 「각각 달성해야 하는 조건」으로
    읽는 것. 막는 수단이 문장에서 **자리와 라벨**로 바뀌었을 뿐이다.
    """
    text = render_markdown(_report())

    flip = text.index("### 5.1 불확실 인자")
    combined = text.index("#### 결합 시나리오 — ")
    policy = text.index("### 5.2 정책 설정값")
    assert flip < combined < policy, "결합 표가 5.1 안에 있지 않다"

    # ★ **라벨은 표가 비어도 있어야 한다 (R34).** 구매 비용이 배선된 뒤 실물
    # 대장에서는 검토 범위 안에 전환 인자가 없어 5.1 이 「단독 전환 인자 —
    # 없음」 한 줄이 된다. 그 줄에도 `산출` 라벨이 실려야 하며, 실리지 않으면
    # **바로 아래 결합 표가 1변수 결과로 읽힌다** — 이 검사가 막으려는 오독이
    # 표가 빌 때 오히려 쉬워진다.
    assert SOLO_SWEEP in text[flip:combined], (
        "5.1 의 1변수 산출에 「단독 기여」 라벨이 없다"
    )

    solo_rows = [
        line
        for line in text[flip:combined].splitlines()
        if line.startswith("| `")
    ]
    for row in solo_rows:
        assert SOLO_SWEEP in row, (
            f"산출 방법이 행에 없다 — 「단독 기여」임이 표에서 사라졌다: {row}"
        )
    # 「더해진다」는 **잰 결과**로만 적는다. 잔차 줄이 사라지면 판정을 하지
    # 않고 넘어간 것이다.
    assert "상호작용 잔차" in text[combined:policy]


@pytest.mark.req("FR-1002-AC2", "FR-1002-AC4")
def test_solo_rows_still_carry_the_label_when_the_table_is_not_empty(
    flip_probe_assumptions: Path,
) -> None:
    """★ **행이 있을 때 라벨이 행에 붙는가** — 위 검사의 빈 표 갈래를 메운다.

    실물 대장에서는 5.1 의 1변수 표가 비어 있다(전환 인자 0건 — R34 에 구매
    비용이 배선된 뒤). 그러면 위 검사의 **행 순회가 0회 돌아** 「행마다 라벨이
    붙는가」를 아무도 보지 않게 된다. 라벨을 행에서 지우는 변이가 그때 초록불이
    되므로, 전환 인자가 존재하는 탐침 대장에서 그 갈래를 따로 붙든다.

    ⚠ 탐침이 바꾸는 것은 **검토 범위 하나**이며 기준선 수치는 실물과 같다
    (`conftest.py`).
    """
    text = render_markdown(
        build_case_report(
            _GOLDEN / "scenario_subsidy_80.yaml",
            assumptions_path=flip_probe_assumptions,
        )
    )
    flip = text.index("### 5.1 불확실 인자")
    combined = text.index("#### 결합 시나리오 — ")

    solo_rows = [
        line for line in text[flip:combined].splitlines() if line.startswith("| `")
    ]
    assert solo_rows, (
        "탐침 대장에서도 5.1 에 단독 인자 행이 없다 — 이 검사가 0회 순회로 "
        "통과한다. `conftest.py` 의 탐침 범위를 넓힐 것"
    )
    for row in solo_rows:
        assert SOLO_SWEEP in row, (
            f"산출 방법이 행에 없다 — 「단독 기여」임이 표에서 사라졌다: {row}"
        )


@pytest.mark.req("FR-1002-AC4")
def test_summary_carries_the_combined_case_not_only_the_solo_ones(
    flip_probe_assumptions: Path,
) -> None:
    """★ **요약(1절)이 결합 결과를 함께 말한다.**

    심의위원은 1절만 읽고 판단의 뼈대를 잡는다(양식). 요약에 단독 기여만
    실으면 *「PV 와 ESS 가 각각 18%·17% 내려가야 한다」* 로 읽히고, 그것은
    **사업을 실제보다 어렵게** 그린다 — 5.1 에 결합 표를 넣고도 요약을 그대로
    두면 이 의견은 절반만 닫힌다.

    ⚠ 요약이 **제 손으로 계산하지 않았는지**도 함께 본다. 요약의 수는 5.1 의
    결합 행에서 그대로 와야 하며, 갈라지면 두 표를 대조할 때에야 드러난다.

    ⚠ **탐침 대장으로 돈다 (R34).** 구매 비용이 배선된 뒤 실물 범위에서는
    동반 하락도 −3,196,392원이라 **회수되는 결합 행이 0건**이고, 그러면 이
    검사가 아무것도 순회하지 않는다 — 「요약이 결합 결과를 말하지 않는다」를
    잡으려는 검사가 정작 결합 결과가 없을 때 초록불이 되는 형태다. 탐침은
    설비단가 하단만 넓혀 **동반 하락에서만** 회수되게 한다(`conftest.py`).
    """
    report = _report(assumptions=flip_probe_assumptions)
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
    for sweep in report.coupled_sweeps:
        if any(p.is_combined and p.recovers for p in sweep.points):
            assert sweep.bundle in summary, (
                f"{sweep.bundle}: 요약이 결합 결과를 말하지 않는다"
            )
    for point in recovering:
        assert f"{point.npv:,.0f}원" in summary, (
            f"요약의 수가 5.1 결합 행({point.npv:,.0f}원)과 다르다 — 요약이 "
            "스스로 계산하고 있다"
        )


@pytest.mark.req("FR-1002-AC2")
def test_appendix_two_marks_every_row_with_its_sweep_method() -> None:
    """붙임 2 의 모든 행이 **산출 방법**을 함께 싣는다.

    붙임 2 는 인자별 변동폭을 한 열에 세로로 늘어놓는다 — 그 모양이 곧 합을
    권하는 모양이다. 붙임을 먼저 펴는 검토자가 두 줄을 더해 「함께 움직이면
    3,920,000원」으로 읽으면, 지금 구성에서는 그것이 **우연히 맞으므로**
    스스로 드러나지도 않는다.

    ⚠ 종전에는 *「더해서 쓰지 말 것」* 이라는 지시 문장으로 막았다. 지금은
    행마다 `1변수 스윕` 을 적고 결합 결과의 자리(5.1)를 가리킨다.
    """
    lines = influence_section(_report())
    text = "\n".join(lines)

    # 「판단용」 표만 본다 — 산출 방법 열은 거기 있고, 「감사·추적용」 표는
    # 부기(출처·신뢰도)를 나르므로 열 구성이 다르다.
    judged = text[text.index("### 판단용") : text.index("### 감사·추적용")]
    rows = [
        line
        for line in judged.splitlines()
        if line.startswith("| ") and not line.startswith(("|---", "| 순위"))
    ]
    assert rows, "붙임 2 에 인자 행이 없다"
    for row in rows:
        assert SOLO_SWEEP in row or UNREAD_BY_PIPELINE in row, (
            f"산출 방법이 없는 행이 있다: {row}"
        )
    assert "5.1" in text, "붙임 2 가 결합 표의 자리를 가리키지 않는다"
