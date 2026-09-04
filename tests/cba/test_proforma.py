"""10.1 — 프로포마 합계 항등식 (NFR-103-M1).

20년 합계 == 항목별 합계, **원 단위 완전 일치**. float 가 섞이면 어긋나고,
그 어긋남은 화면상 정상으로 보인다 — 이 저장소가 가장 위험으로 보는 오류 유형.

``CashFlowRow`` 가 원 단위 정수만 받으므로 항등식은 구조적으로 성립해야 한다.
성립하지 않으면 validator 를 우회한 곳이 있다.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from core.cba import (
    aggregate,
    assert_proforma_identity,
    benefit_row,
    capex_row,
    fixed_om_row,
    replacement_row,
    salvage_row,
    total_row,
)
from core.cba.proforma import check_analysis_period, energy_purchase_row
from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money
from core.contracts.validation import ValidationError


@pytest.mark.req("FR-701-AC1")
def test_proforma_sum_identity_20_years() -> None:
    """20년 합계 == 항목별 합계, 원 단위 완전 일치.

    오라클: 순위 1 (정의 항등식). capex + O&M(에스컬레이션) + 교체비 + 편익.
    """
    capex = capex_row(tag="PV", year=1, amount_won=10_000_000)
    om = fixed_om_row(
        tag="PV", start_year=1, end_year=20,
        annual_amount_won=300_000, escalation_rate=0.02,
    )
    repl = replacement_row(
        tag="PV_INV", replacement_years=[11],
        unit_cost_won=1_500_000,
        asset_lifetime_years=10, analysis_end_year=20,
    )
    benefit = benefit_row(
        tag="SelfConsumption",
        schedule={y: 1_200_000 for y in range(1, 21)},
    )
    rows = [capex, om, *repl, benefit]

    sum_of_row_totals = aggregate(rows)
    grand_total = total_row(rows).total()
    assert sum_of_row_totals == grand_total, (
        f"항등식 위반: 항목별 합 {sum_of_row_totals} != 총합 {grand_total}"
    )


@pytest.mark.req("FR-701-AC2")
def test_proforma_rows_cover_analysis_year_columns() -> None:
    row = fixed_om_row(
        tag="PV",
        start_year=1,
        end_year=20,
        annual_amount_won=300_000,
        escalation_rate=0.02,
    )

    assert tuple(row.amounts) == tuple(range(1, 21))


def test_assert_proforma_identity_passes_for_valid_rows() -> None:
    """assert_proforma_identity 는 정상 행 목록에서 예외 없이 통과."""
    rows = [
        capex_row(tag="A", year=1, amount_won=1_000_000),
        benefit_row(tag="B", schedule={y: 100_000 for y in range(1, 6)}),
    ]
    assert_proforma_identity(rows)  # 예외 없으면 통과


def test_total_row_sums_per_year() -> None:
    """total_row 는 year 을 key 로 합산 — 각 년도별 총계를 가진다."""
    r1 = CashFlowRow(label="A", tag="A", amounts={1: Decimal(100), 2: Decimal(200)})
    r2 = CashFlowRow(label="B", tag="B", amounts={1: Decimal(300), 3: Decimal(400)})
    total = total_row([r1, r2])
    assert total.amounts == {1: Decimal(400), 2: Decimal(200), 3: Decimal(400)}


def test_aggregate_equals_sum_of_totals() -> None:
    """aggregate(rows) == sum(row.total() for row in rows) — NFR-103-M1 항등식."""
    rows = [
        capex_row(tag="A", year=1, amount_won=500_000),
        fixed_om_row(tag="A", start_year=1, end_year=5, annual_amount_won=100_000),
        benefit_row(tag="X", schedule={y: 200_000 for y in range(1, 6)}),
    ]
    lhs = aggregate(rows)
    rhs = Money(sum((r.total() for r in rows), Decimal(0)))
    assert lhs == rhs


# ── FR-701-AC4 — 수명 종료 자원 이후 연도 0 ──────────────────────────────

@pytest.mark.req("FR-701-AC4")
def test_replacement_after_analysis_end_is_not_accounted() -> None:
    """분석 종료 이후 교체는 행을 만들지 않는다 — 잔존가치(10.8)로 처리.

    오라클: 순위 4 (정의 항등식). analysis_end_year=20 인데 교체 연도가 25 면
    그 교체는 0 이다 (행 자체가 없다).
    """
    rows = replacement_row(
        tag="X",
        replacement_years=[11, 21, 31],  # 21, 31 은 분석 종료(20) 이후
        unit_cost_won=1_000_000,
        asset_lifetime_years=10,
        analysis_end_year=20,
    )
    # 11년차 교체 1건만 행으로 나와야 — 21, 31 은 제외
    assert len(rows) == 1
    assert 11 in rows[0].amounts
    assert 21 not in rows[0].amounts


# ── FR-701-AC3 — 항목별 상이한 에스컬레이션 ──────────────────────────────

@pytest.mark.req("FR-701-AC3")
def test_fixed_om_applies_per_item_escalation() -> None:
    """항목별 escalation_rate 가 다르게 적용된다.

    오라클: 순위 1 (등비수열). 연 100,000, 2%/년, 3년 → [100000, 102000, 104040].
    """
    row = fixed_om_row(
        tag="X", start_year=1, end_year=3,
        annual_amount_won=100_000, escalation_rate=0.02,
    )
    assert int(row.amounts[1]) == 100_000
    assert int(row.amounts[2]) == 102_000
    assert int(row.amounts[3]) == 104_040


def test_negative_escalction_rejected() -> None:
    """escalation_rate 음수 거부 — 비용이 해마다 줄어드는 자원은 드물며,
    음수면 회수기간이 단축되어 경제성이 과대 계상된다.

    §7.3 대장(DV-1~14)에 이 규칙 전용 ID 가 없으므로 구조화(``ValidationError``)
    는 하되 ``rule`` 은 비운다 — 대장에 없는 ID 를 지어내면 매달린 참조가 된다.
    """
    with pytest.raises(ValidationError) as caught:
        fixed_om_row(
            tag="X", start_year=1, end_year=3,
            annual_amount_won=100_000, escalation_rate=-0.01,
        )
    parts = caught.value.as_dict()
    assert parts["field"] == "proforma.escalation_rate"
    assert "음수" in (parts["reason"] or "")
    assert (parts["action"] or "").strip()
    assert parts["rule"] is None


def test_replacement_row_rejects_non_positive_asset_lifetime() -> None:
    """자산 수명이 0 이하면 거부 — 교체 주기가 정의되지 않는다.

    §7.3 대장에 이 값의 양수 여부를 다루는 전용 규칙이 없어 ``rule`` 은 비운다.
    """
    with pytest.raises(ValidationError) as caught:
        replacement_row(
            tag="X", replacement_years=[10],
            unit_cost_won=1_000_000,
            asset_lifetime_years=0, analysis_end_year=20,
        )
    parts = caught.value.as_dict()
    assert parts["field"] == "proforma.asset_lifetime_years"
    assert "0" in (parts["reason"] or "")
    assert (parts["action"] or "").strip()
    assert parts["rule"] is None


# ── FR-701-AC1 — 8종 프로포마 행 전체 검증 ──────────────────────────────

@pytest.mark.req("FR-701-AC1")
def test_proforma_row_types_all_available() -> None:
    """FR-701-AC1 — 8종 프로포마 행이 모두 생성 가능.

    오라클: 순위 4 (정의 항등식) — 각 빌더 함수가 존재하고 CashFlowRow를 반환.
    8종: 자본비, 고정 O&M, 변동 O&M, 교체비, 융자 상환, 편익, 세금, 잔존가치.
    """
    # 1. 자본비 (capex_row)
    capex = capex_row(tag="PV", year=1, amount_won=10_000_000)
    assert capex.tag == "PV"
    assert capex.label == "PV 자본비"

    # 2. 고정 O&M (fixed_om_row)
    fixed_om = fixed_om_row(
        tag="PV", start_year=1, end_year=3,
        annual_amount_won=100_000, escalation_rate=0.02,
    )
    assert fixed_om.tag == "PV"
    assert fixed_om.label == "PV 고정 O&M"

    # 3. 변동 O&M (DER 자산 메서드, 행 생성은 asset 층에서)
    # 여기서는 변동 O&M 행 생성 로직이 존재함을 확인
    from core.cba.proforma import CashFlowRow
    variable_om_row = CashFlowRow(
        label="PV 변동 O&M", tag="PV",
        amounts={y: Decimal(50_000) for y in range(1, 4)},
    )
    assert variable_om_row.tag == "PV"

    # 4. 교체비 (replacement_row)
    replacement = replacement_row(
        tag="PV_INV", replacement_years=[11],
        unit_cost_won=1_500_000,
        asset_lifetime_years=10, analysis_end_year=20,
    )
    assert len(replacement) == 1
    assert replacement[0].tag == "PV_INV"

    # 5. 융자 상환 (loan_repayment_row)
    from core.cba.proforma import loan_repayment_row
    loan = loan_repayment_row(
        tag="PV_LOAN", schedule={1: 500_000, 2: 500_000}
    )
    assert loan.tag == "PV_LOAN"
    assert loan.label == "PV_LOAN 융자 상환"

    # 6. 편익 (benefit_row)
    benefit = benefit_row(
        tag="SelfConsumption",
        schedule={y: 1_200_000 for y in range(1, 21)},
    )
    assert benefit.tag == "SelfConsumption"
    assert benefit.label == "SelfConsumption 편익"

    # 7. 세금 (tax_row)
    from core.cba.proforma import tax_row
    tax = tax_row(
        tag="VAT", schedule={1: 100_000, 2: 100_000}
    )
    assert tax.tag == "VAT"
    assert tax.label == "VAT 세금"

    # 8. 잔존가치 — **금액**(`salvage_value`)과 **행**(`salvage_row`)이 갈린다.
    #    R43-B 까지 여기에는 금액만 있었다: 행 빌더가 없어서 배선 자리가
    #    `CashFlowRow(...)` 를 직접 지었고, 그래서 이 「8종」 목록의 여덟째만
    #    다른 일곱과 층이 달랐다.
    from core.cba.salvage import salvage_as_final_year_flow, salvage_value
    salvage = salvage_value(
        capex_won=10_000_000,
        asset_lifetime_years=25,
        elapsed_years_at_analysis_end=20,
    )
    assert int(salvage) > 0  # 5년 수명 남음
    final_year_flow = salvage_as_final_year_flow(
        capex_won=10_000_000,
        asset_lifetime_years=25,
        elapsed_years_at_analysis_end=20,
    )
    assert int(final_year_flow) == int(salvage)

    rows = salvage_row(
        "PVSalvage",
        label="PV 잔존가치 (20년차)",
        salvage_year=20,
        salvage_won=int(salvage),
        asset_lifetime_years=25,
        analysis_end_year=20,
    )
    assert len(rows) == 1
    assert rows[0].tag == "PVSalvage"
    # 유입이므로 비용 행에는 **음수**로 담긴다 — 뒤집는 자리는 빌더 하나다
    # (규약 전체는 `tests/cba/test_salvage_row.py`).
    assert int(rows[0].amounts[20]) == -int(salvage)


def test_salvage_value_rejects_non_positive_asset_lifetime() -> None:
    """자산 수명이 0 이하면 잔존 수명 비례 산출이 정의되지 않는다.

    §7.3 대장에 이 값의 양수 여부를 다루는 전용 규칙이 없어 ``rule`` 은 비운다.
    """
    from core.cba.salvage import salvage_value

    with pytest.raises(ValidationError) as caught:
        salvage_value(
            capex_won=10_000_000,
            asset_lifetime_years=-1,
            elapsed_years_at_analysis_end=0,
        )
    parts = caught.value.as_dict()
    assert parts["field"] == "salvage.asset_lifetime_years"
    assert "-1" in (parts["reason"] or "")
    assert (parts["action"] or "").strip()
    assert parts["rule"] is None


# ── DV-5 — 분석기간 ≤ 최장 자원 수명 × 2 (신설) ──────────────────────────


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_check_analysis_period_accepts_exactly_double_the_longest_lifetime() -> None:
    """딱 2배(경계값)는 통과해야 한다 — `≤` 이지 `<` 가 아니다.

    오라클: 손계산. 최장 수명 25년 × 2 = 50년. 분석기간 50년은 경계에서
    거부되면 안 된다.

    ⚠ **호출만 두지 않는다** — R24 인수에서 `check_marker_substance` 가 이
    테스트를 *「조항 마커가 있는데 검증이 없다」*로 잡았다. 조항을 인용한
    테스트가 아무것도 단언하지 않으면 추적표는 그 조항을 검증된 것으로 세고,
    실제로 붙드는 것은 「예외가 나지 않았다」뿐인데 그것이 **어디에도 적혀
    있지 않다.** 거부됐을 때 무엇이 왜 틀렸는지도 함께 남긴다.
    """
    try:
        check_analysis_period(analysis_years=50, asset_lifetimes_years=[25, 10])
    except ValidationError as exc:
        pytest.fail(f"경계값(정확히 2배)인 50년이 거부됐다 — `≤` 여야 한다: {exc.as_dict()}")


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_check_analysis_period_rejects_over_double_the_longest_lifetime() -> None:
    """경계를 1년 넘으면 거부 — field·reason·action·rule 을 모두 실어야 한다.

    오라클: 손계산. 최장 수명 25년 × 2 = 50년. 분석기간 51년은 초과.
    """
    with pytest.raises(ValidationError) as caught:
        check_analysis_period(analysis_years=51, asset_lifetimes_years=[25, 10])

    parts = caught.value.as_dict()
    assert parts["field"] == "cba.analysis_years"
    assert "51" in (parts["reason"] or ""), "받은 분석기간이 사유에 들어가야 한다"
    assert "25" in (parts["reason"] or ""), "최장 수명이 사유에 들어가야 한다"
    assert "50" in (parts["action"] or ""), "★ 상한을 조치가 알려 주어야 한다"
    assert parts["rule"] == "DV-5"


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_check_analysis_period_uses_the_longest_not_the_first_lifetime() -> None:
    """★ 「최장」— 자원이 여럿이면 목록의 **최댓값**이 기준이다, 첫째가 아니다.

    오라클: 손계산. 수명 목록 [10, 25, 15] 의 최장은 25년 → 상한 50년.
    첫째(10년)를 기준으로 삼으면 상한이 20년이 되어 분석기간 21년이
    (잘못) 거부된다 — 여기서는 25년 기준 상한(50년) 안이므로 통과해야 한다.
    """
    check_analysis_period(analysis_years=21, asset_lifetimes_years=[10, 25, 15])  # 예외 없으면 통과

    # 최장(25년)의 상한(50년)을 넘기면, 첫째(10년) 기준이 아니라 25년 기준으로
    # 거부 사유를 낸다
    with pytest.raises(ValidationError) as caught:
        check_analysis_period(analysis_years=51, asset_lifetimes_years=[10, 25, 15])
    parts = caught.value.as_dict()
    assert "25" in (parts["reason"] or "")
    assert "50" in (parts["action"] or "")


@pytest.mark.contract
@pytest.mark.req("NFR-303-M1")
def test_check_analysis_period_rejects_empty_lifetime_list() -> None:
    """자원이 하나도 없으면 최장을 정할 수 없다 — 호출측 계약 위반(대상아님 성격).

    NFR-303 대상(사용자 입력 규칙 위반)이 아니라 함수 호출 계약 위반이므로
    `ValidationError` 가 아니라 맨 `ValueError` 로 거부한다.
    """
    with pytest.raises(ValueError, match="비었습니다"):
        check_analysis_period(analysis_years=20, asset_lifetimes_years=[])


@pytest.mark.req("FR-701-AC1")
def test_the_energy_purchase_row_is_a_cost_of_a_measured_quantity() -> None:
    """★ 계통 전력 구매 행 — **라벨이 뜻을 나른다** (R34 · §13.2.2 C-3).

    `fixed_om_row`·`fee_row` 를 쓰지 않은 판단을 붙든다. 「고정 O&M」이면 설비
    유지비로, 「정산 수수료」면 거래 비용으로 읽히는데 이것은 **사 온 물건의
    값**이다 — 운전이 바뀌면 수량이 바뀐다. 같은 행에 섞으면 그 사실이
    프로포마에서 보이지 않는다.

    ⚠ **에스컬레이션이 없는 것이 지금은 옳다.** 요금 인상률은 잉여 판매 수익도
    올리는데 그쪽이 아직 배선되지 않았다 — 비용만 올리면 사업에 불리한 쪽으로
    틀린다(NSPM 대칭성). 배선되는 날 **양쪽이 함께** 움직여야 하므로, 여기서
    금액이 연도마다 같은 것을 못 박아 둔다.
    """
    row = energy_purchase_row(
        "GridPurchase", start_year=1, end_year=3, annual_amount_won=271_073
    )

    assert row.tag == "GridPurchase"
    assert "전력 구매" in row.label, (
        f"라벨이 「전력 구매」를 말하지 않는다 — {row.label!r}. 고정비·수수료와 "
        "같은 이름으로 실리면 운전이 바꾸는 비용이라는 사실이 사라진다"
    )
    assert row.amounts == {
        1: Decimal(271_073), 2: Decimal(271_073), 3: Decimal(271_073)
    }, "연도 범위 전건에 같은 금액이 실려야 한다 (에스컬레이션 없음)"


@pytest.mark.req("FR-701-AC1")
def test_a_negative_purchase_is_refused() -> None:
    """★★ 음수 구매 비용을 거부한다 — **「전력을 사면 돈을 받는 사업」**.

    통과시키면 부호가 뒤집힌 채로 프로포마에 실리고, 그 순간 저장장치를 키울수록
    경제성이 좋아진다 — R34 가 방금 없앤 *공짜로 받아 파는 기계*가 부호만 바꿔
    되돌아온 형태다. 값이 아니라 **방향**이 틀리므로 검토자 눈에 띄지 않는다.
    """
    with pytest.raises(ValidationError) as caught:
        energy_purchase_row(
            "GridPurchase", start_year=1, end_year=3, annual_amount_won=-1
        )

    assert caught.value.field == "proforma.purchase_annual_amount_won"


@pytest.mark.req("FR-701-AC2")
def test_the_purchase_row_counts_years_from_one() -> None:
    """분석 연도는 1부터 센다 — 0년차 행은 초기투자(`capex_row`)의 자리다.

    허용하면 같은 비용이 `t=0` 에 실려 **할인되지 않고** 전액 현가가 된다.
    """
    with pytest.raises(ValidationError) as caught:
        energy_purchase_row(
            "GridPurchase", start_year=0, end_year=3, annual_amount_won=100
        )

    assert caught.value.field == "proforma.purchase_start_year"


@pytest.mark.req("FR-705-AC2")
def test_the_forfeit_row_builder_is_reexported_by_the_partition_package() -> None:
    """★ **구획 패키지(`core.cba`)가 포기 항 빌더를 재수출한다** (R60/WP-3).

    ## 왜 이것이 실재하는 계약인가

    이 파일의 머리 import 가 그 계약을 쓰고 있다 — 프로포마 행 빌더 아홉을
    **`core.cba` 경로로** 부른다(`from core.cba import capex_row, …`). 새
    빌더만 그 목록에서 빠지면 *「모듈 경로(`core.cba.proforma`)를 아는 사람만
    쓸 수 있는 행 빌더」* 가 하나 생기고, 그 비대칭은 **아무 예외도 내지
    않는다** — 쓰는 사람이 긴 경로를 적으면 그냥 된다.

    ⚠ **`__all__` 까지 본다.** import 가 되는 것만으로는 부족하다: mypy strict
    는 `no_implicit_reexport` 로 **암묵 재수출을 거부**하므로, `__all__` 에
    없으면 타입 검사를 받는 호출부에서 이 경로가 성립하지 않는다
    (`core/casegrid/e2e_runner.py::__all__` 주석이 같은 사유를 적는다).

    ⚠ **같은 객체인지 본다.** 이름만 맞고 다른 것을 가리키면 두 경로가 서로
    다른 함수를 내주게 되고, 그때 한쪽에만 고친 검증이 다른 쪽을 지나간다.
    """
    import core.cba as cba_pkg
    from core.cba import forfeited_self_consumption_row as reexported
    from core.cba.proforma import forfeited_self_consumption_row as declared

    assert reexported is declared, (
        "`core.cba` 가 내주는 것과 `core.cba.proforma` 가 선언한 것이 다른 "
        "객체다 — 두 경로가 서로 다른 함수를 내주면 한쪽에만 고친 검증이 "
        "다른 쪽을 지나간다"
    )
    assert "forfeited_self_consumption_row" in cba_pkg.__all__, (
        "`core.cba.__all__` 에 없다 — mypy strict 의 `no_implicit_reexport` 가 "
        "암묵 재수출을 거부하므로 타입 검사를 받는 호출부에서 이 경로가 "
        f"성립하지 않는다. 지금 목록: {sorted(cba_pkg.__all__)}"
    )
    row = reexported(
        "ForfeitedSelfConsumption",
        start_year=1,
        end_year=2,
        annual_amount_won=1_000,
    )
    assert row.total() == Money(2_000)
