"""FR-704-AC4 세 관점 병렬 리포트 — WP-10.

조항: *「세 관점이 **하나의 리포트에 병렬 표시**」*

**「담고 있다」로는 조항이 닫히지 않는다.** 세 결과를 한 객체에 담기만 하고 표를
내지 않으면 사람은 여전히 세 리포트를 나란히 놓고 봐야 한다. 그래서 여기서
붙드는 것은 **표의 모양**이다 — 지표 한 줄에 관점 셋의 값이 **같은 순서로**
실려 있는지.

그리고 **각 열이 자기 수치를 드는지**를 따로 본다. 세 열이 같은 결과를 복사해도
「열이 셋인 표」는 만들어지고, 그 표는 그럴듯하게 보인다.
"""

from __future__ import annotations

import pytest

from core.cba.perspective import (
    Perspective,
    compute_perspective_npv,
    society_excludes_subsidy,
)
from core.cba.proforma import benefit_row
from core.contracts.units import Money
from core.contracts.validation import ValidationError
from core.report.perspective_report import (
    METRIC_NPV,
    REQUIRED_PERSPECTIVES,
    build_parallel_perspective_report,
)

_DISCOUNT = 0.05


def _result(perspective: Perspective, annual: int, investment: int, **kwargs):
    """관점 하나의 결과 — 관점마다 **다른 수치**를 준다.

    같은 수치를 주면 「세 열이 한 결과를 복사한다」는 결함이 드러나지 않는다.
    """
    rows = [benefit_row(tag=str(perspective.value), schedule={y: annual for y in range(1, 11)})]
    return compute_perspective_npv(
        perspective, rows, [], Money(investment), _DISCOUNT, **kwargs
    )


def _three_results() -> list:
    return [
        _result(Perspective.OPERATOR, 150_000, 1_000_000),
        _result(Perspective.RESIDENT, 100_000, 500_000),
        _result(Perspective.GOVERNMENT, 1_000_000, 100_000_000),
    ]


@pytest.mark.req("FR-704-AC4")
def test_one_report_carries_the_three_perspectives_in_the_spec_order() -> None:
    """리포트 **하나**에 세 관점이 있고 순서가 spec 문면 순서다."""
    report = build_parallel_perspective_report(_three_results())

    assert report.perspectives == REQUIRED_PERSPECTIVES
    assert REQUIRED_PERSPECTIVES == (
        Perspective.OPERATOR,
        Perspective.RESIDENT,
        Perspective.GOVERNMENT,
    ), "spec 문면 순서는 「사업자 / 참여 주민 / 정부(재정)」다"
    assert report.header_row() == ("지표", "사업자", "참여 주민", "정부")


@pytest.mark.req("FR-704-AC4")
def test_each_metric_row_places_all_three_values_side_by_side() -> None:
    """지표 한 줄에 관점 셋의 값이 열 순서대로 실린다 — 「병렬 표시」의 실물."""
    report = build_parallel_perspective_report(_three_results())
    table = report.as_table()

    header, *metric_rows = table
    assert len(header) == 4, header
    assert metric_rows, "지표 행이 없으면 표가 아니다"
    for row in metric_rows:
        assert len(row) == len(header), (
            f"지표 행의 칸 수가 머리행과 다르다: {row}. 열이 어긋나면 읽는 사람이 "
            "다른 관점의 값을 그 관점의 값으로 읽는다"
        )

    # 열의 자리가 관점과 실제로 대응하는가 — 이름이 아니라 **값**으로 확인한다
    npv_row = next(row for row in metric_rows if row[0] == METRIC_NPV)
    for index, perspective in enumerate(report.perspectives, start=1):
        assert npv_row[index] == str(int(report.column_for(perspective).npv))


