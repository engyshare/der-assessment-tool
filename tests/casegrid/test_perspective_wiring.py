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

from core.cba.perspective import Perspective
from core.report.case_report import CONCLUSION_METRIC, build_case_report
from core.report.narrative import render_markdown
from core.report.perspective_report import REQUIRED_PERSPECTIVES

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
    """
    operator = next(
        r for r in report.perspectives.results if r.perspective is Perspective.OPERATOR
    )
    assert int(operator.npv_value) == int(report.metrics[CONCLUSION_METRIC])
    assert int(operator.npv_value) == -12_591_162


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
    """
    text = render_markdown(report)
    npv_line = next(line for line in text.splitlines() if line.startswith("| NPV |"))
    assert npv_line.count("미산출") == 3, npv_line
    assert "-12,591,162원" in npv_line, npv_line
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
    """편익 합계 행은 비용 배분과 무관하게 늘 참인 수다 (WP-A-fix 결함 1 항목 2)."""
    text = render_markdown(report)
    benefit_line = next(line for line in text.splitlines() if line.startswith("| 편익 합계 |"))
    assert "미산출" not in benefit_line and "미배분" not in benefit_line
    assert "1,497,600원" in benefit_line  # 참여 주민
    assert "4,038,000원" in benefit_line  # 사업자


def test_header_row_pairs_repository_and_user_vocabulary(report) -> None:
    """표 머리에 사용자 어휘(국가·전기사용자·분산e사업자)를 병기한다 (결함 2-②)."""
    text = render_markdown(report)
    assert (
        "| 지표 | 사회(국가) | 참여 주민(전기사용자) | 사업자(분산E) | 정부 |"
        in text
    )
