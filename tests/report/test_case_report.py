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
    _scheme_for,
    build_case_report,
)
from tests.report.conftest import report_shapes

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"
_GOLDEN = _REPO_ROOT / "fixtures" / "golden"


def _report(name: str = "scenario_unsubsidized", assumptions: Path | None = None):
    return build_case_report(
        _GOLDEN / f"{name}.yaml", assumptions_path=assumptions or _ASSUMPTIONS
    )


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
def test_the_sweep_follows_the_supported_variant_too(
    flip_probe_assumptions: Path,
) -> None:
    """★ **영향도 스윕도 지원을 반영한다.**

    결론 한 줄과 스윕은 **서로 다른 줄**에서 변형을 읽는다. 결론만 고치면
    표는 「보조 80% 사업」인데 영향도 순위는 **무보조 사업의 것**이 된다 —
    검토자는 지원을 받은 사업을 보면서 지원 없는 사업의 위험 인자를 읽는다.

    변이로 확인했다: 스윕 쪽만 케이스 지표로 되돌리면 위 결론 검사는 **전건
    초록불**이었다. 무보조 시나리오에서는 두 값이 같아서 드러나지 않는다.

    ⚠ **탐침 대장으로 돈다 (R34).** 실물 대장에서는 구매 비용이 배선된 뒤
    **어느 시나리오에도 전환 인자가 없어졌고**(무보조 −5,156,392원 · 보조 80%
    +2,683,608원, 어느 인자도 검토 범위 안에서 0 선을 넘기지 못한다), 그러면 이
    검사가 `set() != set()` 로 **정당한 상태를 빨간불**로 만든다. 범위를 넓힌
    탐침에서는 보조 80% 만 전환을 갖는다 — 스윕이 변형을 읽지 않고 케이스
    지표로 돌면 **양쪽이 다시 같아져** 이 검사가 빨간불이 된다(`conftest.py`).
    """
    plain = _report("scenario_unsubsidized", flip_probe_assumptions)
    subsidised = _report("scenario_subsidy_80", flip_probe_assumptions)

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
def test_reported_flip_threshold_actually_flips_the_conclusion(
    flip_probe_assumptions: Path,
) -> None:
    """★★ **보고된 임계값으로 다시 돌려 결론이 실제로 뒤집히는지 본다.**

    이 검사가 없으면 임계값을 **표시만** 하는 구현이 통과한다 — 검토자는
    리포트에서 *「단가가 이 값을 넘으면 사업성이 뒤집힌다」* 를 읽고 정책
    판단을 하는데, 그 값이 계산과 무관해도 아무도 모른다.

    ⚠ **탐침 대장 + 보조 80% 로 돈다 (R34).** 실물 대장에서는 전환 인자가
    0건이고, 그러면 아래 순회가 **0회 돌면서 초록불**이 된다 — 이 저장소가
    반복해서 경계해 온 *조용한 통과*이며, 이 검사가 잡으려는 결함(R33 의
    `_find_flip_threshold` 허용오차)은 **전환 인자가 있었기 때문에** 잡혔다.
    그래서 순회 대상이 비면 그것 자체를 빨간불로 만든다.
    """
    subsidy_rate = 0.8
    report = _report("scenario_subsidy_80", flip_probe_assumptions)
    flipping = report.flipping
    assert flipping, (
        "탐침 대장에서도 전환 인자가 없다 — 이 검사가 0회 순회로 통과한다. "
        "`conftest.py` 의 탐침 범위를 넓힐 것"
    )

    level_map = build_level_map(flip_probe_assumptions)
    horizon = report.basis.horizon_years
    # ⚠ **지원 조건을 함께 넘긴다.** 넘기지 않으면 재실행은 무보조 사업의
    # 결론을 내고, 보조 80% 리포트의 임계값을 **다른 사업의 0 선**에 대고
    # 재는 것이 된다 — 그러면 이 검사는 옳은 임계값을 빨간불로 만든다.
    scheme = _scheme_for(subsidy_rate)

    for entry in flipping:
        assert entry.threshold is not None
        span = entry.high - entry.low
        below = _conclusion_at(
            level_map, entry.variable, entry.threshold - span * 0.05, horizon, scheme
        )
        above = _conclusion_at(
            level_map, entry.variable, entry.threshold + span * 0.05, horizon, scheme
        )
        assert (below >= 0.0) != (above >= 0.0), (
            f"{entry.variable}: 보고된 임계값 {entry.threshold} 를 사이에 두고 "
            f"결론이 바뀌지 않는다 (아래 {below:,.0f}원 · 위 {above:,.0f}원). "
            "리포트가 임계값을 표시만 하고 있다"
        )


