"""관점 넷이 **배포 진입점**을 실제로 지나는가 — R52/WP-A.

⚠⚠⚠ **`status.md` 함정 맨 위 항** — 「검사가 배포 코드가 부르지 않는 함수를
직접 불러 통과한다」. 이 파일은 그 함정을 다시 만들지 않는다 — `core.cba.
perspective`·`core.casegrid.perspectives` 를 직접 부르지 않고, `app.run.
report_cli` 가 실제로 쓰는 진입점(`build_case_report` → `render_markdown`)만
지난다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.casegrid.e2e_runner import run_single_case_e2e
from core.casegrid.ledger_levels import build_level_map
from core.casegrid.perspectives import build_perspective_wiring, build_society_annualised
from core.casegrid.profiles import load_daily_shapes
from core.cba.perspective import Perspective
from core.contracts.units import ZERO
from core.report.case_report import CONCLUSION_METRIC, build_case_report
from core.report.narrative import render_markdown
from core.report.perspective_report import REQUIRED_PERSPECTIVES
from core.valuestream import DistributedSubItems

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO_ROOT / "fixtures" / "golden" / "scenario_unsubsidized.yaml"
_ASSUMPTIONS = _REPO_ROOT / "docs" / "assumptions.yaml"


@pytest.fixture(scope="module")
def report():
    return build_case_report(_GOLDEN, assumptions_path=_ASSUMPTIONS)


@pytest.mark.req("FR-704-AC4")
def test_deployed_report_carries_the_four_perspectives_in_user_order(report) -> None:
    """`app.run.report_cli` 가 쓰는 진입점이 관점 넷을 사용자 판정 순서로 낸다."""
    text = render_markdown(report)
    assert (
        "| 지표 | 사회(국가) | 참여 주민(전기사용자) | 사업자(분산E) | 정부 |"
        in text
    )
    assert REQUIRED_PERSPECTIVES == (
        Perspective.SOCIETY,
        Perspective.RESIDENT,
        Perspective.OPERATOR,
        Perspective.GOVERNMENT,
    )


def test_operator_perspective_keeps_the_conclusion_axis(report) -> None:
    """사업자(`OPERATOR`) 관점의 NPV 는 4.1 결론축과 같다 — 다시 계산하지 않는다.

    ⚠ spec 조항이 아니라 R52/WP-A 판정 아-7(결론축 불변)의 검사다 —
    `@pytest.mark.req` 를 달지 않는다.

    ⚠ **리터럴을 R52/WP-6 이 갱신했다** — `benefit.rec_price` 가
    `default0`(0원) → `assume`(70원/kWh)으로 올라 결론축이 −12,591,162 →
    **−11,537,129원**(+1,054,033원)으로 움직였다. 이 검사는 「관점이 축을
    다시 계산하지 않는가」를 재는 것이지 축 자체의 값을 고정하는 자리가
    아니므로, 위 첫 단언(`report.metrics[CONCLUSION_METRIC]` 과 같은가)이
    실질이고 아래는 그 값을 실측으로 못박아 둔다.
    """
    operator = next(
        r for r in report.perspectives.results if r.perspective is Perspective.OPERATOR
    )
    assert int(operator.npv_value) == int(report.metrics[CONCLUSION_METRIC])
    assert int(operator.npv_value) == -11_537_129


@pytest.mark.req("FR-402-AC7")
def test_benefit_tags_do_not_overlap_between_resident_and_operator(report) -> None:
    """관점마다 편익 집합이 다르다 — `payer` 로 가른 태그가 겹치지 않는다."""
    by_perspective = {
        r.perspective: {row.tag for row in r.benefit_rows}
        for r in report.perspectives.results
    }
    resident_tags = by_perspective[Perspective.RESIDENT]
    operator_tags = by_perspective[Perspective.OPERATOR]
    assert resident_tags, "참여 주민 관점에 편익 태그가 없다 — PeakShaving 이 배선되지 않았다"
    assert resident_tags.isdisjoint(operator_tags), (
        f"참여 주민과 사업자 열의 편익 태그가 겹친다: {resident_tags & operator_tags}"
    )


def test_outside_perspective_wallets_are_not_attributed_to_any_column(report) -> None:
    """`NWAs`(배전사업자)·`CP`(전력시장)는 관점 넷 어디에도 들어가지 않는다."""
    all_tags = {
        row.tag for r in report.perspectives.results for row in r.benefit_rows
    }
    assert "NWAs" not in all_tags
    assert "CP" not in all_tags
    assert "관점 넷 밖의 지갑" in render_markdown(report)


@pytest.mark.req("FR-704-AC5")
def test_society_perspective_has_no_subsidy_benefit(report) -> None:
    """사회 관점 편익에 보조금이 없다 — `assert_subsidy_excluded_from_society` 통과."""
    society = next(
        r for r in report.perspectives.results if r.perspective is Perspective.SOCIETY
    )
    assert not any("보조" in (row.tag or "") for row in society.benefit_rows)


def test_resident_perspective_shows_what_is_present_and_absent(report) -> None:
    """참여 주민(전기사용자) 관점에 있는 편익과 없는 편익이 리포트에 드러난다.

    ⚠ 「거의 빈다」로 뭉뚱그리지 않는다(WP-A-fix 결함 2-③) — `PeakShaving`
    은 이 실행에서 0원이 아니므로 「빈다」는 과장이다.
    """
    text = render_markdown(report)
    assert "PeakShaving" in text
    assert "SelfConsumption" in text
    assert "거의 빈다" not in text


def test_npv_row_prints_no_number_for_perspectives_without_cost_basis(report) -> None:
    """NPV 행 — 비용 배분이 없는 관점은 「미산출」이고 「0」이 인쇄되지 않는다.

    WP-A-fix 결함 1 의 핵심 단언: 참여 주민 974,035원이 「이득」으로,
    사회·정부 0원이 「손익 0」으로 오독되던 것을 막는다.

    ⚠ **리터럴을 R52/WP-6 이 갱신했다** — `benefit.rec_price` 가 결론축을
    −12,591,162 → **−11,537,129원**으로 옮겼다(위
    `test_operator_perspective_keeps_the_conclusion_axis` 참조).
    """
    text = render_markdown(report)
    npv_line = next(line for line in text.splitlines() if line.startswith("| NPV |"))
    assert npv_line.count("미산출") == 3, npv_line
    assert "-11,537,129원" in npv_line, npv_line
    assert "0" not in npv_line.replace("미산출", ""), npv_line


def test_cost_total_row_prints_not_allocated_for_perspectives_without_cost_basis(
    report,
) -> None:
    """비용 합계 행 — 같은 관점 셋은 「미배분」이지 「0원」이 아니다."""
    text = render_markdown(report)
    cost_line = next(line for line in text.splitlines() if line.startswith("| 비용 합계 |"))
    assert cost_line.count("미배분") == 3, cost_line
    assert "17,967,077원" in cost_line, cost_line


def test_benefit_total_row_always_prints_a_real_number(report) -> None:
    """편익 합계 행은 비용 배분과 무관하게 늘 참인 수다 (WP-A-fix 결함 1 항목 2).

    ⚠ **사업자 리터럴을 R52/WP-6 이 갱신했다** — REC 편익(0 → 70원/kWh)이
    사업자 편익 합계에 더해져 4,038,000 → **5,658,600원**이 됐다. 참여
    주민은 REC 를 포함하지 않아 그대로다.
    """
    text = render_markdown(report)
    benefit_line = next(line for line in text.splitlines() if line.startswith("| 편익 합계 |"))
    assert "미산출" not in benefit_line and "미배분" not in benefit_line
    assert "1,497,600원" in benefit_line  # 참여 주민
    assert "5,658,600원" in benefit_line  # 사업자


def test_header_row_pairs_repository_and_user_vocabulary(report) -> None:
    """표 머리에 사용자 어휘(국가·전기사용자·분산e사업자)를 병기한다 (결함 2-②)."""
    text = render_markdown(report)
    assert (
        "| 지표 | 사회(국가) | 참여 주민(전기사용자) | 사업자(분산E) | 정부 |"
        in text
    )


# ── R53/WP-1 — 사회 관점 편익(`DistributedBenefit`)의 배선 ──────────────────
#
# ⚠ 아래 세 검사는 `run_single_case_e2e()`(배포 진입점)를 직접 지난다 — 대장의
# `benefit.distributed_credit.*` 다섯 칸이 항상 0(`default0`)이라 `report`
# 픽스처만으로는 ⓒ(0이 아닌 값에서 축이 안 움직이는가)를 잴 수 없다.


def _run_with_distributed_credit(sub_items: DistributedSubItems):
    """`distributed_sub_items` 하나만 바꿔 배포 경로를 돈다.

    `test_rec_wiring.py::_run` 과 같은 이유로 대장 수준표를 그대로 쓴다 —
    이 파일이 재는 것이 배선이지 값이 아니기 때문이다.
    """
    level_map = build_level_map(_ASSUMPTIONS)
    return run_single_case_e2e(
        {},
        level_map=level_map,
        horizon_years=20,
        daily_shapes=load_daily_shapes(),
        annual_load_kwh=level_map["household_load_annual_kwh"]["base"],
        distributed_sub_items=sub_items,
    )


def test_society_column_receives_a_distributed_benefit_row() -> None:
    """ⓐ 사회 열이 `DistributedBenefit` 행을 받는다 — 값이 0이어도 행은 있다.

    「행이 없어서 0원」과 「값이 0이어서 0원」은 뜻이 정반대다(러너
    `GridPurchase` 주석 — 826~830줄 — 이 같은 규칙을 적는다).
    """
    outcome = _run_with_distributed_credit(DistributedSubItems())
    society = next(
        r for r in outcome.perspectives.results if r.perspective is Perspective.SOCIETY
    )
    tags = {row.tag for row in society.benefit_rows}
    assert "DistributedBenefit" in tags, (
        f"사회 열에 DistributedBenefit 행이 없다 — {tags}. 값이 0이어도 행은 있어야 한다"
    )


def test_distributed_benefit_wiring_leaves_the_conclusion_axis_untouched_when_empty() -> None:
    """ⓑ `society_annualised` 가 비어 있으면 `build_perspective_wiring()` 은
    종전과 완전히 같게 동작한다 — 사업자 `npv_value` 가 원 단위로 같다.

    ⚠ 이 검사는 `core.casegrid.perspectives` 를 직접 부른다 — 이 파일 머리말의
    「배포 진입점만 지난다」원칙에서 벗어나지만, 위·아래 검사가 이미
    `run_single_case_e2e()`(배포 경로)를 지나므로 「내부만 통과하고 배포는
    안 지난다」함정을 재현하지 않는다. 이 검사가 재는 것은 인자 기본값의
    **계약**(비어 있으면 옛 동작과 같다)이며 함수 서명의 성질이다.
    ⚠⚠ 값이 0이라 잘못 배선해도 초록불일 수 있다 — 아래
    `test_distributed_benefit_structurally_cannot_touch_the_conclusion_axis`
    가 0이 아닌 값으로 그 빈틈을 막는다.
    """
    without_kwarg = build_perspective_wiring((), (), (), ZERO, 0.05, horizon_years=1)
    with_kwarg = build_perspective_wiring(
        (), (), (), ZERO, 0.05, horizon_years=1,
        society_annualised=build_society_annualised(),
    )
    op_without = next(
        r for r in without_kwarg.results if r.perspective is Perspective.OPERATOR
    )
    op_with = next(r for r in with_kwarg.results if r.perspective is Perspective.OPERATOR)
    assert int(op_without.npv_value) == int(op_with.npv_value)


def test_distributed_benefit_structurally_cannot_touch_the_conclusion_axis() -> None:
    """ⓒ ★★★ 사회 편익 단가를 0이 아닌 큰 값으로 주면 **사회 열만** 움직이고
    사업자 `npv` 는 한 원도 안 움직인다.

    「값이 0이라 축이 안 움직인다」가 아니라 「구조적으로 축에 닿을 수
    없다」는 것을 잰다 — R53/WP-1 판정 ①의 핵심 단언.
    """
    zero = _run_with_distributed_credit(DistributedSubItems())
    large = _run_with_distributed_credit(
        DistributedSubItems(transmission_avoidance_won=50_000_000.0)
    )

    zero_society = next(
        r for r in zero.perspectives.results if r.perspective is Perspective.SOCIETY
    )
    large_society = next(
        r for r in large.perspectives.results if r.perspective is Perspective.SOCIETY
    )
    assert large_society.npv_value != zero_society.npv_value, (
        "사회 편익 단가를 50,000,000원으로 올렸는데 사회 열 NPV 가 움직이지 않았다 "
        "— DistributedBenefit 이 사회 열에 실제로 실리지 않는다"
    )
    assert int(large.metrics["npv"]) == int(zero.metrics["npv"]), (
        f"사회 편익만 올렸는데 사업자 npv 가 {int(zero.metrics['npv']):,} → "
        f"{int(large.metrics['npv']):,} 로 움직였다 — 사회 편익이 결론축에 샜다"
    )