@pytest.mark.req("FR-704-AC4")
def test_the_three_columns_hold_their_own_numbers() -> None:
    """세 열의 값이 서로 다르다 — 한 결과를 복사한 표를 배제한다."""
    report = build_parallel_perspective_report(_three_results())

    npvs = [column.npv for column in report.columns]
    assert len(set(npvs)) == 3, f"세 열이 같은 값을 들고 있다: {npvs}"

    # 없는 관점을 물으면 **오류**다 — 아무 열이나 돌려주면 관점을 섞게 된다
    with pytest.raises(KeyError):
        report.column_for(Perspective.SOCIETY)

    benefits = [column.total_benefit for column in report.columns]
    assert len(set(benefits)) == 3, f"세 열의 편익 합계가 같다: {benefits}"

    # 열마다 자기 관점의 편익 태그를 들고 있다
    for column in report.columns:
        assert column.total_benefit > Money(0)


@pytest.mark.req("FR-704-AC4")
def test_a_missing_perspective_refuses_the_report() -> None:
    """관점이 빠지면 표를 내지 않는다.

    빠진 열을 비워 두면 읽는 사람이 「0」인지 「산출하지 않았다」인지 구분할 수
    없고, 관점 섞기는 이 도메인에서 가장 흔한 중복 오류다 (원칙 2-3).
    """
    two_only = _three_results()[:2]

    with pytest.raises(ValidationError) as caught:
        build_parallel_perspective_report(two_only)

    error = caught.value
    assert error.field == "report.perspectives"
    assert "정부" in error.reason
    assert error.action.strip()


@pytest.mark.req("FR-704-AC4")
def test_a_duplicated_perspective_refuses_the_report() -> None:
    """같은 관점이 두 번 들어오면 어느 값을 실을지 판정할 수 없다."""
    results = [*_three_results(), _result(Perspective.OPERATOR, 999_999, 1)]

    with pytest.raises(ValidationError, match="두 번"):
        build_parallel_perspective_report(results)


@pytest.mark.req("FR-704-AC4")
def test_a_fourth_perspective_appends_without_moving_the_required_three() -> None:
    """네 번째 관점(사회)이 뒤에 붙고 앞 세 열의 자리는 그대로다.

    확장점을 신설했으면 그 경로로 **두 번째 인스턴스**를 넣어 보인다 —
    `Perspective.SOCIETY` 가 FR-704-AC5 의 기준 관점이다.
    """
    subsidy = benefit_row(tag="보조금", schedule={1: 300_000})
    society = compute_perspective_npv(
        Perspective.SOCIETY,
        [subsidy, benefit_row(tag="사회편익", schedule={y: 80_000 for y in range(1, 11)})],
        [],
        Money(700_000),
        _DISCOUNT,
        inclusions=society_excludes_subsidy(subsidy),
    )

    report = build_parallel_perspective_report([*_three_results(), society])

    assert report.perspectives[:3] == REQUIRED_PERSPECTIVES
    assert report.perspectives[3] == Perspective.SOCIETY
    assert report.header_row() == ("지표", "사업자", "참여 주민", "정부", "사회")
    for row in report.metric_rows():
        assert len(row) == 5, row


@pytest.mark.req("FR-704-AC4", "FR-704-AC7")
def test_the_report_says_why_an_item_was_excluded_from_a_perspective() -> None:
    """관점 전환 시 「무엇이 왜 제외되었는지」가 리포트에 남는다 (FR-704-AC7).

    병렬 표시가 관점 사이 비교를 쉽게 만드는 만큼, **왜 값이 다른가**를 함께
    보이지 않으면 「관점을 섞은 것」과 「관점을 옳게 가른 것」이 같아 보인다.
    """
    subsidy = benefit_row(tag="보조금", schedule={1: 300_000})
    society = compute_perspective_npv(
        Perspective.SOCIETY,
        [subsidy],
        [],
        Money(700_000),
        _DISCOUNT,
        inclusions=society_excludes_subsidy(subsidy),
    )
    report = build_parallel_perspective_report([*_three_results(), society])

    notes = report.exclusion_notes()
    assert notes, "제외 사유가 하나도 리포트에 실리지 않았다"
    labels = {label for label, _tag, _why in notes}
    assert "사회" in labels
    for label, tag, why in notes:
        assert tag, (label, why)
        assert "이전지출" in why or why.strip(), (label, tag)

    # 제외된 보조금은 사회 열의 편익에서 실제로 빠져 있다
    society_column = report.column_for(Perspective.SOCIETY)
    assert society_column.excluded_tags == ("보조금",)
    assert society_column.total_benefit == Money(0)
