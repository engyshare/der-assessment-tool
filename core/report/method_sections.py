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
from core.report.unreflected import build_unreflected, unreflected_rows


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
        "| 프로포마 비용 행 | 고정 운영비 (변동 O&M · 교체 · 잔존가치 미포함 · "
        "3.4) |",
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
        *unreflected_rows(build_unreflected(report)),
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
        f"| {line.label} | {line.from_resource} | {_won(line.annual_won)} | "
        f"{share} |"
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
    lines = [
        "### 4.3 자원별 수지 — 얼마를 넣고 얼마를 버는가",
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
        "- 「단순 회수」 산식 — 초기투자 ÷ 연 순편익 (**할인하지 않음** · 결론에 "
        "쓰는 지표는 4.1 의 할인 회수기간)",
        "- 이 표의 성립 조건 — 편익이 자원에 1:1 로 귀속될 때 "
        "(이 구성: PV→잉여판매 · ESS→첨두절감)",
        "",
    ]
    return lines


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
            lines += ["**만드는 편익**", ""]
            lines += [
                f"- {line.label} — {_won(line.annual_won)}/년 · `{line.formula}`"
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
