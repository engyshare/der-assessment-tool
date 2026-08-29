"""리포트 앞머리 세 절 — **무엇을 · 어떻게 · 무엇으로부터** (R33 검토 반영).

## 왜 이 파일이 생겼는가

리포트 첫 판을 검토에 걸었더니 다섯 가지가 지적됐고 그중 셋이 앞머리의 공백이었다.

    「분석 대상 모델에 대한 소개가 없음」
    「각 조건이 어떻게 작용하는지 알 수 없음 —
      pv.rooftop capex 는 잡혀 있는데 그 비용 대비 편익이 적정한지는 어떻게 보는가」
    「분석 방법론 설명이 없음」

셋 다 옳다. 첫 판은 **결론과 민감도만** 실었다 — 검토자는 *무엇을 평가했는지*
모르는 채 *그 결론이 무엇에 민감한지*를 읽었다.

「1차 의견」 4 가 그 자리를 한 번 더 짚었다 — *「2.1 이 표부터 시작해 무엇을
평가하는가가 문장으로 없다」*. 그래서 `_target_summary()` 가 **300자 내외의
대상 요약**을 표 앞에 둔다.

⚠ **그 요약은 해설이 아니라 대입이다** (양식 0절). 값·자원 종류·기간을 전부
`CaseBasis` 에서 채우며, 이 파일에 사실 이외의 문장을 두지 않는다.

`narrative.py` 와 갈라 둔 이유는 길이다(`NFR-206`). 갈랐어도 **순서의 소유자는
`narrative.py` 하나**이며 여기서는 절을 만들기만 한다.
"""
from __future__ import annotations

from core.casegrid.models import BenefitLine, CaseBasis, ResourceLine
from core.report.case_report import CaseReport
from core.report.unreflected import (
    LABEL_VARIABLE_OM,
    build_unreflected,
    unreflected_rows,
    variable_om_unreflected,
)


def _won(value: float) -> str:
    return f"{value:,.0f}원"


def _resource_row(line: ResourceLine) -> str:
    produces = " · ".join(line.produces) if line.produces else "없음 (비용만)"
    return (
        f"| {line.kind} | {line.capacity} | {line.operating_mode} | "
        f"{line.lifetime_years}년 | {line.unit_capex} | "
        f"{_won(line.capex_won)} | {_won(line.fixed_om_won_per_year)}/년 | "
        f"{produces} |"
    )


def _target_summary(report: CaseReport) -> list[str]:
    """2.1 머리의 **평가 대상 요약** — 검토 「1차 의견」 4.

    ## 왜 표 앞에 문단이 필요한가

    의견 원문은 *「2.1 이 표부터 시작해 무엇을 평가하는가가 문장으로 없다」*
    였다. 표는 *어떤 값인가*에 답하지만 *무엇을 평가한 것인가*에는 답하지
    않는다 — 열 이름을 읽을 줄 아는 사람에게만 답한다.

    ⚠ **값을 전부 대입한다.** 자원 종류·용량 문면·기간·금액·편익 갈래·지원
    조건이 모두 `CaseBasis` 와 `CaseReport` 에서 온다. 고정된 것은 조사와
    이음말뿐이며, 그래서 구성이 바뀌면 이 문단도 함께 바뀐다.
    """
    basis = report.basis
    total_capex = sum(line.capex_won for line in basis.resources)
    resources = " · ".join(
        f"{line.kind} {line.capacity.split('·', maxsplit=1)[0].strip()}"
        for line in basis.resources
    )
    benefits = " · ".join(line.label for line in basis.benefits)
    return [
        f"단지 한 곳에 {resources} 를 함께 설치했을 때의 **사업주 관점 경제성**을 "
        f"평가한다. 총 초기투자 {_won(total_capex)}(부가세 별도·지원 반영 전), "
        f"지원 조건은 보조율 {report.subsidy_rate:.0%}다. 편익은 {benefits} 이며, "
        f"이를 분석기간 {basis.horizon_years}년 · 할인율 "
        f"{basis.discount_rate:.1%} 로 할인해 **할인 회수기간과 순현재가치**를 "
        f"낸다. 용량·이용률·운전 방식은 파이프라인이 세운 기준 구성이며 실제 "
        f"단지 설계가 아니다 — 결론은 이 구성에 한정된다.",
        "",
    ]