def _conclusion_at(
    level_map, variable: str, value: float, horizon: int, scheme=None
) -> float:
    """그 인자를 `value` 로 두고 파이프라인을 다시 돌린 결론 축."""
    probe = {name: dict(levels) for name, levels in level_map.items()}
    probe[variable] = {**probe[variable], "base": value}
    # ★ **리포트와 같은 배선으로 돌린다 (R37).** `build_case_report` 가
    # 일사 곡선을 본 실행·스윕에 넘기므로, 형상 없이 다시 돌리면 리포트의
    # 수를 **다른 사업**의 0 선에 대고 재는 것이 된다. 형상은 검사가
    # 자산에서 직접 읽는다(`conftest.report_shapes` 독스트링).
    outcome = run_single_case_e2e(
        {},
        level_map=probe,
        horizon_years=horizon,
        scheme=scheme,
        daily_shapes=report_shapes(),
    )
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
    # ⚠ **회수하지 못하는 경우를 함께 본다 (R34).** 구매 비용이 배선된 뒤
    # 보조 20% 는 분석기간 내 미회수(`inf`)가 됐다. 종전 문면(`{payback:.2f}년`)
    # 을 그대로 요구하면 「`inf년`」이라는 **없는 표기를 강제**하게 되고, 그러면
    # 실제로 회수하는 시나리오와 못 하는 시나리오 중 한쪽은 반드시 빨간불이다.
    payback = report.metrics[HEADLINE_METRIC]
    if payback == float("inf"):
        assert "미회수" in substituted["할인 회수기간"], (
            "회수기간이 무한인데 산식이 그것을 말하지 않는다 — 대입값 줄이 "
            "빈칸이거나 없는 연수를 적고 있다"
        )
        assert f"{report.basis.horizon_years}년" in substituted["할인 회수기간"], (
            "미회수 판정의 근거인 분석기간이 대입값에 없다"
        )
    else:
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


@pytest.mark.req("FR-1002-AC3")
def test_displayed_values_are_in_the_units_the_report_prints() -> None:
    """★ **값과 단위가 어긋나지 않는다.**

    `tariff_escalation` 은 대장에 `2.5 %/년` 으로 있고 계산에는 비율 `0.025` 로
    들어간다. 리포트가 **계산값과 대장 단위를 같은 행에** 실으면 「0.025 %/년」이
    나가고, 이것은 실제의 **100분의 1** 로 조용히 읽힌다 — 예외도 나지 않고
    표도 그럴듯하다.

    실물을 뽑아 보고서야 드러났다. 여기서 붙드는 것은 표시값이 **대장 값과 같은
    자리에 있는가**이며, 기대값을 이 파일에 적지 않고 **대장을 다시 읽어**
    대조한다(적으면 사본이 되고 대장이 바뀔 때 따라오지 않는다).
    """
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
        sensitivity = ledger[entry.ledger_key]["sensitivity"]
        assert entry.used_value == pytest.approx(float(sensitivity["base"])), (
            f"{entry.variable}: 표시값 {entry.used_value} 가 대장 값 "
            f"{sensitivity['base']} 와 다르다 — 단위 환산이 표시까지 새어 나왔다"
        )
        assert entry.low == pytest.approx(float(sensitivity["low"]))
        assert entry.high == pytest.approx(float(sensitivity["high"]))
    assert checked, "대장에서 오는 인자가 하나도 없다"
