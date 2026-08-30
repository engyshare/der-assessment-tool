from decimal import Decimal
from typing import Literal, NamedTuple

from core.contracts.schemas import CashFlowRow
from core.contracts.units import Money, to_won
from core.contracts.validation import ValidationError
from core.incentive.schemas import IncentiveScheme


class PrefundingRiskCases(NamedTuple):
    """FR-611-AC4: 지원 예정 설비의 현재/무산 병기 케이스."""

    current_rows: tuple[CashFlowRow, ...]
    support_failure_rows: tuple[CashFlowRow, ...] | None
    support_failure_note: str | None


def _is_planned_prefunding(scheme: IncentiveScheme | None) -> bool:
    return bool(
        scheme is not None
        and scheme.is_prefunded
        and scheme.prefunded_status == "지원 예정"
    )


def calculate_loan_schedule(
    scheme: IncentiveScheme, loan_principal: float | Decimal
) -> dict[int, Money]:
    """FR-606-AC1, AC2: 융자 상환 스케줄 계산."""
    principal = to_won(loan_principal)
    if principal == Decimal(0) or scheme.loan_repayment_years == 0:
        return {}

    r = scheme.loan_interest
    n = scheme.loan_repayment_years
    grace = scheme.loan_grace_years

    schedule: dict[int, Money] = {}

    interest_only = to_won(float(principal) * r)
    for year in range(1, grace + 1):
        schedule[year] = interest_only

    rem_principal = principal
    for y in range(1, n + 1):
        year = grace + y
        if scheme.loan_repayment_type == "만기일시":
            payment = to_won(float(principal) * (1 + r)) if y == n else interest_only
        elif scheme.loan_repayment_type == "원금균등":
            prin_payment = to_won(rem_principal) if y == n else to_won(float(principal) / n)

            interest = to_won(float(rem_principal) * r)
            payment = to_won(prin_payment + interest)
            rem_principal = to_won(rem_principal - prin_payment)
        elif scheme.loan_repayment_type == "원리금균등":
            annuity = float(principal) / n if r == 0 else float(principal) * (r * (1 + r) ** n) / ((1 + r) ** n - 1)  # noqa: E501

            if y == n:
                interest = to_won(float(rem_principal) * r)
                payment = to_won(rem_principal + interest)
            else:
                payment = to_won(annuity)
                interest = to_won(float(rem_principal) * r)
                prin_payment = to_won(payment - interest)
                rem_principal = to_won(rem_principal - prin_payment)
        else:
            raise ValueError(f"알 수 없는 상환 방식: {scheme.loan_repayment_type}")

        schedule[year] = payment

    return schedule


def capex_viewpoint_row(*, label: str, tag: str, signed_amount_won: Decimal) -> CashFlowRow:
    """관점별 CAPEX 현금흐름 한 행 — 1년차 일시 계상 (`FR-611-AC3`).

    `build_capex_cashflows()` 가 관점마다 짓던 네 자리(자부담·타 사업 기지원·
    본 사업 보조금·사회 전체 비용)가 **같은 모양**이라 여기로 모았다 — 라벨과
    태그와 1년차 금액 하나. 네 자리 다 문면만 다르고 구조가 같다.

    ## ★★ 부호 규약 — **이 함수는 부호를 뒤집지 않는다**

    여기서 나오는 행은 **관점별 현금흐름**이고 위 넷은 전부 **유출**이므로
    ``signed_amount_won`` 은 **음수(또는 0)** 다. 부호를 만드는 것은 **호출자**이며
    이 함수는 받은 값을 **그대로** 싣는다. 양수를 넘기면 거부한다.

    ⚠ **`core/cba/proforma.py::capex_row` 의 규약을 끌어다 쓰지 마라.** 그쪽은
    *「amount 는 양수(비용)」* 인 **프로포마 비용 행**이고 이것은 **관점별
    현금흐름**이다 — 층이 다르다. 그 규약을 여기에 강제하면 네 행의 부호가
    조용히 뒤집히고, 그때 초기투자비는 **유입**이 되어 아무 예외 없이 결론이
    총사업비의 두 배만큼 좋아진다.

    ⚠ **`core/cba/proforma.py::salvage_row` 와도 반대다.** 잔존가치는 호출자가
    **양수**를 넘기고 **그 함수가** 뒤집는다(*「부호를 뒤집는 자리는 이 함수
    하나다」*). 여기서는 그 반대로 **호출자가 이미 뒤집어 넘긴다** — 이 함수가
    또 뒤집으면 두 번 뒤집혀 다시 양수가 된다. 그래서 뒤집기를 **넣지 않았고**,
    대신 양수 거부로 「호출자가 뒤집었는가」를 문턱에서 잡는다.

    연차가 1 로 고정인 것은 `FR-611` 이 말하는 것이 **초기 투자**이기 때문이다 —
    교체·잔존처럼 연차가 열리는 항목은 프로포마 쪽 빌더가 따로 진다.
    """
    if signed_amount_won > 0:
        raise ValidationError(
            field="incentive.capex_viewpoint_row.signed_amount_won",
            reason=(
                f"관점별 CAPEX 현금흐름은 유출이므로 0 이하여야 합니다: "
                f"{signed_amount_won} ({tag})"
            ),
            action=(
                "부호를 뒤집어 넘기십시오 — 이 함수는 뒤집지 않습니다. 양수를 "
                "그대로 실으면 초기투자비가 유입으로 잡혀 결론이 그 금액의 두 "
                "배만큼 좋아집니다"
            ),
        )
    return CashFlowRow(label=label, tag=tag, amounts={1: signed_amount_won})


