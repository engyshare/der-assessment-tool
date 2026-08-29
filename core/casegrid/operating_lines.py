"""운영 흐름의 **연간 표시줄** — 대표일 금액을 연간액으로 만들고 행으로 담는 한 자리.

## 왜 `e2e_runner` 에서 갈라냈나

`NFR-206`(파일 500줄)의 **코드 줄** 상한에 러너가 **499/500** 으로 닿아 있었다.
R43-F 의 첫 형태가 그 상한을 501줄로 넘겨 `check_file_size --code-strict` 를
빨간불로 냈고, 호출을 3줄로 줄여 499 로 되돌린 채 지나갔다 — 즉 **게이트가 이미
한 번 울렸고 그 자리를 좁혀서 지나간 상태**였다. 한 줄 더 줄여 또 넘기는 것은
이 저장소가 *「길이가 낡음을 만든다」* 로 한 번 배운 형태이므로 갈래를 뗀다.
상한을 고치는 것은 spec 개정(§16.5)이고, 근거 주석을 지워 줄이는 것은 조항이
지키려던 것을 정면으로 해친다 — `lifecycle.py` 가 R39-E2 에서 같은 판단을 했다.

## 무엇을 가르는 선으로 골랐나 — **연간화**

이 파일에 모인 다섯은 전부 **「대표일인가 연간인가」** 라는 한 규약을 다룬다:

    annualise()            편익마다 자기가 선언한 대로 ×365 를 붙인다
    cost_lines()           비용 표시줄. 고정 O&M 은 이미 연간, 수전은 ×365 다
    benefit_lines()        편익 표시줄. 창을 읽는 편익만 ×365 다
    benefit_line()         그 곱을 **산식 문면에 그대로 적는다**
    net_operating_flows()  연간 행 둘을 `npv()` 가 받는 순현금흐름으로 접는다

그래서 **연간화 계수 `DAYS_PER_YEAR` 자체가 여기 산다.** 규약과 그 규약을 쓰는
자리가 갈라져 있으면, 한쪽만 고쳐도 아무 예외가 나지 않고 결과가 365배 틀린다 —
이 파일의 세 독스트링이 전부 그 함정을 적고 있다.

⚠ **`_resource_lines()` 는 함께 오지 않았다.** 그것이 읽는 설비 제원 상수
(`PV_CAPACITY_FACTOR`·`ESS_RTE_PCT` 등)의 소유자를 리포트 문면이
*「`core/casegrid/e2e_runner.py` 모듈 상수」* 라고 **이름으로 지목**하고 있고
(`method_sections.py`·`appendix_sections.py` · `test_narrative.py` 가 그 문면을
붙든다), 상수를 옮기면 그 문면이 거짓이 된다. 문면을 고치면 리포트 매니페스트
해시가 움직인다 — 이 이동은 **행동을 한 줄도 바꾸지 않는 것**이 조건이었다.

⚠ **러너는 이 함수들을 `_annualise`·`_cost_lines`·`_benefit_lines`·
`_benefit_line`·`net_operating_flows` 라는 이름으로 계속 부른다** — 밖에서
`from core.casegrid.e2e_runner import ...` 로 그 경로를 쓰는 곳이 있기 때문이다
(`core/report/dispatch_sections.py` 의 `DAYS_PER_YEAR` ·
`tests/casegrid/test_benefit_line_rendering.py` 의 `_benefit_line` ·
`tests/casegrid/test_e2e_cost_sign.py` 의 `net_operating_flows`).
`lifecycle.py` 가 `_lifecycle_rows` 로 같은 재수출을 한 것과 같은 이유다.
"""
from __future__ import annotations

from collections.abc import Sequence

from core.casegrid.models import BenefitLine, CostLine
from core.contracts.der import DispatchResult
from core.contracts.schemas import CashFlowRow
from core.contracts.valuestream import ValueStream
from core.valuestream.settlement import SettlementCost

#: 대표일 하나를 되풀이해 한 해를 덮는 날 수. **연간화 계수이며 이 파일의
#: `annualise`·`cost_lines`·`benefit_line` 셋이 이 하나를 읽는다** (곱하는
#: 자리와 그 곱을 산식 문면에 적는 자리가 같은 값을 본다는 것이 요점이다).
#: `LEAP_YEAR_POLICY` 가 평년 고정을
#: 선언한다(`DV-4`). 러너는 이 이름을 재수출하고
#: (`e2e_runner.HOURS_PER_YEAR = DAYS_PER_YEAR * STEPS_PER_DAY`),
#: `core/report/dispatch_sections.py` 와 검사 다섯이 그 경로로 읽는다.
DAYS_PER_YEAR = 365

__all__ = (
    "DAYS_PER_YEAR",
    "annualise",
    "benefit_line",
    "benefit_lines",
    "cost_lines",
    "net_operating_flows",
)


