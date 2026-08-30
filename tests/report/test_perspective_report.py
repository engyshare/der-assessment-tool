"""FR-704-AC4 세 관점 병렬 리포트 — WP-10.

조항: *「세 관점이 **하나의 리포트에 병렬 표시**」*

**「담고 있다」로는 조항이 닫히지 않는다.** 세 결과를 한 객체에 담기만 하고 표를
내지 않으면 사람은 여전히 세 리포트를 나란히 놓고 봐야 한다. 그래서 여기서
붙드는 것은 **표의 모양**이다 — 지표 한 줄에 관점 셋의 값이 **같은 순서로**
실려 있는지.

그리고 **각 열이 자기 수치를 드는지**를 따로 본다. 세 열이 같은 결과를 복사해도
「열이 셋인 표」는 만들어지고, 그 표는 그럴듯하게 보인다.

파일 끝의 `FR-402-AC7` 시험은 **다른 조항**이다 — *「관점별 편익 집합이 서로
다름을 리포트에 명시」*. 여기 두는 이유는 그 「명시」의 실물이 이 파일이 이미
만들고 있는 병렬 리포트이기 때문이며, 그물 ③-1 이 *그 조항의 인용 전부가
`core.report` 를 만지지 않는다* 고 실측한 자리다.
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
    METRIC_TOTAL_BENEFIT,
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


@pytest.mark.req("FR-402-AC7")
def test_the_report_states_that_the_benefit_set_differs_by_perspective() -> None:
    """`FR-402-AC7` 전단 — *「관점별 편익 집합이 서로 다름을 **리포트에 명시**」*.

    ## 왜 이 시험이 따로 필요한가

    이 조항을 인용하던 시험은 `tests/cba/test_transfer.py` 1건뿐이었고 그것은
    **후단**(*「보조금은 사회 관점에서 이전지출로 처리하여 편익에 포함하지
    않는다」*)만 잰다 — `core.report` 를 만지지 않으므로 *리포트가 그 다름을
    말하는가* 는 아무도 보지 않았다(그물 ③-1 이 실측한 부채).

    ## 무엇을 붙드는가 — **같은 재료를 주고 집합만 갈린다**

    네 관점에 **똑같은 편익 행**을 준다. 그러면 열 사이의 차이는 오직
    *「그 관점이 무엇을 편익으로 세는가」* 에서만 나오고, 리포트가 그 차이를
    말하지 못하면 검토자는 **사회 열의 작은 값을 「사업이 덜 좋다」로 읽는다**
    (실제로는 *이전지출을 빼서* 작은 것이다).

    그래서 셋을 함께 본다 — 제외 tag 집합이 관점마다 **다르게 실려 있는가** ·
    그 사유가 리포트에 **문면으로** 있는가 · 그 다름이 표의 **수에도** 나타나는가.
    셋 중 하나라도 빠지면 「명시」가 아니다(라벨만 다르고 수는 같거나, 수만
    다르고 왜 다른지는 없다).
    """
    subsidy = benefit_row(tag="보조금", schedule={1: 300_000})
    self_use = benefit_row(tag="자가소비", schedule={y: 100_000 for y in range(1, 11)})
    rows = [self_use, subsidy]

    results = [
        compute_perspective_npv(p, rows, [], Money(1_000_000), _DISCOUNT)
        for p in REQUIRED_PERSPECTIVES
    ]
    society = compute_perspective_npv(
        Perspective.SOCIETY,
        rows,
        [],
        Money(1_000_000),
        _DISCOUNT,
        inclusions=society_excludes_subsidy(subsidy),
    )
    report = build_parallel_perspective_report([*results, society])

    # ① 편익 집합이 관점마다 다르게 **실려 있다**
    excluded = {column.label: column.excluded_tags for column in report.columns}
    assert len(set(excluded.values())) > 1, (
        f"모든 열의 제외 tag 가 같다: {excluded}. 같은 재료를 준 네 관점의 "
        "편익 집합이 리포트에서 구별되지 않으면 조항이 요구한 「명시」가 없다"
    )
    assert excluded["사회"] == ("보조금",)
    assert excluded["사업자"] == ()

    # ② **왜** 다른지가 리포트에 문면으로 있다 — 이전지출이라는 사유
    notes = report.exclusion_notes()
    society_notes = [note for note in notes if note[0] == "사회"]
    assert society_notes, f"사회 열의 제외 사유가 리포트에 없다: {notes}"
    assert any(
        tag == "보조금" and "이전지출" in why for _label, tag, why in society_notes
    ), f"보조금을 이전지출로 처리했다는 사유가 리포트에 없다: {society_notes}"

    # ③ 그 다름이 표의 **수**에도 나타난다 — 라벨만 다르고 수가 같으면
    #    검토자는 두 열을 같은 집합으로 읽는다
    operator_column = report.column_for(Perspective.OPERATOR)
    society_column = report.column_for(Perspective.SOCIETY)
    assert Money(
        operator_column.total_benefit - society_column.total_benefit
    ) == Money(300_000), (
        "사회 열의 편익이 사업자 열보다 보조금만큼 작아야 한다 — 같으면 "
        "보조금이 사회 편익에 그대로 남아 있다는 뜻이다 (FR-402-AC7 후단)"
    )

    benefit_row_in_table = next(
        row for row in report.metric_rows() if row[0] == METRIC_TOTAL_BENEFIT
    )
    header = report.header_row()
    values = dict(zip(header[1:], benefit_row_in_table[1:], strict=True))
    assert values["사업자"] != values["사회"], (
        f"표의 편익 합계 행이 두 관점에 같은 수를 싣는다: {values}"
    )
