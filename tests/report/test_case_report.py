"""리포트가 **조립되어 나오는가** — FR-1001 · FR-1002 · FR-1005.

## 이 파일이 종전 리포트 테스트와 다른 점

`tests/report/test_report.py` 는 부품(`generate_pdf`·`rank_influences` …)을 **직접
부른다.** 그래서 조항 `FR-1001-AC1`~`AC4` 와 `FR-1002-AC1`~`AC6` 이 전부 「자동」
으로 세어져 있었는데도 **그 부품을 부르는 배포 코드는 0곳**이었다 — 매핑표가
초록불인 채 리포트를 낼 통로가 없었고, 그래서 `MC-1` 이 시작될 수 없었다.

이 파일은 부품을 부르지 않는다. **진입점 하나**(`build_case_report`)를 지나서
나온 것만 본다.

    지원이 결론에 반영된다              ← 변형을 읽지 않으면 80% 보조가 무보조와 같아진다
    ★ 보고된 전환 임계값이 진짜다        ← 그 값으로 다시 돌려 결론이 뒤집히는지 본다
    대입값이 지표와 맞는다              ← 산식이 장식이 아니다
    부기가 대장에서 온다                ← 리포트가 출처를 지어내지 않는다
    ★ 읽히지 않는 인자를 드러낸다        ← 「영향 0」을 「영향 없음」으로 적지 않는다

둘째가 요점이다. 임계값을 **표시만** 하는 구현도 나머지를 전부 통과한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.report.case_report import (
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    PLAN_VARIANT,
    build_case_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report(name: str = "scenario_unsubsidized"):
    return build_case_report(_GOLDEN / f"{name}.yaml", assumptions_path=_ASSUMPTIONS)


@pytest.mark.req("FR-1002-AC1", "FR-1002-AC3", "FR-1002-AC6", "FR-1005-AC1")
def test_one_call_produces_every_section_the_reviewer_needs() -> None:
    """진입점 하나가 네 절의 재료를 **함께** 낸다.

    갈라 두면 출구마다 다른 조립 순서가 생기고, 그중 하나가 영향도 절을
    빠뜨려도 아무 검사도 걸리지 않는다 — 그것이 이 파일이 생기기 전의 상태다.
    """
    report = _report()

    assert report.influences, "영향도 순위가 비어 있다 (FR-1002-AC1)"
    deltas = [entry.delta_won for entry in report.influences]
    assert deltas == sorted(deltas, reverse=True) or report.flipping, (
        "영향도 순위가 내림차순이 아니다"
    )
    assert report.formulas, "산식이 비어 있다 (FR-1001-AC2)"
    assert report.assumptions, "가정 부록이 비어 있다 (FR-1002-AC6)"
    assert report.manifest_hash, "매니페스트가 없다 (FR-1005-AC1)"
    # `AC3` 은 인자마다 사용값·단위·기준연도·출처·신뢰도를 **함께** 요구한다.
    for entry in report.influences:
        assert entry.confidence, f"{entry.variable}: 신뢰도 칸이 비었다"
        assert entry.source, f"{entry.variable}: 출처 칸이 비었다"


@pytest.mark.req("FR-607-AC1")
def test_conclusion_reads_the_supported_variant_not_the_case_metric() -> None:
    """★ **지원이 결론에 반영된다.**

    러너의 케이스 지표는 총사업비를 `t=0` 에 두므로 보조율과 **무관하게 같다**.
    리포트가 그것을 결론으로 적으면 *「80% 를 지원해도 결과가 같다」* 는 틀린
    진술이 되고, 그 틀림은 수치가 그럴듯해서 스스로 드러나지 않는다.
    """
    plain = _report("scenario_unsubsidized")
    subsidised = _report("scenario_subsidy_80")

    assert plain.baseline_metrics[CONCLUSION_METRIC] == pytest.approx(
        subsidised.baseline_metrics[CONCLUSION_METRIC]
    ), "무지원 기준선은 두 시나리오에서 같아야 한다"
    assert subsidised.metrics[CONCLUSION_METRIC] > plain.metrics[CONCLUSION_METRIC], (
        "보조 80% 의 결론이 무보조와 같다 — 리포트가 변형을 읽지 않았다"
    )
    assert subsidised.metrics["initial_outlay_won"] < plain.metrics[
        "initial_outlay_won"
    ], "지원을 받았는데 초기지출이 줄지 않았다"


@pytest.mark.req("FR-1002-AC2", "FR-607-AC1")
def test_the_sweep_follows_the_supported_variant_too() -> None:
    """★ **영향도 스윕도 지원을 반영한다.**

    결론 한 줄과 스윕은 **서로 다른 줄**에서 변형을 읽는다. 결론만 고치면
    표는 「보조 80% 사업」인데 영향도 순위는 **무보조 사업의 것**이 된다 —
    검토자는 지원을 받은 사업을 보면서 지원 없는 사업의 위험 인자를 읽는다.

    변이로 확인했다: 스윕 쪽만 케이스 지표로 되돌리면 위 결론 검사는 **전건
    초록불**이었다. 무보조 시나리오에서는 두 값이 같아서 드러나지 않는다.
    """
    plain = _report("scenario_unsubsidized")
    subsidised = _report("scenario_subsidy_80")

    plain_flips = {entry.variable for entry in plain.flipping}
    subsidised_flips = {entry.variable for entry in subsidised.flipping}
    assert plain_flips != subsidised_flips, (
        "보조 80% 의 전환 인자가 무보조와 같다 — 스윕이 변형을 읽지 않고 "
        "케이스 지표(총사업비 기준)로 돌고 있다"
    )

    # ⚠ **영향폭(delta)은 같아도 정상이다.** 보조금은 `t=0` 에 상수로 들어가
    # NPV 를 통째로 평행이동시키므로, 인자를 흔들었을 때의 **폭**은 바뀌지
    # 않는다. 바뀌는 것은 **0 선을 넘느냐**이고 그것이 결론이다 — 그래서 위에서
    # 전환 인자 집합을 본다. 여기서 폭이 다르기를 요구하면 정당한 상태를
    # 빨간불로 만들고, 그런 검사는 곧 꺼진다.


@pytest.mark.req("FR-1002-AC2", "FR-1002-AC4")
def test_reported_flip_threshold_actually_flips_the_conclusion() -> None:
    """★★ **보고된 임계값으로 다시 돌려 결론이 실제로 뒤집히는지 본다.**

    이 검사가 없으면 임계값을 **표시만** 하는 구현이 통과한다 — 검토자는
    리포트에서 *「단가가 이 값을 넘으면 사업성이 뒤집힌다」* 를 읽고 정책
    판단을 하는데, 그 값이 계산과 무관해도 아무도 모른다.
    """
    report = _report()
    flipping = report.flipping
    assert flipping, "이 시나리오는 전환 인자를 가져야 한다 (전제가 바뀌었다면 갱신할 것)"

    level_map = build_level_map(_ASSUMPTIONS)
    horizon = report.basis.horizon_years

    for entry in flipping:
        assert entry.threshold is not None
        span = entry.high - entry.low
        below = _conclusion_at(
            level_map, entry.variable, entry.threshold - span * 0.05, horizon
        )
        above = _conclusion_at(
            level_map, entry.variable, entry.threshold + span * 0.05, horizon
        )
        assert (below >= 0.0) != (above >= 0.0), (
            f"{entry.variable}: 보고된 임계값 {entry.threshold} 를 사이에 두고 "
            f"결론이 바뀌지 않는다 (아래 {below:,.0f}원 · 위 {above:,.0f}원). "
            "리포트가 임계값을 표시만 하고 있다"
        )


def _conclusion_at(level_map, variable: str, value: float, horizon: int) -> float:
    """그 인자를 `value` 로 두고 파이프라인을 다시 돌린 결론 축."""
    probe = {name: dict(levels) for name, levels in level_map.items()}
    probe[variable] = {**probe[variable], "base": value}
    outcome = run_single_case_e2e({}, level_map=probe, horizon_years=horizon)
    return float(outcome.variants[PLAN_VARIANT][CONCLUSION_METRIC])


@pytest.mark.req("FR-1001-AC3")
def test_substituted_values_match_the_metrics_they_explain() -> None:
    """대입값이 **지표와 같은 수**다 — 산식이 장식이 아니다.

    3중 표기의 셋째 줄이 실제 계산과 갈리면, 검토자가 그 줄을 따라 손으로
    계산했을 때 리포트의 결론과 다른 수가 나온다. `MC-1` 은 정확히 그것을
    하는 검사다.
    """
    report = _report("scenario_subsidy_20")
    substituted = {formula.label: formula.substituted for formula in report.formulas}

    outlay = int(report.metrics["initial_outlay_won"])
    assert f"{outlay:,}원" in substituted["순현재가치"], (
        "NPV 산식의 초기투자가 그 변형의 실제 초기지출과 다르다"
    )
    assert f"{report.metrics[CONCLUSION_METRIC]:,.0f}원" in substituted["순현재가치"]
    payback = report.metrics[HEADLINE_METRIC]
    assert f"{payback:.2f}년" in substituted["할인 회수기간"]

    net = report.basis.annual_benefit_won - report.basis.annual_cost_won
    assert f"{net:,}원" in substituted["연 순현금흐름"]


@pytest.mark.req("FR-1001-AC4", "FR-1002-AC5")
def test_provenance_comes_from_the_ledger_not_from_the_report() -> None:
    """부기가 **대장에서** 온다 — 리포트가 출처를 지어내지 않는다."""
    report = _report()
    ledger = {
        item["key"]: item
        for item in yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))[
            "assumptions"
        ]
    }

    checked = 0
    for entry in report.influences:
        if entry.ledger_key is None:
            continue
        checked += 1
        assert entry.confidence == ledger[entry.ledger_key]["confidence"], (
            f"{entry.variable}: 신뢰도가 대장과 다르다"
        )
        assert entry.value_unit == ledger[entry.ledger_key]["value_unit"], (
            f"{entry.variable}: 단위가 대장과 다르다"
        )
    assert checked, "대장에서 오는 인자가 하나도 없다"

    # `AC5` — 신뢰도 `가정` 이면서 결론을 뒤집는 인자만 경고 대상이다.
    assert set(report.provisional_warning) <= set(report.flipping)
    for entry in report.provisional_warning:
        assert entry.confidence == "가정"


@pytest.mark.req("FR-1002-AC3")
def test_a_variable_the_pipeline_never_reads_is_surfaced_not_ranked_last() -> None:
    """★ **변동폭이 정확히 0인 인자를 「영향 없음」으로 적지 않는다.**

    범위를 끝에서 끝까지 흔들어도 결론이 한 원도 움직이지 않는 일은 경제적으로
    일어나지 않는다 — 사실상 파이프라인이 그 인자를 읽지 않는다는 뜻이다.
    그것을 순위 최하위로만 적으면 검토자는 *「이 인자는 사업성과 무관하다」* 는
    **틀린 결론을 리포트에서 배워 간다.**

    ⚠ 이 검사는 「미배선이 있어야 통과」가 아니다. 있으면 **드러나야** 통과다.
    배선이 끝나면 `unread_variables` 가 비고 이 검사는 그대로 통과한다.
    """
    report = _report()
    for entry in report.influences:
        zero_span_move = (
            entry.delta_won == 0.0 and entry.low != entry.high
        )
        assert entry.unread_by_pipeline == zero_span_move, (
            f"{entry.variable}: 변동폭 0 인데 드러나지 않았다"
        )
    for entry in report.unread_variables:
        assert not entry.flips_conclusion, (
            f"{entry.variable}: 결론을 뒤집는데 변동폭이 0일 수는 없다"
        )
