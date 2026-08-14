"""프로포마 빌더 — 작업 10.2 / FR-701.

프로포마 한 행 = ``CashFlowRow``. 이 모듈은 **자원·항목별로 행을 만드는 빌더**를
제공하며, 빌드된 행들의 합계 항등식은 ``tests/cba/test_proforma.py`` 가 검증한다
(10.1 — 20년 합계 == 항목별 합계, 원 단위 완전 일치).

항목별 상이한 에스컬레이션(AC3) — 각 항목이 자기 escalation_rate 를 가진다.
수명 종료 자원의 이후 연도는 0(AC4) — ``replacement_schedule`` 이 수명 종료
이후에는 행을 만들지 않는다.
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money, to_won
from core.contracts.validation import ValidationError


def check_analysis_period(
    *, analysis_years: int, asset_lifetimes_years: Sequence[int]
) -> None:
    """분석기간 상한 검사 — 분석기간 ≤ 최장 자원 수명 × 2, 경계 포함 (DV-5).

    ``asset_lifetimes_years`` 는 분석 대상 전 자원의 수명(년) 목록이다.
    ``CommonAsset`` 처럼 SW·HW 수명이 따로 있으면 **둘 다** 넣는다 — 대표수명
    (``CommonAsset.lifetime``, SW·HW 중 짧은 쪽)은 교체를 놓치지 않으려고
    작은 쪽을 쓰지만, 이 규칙이 묻는 것은 그 반대로 «가장 오래 남는
    구성요소가 얼마나 버티는가» 이므로 여기서는 최댓값을 쓴다.

    **「기본 20년」은 이 함수의 대상이 아니다.** 대장 문면의 그 절은 상한이
    아니라 기본값 규칙이고, 기본값을 주는 자리(있다면 케이스그리드·앱 조합
    계층)가 `core/cba` 밖이라 여기서 강제할 근거가 없다 — 구획 밖으로 둔다.
    """
    if not asset_lifetimes_years:
        raise ValueError(
            "asset_lifetimes_years 가 비었습니다 — 최장 자원 수명을 정할 수 없습니다"
        )
    longest = max(asset_lifetimes_years)
    ceiling = longest * 2
    if analysis_years > ceiling:
        raise ValidationError(
            field="cba.analysis_years",
            reason=f"분석기간({analysis_years}년)이 최장 자원 수명"
                   f"({longest}년)의 2배({ceiling}년)를 초과합니다",
            action=f"분석기간을 {ceiling}년 이하로 낮추거나, 최장 자원 수명"
                   f"({longest}년)이 실제와 맞는지 확인하십시오",
            rule="DV-5",
        )


def capex_row(tag: str, year: int, amount_won: int) -> CashFlowRow:
    """자본비 — 건설연도에 일시 계상. amount 는 양수(비용).

    CashFlowRow 는 부호 규약을 갖지 않는다 — 비용은 양수, 편익도 양수.
    합계(총사업비 vs 총편익)는 CBA 가 별도로 가른다.
    """
    return CashFlowRow(
        label=f"{tag} 자본비",
        tag=tag,
        amounts={year: Decimal(amount_won)},
    )


def fixed_om_row(
    tag: str,
    start_year: int,
    end_year: int,
    annual_amount_won: int,
    escalation_rate: float = 0.0,
) -> CashFlowRow:
    """고정 O&M — 매년 계상. 항목별 escalation_rate (FR-701-AC3).

    ``escalation_rate`` 는 소수(0~1). 0.02 = 2%/년. COMMON §6 — 비율은 소수.
    """
    if escalation_rate < 0:
        raise ValidationError(
            field="proforma.escalation_rate",
            reason=f"에스컬레이션율은 음수일 수 없습니다: {escalation_rate}. "
                   "비용이 해마다 줄어드는 자원은 드물며, 음수면 회수기간이 "
                   "단축되어 경제성이 과대 계상된다",
            action="escalation_rate 를 0 이상의 소수로 지정하십시오",
        )
    amounts: dict[int, Decimal] = {}
    current = float(annual_amount_won)
    for y in range(start_year, end_year + 1):
        amounts[y] = to_won(current)
        current *= (1.0 + escalation_rate)
    return CashFlowRow(label=f"{tag} 고정 O&M", tag=tag, amounts=amounts)


def fee_row(
    tag: str,
    start_year: int,
    end_year: int,
    annual_amount_won: int,
) -> CashFlowRow:
    """정산 수수료 — **비용 행** (`FR-205-AC1` / R32).

    ## 왜 편익에서 빼지 않는가

    「단일계약+관리주체 경유」의 관리 수수료(`Q-14`)를 `SelfConsumption` 의
    차감항으로 넣는 안을 버렸다. 수수료는 **비용**이고 편익에서 빼면
    **관점별 NPV 에서 그 비용이 사라진다** — 편익 계정만 줄어들 뿐 비용 계정에는
    한 줄도 남지 않으므로, 정부·사회 관점에서 그 지출이 아예 없는 사업이 된다.
    B/C 의 분모도 그만큼 작아져 비율이 좋아진다(같은 사업이 수수료를 편익 차감으로
    적으면 유리해지는 형태 — 도메인 원칙 「중복」의 부호 반대 판이다).

    ## 왜 `fixed_om_row` 를 쓰지 않는가

    라벨이 「고정 O&M」이 되어 리포트에서 **설비 유지비**로 읽힌다. 프로포마는
    사람이 행을 보고 더해 보는 문서이므로(`won_sum` 독스트링) 항목 이름이 뜻을
    나른다. 에스컬레이션도 두지 않았다 — 이 수수료는 요금 대비 **비율**이라
    요금이 오르면 저절로 따라 오르고, 여기서 또 올리면 이중 상승이 된다.
    """
    if start_year < 1:
        raise ValidationError(
            field="proforma.fee_start_year",
            reason=f"분석 연도는 1부터 셉니다: {start_year}",
            action="start_year 를 1 이상으로 지정하십시오",
        )
    if annual_amount_won < 0:
        raise ValidationError(
            field="proforma.fee_annual_amount_won",
            reason=f"수수료가 음수입니다: {annual_amount_won}",
            action=(
                "수수료는 비용이므로 양수로 지정하십시오. 음수 수수료는 "
                "「수수료를 돌려받는 사업」이 되어 경제성이 과대 계상됩니다"
            ),
        )
    return CashFlowRow(
        label=f"{tag} 정산 수수료",
        tag=tag,
        amounts={
            year: Decimal(annual_amount_won)
            for year in range(start_year, end_year + 1)
        },
    )


def replacement_row(
    tag: str,
    replacement_years: list[int],
    unit_cost_won: int,
    asset_lifetime_years: int,
    analysis_end_year: int,
) -> list[CashFlowRow]:
    """교체비 — 수명 종료 시점마다 계상 (FR-701-AC4).

    **수명 종료 자원의 «이후 연도는 0»** — ``analysis_end_year`` 넘으면 교체 행을
    만들지 않는다. 음수 비용(O&M 이 계속 붙는 것)이 생기지 않게 한다.
    """
    if asset_lifetime_years <= 0:
        raise ValidationError(
            field="proforma.asset_lifetime_years",
            reason=f"자산 수명은 양수여야 합니다: {asset_lifetime_years}",
            action="asset_lifetime_years 를 1 이상의 정수(년)로 지정하십시오",
        )
    rows: list[CashFlowRow] = []
    for rep_year in replacement_years:
        if rep_year > analysis_end_year:
            # 분석 종료 이후 교체는 계상 안 함 — 잔존가치로 처리 (10.8)
            continue
        rows.append(CashFlowRow(
            label=f"{tag} 교체비 ({rep_year}년차)",
            tag=tag,
            amounts={rep_year: Decimal(unit_cost_won)},
        ))
    return rows


def loan_repayment_row(
    tag: str, schedule: dict[int, int]
) -> CashFlowRow:
    """융자 상환 — 원리금균등/원금균등/만기상환 스케줄을 그대로 담는다.

    스케줄 자체는 11.3(WP-8)이 산출한다. 여기서는 «행» 만 만든다.
    """
    amounts = {y: Decimal(a) for y, a in schedule.items()}
    return CashFlowRow(label=f"{tag} 융자 상환", tag=tag, amounts=amounts)


def benefit_row(
    tag: str, schedule: dict[int, int], label_suffix: str = ""
) -> CashFlowRow:
    """편익 행 — tag 별로 연간 금액. 증분만(기준선 대비) 들어와야 한다 (FR-705)."""
    amounts = {y: Decimal(a) for y, a in schedule.items()}
    return CashFlowRow(
        label=f"{tag} 편익{label_suffix}",
        tag=tag,
        amounts=amounts,
    )


def tax_row(tag: str, schedule: dict[int, int]) -> CashFlowRow:
    """세금 행 — 부가세·재산세 등. tag 는 세금 종류."""
    amounts = {y: Decimal(a) for y, a in schedule.items()}
    return CashFlowRow(label=f"{tag} 세금", tag=tag, amounts=amounts)


def total_row(rows: list[CashFlowRow], label: str = "합계") -> CashFlowRow:
    """여러 행의 합계 행 — year 을 key 로 모아 더한다.

    **항목별 값을 그대로 더한다** (CashFlowRow.total 과 같은 규칙, NFR-103-M1).
    이미 원 단위 정수이므로 재반올림하지 않는다.
    """
    totals: dict[int, Decimal] = {}
    for row in rows:
        for year, amount in row.amounts.items():
            totals[year] = totals.get(year, Decimal(0)) + amount
    return CashFlowRow(label=label, tag=None, amounts=totals)


def aggregate(rows: list[CashFlowRow]) -> Money:
    """전 기간 총합 — ``sum(row.total() for row in rows)`` 와 ``total_row(rows).total()``
    이 원 단위로 일치해야 한다 (NFR-103-M1)."""
    return Money(sum((row.total() for row in rows), Decimal(0)))


def assert_proforma_identity(rows: list[CashFlowRow]) -> None:
    """10.1 — «항목별 합계의 합 == 총합계 행의 합» 원 단위 완전 일치.

    float 가 섞이면 어긋나고, 그 어긋남은 화면상 정상으로 보인다. CashFlowRow 가
    원 단위 정수만 받으므로 이 단언은 항상 성립해야 한다 — 성립하지 않으면
    CashFlowRow 의 검증을 우회한 곳이 있다.
    """
    sum_of_row_totals = aggregate(rows)
    grand_total = total_row(rows).total()
    if sum_of_row_totals != grand_total:
        raise ValueError(
            f"프로포마 합계 항등식 위반 (NFR-103-M1): "
            f"항목별 합 {sum_of_row_totals} != 총합 {grand_total}. "
            "CashFlowRow 원 단위 정수 규약을 우회한 곳이 있다"
        )


def _ensure_whole_won(amount: float) -> Money:
    """float 를 Money 로 — to_won 경유. private helper."""
    return to_won(amount)
