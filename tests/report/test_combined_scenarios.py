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
from core.report.narrative import NONE_IN_RANGE, SOLO_SWEEP, render_markdown
from tests.report.conftest import report_rec_terms, report_shapes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"

#: 1절 요약의 **결합** 칸 머리. 문면을 검사가 갖는 이유는 이 칸이 사라졌는지를
#: 재기 때문이다 — 칸 이름을 리포트에서 읽어 오면 「칸이 없다」를 잴 수 없다.
#: 표제를 고치는 라운드는 이 상수를 함께 고친다(그때 빨간불이 알린다).
COMBINED_SUMMARY_ROW = "| 결론 전환 조건 (결합) |"


def _report(name: str = "scenario_unsubsidized", assumptions: Path | None = None):
    return build_case_report(
        _GOLDEN / f"{name}.yaml", assumptions_path=assumptions or _ASSUMPTIONS
    )


#: 5.1 의 인자 행이 `산출` 열에 쓸 수 있는 라벨 **전부**.
#:
#: 종전 이 검사는 `SOLO_SWEEP` 하나만 허용했다. 5.1 이 「전환까지 남는 거리」
#: 표를 싣게 되며(2026-08-17) 그 표의 **미반영 인자 행**은 붙임 2 와 같은
#: 라벨(`UNREAD_BY_PIPELINE`)을 쓰므로 목록으로 넓혔다 — 그 라벨이 「1변수
#: 스윕이 아니다」를 뜻하는 것은 아니고, **끝에서 끝까지 흔들었는데 0원이었다**
#: 는 관측을 함께 나른다.
#:
#: ⚠ **「무엇이든 있으면 통과」로 넓히지 않았다.** 라벨을 지우는 변이는 여전히
#: 빨간불이어야 하고, 그것이 이 검사가 지키는 것이다.
_METHOD_LABELS = (SOLO_SWEEP, UNREAD_BY_PIPELINE)


