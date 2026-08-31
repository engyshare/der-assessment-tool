"""리포트가 **조립되어 나오는가** — FR-1001 · FR-1002 · FR-1005.

## 이 파일이 종전 리포트 테스트와 다른 점

`tests/report/test_report.py` 는 부품(`generate_pdf`·`rank_influences` …)을 **직접
부른다.** 그래서 조항 `FR-1001-AC1`~`AC4` 와 `FR-1002-AC1`~`AC6` 이 전부 「자동」
으로 세어져 있었는데도 **그 부품을 부르는 배포 코드는 0곳**이었다 — 매핑표가
초록불인 채 리포트를 낼 통로가 없었고, 그래서 `MC-1` 이 시작될 수 없었다.

이 파일은 부품을 부르지 않는다. **진입점 하나**(`build_case_report`)를 지나서
나온 것만 본다.

    지원이 결론에 반영된다              ← 변형을 읽지 않으면 80% 보조가 무보조와 같아진다
    ★ 보고된 스윕의 수가 진짜다          ← 그 값으로 다시 돌려 같은 수가 나오는지 본다
    대입값이 지표와 맞는다              ← 산식이 장식이 아니다
    부기가 대장에서 온다                ← 리포트가 출처를 지어내지 않는다
    ★ 읽히지 않는 인자를 드러낸다        ← 「영향 0」을 「영향 없음」으로 적지 않는다

둘째가 요점이다. 스윕의 수를 **표시만** 하는 구현도 나머지를 전부 통과한다.

⚠ **R49 가 앞의 둘의 전제를 바꿨다.** 종전에는 둘 다 *「전환 인자가 존재한다」*
를 전제했는데(집합 대조 · `assert flipping`), R48 이 결론축을 두 배로 내려 실물
범위의 전환 인자가 **두 시나리오 다 0건**이 됐다. 오라클은 버리지 않고 **비어
있어도 갈리는 것**으로 옮겼다 — 각 검사 독스트링이 그 경위를 진다
(`docs/decisions-2026-08-31-R49.md` §3).
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map, ledger_unit_scales
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
def test_the_sweep_follows_the_supported_variant_too() -> None:
    """★ **영향도 스윕도 지원을 반영한다.**

    결론 한 줄과 스윕은 **서로 다른 줄**에서 변형을 읽는다. 결론만 고치면
    표는 「보조 80% 사업」인데 영향도 순위는 **무보조 사업의 것**이 된다 —
    검토자는 지원을 받은 사업을 보면서 지원 없는 사업의 위험 인자를 읽는다.

    변이로 확인했다: 스윕 쪽만 케이스 지표로 되돌리면 위 결론 검사는 **전건
    초록불**이었다. 무보조 시나리오에서는 두 값이 같아서 드러나지 않는다.

    ## ⚠⚠ **이 검사는 자기 죽음을 예고해 두었고, 그 예고가 맞았다** (R49)

    R41 판은 전환 인자 **집합**으로 재면서 이렇게 적어 두었다 — *「이 검사는
    이제 결론축이 다시 올라가면 죽는다 … 그때 죽는 방식은 빨간불이며 그것이
    옳다: 전제가 바뀐 것을 알려야 한다」*. R48 이 결론축을 **−6,289,675 →
    −12,956,180원**(무보조)으로 두 배로 내리자 보조 80% 도 실물 범위에서 전환을
    잃어 **두 집합이 다시 같아졌다**(둘 다 `set()`). 예고대로 빨간불이 됐고,
    그것이 이 갱신을 불렀다(판정 §3 · `docs/decisions-2026-08-31-R49.md`).

    ## ★ 새 전제 — **비어 있어도 갈리는 것으로 옮긴다**

    전환 인자는 *결론축이 0 선을 넘느냐*이므로 **결론이 나쁠 때 0건이 된다** —
    즉 오라클이 사업의 형편에 매여 있었다. 그래서 **인자별 두 끝의 결론 축**
    으로 옮긴다. 그 수는 사업이 아무리 나빠도 9건 × 두 끝이 있다.

    무엇으로 견주는가 — **지원 1원은 그 사업의 결론 축을 정확히 1원 올린다**
    (`residual_gap_at_full_support_won` 독스트링). 그러므로 같은 인자·같은 끝
    에서 두 시나리오의 결론 축 차는 **보조율 × 그 끝에서의 총사업비**여야 한다.

    ⚠ **기대값을 리포트에서 읽지 않는다**(동어반복). 보조율은 **시나리오
    정본**에서, 그 끝에서의 총사업비는 **지원 없이 파이프라인을 다시 돌려**
    짓는다 — 리포트의 어느 칸도 읽지 않는다.

    ★ 이 견줌이 종전 집합 대조보다 **더 잡는다**:

        스윕이 변형을 안 읽는다        → 차가 18곳 전부 0원          → 빨간불
        기준 보조액을 상수로 더한다    → 설비단가 끝 넷이 어긋난다    → 빨간불

    뒤쪽이 요점이다 — 지원은 **그 끝에서의 설비비**의 80% 이므로 설비단가를
    흔들면 지원액도 함께 움직인다(실측: 7,040,000 · 8,640,000 · 7,072,000 ·
    8,608,000원). 나머지 다섯 인자는 설비비를 건드리지 않아 전부
    7,840,000원(= 0.8 × 9,800,000)이다. **차가 한 값이 아니라는 사실**을 아래
    마지막 단정이 함께 붙든다 — 한 값이 되면 이 검사는 상수 하나만 재게 된다.

    ⚠ **영향폭(delta)은 같아도 정상이다.** 보조금은 `t=0` 에 상수로 들어가
    인자를 흔들었을 때의 **폭**을 바꾸지 않는다(설비단가는 예외다). 그래서
    폭이 아니라 **두 끝의 값**을 본다.
    """
    plain = _report("scenario_unsubsidized")
    subsidised = _report("scenario_subsidy_80")
    subsidy_rate = _declared_subsidy_rate("scenario_subsidy_80")
    assert subsidy_rate > 0.0, (
        "보조 시나리오의 보조율이 0 이다 — 이 검사가 지원 없는 사업 둘을 견준다"
    )

    level_map = build_level_map(_ASSUMPTIONS)
    horizon = plain.basis.horizon_years
    supported = {entry.variable: entry for entry in subsidised.uncertain_influences}
    assert plain.uncertain_influences, (
        "스윕한 인자가 0건이다 — 아래 순회가 0회 돌면서 초록불이 된다"
    )
    assert supported.keys() == {
        entry.variable for entry in plain.uncertain_influences
    }, "두 시나리오가 서로 다른 인자를 스윕했다 — 견줄 짝이 없다"

    lifts: set[int] = set()
    for entry in plain.uncertain_influences:
        counterpart = supported[entry.variable]
        for end in ("low", "high"):
            # ★ 끝값은 **대장에서** 읽는다. `InfluenceEntry.low`·`high` 는 표시용
            # 으로 대장 단위로 되돌린 값이므로(그 독스트링) 배율이 1 이 아닌
            # 인자에서 파이프라인에 그대로 넣으면 다른 값을 재게 된다.
            value = level_map[entry.variable][end]
            unsupported = _variant_at(level_map, entry.variable, value, horizon, None)
            expected = subsidy_rate * float(unsupported["initial_outlay_won"])
            lift = getattr(counterpart, f"npv_{end}") - getattr(entry, f"npv_{end}")
            assert lift == pytest.approx(expected, abs=1.0), (
                f"{entry.variable} `{end}` 끝: 보조 80% 의 결론 축이 무보조보다 "
                f"{lift:,.0f}원 높다 — 지원분 {expected:,.0f}원과 다르다. "
                "스윕이 변형을 읽지 않거나(차 0원), 기준 보조액을 상수로 "
                "더하고 있다(설비단가 끝에서 어긋난다)"
            )
            lifts.add(round(lift))

    assert len(lifts) > 1, (
        f"두 시나리오의 차가 {lifts} 한 값뿐이다 — 지원액이 그 끝에서의 "
        "설비비를 따라 움직이지 않는다. 설비단가 축이 표에서 빠졌다면 이 "
        "검사는 상수 하나만 재고 있으므로 그때 다시 세울 것"
    )


@pytest.mark.req("FR-1002-AC2", "FR-1002-AC4")
def test_reported_sweep_numbers_survive_a_rerun_of_the_pipeline() -> None:
    """★★ **보고된 수로 다시 돌려 본다** — 표시만 하는 구현을 잡는다.

    이 검사가 없으면 스윕의 수를 **표시만** 하는 구현이 통과한다 — 검토자는
    리포트에서 *「단가가 이 값을 넘으면 사업성이 뒤집힌다」* 와 *「끝까지 밀어도
    3,853,240원이 남는다」* 를 읽고 정책 판단을 하는데, 그 수가 계산과 무관해도
    아무도 모른다.

    ## ⚠⚠ 전제를 바꿨다 — **임계값 하나에서 「보고된 수 전부」로** (R49)

    종전 이름은 `test_reported_flip_threshold_actually_flips_the_conclusion` 이고
    첫 줄이 `assert flipping` 이었다. R48 이 결론축을 두 배로 내려 **실물 범위의
    전환 인자가 두 시나리오 다 0건**이 되면서 그 단정이 빨간불이 됐다 —
    정당한 상태를 빨간불로 만드는 자리다(판정 §3).

    ★ **오라클은 버리지 않는다.** 잡으려는 결함은 *「보고된 수가 파이프라인에서
    오지 않는다」* 이고, 그 수는 임계값 하나가 아니다 — 전환 인자가 0건인 지금
    리포트가 5.1 에서 기대는 수는 **두 끝의 결론 축**(그 끝의 남은 거리 ·
    줄어드는 결손 · 결합 표)이다. 그래서 재는 대상을 셋으로 넓혔다:

        ㉠ 두 끝의 결론 축이 재실행과 같은가        ← 인자 9건 × 2 = 18곳
        ㉡ 「전환 없음」이 실물인가                  ← 두 끝과 **중점**이 0 선 아래
        ㉢ 전환 인자가 있으면 그 임계값이 뒤집는가   ← 종전 오라클, 그대로

    ㉡ 가 종전 `assert flipping` 이 지던 몫을 진다. 이분탐색은 **단조성을
    전제**하므로 두 끝만 보면 가운데서 0 선을 넘는 인자를 놓친다 — 그때 리포트는
    「없음」을 **거짓으로** 인쇄하고, 그것이 R33 의 `_find_flip_threshold`
    허용오차 결함과 같은 자리다. 중점을 함께 재는 것이 그 자리를 붙든다.

    ⚠ **순회 대상이 비면 그것 자체를 빨간불로 만든다** — 그 규약은 그대로다.
    다만 이제 순회 대상이 *전환 인자*가 아니라 **스윕한 인자 전건**이므로,
    사업이 나빠져도 비지 않는다.

    ⚠ **단위를 대장에서 되돌린다.** `InfluenceEntry` 의 `low`·`high`·`threshold`
    는 표시용으로 **대장 단위**이고(`ledger_unit_scales`) 파이프라인은 환산값을
    받는다. 종전 판은 배율 1 인 인자만 순회해 드러나지 않았다 — 배율이 1 이
    아닌 인자가 전환을 내는 날 조용히 다른 값을 재게 되는 자리였다.
    """
    subsidy_rate = _declared_subsidy_rate("scenario_subsidy_80")
    report = _report("scenario_subsidy_80")
    level_map = build_level_map(_ASSUMPTIONS)
    scales = ledger_unit_scales()
    horizon = report.basis.horizon_years
    # ⚠ **지원 조건을 함께 넘긴다.** 넘기지 않으면 재실행은 무보조 사업의
    # 결론을 내고, 보조 80% 리포트의 수를 **다른 사업의 0 선**에 대고 재는 것이
    # 된다 — 그러면 이 검사는 옳은 리포트를 빨간불로 만든다.
    scheme = _scheme_for(subsidy_rate)

    assert report.uncertain_influences, (
        "스윕한 인자가 0건이다 — 아래 순회가 0회 돌면서 초록불이 된다"
    )

    for entry in report.uncertain_influences:
        levels = level_map[entry.variable]
        low, high = float(levels["low"]), float(levels["high"])
        scale = scales.get(entry.variable, 1.0) or 1.0

        # ㉠ 두 끝의 결론 축이 **재실행과 같은 수**인가.
        for end, value in (("low", low), ("high", high)):
            rerun = _conclusion_at(level_map, entry.variable, value, horizon, scheme)
            assert getattr(entry, f"npv_{end}") == pytest.approx(rerun, abs=1.0), (
                f"{entry.variable} `{end}` 끝: 리포트가 싣는 결론 축 "
                f"{getattr(entry, f'npv_{end}'):,.0f}원이 같은 값으로 다시 돌린 "
                f"{rerun:,.0f}원과 다르다 — 리포트가 그 수를 표시만 하고 있다"
            )

        if entry.threshold is None:
            # ㉡ 「전환 없음」이 실물인가 — 가운데도 함께 본다(단조성 전제).
            assert not entry.flips_conclusion
            for label, value in (("low", low), ("중점", (low + high) / 2.0), ("high", high)):
                conclusion = _conclusion_at(
                    level_map, entry.variable, value, horizon, scheme
                )
                assert conclusion < 0.0, (
                    f"{entry.variable} `{label}`: 리포트는 이 인자로 결론이 "
                    f"전환되지 않는다고 적는데 결론 축이 {conclusion:,.0f}원 "
                    "(0 선 위)이다 — 「없음」이 거짓이거나 임계값 탐색이 "
                    "구간 안의 전환을 놓쳤다"
                )
            continue

        # ㉢ 전환 인자가 있으면 **보고된 임계값**으로 다시 돌려 뒤집히는지 본다.
        span = (high - low) * 0.05
        threshold = entry.threshold * scale
        below = _conclusion_at(
            level_map, entry.variable, threshold - span, horizon, scheme
        )
        above = _conclusion_at(
            level_map, entry.variable, threshold + span, horizon, scheme
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
    return float(_variant_at(level_map, variable, value, horizon, scheme)[
        CONCLUSION_METRIC
    ])


def _variant_at(
    level_map, variable: str, value: float, horizon: int, scheme=None
) -> Mapping[str, float]:
    """그 인자를 `value` 로 둔 재실행의 **변형 지표 전부**.

    결론 축만 돌려주지 않는 이유는 *「지원이 그 끝에서의 총사업비를 따라
    움직이는가」* 를 재는 검사가 같은 재실행의 `initial_outlay_won` 을 함께
    필요로 하기 때문이다 — 두 번 돌리면 같은 사업을 두 번 계산하고, 그 사이에
    배선이 갈리면 어느 쪽이 옳은지 검사가 말하지 못한다.
    """
    probe = {name: dict(levels) for name, levels in level_map.items()}
    probe[variable] = {**probe[variable], "base": value}
    # ★ **리포트와 같은 배선으로 돌린다 (R37 · R48/WP-B).** `build_case_report`
    # 가 일사 곡선과 **가구 부하**를 본 실행·스윕에 넘기므로(`_Sweeper`), 그
    # 둘 없이 다시 돌리면 리포트의 수를 **다른 사업**의 0 선에 대고 재는 것이
    # 된다. 형상은 검사가 자산에서 직접 읽는다(`conftest.report_shapes`).
    outcome = run_single_case_e2e(
        {},
        level_map=probe,
        horizon_years=horizon,
        scheme=scheme,
        daily_shapes=report_shapes(),
        annual_load_kwh=probe["household_load_annual_kwh"]["base"],
    )
    return outcome.variants[PLAN_VARIANT]


def _declared_subsidy_rate(name: str) -> float:
    """시나리오 정본이 **선언한** 보조율 — 리포트를 읽지 않는다.

    ⚠ `report.subsidy_rate` 를 쓰면 리포트에게 *「네가 읽은 보조율로 재면
    맞느냐」* 를 묻는 것이 되어, 시나리오를 못 읽는 구현이 자기 기준으로
    통과한다. 기대값은 **밖에서** 지어야 한다.
    """
    data = yaml.safe_load((_GOLDEN / f"{name}.yaml").read_text(encoding="utf-8"))
    return float(data["subsidy_rate"])


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