def annualise(
    streams: Sequence[ValueStream], window: DispatchResult
) -> list[tuple[ValueStream, int]]:
    """편익마다 **자기가 선언한 대로** 연간화한다 — 러너 호출부의 ★★★ 참조
    (`e2e_runner.py::run_single_case_e2e` 의 `annualised = _annualise(...)` 자리).

    창을 읽는 편익만 대표일 금액에 `DAYS_PER_YEAR` 를 곱한다. 여기에 태그
    목록을 두지 않은 이유가 그 별표에 있다 — 목록은 편익이 늘 때 낡는다.
    """
    annualised: list[tuple[ValueStream, int]] = []
    for stream in streams:
        value = float(stream.annual_value(window, year=1))
        if type(stream).scales_with_dispatch_window:
            value *= DAYS_PER_YEAR
        annualised.append((stream, int(value)))
    return annualised


def cost_lines(
    *,
    pv_fixed_om: int,
    ess_fixed_om: int,
    daily_grid_import_kwh: float,
    grid_purchase_price: float,
    annual_purchase_won: int,
    settlement_costs: Sequence[SettlementCost],
) -> tuple[CostLine, ...]:
    """운영비를 **항목별로** 갈라 담는다 (`CostLine` 독스트링 참조).

    ⚠ **연간화 규약이 항목마다 다르다** — 편익 쪽과 같은 함정이다. 고정 O&M 은
    이미 연간액이고, 전력 구매는 **대표일 수량**에 365를 곱해야 한다. 산식
    문면에 그 곱을 그대로 적는다: 수량과 단가 중 어느 쪽이 틀렸는지 검토자가
    가릴 수 있어야 하고, 둘은 서로 다른 사람이 고친다(단가는 대장, 수량은 운전).
    """
    lines = [
        CostLine(
            tag="PVFixedOM",
            label="태양광 고정 운영비",
            annual_won=pv_fixed_om,
            resource_code="PV",
            formula=f"연 {pv_fixed_om:,}원 (1년차 · 연 2% 상승)",
        ),
        CostLine(
            tag="ESSFixedOM",
            label="저장장치 고정 운영비",
            annual_won=ess_fixed_om,
            resource_code="ESS",
            formula=f"연 {ess_fixed_om:,}원",
        ),
        CostLine(
            tag="GridPurchase",
            label="계통 전력 구매",
            annual_won=annual_purchase_won,
            # ⚠ 자원 이름을 「ESS」로 적지 않는다. 수전은 **부하와 충전의 합**이
            # 발전을 넘을 때 생기므로 어느 한 자원의 것이 아니다 — 지금 구성에서
            # 충전이 대부분이라는 것은 붙임 7 이 스텝별로 보여 준다.
            resource_code="",
            formula=(
                f"대표일 수전 {daily_grid_import_kwh:,.2f}kWh × "  # noqa: RUF001
                f"{DAYS_PER_YEAR}일 × "  # noqa: RUF001
                f"{grid_purchase_price:,.0f}원/kWh "
                f"= {annual_purchase_won:,}원"
            ),
        ),
    ]
    lines.extend(
        CostLine(
            tag=cost.tag,
            label=cost.label,
            annual_won=int(cost.annual_amount_won),
            resource_code="",
            formula=f"연 {int(cost.annual_amount_won):,}원 (정산 구조가 만드는 비용)",
        )
        for cost in settlement_costs
    )
    return tuple(lines)


def benefit_lines(
    settlement_by_stream: Sequence[tuple[ValueStream, int]],
    *,
    peak: ValueStream,
    peak_per_year: int,
    dispatch: DispatchResult,
) -> tuple[BenefitLine, ...]:
    """편익을 **갈래별로** 갈라 담는다 (`BenefitLine` 독스트링 참조).

    ⚠ **연간화 규약이 갈래마다 다르다.** 창에서 읽는 편익은 대표일 1일치라
    365를 곱하고, 생성자에서 연간 수량을 받는 편익은 곱하지 않는다. 이 차이는
    합계만 보면 보이지 않으므로 **산식 문면에 그대로 적는다** — 검토자가 곱하기
    하나를 잘못 짚으면 365배가 틀린다. 어느 쪽인지는 편익이 선언하며
    (`scales_with_dispatch_window`) 여기서 짐작하지 않는다.

    ⚠ **이름을 인스턴스에서 읽는다.** 종전에는 라벨이 `f"잉여 전력 판매 ({tag})"`
    로 박여 있었고, 그래서 「집합 PPA」·「분산특구 직접거래」가 배선되면
    **전량 판매·직접거래가 「잉여 전력 판매」로 인쇄된다**. 자원 귀속도 마찬가지다.

    ★ **첨두 절감도 같은 통로를 지난다** (R36). 종전에는 이 편익만 라벨과 산식이
    여기에 박여 있었고, 그래서 위 규칙의 예외로 남아 있었다 — 라벨은
    「첨두 수요 절감」으로 고정(인스턴스 이름은 「기본요금(피크) 절감」)이고
    산식은 러너가 지었다. 자원 귀속만 다르므로 그것만 인자로 받는다.
    """
    return tuple(
        benefit_line(stream, annual_won, resource, dispatch)
        for stream, annual_won, resource in (
            *((s, v, "PV") for s, v in settlement_by_stream),
            (peak, int(peak_per_year), "ESS"),
        )
    )