def _assert_method_label(row: str) -> None:
    assert any(label in row for label in _METHOD_LABELS), (
        f"산출 방법이 행에 없다 — 「단독 기여」임이 표에서 사라졌다: {row}"
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
    # ★ **리포트와 같은 배선으로 돌린다 (R37).** `build_case_report` 가
    # 일사 곡선을 본 실행·스윕에 넘기므로, 형상 없이 다시 돌리면 리포트의
    # 수를 **다른 사업**의 0 선에 대고 재는 것이 된다. 형상은 검사가
    # 자산에서 직접 읽는다(`conftest.report_shapes` 독스트링).
    # ★★ **가구 부하도 같은 배선으로 돌린다 (R48/WP-B → WP-F).** 본 실행·
    # `_Sweeper.conclusion_at_many()` 모두 `household_load_annual_kwh` 를
    # 넘긴다(`docs/decisions-2026-08-31-R48.md` §5·§1·§4). 이 헬퍼만 안 넘기면
    # 리포트가 실은 수(부하 있음)와 이 재실행(부하 없음)이 갈린다 — R48 착수
    # 직후 실측: 결합 기준행이 리포트 −12,956,180원인데 이 헬퍼는 −8,466,123원을
    # 냈다. 부하 없는 재실행은 리포트가 실제로 돈 실행이 아니므로 오라클이
    # 아니라 이 헬퍼 쪽이 낡아 있었다.
    rec_price, rec_weight = report_rec_terms()
    outcome = run_single_case_e2e(
        {},
        level_map=probe,
        horizon_years=horizon,
        daily_shapes=report_shapes(),
        annual_load_kwh=probe["household_load_annual_kwh"]["base"],
        rec_price_won_per_unit=rec_price, rec_weight_pv=rec_weight,
    )
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
        _assert_method_label(row)
    # 「더해진다」는 **잰 결과**로만 적는다. 잔차 줄이 사라지면 판정을 하지
    # 않고 넘어간 것이다.
    assert "상호작용 잔차" in text[combined:policy]


@pytest.mark.req("FR-1002-AC2", "FR-1002-AC4")
def test_solo_rows_still_carry_the_label_when_the_table_is_not_empty() -> None:
    """★ **행이 있을 때 라벨이 행에 붙는가** — 위 검사의 빈 표 갈래를 메운다.

    위 검사는 표가 **빌 때**의 갈래를 본다. 그때 행 순회가 0회 돌아 「행마다
    라벨이 붙는가」를 아무도 보지 않게 되므로, 행이 있는 갈래를 여기서 따로
    붙든다 — 라벨을 행에서 지우는 변이가 그 갈래에서만 빨간불이 된다.

    ✔ **실물 대장으로 돈다 (R41).** R34 는 이 자리에 탐침 대장을 세웠고 사유는
    *「실물 대장에서는 5.1 의 1변수 표가 비어 있다」* 였다 — **그 사유는 두 번
    낡았다.** ⓐ R35 ② 가 5.1 을 고쳐 전환 인자가 0건이어도 **거리 행**을 싣게
    했고(무보조도 5행이다) ⓑ 결론축이 세 번 내려가 보조 80% 는 전환 인자를
    실제로 갖는다. R41 실측: 두 시나리오 모두 **단독 행 5건**이다.
    """
    text = render_markdown(
        build_case_report(
            _GOLDEN / "scenario_subsidy_80.yaml", assumptions_path=_ASSUMPTIONS
        )
    )
    flip = text.index("### 5.1 불확실 인자")
    combined = text.index("#### 결합 시나리오 — ")

    solo_rows = [
        line for line in text[flip:combined].splitlines() if line.startswith("| `")
    ]
    assert solo_rows, (
        "실물 대장에서 5.1 에 단독 인자 행이 없다 — 이 검사가 0회 순회로 통과한다"
    )
    for row in solo_rows:
        _assert_method_label(row)


@pytest.mark.req("FR-1002-AC4")
def test_summary_carries_the_combined_case_not_only_the_solo_ones() -> None:
    """★ **요약(1절)이 결합 결과를 함께 말한다.**

    심의위원은 1절만 읽고 판단의 뼈대를 잡는다(양식). 요약에 단독 기여만
    실으면 *「PV 와 ESS 가 각각 18%·17% 내려가야 한다」* 로 읽히고, 그것은
    **사업을 실제보다 어렵게** 그린다 — 5.1 에 결합 표를 넣고도 요약을 그대로
    두면 이 의견은 절반만 닫힌다.

    ⚠ 요약이 **제 손으로 계산하지 않았는지**도 함께 본다. 요약의 수는 5.1 의
    결합 행에서 그대로 와야 하며, 갈라지면 두 표를 대조할 때에야 드러난다.

    ## ⚠⚠ 전제를 바꿨다 — **탐침 대장에서 실물 대장으로** (R49)

    종전 판은 `recovery_probe_assumptions`(설비단가 하단 둘을 넓힌 탐침)로 돌며
    *「동반 하락에서 회수되는 행이 있어야 한다」* 를 단정했다. R48 이 결론축을
    **−6,289,675 → −12,956,180원**으로 두 배로 내리자 **탐침으로도 회수가
    0건**이 됐다(R49 실측 · 무보조 · 탐침 대장: 동반 하락 −5,916,200원 —
    0 선에 그만큼 못 미친다). 그래서 이 검사가 빨간불이 됐다.

    🚫 **탐침을 더 밀지 않았다.** 판정 §3 이 명시로 막는다 — *「검사용 탐침
    단가를 더 낮춰 억지로 답을 만들지 마라. 현실에 없는 설비값이 되고 「이 값이면
    됩니다」가 실현 불가능한 조건이 된다」*. 그러므로 탐침이 살릴 수 있는 갈래는
    **더 이상 없다**(`conftest.py` 머리말이 그 사실을 진다).

    ## ★ 대신 오라클을 **갈래 둘로** 세운다 — 어느 쪽이든 재는 것이 있다

        회수 행이 있으면   → 요약이 그 묶음과 **그 수**를 말한다   (종전 오라클 그대로)
        회수 행이 없으면   → 요약이 결합 칸을 **비우지 않고** 「없음」이라 적고,
                             5.1 결합 표는 **행 전건의 수를 그대로 싣는다**

    ⚠ 뒤쪽 갈래가 「0건이면 통과」가 아니다 — 세 가지를 실제로 잰다: **결합
    점이 존재하는가**(0회 순회 방지) · **요약의 결합 칸이 살아 있는가**(요약이
    결합을 통째로 빼면 빨간불) · **「없음」이 실물과 맞는가**(어느 결합 점도
    0 선을 넘지 않아야 그 문면이 참이다). 마지막 것이 `point.recovers` 판정을
    거꾸로 매긴 변이를 잡는다.

    ⚠ 무보조로 돈다 — 결합 회수가 가장 먼 시나리오이며, 「없음」 갈래를 실제로
    지나는 자리다.
    """
    report = _report()
    text = render_markdown(report)
    summary = text[text.index("## 1. 요약") : text.index("## 2. 평가 개요")]
    combined_section = text[text.index("#### 결합 시나리오") : text.index("### 5.2")]

    combined = [
        point
        for sweep in report.coupled_sweeps
        for point in sweep.points
        if point.is_combined
    ]
    assert combined, (
        "결합 이동 점이 0건이다 — 이 검사가 0회 순회로 통과한다 "
        "(묶음 선언이 사라졌다면 `coupled_variable_sets` 부터 볼 것)"
    )
    assert COMBINED_SUMMARY_ROW in summary, (
        f"요약에 「{COMBINED_SUMMARY_ROW}」 칸이 없다 — 요약이 단독만 말한다"
    )
    cell = next(
        line for line in summary.splitlines() if line.startswith(COMBINED_SUMMARY_ROW)
    )

    recovering = [point for point in combined if point.recovers]
    if recovering:
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
        return

    assert NONE_IN_RANGE in cell, (
        f"결합 회수 행이 0건인데 요약의 결합 칸이 「{NONE_IN_RANGE}」라 적지 "
        f"않는다: {cell}"
    )
    # ⚠ **「없음」이 실물과 맞는가.** 회수 판정을 거꾸로 매긴 구현은 여기서
    # 걸린다 — 0 선을 넘은 점이 있는데 요약은 「없음」이라 적고 있게 된다.
    worst_short = max(point.npv for point in combined)
    assert worst_short < 0.0, (
        f"요약은 결합 전환 조건이 「없음」이라 적는데 결합 점 하나가 "
        f"{worst_short:,.0f}원(0 선 위)이다 — 회수 판정이 요약과 갈렸다"
    )
    # ★ **결합 결과 자체는 사라지지 않는다** — 요약이 「없음」이라 적더라도
    # 5.1 은 행 전건의 수를 싣는다. 이것이 없으면 「함께 움직이면 어디까지
    # 가는가」를 검토자가 어디서도 읽을 수 없다.
    for point in combined:
        assert f"{point.npv:,.0f}원" in combined_section, (
            f"5.1 결합 표가 {point.level} 행의 수({point.npv:,.0f}원)를 싣지 않는다"
        )


def test_the_recovery_probe_can_no_longer_reach_the_zero_line(
    recovery_probe_assumptions: Path,
) -> None:
    """⚠⚠ **탐침 대장의 상태 자체를 잰다** — 위 검사가 실물로 옮긴 사유 (R49).

    `conftest.py` 의 탐침은 설비단가 하단 둘을 넓혀 *「동반 하락에서만 회수된
    다」* 를 만들어 두는 대장이었다. R48 이 결론축을 두 배로 내리면서 **넓힌
    하단으로도 회수가 0건**이 됐고, 그래서 위 검사는 실물 대장으로 옮겼다.

    ## ⚠⚠ **값을 밀어서는 되돌릴 수 없다 — 실측으로 확인했다** (R49)

    판정 §3 은 *「탐침 단가를 더 낮춰 억지로 답을 만들지 마라」* 로 막는데,
    **막기 이전에 가능하지도 않다.** 무보조 · 동반 하락의 최선값:

        하단 600,000 / 150,000 (지금)   −5,916,200원
        하단 100,000 /  20,000          −2,916,361원
        하단       0 /       0 (공짜)   **−2,385,746원**  ← 5.3 「운영 단계 20년 누적」

    ★ 설비를 **공짜로 줘도** 회수되지 않는다 — 설비단가 축의 하한이 **운영 단계
    누적**이기 때문이다. 그래서 이 검사가 빨간불이 되는 길은 값이 아니라 **구조**
    뿐이다(운영 단계가 플러스로 돌아서는 것 · 넓힘이 사라지는 것).

    🚫 **이 검사를 「회수가 없으면 통과」로 읽지 마라.** 재는 것은 *탐침이 실물과
    같아졌는지*이며, 그것을 위해 **탐침이 실제로 넓혀졌다**는 사실(실물과 다른
    결합 값을 낸다)을 함께 단정한다. 넓힘이 사라져 탐침이 실물의 사본이 되면
    이 검사가 그것을 잡는다 — 픽스처의 `assert item is not None` 이 잡는 것과
    같은 자리의, 값 쪽 짝이다(R49 실측: 하단 둘을 지우면 빨간불).
    """
    probed = [
        point
        for sweep in _report(assumptions=recovery_probe_assumptions).coupled_sweeps
        for point in sweep.points
        if point.is_combined
    ]
    plain = [
        point
        for sweep in _report().coupled_sweeps
        for point in sweep.points
        if point.is_combined
    ]
    assert probed and len(probed) == len(plain), "결합 이동 점이 없다 — 잴 대상이 없다"

    # ★ 탐침이 **실제로 넓혀졌는가** — 아니면 실물의 사본이다.
    assert [p.npv for p in probed] != [p.npv for p in plain], (
        "탐침 대장이 실물과 같은 결합 값을 낸다 — `_WIDENED` 가 비었거나 "
        "대장 값이 탐침값까지 내려왔다"
    )

    best = max(point.npv for point in probed)
    assert best < 0.0, (
        f"탐침 대장에서 결합 이동이 회수된다(최선 {best:,.0f}원) — 운영 단계가 "
        "플러스로 돌았다는 뜻이다(설비단가 하단만으로는 여기까지 오지 못한다: "
        "공짜로 줘도 -2,385,746원). 그러면 "
        "`test_summary_carries_the_combined_case_not_only_the_solo_ones` 의 "
        "회수 갈래를 이 탐침으로 되돌릴 수 있다(`conftest.py` 머리말). "
        "⚠ 하단을 누가 더 밀었다면 판정 §3 이 금지한 것이므로 먼저 되돌려라"
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