def build_capex_cashflows(
    scheme: IncentiveScheme | None,
    capex: float | Decimal,
    viewpoint: Literal["OWNER", "PARTICIPANT", "GOV", "SOCIAL"],
) -> list[CashFlowRow]:
    """FR-611-AC1~AC6: 초기 투자 및 지원 현금흐름 산출 — 입력 스킴 그대로.

    기준선(무지원) 케이스는 이 함수의 인자가 아니라
    `build_baseline_capex_cashflows()` 라는 별개의 함수다. 예전에는
    `is_baseline: bool` 이 호출자가 손으로 넘기는 깃발이었고, 안 넘기면
    기준선은 그냥 없었다 — FR-607-AC1 의 「모든 실행에서 자동 포함」이
    성립하지 않았다. 등록된 목록을 그대로 따라 돌며 기준선 여부를 판정하는
    것은 **위층**인 `core.casegrid.incentive_cases`
    `build_capex_cashflows_for_all_cases()` 다 — 그 목록
    (`core.casegrid.variants.run_order()`)이 이 구획보다 상위 계층이라
    여기서 부를 수 없다 (`NFR-208-AC1`). 이 함수는 「이 스킴대로 계산」만
    책임진다.
    """
    capex_won = to_won(capex)
    if capex_won == Decimal(0):
        return []

    if scheme is None:
        scheme = IncentiveScheme.create_baseline()

    # FR-611-AC2: 기지원 설비는 본 사업의 지원액 0원 처리
    if scheme.is_prefunded:
        # 기지원 설비는 이미 재원이 확정되었으므로, 본 사업의 신규 보조금은 0.
        #
        # **자부담도 0이다** (FR-611-AC3.OWNER: *"사업자·주민 — 자기부담 0
        # (현금흐름 미발생). 근거: 실제 지출이 없음"*). 여기에 `capex_won` 을
        # 넣으면 타 사업이 낸 돈이 사업자 지갑에서 나간 것으로 잡혀, 조항이
        # 막으려던 바로 그 왜곡이 생긴다 — FR-611 의 Rationale 은 *"보조율
        # 100%로 우겨넣으면 본 사업의 필요 지원액에 타 사업 국비가 섞여 지원
        # 수준 산출이 왜곡된다"* 고 적었고, 부호만 반대인 같은 오류다.
        #
        # 취득원가 자체는 0으로 만들지 않는다 (AC2 「전액 계상」). 0이 되는
        # 것은 **관점별 현금흐름**이지 취득원가가 아니다.
        financing = {"subsidy": Money(0), "loan": Money(0), "equity": Money(0)}
    else:
        financing = scheme.calculate_financing(capex_won)

    rows = []

    if viewpoint in ("OWNER", "PARTICIPANT"):
        # 사업자/주민 관점: 총사업비 중 자기 자부담만 현금 유출
        rows.append(
            capex_viewpoint_row(
                label="초기투자비(자부담)",
                tag="capex.equity",
                signed_amount_won=-financing["equity"],
            )
        )
    elif viewpoint == "GOV":
        if scheme.is_prefunded:
            # FR-611-AC3.GOV: 정부 관점 기지원 설비 보조금은 '타 사업 국비'로 분리
            # 여기서는 본 사업의 보조금이 아니므로 분리 계상
            rows.append(
                capex_viewpoint_row(
                    label=f"타 사업 기지원 ({scheme.funding_program or '불명'})",
                    tag="capex.prefunded_subsidy",
                    signed_amount_won=-capex_won,
                )
            )
        else:
            # 신규 설비의 정부 지출
            rows.append(
                capex_viewpoint_row(
                    label="본 사업 정부 지원(보조금)",
                    tag="capex.gov_subsidy",
                    signed_amount_won=-financing["subsidy"],
                )
            )
            # 신규 설비의 전체 설치 비용 (사회 전체 관점에서 자원 소모를 보려면
            # 정부 관점에서도 전체 투자비 대비 편익을 볼 때 사용될 수 있으나
            # 일단 정부지출 관점의 보조금만 명시)
    elif viewpoint == "SOCIAL":
        # FR-611-AC3.SOCIAL: 재원이 어디서 왔든(보조금·융자·자부담·타 사업
        # 기지원) 자원 자체는 전액 소모된다 — 사회 관점은 그 소모분 전체를
        # 비용으로 본다. `financing`(스킴별 자금조달 분해)이나 `is_prefunded`
        # 여부와 무관하게 `capex_won` 그대로다.
        rows.append(
            capex_viewpoint_row(
                label="취득원가(사회 전체 비용)",
                tag="capex.social_cost",
                signed_amount_won=-capex_won,
            )
        )

    return rows