def benefit_line(
    stream: ValueStream, annual_won: int, resource: str, dispatch: DispatchResult
) -> BenefitLine:
    """편익 한 줄 — **산식은 편익이 내고 연간화는 여기가 붙인다**.

    ## ★★★ 왜 산식을 여기서 짓지 않는가 (R36)

    종전 이 자리는 창을 읽는 편익에 **`대표일 1,771원 × 365일`** 을 적었다.
    곱해서 나온 금액만 있고 **무엇에 얼마를 곱했는지가 없다** — 같은 리포트의
    비용 쪽은 `대표일 수전 6.19kWh × 365일 × 120원/kWh` 로 수량과 단가를 갈라
    적는데(`cost_lines`), 편익 쪽만 그러지 못했다. 그래서 **영향도 1위 인자인
    잉여 판매단가의 값이 붙임 4 어디에도 없었다.**

    대입값을 아는 것은 그 값을 생성자에서 받은 **편익 자신**이므로 문면을
    `ValueStream.formula()` 가 낸다. 여기서 지으려면 태그별 분기를 들게 되고
    그 목록은 편익이 늘 때 낡는다 — 위 연간화와 같은 근거다.

    ⚠ **연간화와 합계는 여기가 붙인다.** 편익은 자기 대입값까지만 알고,
    *「이 창이 대표일인가」* 는 호출측의 사정이다. 두 곳이 다 적으면 갈릴 수
    있고 갈린 쪽이 365배다.
    """
    # RUF001: 「×」는 검토자가 읽는 산식 문면이다. `x` 로 바꾸면 곱셈이 변수
    # 이름처럼 보인다 — 대상을 좁히는 면제이지 규칙을 넓히는 것이 아니다.
    body = stream.formula(dispatch, year=1)
    formula = (
        f"대표일 {body} × {DAYS_PER_YEAR}일 = {annual_won:,}원"  # noqa: RUF001
        if type(stream).scales_with_dispatch_window
        else f"{body} = {annual_won:,}원 (연간 수량으로 산정 · 연간화 없음)"
    )
    return BenefitLine(
        tag=stream.tag,
        label=f"{stream.name} ({stream.tag})",
        annual_won=annual_won,
        resource_code=resource,
        formula=formula,
    )


def net_operating_flows(
    benefit_rows: Sequence[CashFlowRow],
    cost_rows: Sequence[CashFlowRow],
) -> list[CashFlowRow]:
    """편익·비용 행을 `npv()` 가 받는 **순현금흐름**으로 만든다 — 비용의 부호를
    여기서 **한 번만** 뒤집는다 (R32).

    ## ★★ 이것이 없어서 비용이 NPV 를 늘리고 있었다

    `CashFlowRow` 는 **부호 규약을 갖지 않는다** — 「비용은 양수, 편익도 양수」이며
    가르는 것은 소비자다(`capex_row` 독스트링). `bcr()` 은 그래서 편익 목록과 비용
    목록을 **따로** 받는다. 그런데 `npv()` 는 목록 하나를 받아 `_pv()` 로 **부호
    있는 합**을 낸다. 즉 그 하나는 순현금흐름이어야 한다.

    종전 이 파일은 `benefit_rows + cost_rows` 를 **그대로** 넘겼다. 고정 O&M 이
    양수이므로 **비용이 편익으로 더해졌고**, NPV 는 O&M 현가의 두 배만큼 과대
    계상됐다. 아무 예외도 나지 않고, 두 배 오차는 「그럴듯한 큰 수」로 보인다.

    R32 가 관리 수수료를 비용 행으로 넣자 **수수료율을 올릴수록 NPV 가 커져서**
    드러났다 — 새 항목이 기존 결함을 밟은 형태이며, 그 결함은 비용 항목이
    O&M 둘뿐일 때는 아무도 밟지 않았다.

    ⚠ **`fee_row`·`fixed_om_row` 를 음수로 바꾸는 것으로 고치지 않았다.** 그러면
    프로포마 표시와 `bcr()` 의 분모가 함께 뒤집힌다 — 부호를 뒤집을 자리는 **순
    현금흐름을 만드는 이 경계 하나**여야 하고, 두 곳에서 뒤집으면 다시 양수가 된다.
    """
    negated = [
        CashFlowRow(
            label=row.label,
            tag=row.tag,
            amounts={year: -amount for year, amount in row.amounts.items()},
            assumption_refs=row.assumption_refs,
        )
        for row in cost_rows
    ]
    return [*benefit_rows, *negated]
