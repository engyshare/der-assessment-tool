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

from core.assumption.provider import AssumptionSet
from core.casegrid.e2e_runner import run_single_case_e2e
from core.report.case_report import (
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    PLAN_VARIANT,
    _overrides,
    build_case_report,
)
from tests.report.conftest import (
    report_household_wiring,
    report_rec_terms,
    report_shapes,
    report_shift_share,
)

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

    assert report.ledger_inputs, "대장 입력이 비어 있다"
    assert report.formulas, "산식이 비어 있다 (FR-1001-AC2)"
    assert report.assumptions, "가정 부록이 비어 있다 (FR-1002-AC6)"
    assert report.manifest_hash, "매니페스트가 없다 (FR-1005-AC1)"
    # `AC3` 은 인자마다 사용값·단위·기준연도·출처·신뢰도를 **함께** 요구한다.
    for entry in report.ledger_inputs:
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
    # ★ **리포트와 같은 배선으로 돌린다 (R37 · R48/WP-B · R52/WP-6).**
    # `build_case_report` 가 일사 곡선·**가구 부하**·REC 단가·가중치를 본
    # 실행·스윕에 넘기므로(`_Sweeper`), 그것들 없이 다시 돌리면 리포트의 수를
    # **다른 사업**의 0 선에 대고 재는 것이 된다. 형상·REC 는 검사가 자산·
    # 대장에서 직접 읽는다(`conftest.report_shapes`·`report_rec_terms`).
    rec_price, rec_weight = report_rec_terms()
    outcome = run_single_case_e2e(
        {},
        level_map=probe,
        horizon_years=horizon,
        scheme=scheme,
        daily_shapes=report_shapes(),
        annual_load_kwh=probe["household_load_annual_kwh"]["base"],
        rec_price_won_per_unit=rec_price, rec_weight_pv=rec_weight,
        # ★ **부하 이동도 같은 배선** (R64/WP-7 · 사용자 요구 2) — 안 넘기면
        # 리포트(옮긴 하루)와 재실행(옮기지 않은 하루)이 서로 다른 사업을 그린다.
        dr_shiftable_share_pct=report_shift_share(),
        # ★★ **단지 규모·기기 부하·계절 몫도 같은 배선** (R65/WP-2c) — 안 넘기면
        # 리포트(20호 단지)의 수를 **한 호짜리** 재실행과 맞대게 된다.
        **report_household_wiring(),
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
    for entry in report.ledger_inputs:
        checked += 1
        assert entry.confidence == ledger[entry.ledger_key]["confidence"], (
            f"{entry.variable}: 신뢰도가 대장과 다르다"
        )
        assert entry.value_unit == ledger[entry.ledger_key]["value_unit"], (
            f"{entry.variable}: 단위가 대장과 다르다"
        )
    assert checked, "대장에서 오는 인자가 하나도 없다"




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
    for entry in report.ledger_inputs:
        checked += 1
        sensitivity =ledger[entry.ledger_key]["sensitivity"]
        assert entry.used_value == pytest.approx(float(sensitivity["base"])), (
            f"{entry.variable}: 표시값 {entry.used_value} 가 대장 값 "
            f"{sensitivity['base']} 와 다르다 — 단위 환산이 표시까지 새어 나왔다"
        )
        assert entry.low == pytest.approx(float(sensitivity["low"]))
        assert entry.high == pytest.approx(float(sensitivity["high"]))
    assert checked, "대장에서 오는 인자가 하나도 없다"


@pytest.mark.req("FR-602-AC2", "FR-602-AC3")
def test_the_change_list_carries_the_value_it_replaced_and_the_reason() -> None:
    """★ **「기준 전제 대비 변경 항목」이 바뀌기 전 값과 사유를 함께 진다.**

    변경값만 실으면 검토자는 *「무엇을 바꿨는가」* 에 답을 얻지 못한다 — 바뀐
    값 하나는 붙임 1 의 주제별 표에도 이미 있고(`_appendix` 독스트링), 「변경」
    은 **두 값이 나란히 설 때**에야 성립한다.

    ⚠ 리포트가 `items()` 와 `get()` 을 맞대 보지 **않는다**는 것도 함께 본다 —
    대장의 `overridden_items()` 가 지은 짝을 그대로 옮기는지다. 변이로
    확인했다: `base_value` 를 변경값으로 채우면 이 검사만 빨개진다.
    """
    provider = AssumptionSet.load_from_yaml(str(_ASSUMPTIONS))
    key = "analysis.period_years"
    base = provider.items()[key].value
    changed = provider.override(
        {key: base + 5}, reasons={key: "심의 요청 — 분석기간 연장"}
    )

    # ⚠ `read_keys` 는 조립부가 **계산이 끝난 자리에서 굳혀** 넘기는 것이다
    # (R63/N3). 여기서는 이 검사가 재는 것(기준값·변경값·사유·정렬)과 무관
    # 하므로 「이 실행이 읽었다」로 두고, 표시 자체는
    # `tests/report/test_unread_override_marking.py` 가 잰다.
    rows = _overrides(changed, read_keys=frozenset({key}))

    assert [row.key for row in rows] == [key], f"변경 항목 목록이 어긋난다 — {rows}"
    assert rows[0].base_value == base, "바뀌기 전 값이 기준값 칸에 없다"
    assert rows[0].override_value == base + 5, "변경값이 실행이 쓴 값과 다르다"
    assert rows[0].reason == "심의 요청 — 분석기간 연장", (
        "사유가 떨어졌다 — FR-602-AC3 이 같은 절에서 사유를 요구한다"
    )
    # ★ 배포 경로는 오버라이드를 걸지 않는다 — **비어 있는 것이 정상**이며,
    # 그 사실을 붙임이 인쇄하는지는 `test_narrative.py` 의 같은 조항 검사가
    # 본다. 여기서는 「비었다」가 참인지만 고정한다.
    assert _report().overrides == (), "배포 경로에 없던 오버라이드가 생겼다"
