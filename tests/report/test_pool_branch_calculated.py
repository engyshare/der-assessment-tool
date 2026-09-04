"""ⓒ「자가용 집합자원화」가 **계산된다** — 포기 항이 서고, 미확인이 드러난다.

## 이 파일이 붙드는 것

R60/WP-2 는 ⓒ 를 **거부되는 갈래**로 실행 경로에 세웠다
(`tests/report/test_baseline_arrangement_wiring.py::
test_the_pool_branch_is_refused_on_the_execution_path`). 그 거부의 사유가
둘이었고 둘째가 *「대칭 항이 없다 — 집합자원화 대가를 편익으로 세우려면
**포기한 자가소비를 비용으로** 세야 하는데 그 자리가 저장소에 없다」* 였다
(총괄지침 **제45조③** · 판정 정본 `docs/decisions-2026-09-03-R57.md` §4④).

    ★ 계측 선언을 넣으면 ⓒ 가 돈다                     ← T4 의 전제
    ★ 프로포마에 「포기한 자가소비」 **비용 행**이 선다   ← T4
    ★ 집합자원화 대가가 **0** 이고 그 이유가 산출물에 선다 ← T5

★★ **T4 가 요점이다.** 「거부를 풀었다」만으로는 *「없는 전제를 0 으로 메운」*
것과 산출물에서 구별되지 않는다 — **포기 항이 실제로 실려 결론을 나쁘게
움직이는 것**이 대칭성이 섰다는 증거다.

## ⚠ 왜 ⓒ 의 결론이 ⓑ 보다 **나쁜가** — 그것이 옳다

이 라운드가 세운 것은 **비용 쪽 절반**이다. 대칭 항의 짝인 「집합자원화
대가」는 제도·단가 근거가 확인되지 않아 대장에서 `track: default0`(값 0)이며,
*「제도가 없으면 편익은 작은 게 아니라 0」* 이 그 갈래의 정의다
(`docs/assumptions.yaml` 머리말). 그러므로 지금의 ⓒ 는 **포기는 세고 대가는
0인 사업**이고, 그 상태를 산출물이 말해야 한다 — 말하지 않으면 다음 사람이
**「대가가 0원인 사업」**으로 읽는다. T5 가 그 자리를 잰다.

## ⚠ 골든을 고치지 않는다

골든 셋은 ⓑ 이고 이 파일이 여는 것은 ⓒ 경로뿐이다. ⓒ 는 시나리오를 이
파일이 임시 폴더에 짓는다 — `fixtures/golden/*.yaml` 에 필드를 넣으면 골든
재생성 압력이 생기고, **필드 부재 = ⓑ** 가 R60/WP-2 가 세운 계약이다.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.casegrid.operating_lines import DAYS_PER_YEAR
from core.cba.baseline import BaselineArrangement
from core.report.case_report import CaseReport, build_case_report
from core.report.narrative import render_markdown

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"

# ⚠ 대장 열쇠·미반영 항목명을 이 파일이 리터럴로 갖지 않는다 —
# `core/report/unreflected.py` 가 선언한 것을 각 검사가 지역 import 로 읽는다.
# 두 곳에 적으면 한쪽만 바뀐다.


def _scenario_file(folder: Path, *, arrangement: str, declared: bool) -> Path:
    """갈래와 **계측 선언**만 다른 시나리오 하나.

    ⚠ 선언을 적지 않은 ⓒ 는 이 파일이 쓰지 않는다 — 그 거부는 R60/WP-2 의
    `test_the_pool_branch_is_refused_on_the_execution_path` 와 T1~T3
    (`tests/cba/test_pool_metering_declaration.py`)이 이미 잰다.
    """
    data: dict[str, object] = {
        "scenario": f"pool-branch-{arrangement}",
        "subsidy_rate": 0.0,
        "baseline_arrangement": arrangement,
    }
    if declared:
        data["pool_metering"] = {
            "ownership_or_operation_transferred": True,
            "metering_separated": True,
        }
    path = folder / f"scenario-{arrangement}-{declared}.yaml"
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


@pytest.fixture(scope="module")
def reports(tmp_path_factory: pytest.TempPathFactory) -> dict[str, CaseReport]:
    """ⓑ 와 ⓒ 의 리포트. **모듈에 한 번만** 조립한다 (한 건이 1초를 넘는다)."""
    folder = tmp_path_factory.mktemp("pool-branch")
    return {
        BaselineArrangement.MAINTAIN.value: build_case_report(
            _scenario_file(
                folder,
                arrangement=BaselineArrangement.MAINTAIN.value,
                declared=False,
            ),
            assumptions_path=_ASSUMPTIONS,
        ),
        BaselineArrangement.POOL.value: build_case_report(
            _scenario_file(
                folder, arrangement=BaselineArrangement.POOL.value, declared=True
            ),
            assumptions_path=_ASSUMPTIONS,
        ),
    }


def _pool(reports: dict[str, CaseReport]) -> CaseReport:
    return reports[BaselineArrangement.POOL.value]


def _maintain(reports: dict[str, CaseReport]) -> CaseReport:
    return reports[BaselineArrangement.MAINTAIN.value]


def _daily_self_consumption_kwh(report: CaseReport) -> float:
    """본 실행의 대표일 자가소비(kWh) — **스텝마다 min(발전, 부하)**.

    ⚠ 러너의 내부(잉여 시계열)를 읽지 않는다. 운전 결과로 드러난 사실에서
    독립적으로 다시 세어야 *「포기 항의 물량이 실제 자가소비인가」* 가 재진다 —
    같은 규약을 `core/report/unreflected.py::_measured_quantities` 가 쓴다.
    """
    hours = report.dispatch_hours
    names = tuple(hours[0].per_resource)
    generation = [
        name
        for name in names
        if all(hour.per_resource.get(name, 0.0) >= 0.0 for hour in hours)
        and any(hour.per_resource.get(name, 0.0) > 0.0 for hour in hours)
    ]
    load = [
        name
        for name in names
        if all(hour.per_resource.get(name, 0.0) <= 0.0 for hour in hours)
        and any(hour.per_resource.get(name, 0.0) < 0.0 for hour in hours)
    ]
    return sum(
        min(
            sum(hour.per_resource.get(name, 0.0) for name in generation),
            -sum(hour.per_resource.get(name, 0.0) for name in load),
        )
        for hour in hours
    )


@pytest.mark.req("FR-705-AC2")
def test_the_pool_branch_carries_a_forfeited_self_consumption_cost_row(
    reports: dict[str, CaseReport],
) -> None:
    """**T4** ★★★ — ⓒ 가 계산되고 프로포마에 **「포기한 자가소비」 비용 행**이 선다.

    ★ **넷을 함께 단언한다.** 하나씩 두면 각각을 통과하는 빈 구현이 있다:

        행이 있다              → 라벨만 붙이고 금액이 0인 행도 통과한다
        금액이 양수다          → 아무 수나 넣어도 통과한다
        **운영비 계정에 있다** → 편익 차감으로 넣은 구현을 잡는다
        **물량이 자가소비다**  → 근거 없는 수를 잡는다 (아래 오라클)

    ★★ **오라클은 「포기액 = 대표일 자가소비 × 365 × 구매단가」다.** 포기하는
    것은 *그 Without 에서 실제로 자가소비하던 전력*이고, 그것을 잃으면
    전기사용자는 같은 양을 **사야** 한다 — 그 값이 회피하고 있던 요금이다
    (단가는 대장 `tariff.hv_single_contract.energy_only` 에서 오며 이 파일이
    리터럴로 갖지 않는다).

    ⚠ **ⓑ 에는 이 행이 없어야 한다** — ⓑ 는 자가소비가 Without·With 양쪽에
    똑같이 있어 **차액에서 소거**된다(판정 정본 R57 §1 둘째). ⓑ 에도 서면
    같은 자가소비를 두 갈래에서 다르게 세는 것이 아니라 **아무 데서나 세는**
    것이 된다.
    """
    from core.casegrid.e2e_runner import FORFEITED_SELF_CONSUMPTION_TAG

    pool = _pool(reports)
    maintain = _maintain(reports)

    forfeited = [
        row
        for row in pool.cashflows.operating_cost
        if row.tag == FORFEITED_SELF_CONSUMPTION_TAG
    ]
    assert len(forfeited) == 1, (
        f"ⓒ 의 운영비 계정에 포기 항이 {len(forfeited)}건입니다 — 대칭 항"
        "(총괄지침 제45조③)이 한 줄로 서야 합니다: "
        f"{[row.label for row in pool.cashflows.operating_cost]}"
    )
    row = forfeited[0]
    assert "포기한 자가소비" in row.label
    assert all(amount > 0 for amount in row.amounts.values()), (
        f"포기 항이 비용 부호가 아닙니다: {row.amounts!r} — 비용 행은 양수이고 "
        "뒤집는 자리는 `net_operating_flows` 경계 하나입니다"
    )
    assert not [
        benefit
        for benefit in pool.cashflows.benefit
        if benefit.tag == FORFEITED_SELF_CONSUMPTION_TAG
    ], (
        "포기 항이 편익 계정에 실렸습니다 — 편익에서 빼면 비용 계정에 한 줄도 "
        "남지 않아 정부·사회 관점에서 그 지출이 없는 사업이 됩니다(`fee_row` "
        "독스트링)"
    )

    expected = int(
        _daily_self_consumption_kwh(pool)
        * DAYS_PER_YEAR
        * pool.basis.grid_purchase_price_won_per_kwh
    )
    assert expected > 0, (
        "본 실행의 자가소비가 0 입니다 — 이 오라클의 재료가 없습니다(부하가 "
        "세워지지 않았거나 형상이 바뀌었습니다)"
    )
    assert row.amounts[1] == pytest.approx(expected, rel=1e-6), (
        f"1년차 포기액 {row.amounts[1]!r} 이 「자가소비 곱하기 365일 곱하기 "
        f"구매단가」({expected:,}원)와 다릅니다 — 물량이 실제 자가소비가 아닙니다"
    )

    assert not [
        row
        for row in maintain.cashflows.operating_cost
        if row.tag == FORFEITED_SELF_CONSUMPTION_TAG
    ], "ⓑ 에도 포기 항이 섰습니다 — ⓑ 의 자가소비는 차액에서 소거됩니다"


@pytest.mark.req("FR-705-AC2")
def test_the_forfeit_moves_the_conclusion_against_the_project(
    reports: dict[str, CaseReport],
) -> None:
    """포기 항이 **결론축을 나쁜 쪽으로** 움직인다 — 실렸다는 증거는 지표에서 나온다.

    ★ 행의 존재만 재면 *「행을 만들어 놓고 순현금흐름에 넣지 않은」* 구현이
    통과한다. `net_operating_flows` 가 비용 행을 빼는 자리를 지나야 이 단언이
    성립한다.

    ⚠ **크기까지 못 박지 않는다** — 할인·변형 조합이 바뀌면 절대값이 움직이고,
    그때 이 검사가 재는 성질(*비용이 결론에 실렸는가*)은 그대로다. 실측값은
    `.orch/R60/result_3.md` 가 갖는다.
    """
    pool = _pool(reports)
    maintain = _maintain(reports)

    assert pool.metrics["npv"] < maintain.metrics["npv"], (
        f"ⓒ 의 순현재가치({pool.metrics['npv']:,.0f}원)가 ⓑ"
        f"({maintain.metrics['npv']:,.0f}원)보다 나쁘지 않습니다 — 포기 항이 "
        "만들어졌으나 순현금흐름에 실리지 않았습니다"
    )


@pytest.mark.req("FR-705-AC2")
def test_the_pool_compensation_is_zero_and_the_report_says_why(
    reports: dict[str, CaseReport],
) -> None:
    """**T5** ★★ — 집합자원화 대가가 **0** 이고 그 이유(**단가 미확인**)가 산출물에 선다.

    ## 왜 이 검사가 필요한가

    포기는 세고 대가는 0인 상태에서 그 사실이 리포트에서 사라지면 다음 사람은
    이 산출을 **「대가가 0원인 사업」**으로 읽는다 — 「제도가 확인되지 않아
    0」과 「대가가 실제로 0」은 결론이 같고 뜻이 정반대다. 저장소에는 그것을
    말하는 자리가 이미 있다(붙임 8 미반영 항목 · `core/report/unreflected.py`).

    ⚠ **ⓑ 에는 서지 않아야 한다** — ⓑ 는 집합자원화를 하지 않으므로 대가가
    미반영인 것이 아니라 **해당이 없다.** 늘 실으면 미반영 건수가 갈래와
    무관해지고, 요약 1절의 방향별 내역이 그만큼 틀린다.
    """
    from core.report.unreflected import (
        POOL_COMPENSATION_LABEL,
        POOL_COMPENSATION_LEDGER_KEY,
        build_unreflected,
    )

    pool = _pool(reports)
    items = build_unreflected(pool)
    matched = [item for item in items if item.label == POOL_COMPENSATION_LABEL]
    assert len(matched) == 1, (
        f"ⓒ 의 미반영 항목에 「{POOL_COMPENSATION_LABEL}」이 "
        f"{len(matched)}건입니다: {[item.label for item in items]}"
    )
    item = matched[0]
    assert POOL_COMPENSATION_LEDGER_KEY in item.magnitude, (
        f"크기 칸이 대장 열쇠를 가리키지 않습니다: {item.magnitude!r} — 좌표가 "
        "없으면 검토자가 0의 근거를 확인할 수 없습니다"
    )
    assert "미확인" in item.reason, (
        f"사유가 「단가 미확인」을 말하지 않습니다: {item.reason!r}"
    )
    assert item.resolves_when.strip(), "해소 조건이 비어 있습니다"
    assert item.measured, (
        "매 실행 재어 판정한 항목이 아니라고 표시됐습니다 — 갈래를 보고 "
        "판정하므로 구성이 바뀌면 이 행이 사라집니다"
    )

    rendered = render_markdown(pool)
    assert POOL_COMPENSATION_LABEL in rendered, (
        "산출물에 항목이 인쇄되지 않습니다 — 자료형에만 있고 리포트에 없으면 "
        "검토자는 그것을 볼 수 없습니다"
    )

    maintain_labels = [
        item.label for item in build_unreflected(_maintain(reports))
    ]
    assert POOL_COMPENSATION_LABEL not in maintain_labels, (
        f"ⓑ 에도 집합자원화 대가가 미반영으로 섰습니다: {maintain_labels}"
    )


@pytest.mark.req("FR-705-AC2")
def test_the_pool_compensation_price_is_a_default0_ledger_item() -> None:
    """★ **래칫** — 대가 단가는 대장에 `track: default0`(값 0)으로 서 있다.

    ⚠⚠ **크기를 추정하지 않는다.** *「제도가 없으면 편익은 작은 게 아니라
    0이다」* 가 그 갈래의 정의이며(`docs/assumptions.yaml` 머리말 ·
    `benefit.nwas_price`·`benefit.cp_price` 가 같은 자리에 있다), 그럴듯한
    단가를 넣으면 **없는 제도 위에 편익을 쌓아** 필요 지원액을 과소 산정한다.

    ★ **값이 0 을 벗어나는 날 이 시험이 빨간불이 된다 — 지우지 말고 뒤집어라.**
    그때 해야 하는 것은 ① 대가를 **편익 행**으로 프로포마에 세우고 ② 그 물량
    (집합자원에 반입한 kWh)의 정의를 판정으로 받고 ③ 미반영 항목을 **거두는**
    것이다. 세 개가 함께 서지 않으면 리포트가 *「대가가 반영됐다」* 와
    *「0이라 미반영이다」* 를 동시에 말한다.
    """
    from core.report.unreflected import POOL_COMPENSATION_LEDGER_KEY

    ledger = yaml.safe_load(_ASSUMPTIONS.read_text(encoding="utf-8"))
    matched = [
        item
        for item in ledger["assumptions"]
        if item.get("key") == POOL_COMPENSATION_LEDGER_KEY
    ]
    assert len(matched) == 1, (
        f"대장에 `{POOL_COMPENSATION_LEDGER_KEY}` 가 {len(matched)}건입니다 — "
        "미반영 항목이 가리키는 좌표가 실재해야 합니다(매달린 참조, NFR-107)"
    )
    entry = matched[0]
    assert entry["track"] == "default0", (
        f"단가 갈래가 `default0` 이 아닙니다: {entry['track']!r}"
    )
    assert entry["value"] == 0, (
        f"단가가 0 이 아닙니다: {entry['value']!r} — 제도·값 근거가 확인됐다면 "
        "이 시험을 지우지 말고 위 독스트링의 ①②③ 을 함께 세운 뒤 뒤집으십시오"
    )
    assert entry.get("q_ref") is None, (
        "새 `Q-*` 번호가 달렸습니다 — spec §15.1 표에 행이 없으면 "
        "`scripts/check_assumptions.py` 의 「Q 목록 대조」가 유령 Q 로 잡습니다"
    )


#: ⓒ 가 본문에 더하는 줄 수 — **셋이며 자리가 각각 다르다**(R60/WP-3 실측).
#:
#:   3.4 미반영 항목 표      `| 집합자원화 대가 | 반영 시 결과 개선 | … |`
#:   6.3 미해소 항목 표      `| 미반영 | 집합자원화 대가 | 해소 조건 |`
#:   4.x 결손 분해           `| └ ForfeitedSelfConsumption 포기한 자가소비 | … |`
#:
#: ★★ **미반영 항목 하나가 본문 두 줄을 만든다** — `unreflected_rows`(3.4)와
#: `core/report/narrative.py:751`(6.3)이 같은 목록을 각각 한 줄씩 인쇄한다.
#: 착수 시점의 예상은 「한 줄」이었고 실측은 **셋**이다.
_POOL_BODY_LINES_ADDED = 3


@pytest.mark.req("FR-705-AC2")
def test_the_pool_branch_adds_exactly_three_body_lines(
    reports: dict[str, CaseReport],
) -> None:
    """ⓑ 의 본문은 **움직이지 않고**, ⓒ 가 더하는 줄은 **셋**이다.

    ## ★ 골든 쪽이 합격 조건이다 — 그리고 움직이지 않았다

    양식의 본문 부피 상한(219줄)을 재는 검사는 **골든 시나리오**로 잰다
    (`tests/report/test_overview_sections.py::
    test_body_stays_within_the_form_length_budget`). 이 WP 가 세운 것은 ⓒ 를
    고른 실행에서만 서므로 그 수는 **218 그대로**여야 하고, 여기가 그것을
    직접 잰다.

    ## ⚠⚠ ⓒ 의 본문은 **221줄로 상한을 2줄 넘는다** — 이 WP 가 고치지 않았다

    상한을 올려서 풀지 않았다(이미 다섯 번 밀린 자리이며 그 검사 독스트링이
    200 → 219 의 경위를 전부 진다). 넘친 줄을 붙임으로 내리려면 본문 절
    구성을 고쳐야 하고(`core/report/narrative.py` 의 6.3 절 · 3.4 절), 그
    파일은 이 WP 의 소관 밖이다 — **경위와 실측을 `.orch/R60/result_3.md` 에
    적었다.**

    ⚠ 셋 중 어느 것도 뺄 수 없다: 3.4·6.3 은 지시문이 요구한 **미반영 항목
    하나**가 만드는 두 줄이고(*「대가가 0인 이유가 산출물에서 사라지면 다음
    사람이 「대가가 0원인 사업」으로 읽는다」*), 결손 분해의 한 줄은 **포기
    항의 금액 그 자체**다(그것을 빼면 ⓒ 의 결론을 가른 수가 본문에서 사라진다).

    ## ★ 왜 「절대 줄 수」가 아니라 **증분**을 재는가

    절대값으로 못 박으면 갈래와 무관한 표 하나가 늘 때마다 이 검사가 함께
    움직여야 하고, 그때 재는 성질(*ⓒ 가 본문에 무엇을 더하는가*)은 그대로다.
    같은 코드로 돈 두 실행의 **차**는 갈래가 만든 것만 센다.
    """
    maintain_body = _body_lines(_maintain(reports))
    pool_body = _body_lines(_pool(reports))

    assert len(maintain_body) <= 219, (
        f"ⓑ 의 본문이 {len(maintain_body)}줄이다 — 이 WP 는 ⓒ 경로만 열었으므로 "
        "ⓑ 는 움직이지 않아야 한다. 상한을 올리지 말고 무엇이 늘었는지 보라"
    )
    assert len(pool_body) - len(maintain_body) == _POOL_BODY_LINES_ADDED, (
        f"ⓒ 가 본문에 더한 줄이 {len(pool_body) - len(maintain_body)}줄이다 — "
        f"실측은 {_POOL_BODY_LINES_ADDED}줄이며 자리는 위 주석이 셋을 이름으로 "
        "적는다. 늘었으면 상한을 올리지 말고 붙임으로 내릴 것"
    )


def _body_lines(report: CaseReport) -> list[str]:
    """표제부터 6절 끝까지 — 붙임 앞까지의 빈 줄 아닌 줄.

    ⚠ 세는 규칙을 `test_overview_sections.py` 와 **같게** 둔다. 다르게 세면
    두 검사가 다른 수를 말하면서 둘 다 초록불일 수 있다.
    """
    text = render_markdown(report)
    body = text[: text.index("# 붙임")]
    return [line for line in body.splitlines() if line.strip()]