def build_baseline_capex_cashflows(
    scheme: IncentiveScheme | None,
    capex: float | Decimal,
    viewpoint: Literal["OWNER", "PARTICIPANT", "GOV", "SOCIAL"],
) -> list[CashFlowRow]:
    """FR-607-AC1, FR-607-AC3: 무지원 기준선 케이스의 CAPEX 현금흐름.

    FR-607-AC3 이 정한 기준선의 정의를 그대로 옮긴다 — 타 사업으로
    **확정** 지원된 설비는 기준선에 **포함**하고, **지원 예정**(미확정)은
    **제외**한다. 이 판정은 예전에 `is_baseline` 깃발이 하던 일이었다.
    """
    # FR-607/FR-611-AC4: `지원 예정`은 기준선에서 제외된 병기 케이스다.
    # 설비를 아예 빼는 것이므로 CAPEX 행도 없다. 0원 행을 남기면 "설비는 있는데
    # 비용만 0"인 모델이 되어 AC4의 「해당 설비를 제외한 케이스」가 아니다.
    if scheme is not None and _is_planned_prefunding(scheme):
        return []

    # 무지원 기준선일 경우, 지원을 0으로 둔 가상 스킴 적용.
    # 단 기지원 **확정** 설비는 기준선에 포함된 소여이므로 기존 스킴 유지.
    if scheme is None or not scheme.is_prefunded:
        scheme = IncentiveScheme.create_baseline()

    return build_capex_cashflows(scheme, capex, viewpoint)


def build_prefunding_risk_cases(
    scheme: IncentiveScheme | None,
    capex: float | Decimal,
    viewpoint: Literal["OWNER", "PARTICIPANT", "GOV"],
) -> PrefundingRiskCases:
    """FR-611-AC4: `지원 예정`인 설비는 **현재안 + 무산안**을 함께 꺼낸다.

    현재안은 입력 스킴 그대로 계산한다. 무산안은 **해당 설비 제외**이므로
    CAPEX 행이 빈 튜플이다. 회수기간 병기는 상위 계층이 이 두 케이스를 각각
    평가해 붙인다.
    """
    current_rows = tuple(build_capex_cashflows(scheme, capex, viewpoint))
    if not _is_planned_prefunding(scheme):
        return PrefundingRiskCases(
            current_rows=current_rows,
            support_failure_rows=None,
            support_failure_note=None,
        )

    return PrefundingRiskCases(
        current_rows=current_rows,
        support_failure_rows=(),
        support_failure_note="지원 무산 시 회수기간은 해당 설비 제외 케이스로 병기",
    )
