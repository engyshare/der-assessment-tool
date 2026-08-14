"""리포트 앞머리 세 절 — **무엇을 · 어떻게 · 무엇으로부터** (R33 검토 반영).

## 왜 이 파일이 생겼는가

리포트 첫 판을 검토에 걸었더니 다섯 가지가 지적됐고 그중 셋이 앞머리의 공백이었다.

    「분석 대상 모델에 대한 소개가 없음」
    「각 조건이 어떻게 작용하는지 알 수 없음 —
      pv.rooftop capex 는 잡혀 있는데 그 비용 대비 편익이 적정한지는 어떻게 보는가」
    「분석 방법론 설명이 없음」

셋 다 옳다. 첫 판은 **결론과 민감도만** 실었다 — 검토자는 *무엇을 평가했는지*
모르는 채 *그 결론이 무엇에 민감한지*를 읽었고, 그것으로는 `MC-1` 의 두 질문에
답할 수 없다. 「이 회수기간이 왜 이 값인가」는 **설비 구성과 계산 사슬을 알아야**
답할 수 있는 물음이기 때문이다.

`narrative.py` 와 갈라 둔 이유는 길이다(`NFR-206`). 갈랐어도 **순서의 소유자는
`narrative.py` 하나**이며 여기서는 절을 만들기만 한다 — 순서가 두 곳에서 정해지면
조항(`FR-1002-AC1`)이 어느 파일 소관인지 갈린다.
"""
from __future__ import annotations

from core.casegrid.models import BenefitLine, CaseBasis, ResourceLine
from core.report.case_report import CaseReport


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


