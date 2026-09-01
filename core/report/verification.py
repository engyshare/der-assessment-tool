"""검증 보고서 — 단계별 전제·계산·인계·수식을 손계산으로 따라올 수 있게
늘어놓는다 (사용자 판정 §2 · `docs/decisions-2026-09-02-R52.md`).

## 왜 심의용 리포트(`narrative.py`)와 별개인가

`MC-1` 심의용 리포트는 **결론을 읽는 자리**다. 이 렌더러가 답하는 물음은
다르다 — 사용자 문면 그대로: *「각 단계별로 전제한 수치, 이를 통해 계산된
수치, 그 다음 단계에 계산된 수치, 계산 수식 등을 구체적으로 검증 가능한
형태로 제공해야 함」*. 대조군(`Q-4`·`Q-5`)이 없는 지금, 이 문서가 그 자리를
대신한다.

## 왜 새로 계산하지 않는가

재료는 전부 `CaseReport`·`CaseBasis`·`CashflowSplit` 안에 있다 —
`basis.benefits`·`basis.costs`·`basis.one_off_flows` 는 이미 3중 표기 산식
문면(`formula` 필드)을 갖고, `report.formulas` 는 지표 산식을 3중 표기로
갖는다. 여기서 다시 계산하면 사본이 되고, 엔진이 바뀌어도 옛 표를 그럴듯하게
계속 인쇄한다(`CashflowSplit` 독스트링과 같은 이유로 여기서도 같은 판단을
따른다).

## 이 파일이 하는 유일한 계산 — **표시용 재집계**

단계 경계를 넘어 같은 수가 같은 수인지 눈으로 대조할 수 있게, `CashFlowRow`
의 1년차 값을 더해 `CaseBasis.annual_benefit_won`·`annual_cost_won` 과 나란히
싣는다(7단계). 이것도 **새 계산이 아니다** — 러너가 그 값을 만들 때 쓴 것과
같은 합을 표시 층에서 독립적으로 다시 읽었을 뿐이며
(`core/report/method_sections.py::_target_summary` 의 `total_capex = sum(...)`
가 이미 같은 방식을 쓰고 있다), 두 자리에서 읽어 대조하므로 검사 대상에서
정본을 빌려 오는 동어반복이 아니다(`status.md` 「검사가 자기 검사 대상에서
정본을 읽어 오면 공허해진다」).

⚠ **1년차 값을 20년으로 되짚지 않는다.** `CashflowSplit` 독스트링이 실측해
둔 대로 물가 상승 때문에 1년차 값을 등액으로 놓고 되짚으면 결손 합계와
어긋난다. 그래서 여기서 비교하는 것은 **1년차 값끼리**뿐이다.

## 해설을 붙이지 않는다 (판정 §6)

이 문서는 수치와 수식만 낸다. 「이 사업은 …이다」류 판정 문장은 싣지 않는다.
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from core.casegrid.models import (
    ONE_OFF_REPLACEMENT,
    CaseBasis,
    OneOffLine,
)
from core.contracts.schemas import CashFlowRow
from core.report._format import _date, _num, _won, _years
from core.report.case_report import (
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    MAX_SUBSIDY_RATE,
    CaseReport,
)


def _row_year1(row: CashFlowRow) -> int:
    return int(row.amounts.get(1, Decimal(0)))


def _year1_sum(rows: Iterable[CashFlowRow]) -> int:
    """행 목록의 1년차 금액 합 — 표시용 재집계다(위 머리말 참조)."""
    return sum(_row_year1(row) for row in rows)


def _match_note(label_a: str, value_a: int, label_b: str, value_b: int) -> str:
    if value_a == value_b:
        return f"✔ 일치 — {label_a} {_won(value_a)} = {label_b} {_won(value_b)}"
    return (
        f"⚠ 불일치 — {label_a} {_won(value_a)} ≠ {label_b} {_won(value_b)} "
        f"(차이 {_won(value_a - value_b)})"
    )


def _stage(
    number: int,
    title: str,
    *,
    a: list[str],
    b: list[str],
    c: list[str],
    d: list[str],
) -> list[str]:
    lines = [f"## {number}단계 — {title}", ""]
    lines += ["**ⓐ 전제한 수치**", "", *a, ""]
    lines += ["**ⓑ 계산된 수치**", "", *b, ""]
    lines += ["**ⓒ 다음 단계로 넘긴 값**", "", *c, ""]
    lines += ["**ⓓ 계산 수식**", "", *d, ""]
    return lines


def _stage1_ledger(report: CaseReport) -> list[str]:
    a = [
        f"외부 대장 파일 `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version}(`docs/assumptions.yaml`).",
        "",
        f"항목 {len(report.assumptions)}건 — 값·단위·기준연도·출처·신뢰도·"
        "최종확인일을 각 행이 함께 나른다.",
    ]
    b = [
        "| 키 | 값 | 단위 | 기준연도 | 출처 | 신뢰도 | 최종확인일 |",
        "|---|---|---|---|---|---|---|",
        *(
            f"| `{row.key}` | "
            f"{_num(row.value) if isinstance(row.value, int | float) else row.value} "
            f"| {row.value_unit or '—'} | {row.base_year or '—'} | "
            f"{row.source or '—'} | {row.confidence} | {_date(row.verified_at)} |"
            for row in report.assumptions
        ),
    ]
    influences = report.uncertain_influences
    c = [
        "이 표의 키가 2~9단계 전체에서 대입값으로 쓰인다. 아래는 파이프라인이 "
        "**실제로 읽어 결론에 반영한** 대장 키만 골라낸 것이다(5.1 영향도 분석이 "
        "대장과 결선된 것으로 확인한 인자 — `report.uncertain_influences`):",
        "",
        "| 변수 | 대장 키 | 사용값 | 단위 |",
        "|---|---|---|---|",
        *(
            f"| {entry.variable} | `{entry.ledger_key}` | {_num(entry.used_value)} "
            f"| {entry.value_unit or '—'} |"
            for entry in influences
        ),
    ]
    d = ["해당 없음 — 원시 입력이므로 이 단계에는 산식이 없다."]
    return _stage(1, "전제 대장에서 읽은 값", a=a, b=b, c=c, d=d)


def _stage2_resources(basis: CaseBasis) -> list[str]:
    total_capex = sum(r.capex_won for r in basis.resources)
    a = [
        "| 자원 | 용량 | 단가 문면 |",
        "|---|---|---|",
        *(f"| {r.kind} | {r.capacity} | {r.unit_capex} |" for r in basis.resources),
    ]
    b = [
        "| 자원 | 취득비 | 고정 O&M(연) |",
        "|---|---|---|",
        *(
            f"| {r.kind} | {_won(r.capex_won)} | {_won(r.fixed_om_won_per_year)} |"
            for r in basis.resources
        ),
        f"| **자원별 취득비 합** | **{_won(total_capex)}** | — |",
        f"| **초기투자(`initial_investment_won`)** | "
        f"**{_won(basis.initial_investment_won)}** | — |",
    ]
    c = [
        "자원 목록(용량·운전방식)은 3단계 디스패치가 그대로 받는다.",
        f"초기투자 {_won(basis.initial_investment_won)} 은 8단계 산식의 `I₀` 로 "
        "넘어간다 — 아래 8단계 ⓐ 와 대조.",
    ]
    d = [
        "자원별 취득비는 엔진이 이미 계산한 값이다(용량 x 단가 — 단가 문면은 "
        "위 ⓐ 표에 있다). 이 보고서는 다시 곱하지 않고 결과값을 그대로 싣는다.",
        f"자원별 취득비 합({_won(total_capex)})과 초기투자"
        f"({_won(basis.initial_investment_won)})이 다를 수 있다 — 반올림이 "
        "자원별로 먼저 일어나는가 합산 뒤에 일어나는가의 차이이며, 둘 다 "
        "부가세·지원 반영 전 금액이다.",
    ]
    return _stage(2, "자원 구성과 초기투자", a=a, b=b, c=c, d=d)


def _stage3_dispatch(report: CaseReport) -> list[str]:
    basis = report.basis
    a = [
        "2단계 자원 목록(용량·운전방식) + 엔진 규칙 순서:",
        "",
        "| 자원 | 운전방식 | 디스패치 규칙 | 우선순위 | 가격신호 필요 |",
        "|---|---|---|---|---|",
        *(
            f"| {n.resource_name} | {n.operating_mode} | "
            f"`{n.dispatch_rule.value}` | {n.dispatch_priority} | "
            f"{'예' if n.price_linked else '아니오'} |"
            for n in report.dispatch_notes
        ),
    ]
    hours = report.dispatch_hours
    total_export = sum(h.grid_export for h in hours)
    total_import = sum(h.grid_import for h in hours)
    b = [
        f"대표일 {len(hours)}스텝 운전 — 계통 송전 합계 {_num(total_export)}kWh · "
        f"계통 수전 합계 {_num(total_import)}kWh (붙임 7 이 스텝별 표를 싣는다).",
    ]
    c = [
        "이 운전 결과의 스텝별 자가소비·송전·수전 수량이 4단계 편익 계산과 "
        "5단계 운영비 계산의 수량 근거다.",
    ]
    d = [basis.dispatch_note or "—"]
    return _stage(3, "대표일 운전(디스패치)", a=a, b=b, c=c, d=d)


def _stage4_benefits(basis: CaseBasis) -> list[str]:
    a = ["1단계 단가 대장 + 3단계 운전결과(자가소비·송전 수량)."]
    b = [
        "| 편익 | 1년차 금액 | 만든 자원 |",
        "|---|---|---|",
        *(
            f"| {line.label} | {_won(line.annual_won)} | {line.resource_code or '—'} |"
            for line in basis.benefits
        ),
        f"| **1년차 편익 합계(`annual_benefit_won`)** | "
        f"**{_won(basis.annual_benefit_won)}** | — |",
    ]
    if basis.benefit_attributions:
        b += [
            "",
            "자원별 몫(`benefit_attributions`):",
            "",
            "| 편익 | 자원 | 몫 |",
            "|---|---|---|",
            *(
                f"| {attr.tag} | {attr.resource_name or '(귀속 없음)'} | "
                f"{_won(attr.annual_won)} |"
                for attr in basis.benefit_attributions
            ),
        ]
    c = [
        f"연 편익 합계 {_won(basis.annual_benefit_won)}(1년차)는 7단계 편익 "
        "현금흐름 행의 1년차 합계와 같아야 한다 — 아래 7단계 ⓓ 에서 대조한다.",
    ]
    d = [f"- {line.label}: {line.formula}" for line in basis.benefits] or ["없음"]
    return _stage(4, "편익 화폐화", a=a, b=b, c=c, d=d)


def _stage5_costs(basis: CaseBasis) -> list[str]:
    a = ["3단계 운전결과(계통 수전 수량) + 1단계 요금 단가."]
    subtotal = sum(line.annual_won for line in basis.costs)
    b = [
        "| 비용 | 1년차 금액 | 자원 |",
        "|---|---|---|",
        *(
            f"| {line.label} | {_won(line.annual_won)} | {line.resource_code or '—'} |"
            for line in basis.costs
        ),
        f"| **1년차 운영비 항목 합** | **{_won(subtotal)}** | — |",
        f"| **`CaseBasis.annual_cost_won`** | **{_won(basis.annual_cost_won)}** | "
        "6단계 생애주기 1년차분 포함(대개 0) |",
    ]
    c = [
        f"1년차 운영비 항목 합 {_won(subtotal)}은 7단계 운영비 현금흐름 행의 "
        "1년차 합계와 같아야 한다 — 아래 7단계 ⓓ 에서 대조한다.",
    ]
    d = [f"- {line.label}: {line.formula}" for line in basis.costs] or ["없음"]
    return _stage(5, "운영비", a=a, b=b, c=c, d=d)


def _stage6_lifecycle(basis: CaseBasis) -> list[str]:
    a = [
        f"자원별 수명(`ResourceLine.lifetime_years`) + 분석기간"
        f"({basis.horizon_years}년):",
        "",
        "| 자원 | 수명 |",
        "|---|---|",
        *(f"| {r.kind} | {r.lifetime_years}년 |" for r in basis.resources),
    ]
    if basis.one_off_flows:
        b = [
            "| 자원 | 종류 | 연차 | 금액 |",
            "|---|---|---|---|",
            *(
                f"| {f.resource_name} | "
                f"{'교체비' if f.kind == ONE_OFF_REPLACEMENT else '잔존가치'} | "
                f"{f.year}년차 | {_won(f.amount_won)} |"
                for f in basis.one_off_flows
            ),
        ]
    else:
        b = [
            "없음 — 수명이 분석기간보다 길지도 짧지도 않거나, 배선이 끊긴 "
            "구성이다.",
        ]
    c = [
        "이 표의 항목이 7단계 생애주기 현금흐름 행과 그 연차·금액이 같아야 "
        "한다.",
    ]
    d = [
        f"- {f.resource_name} {f.year}년차: {f.formula}"
        for f in basis.one_off_flows
    ] or ["해당 없음 — 일회성 흐름이 없다."]
    return _stage(6, "생애주기(교체·잔존)", a=a, b=b, c=c, d=d)


def _row_table(rows: tuple[CashFlowRow, ...]) -> list[str]:
    if not rows:
        return ["없음"]
    return [
        "| 행 | 1년차 금액 |",
        "|---|---|",
        *(f"| {row.label} | {_won(_row_year1(row))} |" for row in rows),
    ]


def _lifecycle_year_amounts(rows: tuple[CashFlowRow, ...]) -> dict[tuple[str | None, int], int]:
    """생애주기 행의 (태그, 발생 연차) → **그 연차** 금액.

    ⚠ 「1년차 금액」(`_row_year1`)으로는 안 된다 — `replacement_row`·
    `salvage_row`(`core/cba/proforma.py`)는 행마다 연차를 **정확히 하나만**
    채운다(교체·잔존은 그 정의상 한 해에만 일어난다,
    `core/casegrid/lifecycle.py::lifecycle_rows` 독스트링). 그 연차가 1년차가
    아닌 한 `_row_year1` 은 언제나 0원을 낸다 — 6단계와 대조하려면 행이 실제로
    가진 연차를 읽어야 한다.
    """
    out: dict[tuple[str | None, int], int] = {}
    for row in rows:
        for year, amount in row.amounts.items():
            out[(row.tag, year)] = int(amount)
    return out


def _lifecycle_row_table(
    basis: CaseBasis, year_amounts: dict[tuple[str | None, int], int],
) -> list[str]:
    """6단계 항목 순서 그대로, **각 항목이 실제로 발생한 연차의 금액**을 싣는다.

    (태그, 연차)로 짝짓는다 — `OneOffLine.tag` 와 `CashFlowRow.tag` 는
    `lifecycle_rows()` 가 같은 루프에서 함께 만든 것이라 같은 문자열이다.
    """
    if not basis.one_off_flows:
        return ["없음"]
    lines = ["| 행 | 발생 연차 | 그 연차 금액 |", "|---|---|---|"]
    for f in basis.one_off_flows:
        amount = year_amounts.get((f.tag, f.year))
        cell = _won(amount) if amount is not None else "⚠ 대응 행 없음"
        lines.append(f"| {f.label} | {f.year}년차 | {cell} |")
    return lines


def _lifecycle_match_note(item: OneOffLine, actual: int | None) -> str:
    if actual is None:
        return (
            f"⚠ 불일치 — 6단계 {item.resource_name} {item.year}년차 "
            f"{_won(item.amount_won)}에 대응하는 7단계 생애주기 행을 찾지 못했다"
        )
    return _match_note(
        f"6단계 {item.resource_name} {item.year}년차", item.amount_won,
        f"7단계 생애주기 행 {item.year}년차", actual,
    )


def _stage7_cashflow(report: CaseReport) -> list[str]:
    basis = report.basis
    cf = report.cashflows
    benefit_year1 = _year1_sum(cf.benefit)
    opex_year1 = _year1_sum(cf.operating_cost)
    lifecycle_year1 = _year1_sum(cf.lifecycle)
    lifecycle_year_amounts = _lifecycle_year_amounts(cf.lifecycle)
    a = [
        f"4단계 연 편익 {_won(basis.annual_benefit_won)} · 5단계 연 운영비 항목 · "
        f"6단계 생애주기 항목 {len(basis.one_off_flows)}건.",
    ]
    b = [
        "**편익 행**", "", *_row_table(cf.benefit), "",
        "**운영비 행**", "", *_row_table(cf.operating_cost), "",
        "**생애주기 행** — 「1년차 금액」이 아니라 실제 발생 연차의 금액이다",
        "", *_lifecycle_row_table(basis, lifecycle_year_amounts),
    ]
    c = [
        "이 행 전체(연도별)가 8단계 지표(할인 회수기간·순현재가치) 계산의 "
        "입력이다.",
    ]
    lifecycle_matches = [
        _lifecycle_match_note(f, lifecycle_year_amounts.get((f.tag, f.year)))
        for f in basis.one_off_flows
    ] or ["해당 없음 — 일회성 흐름이 없다."]
    d = [
        f"1년차 편익 합 = Σ 편익 행의 1년차 값 = {_won(benefit_year1)}",
        _match_note(
            "4단계 연 편익 합계", basis.annual_benefit_won,
            "7단계 편익 행 1년차 합", benefit_year1,
        ),
        "",
        "1년차 운영비 합(생애주기 포함) = Σ (운영비 행 + 생애주기 행)의 1년차 값 "
        f"= {_won(opex_year1 + lifecycle_year1)}",
        _match_note(
            "`CaseBasis.annual_cost_won`", basis.annual_cost_won,
            "7단계 (운영비+생애주기) 행 1년차 합", opex_year1 + lifecycle_year1,
        ),
        "",
        "6단계 항목별 발생 연차·금액이 7단계 생애주기 행의 같은 연차와 맞는가"
        "(항목별 대조):",
        *lifecycle_matches,
    ]
    return _stage(7, "현금흐름 행 — 이 보고서의 심장", a=a, b=b, c=c, d=d)


def _stage8_metrics(report: CaseReport) -> list[str]:
    basis = report.basis
    metrics = report.metrics
    a = [
        f"7단계 현금흐름 행 전체 + 2단계 초기투자 "
        f"{_won(basis.initial_investment_won)} + 1단계 할인율 "
        f"{basis.discount_rate:.1%} · 분석기간 {basis.horizon_years}년.",
    ]
    b = [
        "| 지표 | 값 |",
        "|---|---|",
        f"| 할인 회수기간(`{HEADLINE_METRIC}`) | {_years(metrics[HEADLINE_METRIC])} |",
        f"| 순현재가치(`{CONCLUSION_METRIC}`) | {_won(metrics[CONCLUSION_METRIC])} |",
        f"| 초기지출(지원 반영 후) | {_won(metrics['initial_outlay_won'])} |",
    ]
    c = [
        "이 지표(할인 회수기간·순현재가치)가 9단계 변형별 비교와 심의용 리포트 "
        "5.1 영향도 분석의 기준값이다.",
    ]
    d = []
    for f in report.formulas:
        d += [f"**{f.label}**", f"- {f.natural}", f"- `{f.expression}`", f"- {f.substituted}", ""]
    return _stage(8, "지표", a=a, b=b, c=c, d=d)


def _stage9_variants(report: CaseReport) -> list[str]:
    a = [
        f"8단계 지표(무지원 기준선) + 현재 지원율 {report.subsidy_rate:.0%} + "
        f"지원 상한 {MAX_SUBSIDY_RATE:.0%}(사업비 전액).",
    ]
    b = [
        "| 변형 | 할인 회수기간 | 순현재가치 |",
        "|---|---|---|",
        *(
            f"| {label} | {_years(report.variants[tag][HEADLINE_METRIC])} | "
            f"{_won(report.variants[tag][CONCLUSION_METRIC])} |"
            for tag, label in report.variant_labels
            if tag in report.variants
        ),
    ]
    c = [
        "이 보고서의 마지막 단계다 — 이후 단계로 넘기는 값이 없다. 결과는 "
        "심의용 리포트 본문 4.2 절의 지원 비교로 나간다.",
    ]
    d = [
        line
        for f in report.formulas
        if f.label in {"결론 전환 지원율", "전액 지원 시 잔여 결손"}
        for line in (
            f"**{f.label}**", f"- {f.natural}", f"- `{f.expression}`",
            f"- {f.substituted}", "",
        )
    ] or [
        "지원 상한 내에서 결론이 서므로 「전액 지원 시 잔여 결손」 산식은 이 "
        "실행에 없다.",
    ]
    return _stage(9, "변형(지원율)", a=a, b=b, c=c, d=d)


def render_verification_markdown(report: CaseReport) -> str:
    """검증 보고서 — 9단계 전제·계산·인계·수식 (판정 §2).

    ⚠ **해설을 붙이지 않는다** — 판정 문장은 이 문서의 대상이 아니다(판정
    §6). 절 구성은 이 함수의 단계 순서 자체가 양식이다.
    """
    lines = [
        f"# 계산 검증 보고서 — {report.scenario_name}",
        "",
        "> 대조군은 없다(`Q-4`·`Q-5` — 처음 하는 사업이라 계산 결과가 없다). "
        "이 문서는 각 단계의 전제값 → 계산값 → 다음 단계로 넘긴 값 → 계산 "
        "수식을 늘어놓아 손계산으로 따라올 수 있게 한다. 해설은 싣지 않는다.",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 평가 대상 | {report.scenario_name} |",
        f"| 전제 대장 | `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version} |",
        f"| 실행 매니페스트 | `{report.manifest_hash[:16]}` |",
        "",
        "---",
        "",
    ]
    lines += _stage1_ledger(report)
    lines += ["---", ""]
    lines += _stage2_resources(report.basis)
    lines += ["---", ""]
    lines += _stage3_dispatch(report)
    lines += ["---", ""]
    lines += _stage4_benefits(report.basis)
    lines += ["---", ""]
    lines += _stage5_costs(report.basis)
    lines += ["---", ""]
    lines += _stage6_lifecycle(report.basis)
    lines += ["---", ""]
    lines += _stage7_cashflow(report)
    lines += ["---", ""]
    lines += _stage8_metrics(report)
    lines += ["---", ""]
    lines += _stage9_variants(report)
    return "\n".join(lines)