def model_section(report: CaseReport) -> list[str]:
    """2절 — **무엇을 평가했는가.**

    자원 제원은 `CaseBasis` 가 실행 경로에서 실어 온다. 여기서 다시 세우면
    사본이 되고, 제원이 바뀔 때 리포트는 옛 수를 그럴듯하게 계속 인쇄한다.
    """
    basis = report.basis
    total_capex = sum(line.capex_won for line in basis.resources)
    lines = [
        "## 2. 평가 개요",
        "",
        "### 2.1 평가 대상",
        "",
        *_target_summary(report),
        "| 자원 | 용량·성능 | 운전 방식 | 수명 | 단가 | 초기투자 | 고정 운영비 | 만드는 편익 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += [_resource_row(line) for line in basis.resources]
    lines += [
        "",
        f"- 총 초기투자 — **{_won(total_capex)}** (부가세 별도 · 지원 반영 전)",
        "- 구성의 성격 — 기준 구성 (실제 단지 설계 아님 · 부하·지붕 면적·"
        "계량점 구성 확정 시 재산출)",
        "",
        "### 2.2 사업 조건",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 보조율 | {report.subsidy_rate:.0%} |",
        "| 융자 · 세액공제 | 없음 |",
        f"| 시나리오 정의 | `{report.scenario_path}` |",
        "",
        "### 2.3 평가 전제",
        "",
        "| 항목 | 값 | 출처 |",
        "|---|---|---|",
        f"| 분석기간 | {basis.horizon_years}년 | 대장 `analysis.period_years` |",
        f"| 할인율 | {basis.discount_rate:.1%} | 모형 파라미터 (대장 항목 아님 · "
        "감도는 5.2) |",
        f"| 가격 기준 | {report.price_basis} | 전 항목 공통 |",
        f"| 전제 대장 | `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version} | 전건은 붙임 1 |",
        "",
    ]
    return lines


def method_section(report: CaseReport) -> list[str]:
    """3절 — **어떻게 계산했는가** (검토 지적 3).

    방법론을 적지 않으면 검토자는 결과를 **믿거나 말거나** 밖에 할 수 없다.
    `MC-1` 은 「설명할 수 있는가」를 재므로, 설명의 재료인 계산 사슬이 리포트
    안에 있어야 한다.

    ⚠ 3.4 는 **항목명과 방향만** 싣는다. 크기·사유·해소 조건은 붙임 8 이며,
    그 도출은 `core/report/unreflected.py` 하나가 한다 — 여기서 항목을 문장
    으로 적으면 구성이 바뀔 때 틀린 문장이 계속 인쇄된다.
    """
    basis = report.basis
    # ★ **3.2 의 단서와 3.4 의 표가 같은 판정 한 번에서 나온다 (R43-C).**
    # 두 번 부르면 같은 실행 안에서 갈릴 자리가 생긴다.
    unreflected = build_unreflected(report)
    # ★ **비용 행의 구성을 문장으로 박지 않는다 (R34 · R39-E).** 실린 항목에서
    # 지어 이 자리가 구성과 함께 움직이게 한다 — 종전 문면은 *「교체 · 잔존가치
    # 미포함」* 이었고 R39-E 가 그 둘을 배선한 뒤로 **거짓이 됐다.**
    cost_row_note = " · ".join(
        [
            f"연간 {' · '.join(line.label for line in basis.costs)}",
            *(
                [f"일회성 {' · '.join(line.label for line in basis.one_off_flows)}"]
                if basis.one_off_flows
                else []
            ),
        ]
    )
    # ★★ **남은 절반도 사실에서 짓는다 (R43-C).** 종전에는 이 단서가 문자열
    # 리터럴로 박혀 있었다 — 한 줄 안에서 앞 절반은 규약을 지키고 뒤 절반은
    # 지키지 않는 상태였고, **그것이 낡는 날을 붙드는 검사가 없었다.** 이제
    # 붙임 8 의 판정이 단서를 켜고 끈다: 변동 O&M 이 배선되면 단서가 저절로
    # 사라지고 위 `cost_row_note` 에 항목으로 나타난다.
    cost_row_caveat = (
        f" ({LABEL_VARIABLE_OM} 미포함 · 3.4)"
        if variable_om_unreflected(unreflected)
        else ""
    )
    return [
        "## 3. 평가 방법",
        "",
        "### 3.1 계산 절차",
        "",
        "```",
        "① 자원 구성   PV·ESS 를 2.1 제원으로 세운다",
        "② 디스패치    규칙기반 엔진이 대표일을 모의한다 (규칙: 붙임 6)",
        "              → 계통 송전량(PV 잉여) · ESS 저감 가능 첨두 (붙임 7)",
        "③ 편익 화폐화 송전량·첨두를 편익 갈래별 단가로 금액화한다 (4.3)",
        "④ 프로포마    편익 행 - 비용 행 = 연도별 순현금흐름",
        f"⑤ 지표        순현금흐름을 {basis.discount_rate:.1%} 로 할인해",
        "              순현재가치·할인 회수기간을 낸다 (붙임 3 산식)",
        "```",
        "",
        "### 3.2 계산 규약",
        "",
        "| 항목 | 규약 |",
        "|---|---|",
        f"| 시간 해상도 | {basis.dispatch_note} |",
        "| 부호 | 비용은 순현금흐름을 만들 때 **한 번만** 부호를 뒤집는다 |",
        "| 초기투자 시점 | 총사업비를 `t=0` 에 두고 할인하지 않는다 · 운영 "
        "현금흐름만 1년차부터 할인 |",
        f"| 가격 기준 | {report.price_basis} (전 항목 공통) |",
        # ★ **비용 행의 구성을 문장으로 박지 않는다 (R34).** 종전 문면은
        # *「고정 운영비」* 였고, 계통 전력 구매가 비용 행이 된 뒤로 **거짓이
        # 됐다** — 규약 표는 검토자가 「무엇이 비용으로 세어졌는가」를 읽는
        # 자리이므로, 그 자리가 틀리면 붙임 4 의 항목 표와 서로 다른 사업을
        # 말한다. 실린 항목에서 지어 이 자리가 구성과 함께 움직이게 한다.
        f"| 프로포마 비용 행 | {cost_row_note}{cost_row_caveat} |",
        "",
        "### 3.3 평가 관점",
        "",
        "| 항목 | 내용 |",
        "|---|---|",
        "| 관점 | 사업주 (설비 소유·운영 주체) |",
        "| 계상하는 편익 | 사업주에게 귀속되는 현금흐름 (잉여 전력 판매 수입 · "
        "요금 절감) |",
        "| 계상하지 않는 편익 | 사회적 편익 (온실가스 감축 · 계통 혼잡 완화 등) |",
        "",
        "### 3.4 이 평가가 하지 않은 것",
        "",
        "| 항목 | 방향 | 판정 |",
        "|---|---|---|",
        *unreflected_rows(unreflected),
        "",
        "- 크기 · 비어 있는 자리 · 해소 조건 — 붙임 8",
        "",
    ]


def _benefit_row(line: BenefitLine, total: int) -> str:
    """본문 4.3 의 한 행. **산식은 싣지 않는다** — 붙임 4 로 내렸다.

    양식이 본문을 4~5쪽으로 제한하는데 산식 열이 표를 화면 밖으로 밀어냈다.
    *「본문에서 한 줄로 말한 것의 근거는 붙임에」* 가 그 규칙이다.
    """
    share = f"{line.annual_won / total:.0%}" if total else "—"
    return (
        f"| {line.label} | {line.resource_code} | {_won(line.annual_won)} | "
        f"{share} |"
    )


def cost_benefit_section(basis: CaseBasis) -> list[str]:
    """2절 — **자원마다 얼마를 넣고 얼마를 버는가** (검토 지적 2).

    ## 왜 이 표가 필요한가

    지적 원문은 *「pv.rooftop capex 는 잡혀 있는데 그 비용 대비 편익이 적정한지는
    어떻게 보는가」* 였다. 연 편익을 한 덩어리로만 실으면 그 물음에 답할 자리가
    없다 — 검토자는 PV 에 얼마를 쓴 것이 타당한지 보려는데, 리포트는 PV 가 그중
    얼마를 벌어 오는지 말하지 않았다.

    ## ★★★ 왜 「1:1 귀속」을 **선언에서 읽지 않는가** (R43-E2)

    종전 이 함수는 편익을 `line.tag in resource.produces` 로 실었고, 표 아래에
    **스스로** 성립 조건을 적었다 — *「편익이 자원에 1:1 로 귀속될 때 (이
    구성: PV→잉여판매 · ESS→첨두절감)」*. **그 조건이 이 실행에서 거짓이었다.**
    잉여 판매 754,820원의 근거 수량은 계통 송전 18.80kWh 인데 그중 8.00kWh 는
    저장장치 방전분이며(붙임 7 대표일 13~16시), 표는 전액을 태양광 몫으로 적어
    단순 회수를 태양광 7.3년 · 저장장치 50.2년으로 인쇄했다.

    ⚠ **문면을 좁히는 대신 수량으로 갈랐다.** 표가 *「1:1 이 아닐 수 있다」* 고
    말하게 하는 것은 **틀린 수를 남긴 채 각주로 면책하는 것**이며, 이 파일에는
    각주로 면책한 문장이 낡아 거짓이 된 사례가 이미 둘 있다(아래 R34·R39-E
    별표). 몫은 러너가 운전 결과에서 낸다
    (`core/casegrid/attribution.py::attribute_benefits`).

    ⚠ **성립 조건도 실행에서 짓는다** — 아래 `_attribution_notes()`. 조건을
    문장으로 박아 두면 구성이 바뀌는 날 그 문장만 참인 채로 남는다.

    ⚠ **가른 것과 선언한 것을 구별해 적는다.** 계통 송전 창에서 나오지 않은
    금액은 여전히 **자원의 선언**(`produces`)으로 귀속되며 — 첨두 절감이
    그렇다 — 자원이 서로의 편익을 바꾸는 구성(예: PV 자가소비 + ESS 차익거래)
    에서는 그 선언이 종전과 같은 형태로 낡을 수 있다. 그래서 표 아래가 갈래
    마다 **무엇을 근거로 귀속했는지**를 함께 적는다.
    """
    earned_by_name: dict[str, int] = {}
    for share in basis.benefit_attributions:
        earned_by_name[share.resource_name] = (
            earned_by_name.get(share.resource_name, 0) + share.annual_won
        )
    lines = [
        "### 4.3 자원별 수지 — 얼마를 넣고 얼마를 버는가",
        "",
        # ★ **열 이름이 「할인 전 · 참고값」을 스스로 말한다 (R43-G).**
        # 4.1 은 「분석기간 내 미회수」인데 이 열은 태양광 14.4년을 적는다.
        # 표 아래 각주가 그 차이를 이미 적고 있었으나 *「표를 발췌해 가는
        # 사람은 열 이름만 읽는다」* 가 실제로 일어났다(문의사항 2026-08-29
        # 나-4). 값의 옳고 그름은 이 열이 아니라 귀속이 지며 R43-E2 가 다뤘다.
        "| 자원 | 초기투자 | 연 운영비 | 연 편익 | 연 순편익 | "
        "단순 회수(할인 전 · 참고값) |",
        "|---|---|---|---|---|---|",
    ]
    for resource in basis.resources:
        earned = earned_by_name.get(resource.name, 0)
        net = earned - resource.fixed_om_won_per_year
        payback = (
            f"{resource.capex_won / net:.1f}년" if net > 0 else "회수 불가"
        )
        lines.append(
            f"| {resource.kind} | {_won(resource.capex_won)} | "
            f"{_won(resource.fixed_om_won_per_year)} | {_won(earned)} | "
            f"{_won(net)} | {payback} |"
        )
    # ★★ **자원에 붙지 않는 운영비를 잔차로 싣는다 (R34).**
    #
    # 위 표는 자원마다 `fixed_om_won_per_year` 만 세므로, 자원에 귀속되지 않는
    # 비용(계통 전력 구매 · 정산 수수료)이 **표에서 사라진다.** 사라지면 「연
    # 순편익」과 「단순 회수」가 실제보다 좋게 나오고, 그 차이는 합계를 적지
    # 않는 표에서는 아무에게도 보이지 않는다.
    #
    # 항목을 열거하지 않고 **잔차로** 계산하는 것이 요점이다 — 열거하면 새
    # 비용이 생길 때 이 자리를 함께 고쳐야 하고, 고치지 않으면 다시 사라진다.
    attributed = sum(
        resource.fixed_om_won_per_year for resource in basis.resources
    )
    unattributed = basis.annual_cost_won - attributed
    # ★ **편익 쪽 잔여도 같은 행이 싣는다 (R43-E2).** 자원에 귀속되지 않는
    # 편익이 표에서 사라지면 「연 편익」 열의 합이 프로포마가 쓴 편익보다 작아
    # 지고, 합계를 적지 않는 표에서 그 차이는 아무에게도 보이지 않는다 —
    # 아래 비용 잔차가 R34 에 고치러 온 것과 **같은 형태**다.
    names = {resource.name for resource in basis.resources}
    unattributed_benefit = sum(
        share.annual_won
        for share in basis.benefit_attributions
        if share.resource_name not in names
    )
    if unattributed or unattributed_benefit:
        lines.append(
            f"| *자원 미귀속* | — | {_won(unattributed)} | "
            f"{_won(unattributed_benefit)} | — | — |"
        )
    lines += [
        "",
        "- 「단순 회수」 산식 — 초기투자 ÷ 연 순편익 (**할인하지 않음** · 결론에 "
        "쓰는 지표는 4.1 의 할인 회수기간)",
        *_attribution_notes(basis),
        "- 「자원 미귀속」 — 자원 하나에 귀속되지 않는 운영비와 편익 "
        "(항목별 금액·산식은 붙임 4). 자원 행의 회수기간에는 반영되지 않는다",
        "",
    ]
    return lines


def _attribution_notes(basis: CaseBasis) -> list[str]:
    """표 아래의 **성립 조건** — 실행이 실제로 한 귀속을 그대로 적는다 (R43-E2).

    종전 이 자리는 *「편익이 자원에 1:1 로 귀속될 때」* 라는 **문장**이었고, 그
    조건이 참인지는 아무도 재지 않았다. 이제 갈래마다 *누구에게 얼마가 · 어떤
    수량 근거로* 갔는지를 적고, 마지막 줄이 **합계 항등식**을 적는다 — 귀속 합
    ＝ 연 편익 합계. 그 줄이 표와 프로포마가 같은 편익을 말한다는 유일한 증거다.

    ⚠ **「1:1」을 말할 수 있는지도 재어 짓는다.** 갈래가 자원 하나에만 갔으면
    1:1 이 참이고, 여럿에 갈렸으면 그 사실과 몫을 적는다. 어느 쪽인지를 여기서
    가정하지 않는다.
    """
    kinds = {resource.name: resource.kind for resource in basis.resources}
    notes = ["- 편익 귀속 — **자원별 수량 몫으로 가른다** (선언이 아니라 운전 결과)"]
    for line in basis.benefits:
        shares = [s for s in basis.benefit_attributions if s.tag == line.tag]
        rendered = " · ".join(
            f"{kinds.get(share.resource_name, '자원 미귀속')} "
            f"{_won(share.annual_won)} ({share.basis_note})"
            for share in shares
        )
        one_to_one = " · **1:1 귀속**" if len(shares) == 1 else ""
        notes.append(
            f"  - {line.label} {_won(line.annual_won)} → {rendered}{one_to_one}"
        )
    total = sum(share.annual_won for share in basis.benefit_attributions)
    notes.append(
        f"  - 귀속 합계 **{_won(total)}** = 연 편익 합계 "
        f"**{_won(basis.annual_benefit_won)}**"
    )
    return notes


def _own_share_note(basis: CaseBasis, line: BenefitLine, resource_name: str) -> str:
    """붙임 4 의 「만드는 편익」에 **이 자원 몫**을 덧붙인다 — 갈린 갈래만.

    귀속이 갈리지 않았으면 빈 문자열이다. 조건 없이 적으면 갈래 금액과 같은
    수가 한 줄에 두 번 실리고, 그 사본은 한쪽만 고쳐지는 자리가 된다.
    """
    share = sum(
        s.annual_won
        for s in basis.benefit_attributions
        if s.tag == line.tag and s.resource_name == resource_name
    )
    if share == line.annual_won:
        return ""
    return f" · 그중 이 자원 몫 **{_won(share)}** (4.3)"


def _one_off_section(basis: CaseBasis) -> list[str]:
    """붙임 4 의 **일회성 흐름** 표 — 교체비·잔존가치 (R39-E).

    ⚠ **부호를 여기서 뒤집지 않는다.** `OneOffLine.amount_won` 은 프로포마
    비용 행과 **같은 수**이며(양수 = 지출 · 음수 = 유입) 그대로 인쇄한다.
    표시 층이 「보기 좋게」 뒤집으면 붙임 4 와 프로포마가 서로 다른 부호를
    말하고, 검토자는 어느 쪽이 계산에 들어갔는지 가릴 수 없다.

    ⚠ **비면 「없음」이라 적는다.** 표를 지우면 *「교체·잔존이 없는 구성」* 과
    *「배선이 끊긴 구성」* 이 붙임 4 에서 똑같이 보인다 — 그 둘을 가르는 판정은
    붙임 8 이 지고(`core/report/unreflected.py`), 이 자리는 **비었다는 사실**을
    싣는 데까지만 책임진다.
    """
    lines = [
        "### 일회성 흐름 (교체비 · 잔존가치)",
        "",
    ]
    if not basis.one_off_flows:
        return [*lines, "- 해당 없음 · 분석기간 내 교체·잔존 흐름 없음 (붙임 8)", ""]
    net = sum(line.amount_won for line in basis.one_off_flows)
    return [
        *lines,
        "| 항목 | 귀속 자원 | 연차 | 금액 | 산식 |",
        "|---|---|---|---|---|",
        *(
            f"| {line.label} | `{line.resource_name}` | {line.year}년차 | "
            f"{_won(line.amount_won)} | {line.formula} |"
            for line in basis.one_off_flows
        ),
        f"| **순액** | | | **{_won(net)}** | 양수 = 순지출 · 음수 = 순유입 "
        "(명목 · 할인 전) |",
        "",
    ]


def resource_detail_section(basis: CaseBasis) -> list[str]:
    """붙임 4 — 평가 대상 제원 상세.

    본문 2.1 은 **요약표**다. 심의위원이 표 하나로 대상을 잡을 수 있어야 하므로
    거기서는 칸을 늘리지 않고, 자원마다 무엇을 만들고 어떤 산식으로 금액이
    되는지는 여기로 내린다 — 양식이 *「본문에서 한 줄로 말한 것의 근거를 붙임에」*
    로 정한 그대로다.
    """
    total_benefit = sum(line.annual_won for line in basis.benefits)
    lines = [
        "## 붙임 4. 평가 대상 제원 상세",
        "",
        "### 편익 갈래",
        "",
        "| 편익 | 만든 자원 | 연 금액 | 비중 |",
        "|---|---|---|---|",
        *(_benefit_row(line, total_benefit) for line in basis.benefits),
        f"| **합계** | | **{_won(total_benefit)}** | 100% |",
        "",
        # ★★ **비용 항목을 편익과 같은 자리에 싣는다 (R34).**
        #
        # 종전에는 본문·붙임 어디에도 비용의 **항목별** 표가 없었고 「1년차
        # 운영비」 합계 하나만 있었다. 합계만 있는 표에서는 **빠진 행이
        # 드러나지 않는다** — 계통에서 산 전력이 값 없이 쓰이던 동안 운영비는
        # 200,000원(고정 O&M 둘)으로 그럴듯했다. 산식 칸에 수량과 단가를 함께
        # 적는 이유는 둘을 고치는 사람이 다르기 때문이다(단가는 대장, 수량은 운전).
        "### 비용 항목",
        "",
        "| 항목 | 귀속 자원 | 연 금액 | 산식 |",
        "|---|---|---|---|",
        *(
            f"| {line.label} | {line.resource_code or '—'} | "
            f"{_won(line.annual_won)} | `{line.formula}` |"
            for line in basis.costs
        ),
        f"| **합계** | | **{_won(basis.annual_cost_won)}** | |",
        "",
        # ★★ **표를 둘로 갈랐다 (R39-E).** 교체비(18년차)·잔존가치(20년차)는
        # 위 표의 「연 금액」 칸에 담을 수 없다 — 담으면 0원 행이 되고
        # *「합계만 있는 표에서는 빠진 행이 드러나지 않는다」* 가 그대로
        # 되돌아온다(`OneOffLine` 독스트링이 판정 근거다). **연차 칸이 필수인
        # 표를 따로 두는 것**이 그 판정의 실물이다.
        #
        # ⚠ **합계를 순액으로 낸다.** 교체비(지출)와 잔존가치(유입)를 한 표에
        # 싣고 합계를 절대값으로 적으면 두 방향이 상쇄된 뒤의 크기를 검토자가
        # 알 수 없다 — 그 순액이 *「이 결손을 배선하면 결론이 얼마 움직이는가」*
        # 이며, 배선 전 붙임 8 이 「미정량」으로 적고 있던 자리다.
        *_one_off_section(basis),
    ]
    for resource in basis.resources:
        produced = [line for line in basis.benefits if line.tag in resource.produces]
        lines += [
            f"### {resource.kind} — `{resource.name}`",
            "",
            "| 항목 | 값 |",
            "|---|---|",
            f"| 용량·성능 | {resource.capacity} |",
            f"| 운전 방식 | {resource.operating_mode} |",
            f"| 수명 | {resource.lifetime_years}년 |",
            f"| 단가 | {resource.unit_capex} |",
            f"| 초기투자 | {_won(resource.capex_won)} |",
            f"| 고정 운영비 | {_won(resource.fixed_om_won_per_year)}/년 |",
            "",
        ]
        if produced:
            # ★ **「만드는」과 「번다」가 같지 않다 (R43-E2).** 이 목록은 자원이
            # **선언한** 편익 갈래이고(`produces`), 그 갈래의 금액은 갈래
            # 전체다 — 잉여 판매처럼 여러 자원의 송전이 만든 금액이면 이 자원
            # 몫은 그보다 작다. 4.3 과 다른 수를 나란히 인쇄해 두면 검토자가
            # 둘 중 어느 쪽이 틀렸는지 물을 자리가 없으므로, **갈린 갈래에만**
            # 이 자원 몫을 함께 적는다(같으면 적지 않는다 — 같은 수를 두 번
            # 적으면 그것이 새 사본이 된다).
            lines += ["**만드는 편익**", ""]
            lines += [
                f"- {line.label} — {_won(line.annual_won)}/년 · `{line.formula}`"
                f"{_own_share_note(basis, line, resource.name)}"
                for line in produced
            ]
        else:
            lines += ["**만드는 편익** — 없음 (비용만 계상)"]
        lines.append("")
    lines += [
        "- 용량의 소유자 — `core/casegrid/ledger_levels.py` 의 **설계 변수** "
        "(탐색 구간과 검토 결과는 4.4 · 붙임 10)",
        "- 그 밖의 제원 소유자 — `core/casegrid/e2e_runner.py` 모듈 상수 "
        "(전제 대장 아님 · 설비 제원은 금액이 아니다)",
        "- 대장에서 오는 값 — 단가 · 분석기간",
        "",
    ]
    return lines