def model_section(report: CaseReport) -> list[str]:
    """0절 — **무엇을 평가했는가.**

    자원 제원은 `CaseBasis` 가 실행 경로에서 실어 온다. 여기서 다시 세우면
    사본이 되고, 제원이 바뀔 때 리포트는 옛 수를 그럴듯하게 계속 인쇄한다.
    """
    basis = report.basis
    total_capex = sum(line.capex_won for line in basis.resources)
    lines = [
        "## 0. 무엇을 평가했는가",
        "",
        "단지 한 곳에 아래 설비를 함께 놓았을 때의 **사업 경제성**을 본다.",
        "",
        "| 자원 | 용량·성능 | 운전 방식 | 수명 | 단가 | 초기투자 | 고정 운영비 | 만드는 편익 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += [_resource_row(line) for line in basis.resources]
    lines += [
        "",
        f"- **총 초기투자 {_won(total_capex)}** (부가세 별도 · 지원 반영 전)",
        f"- 지원 조건: **보조율 {report.subsidy_rate:.0%}** — 그 외 융자·세액공제는 없다",
        f"- 분석기간 **{basis.horizon_years}년** · 할인율 **{basis.discount_rate:.1%}** · "
        f"가격 기준 **{report.price_basis}**",
        "",
        "> ⚠ **이 구성은 대표 사례이지 실제 단지 설계가 아니다.** 용량·이용률·",
        "> 운전 방식은 파이프라인이 세운 기준 구성이며, 실제 단지의 부하·지붕",
        "> 면적·계량점 구성이 확정되면 그 값으로 다시 돌려야 한다. 아래 결론은",
        "> **이 구성에 한정**된다.",
        "",
    ]
    return lines


def method_section(report: CaseReport) -> list[str]:
    """1절 — **어떻게 계산했는가** (검토 지적 3).

    방법론을 적지 않으면 검토자는 결과를 **믿거나 말거나** 밖에 할 수 없다.
    `MC-1` 은 「설명할 수 있는가」를 재므로, 설명의 재료인 계산 사슬이 리포트
    안에 있어야 한다.
    """
    basis = report.basis
    return [
        "## 1. 어떻게 계산했는가",
        "",
        "### 계산 사슬",
        "",
        "```",
        "① 자원 구성   PV·ESS 를 위 제원으로 세운다",
        "② 디스패치    규칙기반 엔진이 대표일 24스텝을 모의한다",
        "              → 계통 송전량(PV 잉여) · ESS 저감 가능 첨두",
        "③ 편익 화폐화 송전량·첨두를 편익 갈래별 단가로 금액화한다 (2절)",
        "④ 프로포마    편익 행 - 비용 행 = 연도별 순현금흐름",
        f"⑤ 지표        순현금흐름을 {basis.discount_rate:.1%} 로 할인해",
        "              순현재가치·할인 회수기간을 낸다 (7절 산식)",
        "```",
        "",
        "### 이 계산이 서 있는 규약",
        "",
        f"- **시간 해상도** — {basis.dispatch_note}",
        "- **부호 규약** — 비용은 순현금흐름을 만들 때 **한 번만** 부호를 뒤집는다.",
        "  두 번 뒤집으면 비용이 편익으로 더해진다(이 저장소가 실제로 겪은 결함).",
        "- **초기투자 시점** — 총사업비를 `t=0` 에 두고 할인하지 않는다. 운영",
        "  현금흐름만 1년차부터 할인한다.",
        f"- **가격 기준** — {report.price_basis}. 전 항목에 같은 기준을 강제한다.",
        "- **비용 구성** — 프로포마의 비용 행은 **고정 운영비뿐**이다. 변동 O&M ·",
        "  교체 · 잔존가치는 들어 있지 않다 (아래 참조).",
        "",
        "### 이 분석이 하지 않은 것",
        "",
        "**결과를 읽을 때 함께 읽어야 한다.** 하지 않은 것을 적지 않으면 검토자는",
        "다 했다고 읽는다.",
        "",
        *_lifetime_caveat(basis),
        "- **계절·요일 변동을 반영하지 않았다.** 대표일 하나를 365배 했다.",
        "- **요금 인상률이 계산에 들어가지 않았다** — 4절의 「미반영 의심」 참조.",
        "- **자가소비를 계상하지 않았다**(PV 자가소비율 0%). 전량 판매 전제이므로",
        "  실제로 단지가 자가소비하면 편익 구조가 달라진다.",
        "- **불확실성을 확률로 다루지 않았다.** 3수준 스윕이며 몬테카를로가 아니다.",
        "",
    ]


def _lifetime_caveat(basis: CaseBasis) -> list[str]:
    """★ **분석기간보다 수명이 짧은 자원**을 리포트가 스스로 찾아 적는다.

    ## 왜 문장으로 박아 두지 않는가

    지금 구성은 ESS 수명 17년 · 분석기간 20년이라 **교체가 한 번 필요한데
    프로포마에 교체 비용 행이 없다.** 즉 현 결과는 그 자원에 **관대하다.**

    이것을 「ESS 는 교체비가 빠져 있다」고 문장으로 적으면 제원이 바뀔 때
    (수명 25년 ESS 를 쓰면) 리포트가 **틀린 경고를 계속 인쇄한다.** 반대로
    분석기간을 30년으로 늘리면 PV 도 교체 대상이 되는데 그때는 **아무 말도
    하지 않는다.** 그래서 수명과 분석기간을 견주어 그때그때 판정한다.

    빠진 비용을 여기서 **계산하지 않는다** — 교체 시점·잔존가치 규약은
    `FR-104` 소관이며, 리포트가 임의로 메우면 그 수가 어디서 왔는지 아무도
    말할 수 없다. 여기서 하는 일은 **빠졌다는 사실을 드러내는 것**이다.
    """
    short = [r for r in basis.resources if r.lifetime_years < basis.horizon_years]
    if not short:
        return [
            f"- **교체·잔존가치를 계상하지 않았다.** 다만 분석기간"
            f"({basis.horizon_years}년) 안에 수명이 끝나는 자원이 없어 이번"
            " 결과에는 영향이 없다.",
        ]
    listed = " · ".join(
        f"{r.kind} 수명 {r.lifetime_years}년" for r in short
    )
    return [
        f"- ⚠ **교체 비용을 계상하지 않았다.** 분석기간 {basis.horizon_years}년"
        f" 안에 수명이 끝나는 자원이 있다 — {listed}. 프로포마의 비용 행은",
        "  고정 운영비뿐이므로 **교체비가 빠져 있고, 그만큼 이 결과는 해당",
        "  자원에 관대하다.** 잔존가치도 함께 빠져 있어 방향이 상쇄되지만",
        "  크기는 다르다. 교체·잔존가치 규약(`FR-104`)을 태우기 전까지 이",
        "  결과는 **상한선으로** 읽어야 한다.",
    ]


def _benefit_row(line: BenefitLine, total: int) -> str:
    share = f"{line.annual_won / total:.0%}" if total else "—"
    return (
        f"| {line.label} | {line.from_resource} | {_won(line.annual_won)} | "
        f"{share} | {line.formula} |"
    )


def cost_benefit_section(basis: CaseBasis) -> list[str]:
    """2절 — **자원마다 얼마를 넣고 얼마를 버는가** (검토 지적 2).

    ## 왜 이 표가 필요한가

    지적 원문은 *「pv.rooftop capex 는 잡혀 있는데 그 비용 대비 편익이 적정한지는
    어떻게 보는가」* 였다. 연 편익을 한 덩어리로만 실으면 그 물음에 답할 자리가
    없다 — 검토자는 PV 에 얼마를 쓴 것이 타당한지 보려는데, 리포트는 PV 가 그중
    얼마를 벌어 오는지 말하지 않았다.

    ⚠ **여기의 「자원별 회수」는 참고값이다.** 편익 귀속이 깨끗한 것은 이 구성이
    PV→잉여판매, ESS→첨두절감으로 **하나씩 대응하기 때문**이며, 자원이 서로의
    편익을 바꾸는 구성(예: PV 자가소비 + ESS 차익거래)에서는 이렇게 가를 수
    없다. 그 사실을 표 아래에 적는다 — 적지 않으면 다음 사례에서 같은 표를
    보고 같은 방식으로 읽는다.
    """
    total_benefit = sum(line.annual_won for line in basis.benefits)
    lines = [
        "## 2. 자원마다 얼마를 넣고 얼마를 버는가",
        "",
        "### 편익 갈래",
        "",
        "| 편익 | 만든 자원 | 연 금액 | 비중 | 산식 (대입값) |",
        "|---|---|---|---|---|",
    ]
    lines += [_benefit_row(line, total_benefit) for line in basis.benefits]
    lines += [
        f"| **합계** | | **{_won(total_benefit)}** | 100% | |",
        "",
        "### 자원별 수지",
        "",
        "| 자원 | 초기투자 | 연 운영비 | 연 편익 | 연 순편익 | 단순 회수 |",
        "|---|---|---|---|---|---|",
    ]
    for resource in basis.resources:
        earned = sum(
            line.annual_won
            for line in basis.benefits
            if line.tag in resource.produces
        )
        net = earned - resource.fixed_om_won_per_year
        payback = (
            f"{resource.capex_won / net:.1f}년" if net > 0 else "회수 불가"
        )
        lines.append(
            f"| {resource.kind} | {_won(resource.capex_won)} | "
            f"{_won(resource.fixed_om_won_per_year)} | {_won(earned)} | "
            f"{_won(net)} | {payback} |"
        )
    lines += [
        "",
        "> **「단순 회수」는 할인하지 않은 참고값이다** — 초기투자 ÷ 연 순편익이며,",
        "> 결론에 쓰는 지표는 7절의 **할인** 회수기간이다. 여기서 갈라 보는 이유는",
        "> *어느 설비가 제 몫을 하는가*를 보기 위해서다.",
        ">",
        "> ⚠ **편익 귀속이 언제나 이렇게 깨끗하지는 않다.** 이 구성은 PV→잉여판매,",
        "> ESS→첨두절감으로 하나씩 대응한다. 자원이 서로의 편익을 바꾸는 구성",
        "> (PV 자가소비 + ESS 차익거래 등)에서는 자원별로 가를 수 없으며, 그때는",
        "> 이 표 대신 편익 갈래 표만 유효하다.",
        "",
    ]
    return lines
