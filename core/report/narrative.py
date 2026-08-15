"""`CaseReport` 를 **심의보고서**로 그린다 — 양식은 `docs/report-form-심의보고서.md`.

## 이 파일이 지키는 것은 **양식**이다

양식은 우수사례 셋을 대조해 뽑았다(NSPM for DERs · 예비타당성조사 표준지침 ·
분산에너지 특화지역 가이드라인). 셋이 공통으로 요구하는 것이 절의 순서로 서 있다 —
**관점과 전제를 결과보다 먼저**, **민감도를 본문에**, **하지 못한 것을 적기**,
**본문은 짧게 근거는 붙임으로**.

    【본문 4~5쪽】
    1. 요약                  ← 심의위원이 이 절만 읽고도 뼈대를 잡는다
    2. 평가 개요             ← 대상 · 사업 조건 · 전제(할인율·분석기간)
    3. 평가 방법             ← 계산 절차 · 규약 · 관점 · 하지 않은 것
    4. 평가 결과             ← 지표 · 지원 유무 비교 · 자원별 수지
    5. 결론을 좌우하는 요인   ← 5.1 불확실 인자 / 5.2 정책 설정값 (갈라 싣는다)
    6. 종합 판단 및 건의
    【붙임】
    1. 전제 대장 전건 (신뢰도별)   2. 영향도 산출 상세 (판단용/감사용)
    3. 산식 3중 표기               4. 평가 대상 제원 상세
    5. 재현 절차                   6. 용어 설명

**`FR-1002-AC1` 과 어긋나지 않는다.** 그 조항이 부록으로 보내라는 것은
*「입력 순·분류 순 나열」* 이고 그것은 붙임 1 에 있다. 본문 5절이 영향도를
싣는다. 2·3 절은 나열이 아니라 **대상과 방법의 규정**이며, 무엇을 평가했는지
모르면 영향도 순위를 읽을 수 없다.

⚠ **절의 순서와 본문/붙임의 경계를 여기서만 고치지 말 것.** 양식 문서와 함께
움직여야 「양식대로 썼다」가 성립한다.

## ★ 왜 마크다운인가

`MC-1` 은 *「리포트만 준다 — 구두 설명·부연 금지」* 다. 즉 산출물이 **혼자
서야** 하고, 검토자가 열어 보는 데 도구가 필요하면 그 순간 「설명을 보탠」
것이 된다. 마크다운은 편집기·브라우저·인쇄 어디서도 같은 것을 보여 주고
**형상관리에 그대로 들어간다**(`MC-1` 의 `evidence` 칸이 파일 경로를 요구한다).

PDF(`FR-1003-AC2`)는 같은 `CaseReport` 를 받는 **다른 렌더러**의 몫이다. 여기서
PDF 까지 그리면 서식 코드가 조립기와 섞이고, 그때 「무엇을 담는가」와 「어떻게
보이는가」가 한 파일에서 함께 바뀐다.
"""
from __future__ import annotations

from core.report._format import NO_VALUE, _num, _unit_head, _won, _years
from core.report.appendix_sections import (
    appendix_section,
    formula_section,
    glossary_section,
    influence_section,
    reproduction_section,
)
from core.report.case_report import (
    BASELINE_VARIANT,
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    CaseReport,
)
from core.report.method_sections import (
    cost_benefit_section,
    method_section,
    model_section,
    resource_detail_section,
)


def _conclusion_line(report: CaseReport) -> str:
    payback = report.metrics[HEADLINE_METRIC]
    if report.recovers_within_horizon:
        return (
            f"**분석기간 {report.basis.horizon_years}년 안에 회수된다 — "
            f"할인 회수기간 {_years(payback)}.**"
        )
    return (
        f"**분석기간 {report.basis.horizon_years}년 안에 회수되지 않는다 — "
        f"순현재가치 {_won(report.metrics[CONCLUSION_METRIC])}.**"
    )


def _flip_section(report: CaseReport) -> list[str]:
    """`FR-1002-AC4` — 결론이 뒤집히는 인자를 **최상단에 별도로**."""
    lines = ["### 5.1 불확실 인자 — 값이 틀릴 수 있는 것", ""]
    if not report.flipping:
        lines += [
            "검토한 변동 범위 안에서 결론을 뒤집는 인자는 **없다.** 붙임 2 의",
            "범위(대장 `sensitivity` 의 low~high)를 벗어나면 달라질 수 있다.",
            "",
        ]
        return lines
    lines += [
        "아래 인자는 **대장이 스스로 밝힌 변동 범위 안에서** 결론을 뒤집는다.",
        "정책 판단에서 가장 중요한 정보이므로 맨 앞에 둔다.",
        "",
        "| 인자 | 사용값 | 결론이 뒤집히는 값 | 여유 | 신뢰도 |",
        "|---|---|---|---|---|",
    ]
    for entry in report.flipping:
        margin = f"{entry.margin_pct:.1f}%" if entry.margin_pct is not None else NO_VALUE
        threshold = (
            _num(entry.threshold) if entry.threshold is not None else NO_VALUE
        )
        lines.append(
            f"| {entry.variable} | {_num(entry.used_value)} | {threshold} | "
            f"{margin} | {entry.confidence} |"
        )
    lines.append("")
    if report.provisional_warning:
        names = " · ".join(e.variable for e in report.provisional_warning)
        lines += [
            f"> ⚠ **이 결과는 잠정적이다.** 위 인자 중 **{names}** 는 신뢰도가",
            "> `가정` 이다 — 회신·실측으로 값이 바뀌면 결론 자체가 바뀐다",
            "> (`FR-1002-AC5`). 「영향도가 낮은 가정」과 달리 이것은 결과를",
            "> 좌우하므로, 확보 우선순위가 여기서 정해진다.",
            "",
        ]
    return lines




def _policy_section(report: CaseReport) -> list[str]:
    """5절 — **평가자가 정하는 값**의 감도 (R33 검토 지적 4).

    ## 왜 순위표에서 뺐는가

    첫 판은 할인율을 영향도 1위로 실었다. 지적이 정확했다 — *「대부분의 분석은
    할인율을 통제할 수 있는 값으로 보지 않는다. 고정적으로 적용하는 값을 주요
    요인으로 뽑는 것이 의미가 있는가」*.

    영향도 순위가 답하려는 물음은 **「어느 자료를 먼저 확보할 것인가」**다.
    할인율은 확보할 자료가 아니라 정해 놓고 쓰는 규칙이다. 한 표에 섞으면
    1위가 「확보 대상」이 아니게 되고, 표를 읽은 사람은 우선순위를 잘못 잡는다.

    **그렇다고 버리지 않는다.** 할인율을 몇으로 정하느냐가 결론을 바꾸는 것은
    사실이고, 그것은 *자료 문제가 아니라 정책 선택*이다. 그래서 여기서 「이
    선택이 결론을 얼마나 좌우하는가」로 따로 적는다.
    """
    entries = report.policy_influences
    lines = [
        "### 5.2 정책 설정값 — 평가자가 정하는 것",
        "",
        "아래는 **모르는 값이 아니라 정해 놓고 쓰는 값**이다. 5.1 과 성격이",
        "다르므로 갈라 싣는다 — 5.1 은 「무엇을 더 알아봐야 하는가」이고, 여기는",
        "「우리가 어떤 규칙을 골랐고 그 선택이 결론을 얼마나 좌우하는가」다.",
        "",
        "| 설정값 | 적용값 | 검토 범위 | 결론이 바뀌는 값 | 결론 변동폭 |",
        "|---|---|---|---|---|",
    ]
    for entry in entries:
        threshold = (
            _num(entry.threshold) if entry.threshold is not None else "범위 내 없음"
        )
        lines.append(
            f"| {entry.variable} | {_num(entry.used_value)} | "
            f"{_num(entry.low)}~{_num(entry.high)} | {threshold} | "
            f"{_won(entry.delta_won)} |"
        )
    lines += [
        "",
        "> **읽는 법.** 「결론이 바뀌는 값」은 *그 설정값을 그렇게 정했다면* 결론이",
        "> 달라졌다는 뜻이지, 그 값이 틀렸다는 뜻이 아니다. 할인율은 사업 성격과",
        "> 자금 조달 조건에 따라 정하는 것이므로, **바꾸려면 그 근거를 먼저**",
        "> 정해야 한다 — 결론을 유리하게 만들려고 고르는 순간 평가가 아니게 된다.",
        "",
    ]
    return lines


def _variant_section(report: CaseReport) -> list[str]:
    """`FR-607-AC1`(무지원 기준선 자동 포함) · `UI-4`(증분 병기)."""
    lines = [
        "### 4.2 지원 유무 비교",
        "",
        "| 변형 | 초기지출 | 순현재가치 | 할인 회수기간 | 무지원 대비 증분 |",
        "|---|---|---|---|---|",
    ]
    base_npv = report.baseline_metrics[CONCLUSION_METRIC]
    for tag, label in report.variant_labels:
        metrics = report.variants[tag]
        delta = (
            NO_VALUE
            if tag == BASELINE_VARIANT
            else _won(metrics[CONCLUSION_METRIC] - base_npv)
        )
        lines.append(
            f"| {label} | {_won(metrics['initial_outlay_won'])} | "
            f"{_won(metrics[CONCLUSION_METRIC])} | "
            f"{_years(metrics[HEADLINE_METRIC])} | {delta} |"
        )
    lines += [
        "",
        f"이 시나리오의 지원 조건은 **보조율 {report.subsidy_rate:.0%}** 하나다.",
        "",
    ]
    return lines



def _summary_section(report: CaseReport) -> list[str]:
    """【1】 요약 — **심의위원이 이 절만 읽고도 판단의 뼈대를 잡는다.**

    양식(`docs/report-form-심의보고서.md`) 이 요구하는 셋을 담는다: 결론 한 문장 ·
    결론을 좌우하는 요인 · 읽을 때의 유의사항. 우수사례 셋 중 분산특구
    가이드라인이 요구하는 형태이며(심의위원은 짧은 본문으로 판단하고 근거는
    붙임에서 확인한다), 그 앞의 둘도 「관점과 전제를 결과보다 먼저」로 같은
    자리를 가리킨다.
    """
    basis = report.basis
    lines = ["## 1. 요약", "", _conclusion_line(report), ""]

    lines += ["### 결론을 좌우하는 요인", ""]
    if report.flipping:
        for entry in report.flipping:
            margin = (
                f"여유 {entry.margin_pct:.1f}%" if entry.margin_pct is not None else ""
            )
            lines.append(
                f"- **{entry.variable}** — 지금 {_num(entry.used_value)}"
                f"{(' ' + _unit_head(entry.value_unit)) if entry.value_unit else ''}"
                f" 이고, {_num(entry.threshold or 0)}"
                f"{(' ' + _unit_head(entry.value_unit)) if entry.value_unit else ''}"
                f" 이 되면 결론이 뒤집힌다 ({margin}). 신뢰도 **{entry.confidence}**"
            )
    else:
        lines.append(
            "- 검토한 변동 범위 안에서 결론을 뒤집는 불확실 인자는 **없다.**"
        )
    lines.append("")

    lines += ["### 이 결과를 읽을 때", ""]
    if report.provisional_warning:
        names = " · ".join(e.variable for e in report.provisional_warning)
        lines.append(
            f"- ⚠ **잠정 결과다.** 결론을 뒤집는 인자 중 **{names}** 의 신뢰도가 "
            "`가정` 이다 — 회신·실측으로 값이 바뀌면 결론 자체가 바뀐다."
        )
    short = [r for r in basis.resources if r.lifetime_years < basis.horizon_years]
    if short:
        lines.append(
            f"- ⚠ **교체비가 계상되지 않았다** (분석기간 {basis.horizon_years}년 "
            f"안에 수명이 끝나는 자원 {len(short)}건). 그만큼 이 결과는 **관대한 "
            "쪽**이다 — 3.4 참조."
        )
    if report.unread_variables:
        names = " · ".join(e.variable for e in report.unread_variables)
        lines.append(
            f"- ⚠ **{names} 이(가) 계산에 반영되지 않은 것으로 보인다** "
            "(영향폭 정확히 0원). 「영향이 없다」로 읽지 말 것 — 5.1 참조."
        )
    lines.append("")
    return lines


def _judgement_section(report: CaseReport) -> list[str]:
    """【6】 종합 판단 및 건의 — 양식이 요구하는 마지막 절.

    예비타당성조사 지침이 **종합평가·정책제언**으로 닫는 것과 같은 자리다.
    ⚠ **여기서 새 수를 만들지 않는다.** 앞 절이 낸 것만으로 판단을 적는다 —
    결론 절에만 있는 수는 어디서 왔는지 아무도 확인할 수 없다.
    """
    basis = report.basis
    payback = report.metrics[HEADLINE_METRIC]
    lines = ["## 6. 종합 판단 및 건의", "", "### 6.1 판단", ""]
    if report.recovers_within_horizon:
        lines.append(
            f"- 현 전제에서 이 사업은 **분석기간 {basis.horizon_years}년 안에 "
            f"회수된다** (할인 회수기간 {_years(payback)})."
        )
    else:
        lines.append(
            f"- 현 전제에서 이 사업은 **분석기간 {basis.horizon_years}년 안에 "
            f"회수되지 않는다** (순현재가치 "
            f"{_won(report.metrics[CONCLUSION_METRIC])})."
        )
    if report.provisional_warning:
        lines.append(
            "- **신뢰 수준은 낮다.** 결론을 뒤집는 인자에 신뢰도 `가정` 항목이 "
            "있어, 자료가 확보되면 결론이 달라질 수 있다."
        )
    else:
        lines.append(
            "- 검토 범위 안에서 결론이 뒤집히지 않아 **판단의 여유가 있다.**"
        )
    lines += ["", "### 6.2 결론을 바꾸려면 무엇이 필요한가", ""]
    for entry in report.flipping:
        direction = "낮아지면" if (entry.threshold or 0) < entry.used_value else "높아지면"
        lines.append(
            f"- **{entry.variable}** 이(가) {_num(entry.threshold or 0)} 까지 "
            f"{direction} 결론이 바뀐다 — 지금 값에서 "
            f"{entry.margin_pct:.1f}% 거리다."
            if entry.margin_pct is not None
            else f"- **{entry.variable}** — 5.1 참조."
        )
    baseline_gap = (
        report.metrics[CONCLUSION_METRIC]
        - report.baseline_metrics[CONCLUSION_METRIC]
    )
    if baseline_gap:
        lines.append(
            f"- 현재 지원 조건(보조율 {report.subsidy_rate:.0%})이 순현재가치를 "
            f"{_won(baseline_gap)} 끌어올리고 있다 — 4.2 참조."
        )
    lines += ["", "### 6.3 건의", ""]
    asked = [e.ledger_key for e in report.flipping if e.ledger_key]
    if asked:
        lines.append(
            "- **자료 확보 우선순위**: " + " · ".join(f"`{k}`" for k in asked)
            + " — 결론을 뒤집는 인자이므로 다른 항목보다 먼저 확보한다."
        )
    if report.unread_variables or [
        r for r in basis.resources if r.lifetime_years < basis.horizon_years
    ]:
        lines.append(
            "- **미반영 항목을 먼저 닫을 것.** 3.4 의 항목들은 결론에 서로 다른 "
            "방향으로 작용하므로, 닫기 전의 수치는 확정 판단의 근거로 쓰기 "
            "어렵다."
        )
    lines.append(
        "- 설비 구성·용량이 실제 사업과 다르면 2.1 을 바꿔 다시 산출한다 — "
        "이 결과는 그 구성에 한정된다."
    )
    lines.append("")
    return lines


def render_markdown(report: CaseReport) -> str:
    """양식(`docs/report-form-심의보고서.md`) 대로 **본문 + 붙임**을 그린다.

    ⚠ **절의 순서와 본문/붙임의 경계가 곧 양식이다.** 양식 문서를 고치지 않고
    여기만 고치면 「양식대로 썼다」가 성립하지 않는다.
    """
    lines = [
        f"# 경제성 평가 심의보고서 — {report.scenario_name}",
        "",
        "| | |",
        "|---|---|",
        f"| 평가 대상 | {report.scenario_name} |",
        f"| 전제 대장 | `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version} |",
        f"| 분석기간 · 할인율 | {report.basis.horizon_years}년 · "
        f"{report.basis.discount_rate:.1%} |",
        f"| 가격 기준 | {report.price_basis} |",
        f"| 실행 매니페스트 | `{report.manifest_hash[:16]}` |",
        "",
        "> 이 보고서는 `docs/report-form-심의보고서.md` 양식에 따라 **자동 생성**"
        "되었다.",
        "> 손으로 고치지 말 것 — 수치가 바뀌었으면 붙임 5 의 명령으로 다시 뽑는다.",
        "",
        "---",
        "",
    ]
    # ── 본문 ──────────────────────────────────────────────────────────
    lines += _summary_section(report)
    lines += ["---", ""]
    lines += model_section(report)
    lines += ["---", ""]
    lines += method_section(report)
    lines += ["---", ""]
    lines += _result_section(report)
    lines += ["---", ""]
    lines += _driver_section(report)
    lines += ["---", ""]
    lines += _judgement_section(report)
    # ── 붙임 ──────────────────────────────────────────────────────────
    lines += ["---", "", "# 붙임", ""]
    lines += appendix_section(report)
    lines += ["---", ""]
    lines += influence_section(report)
    lines += ["---", ""]
    lines += formula_section(report)
    lines += ["---", ""]
    lines += resource_detail_section(report.basis)
    lines += ["---", ""]
    lines += reproduction_section(report)
    lines += ["---", ""]
    lines += glossary_section()
    return "\n".join(lines)


def _result_section(report: CaseReport) -> list[str]:
    """【4】 평가 결과 — 지표 · 지원 유무 비교 · 자원별 수지."""
    basis = report.basis
    lines = [
        "## 4. 평가 결과",
        "",
        "### 4.1 경제성 지표",
        "",
        "| 지표 | 값 |",
        "|---|---|",
        f"| 할인 회수기간 (주 지표) | **{_years(report.metrics[HEADLINE_METRIC])}** |",
        f"| 순현재가치 | **{_won(report.metrics[CONCLUSION_METRIC])}** |",
        f"| 초기지출 (지원 반영 후) | {_won(report.metrics['initial_outlay_won'])} |",
        f"| 1년차 편익 / 운영비 | {_won(basis.annual_benefit_won)} / "
        f"{_won(basis.annual_cost_won)} |",
        "",
    ]
    lines += _variant_section(report)
    lines += cost_benefit_section(basis)
    return lines


def _driver_section(report: CaseReport) -> list[str]:
    """【5】 결론을 좌우하는 요인 — **두 종류를 갈라 싣는다.**"""
    lines = ["## 5. 결론을 좌우하는 요인", ""]
    lines += _flip_section(report)
    lines += _policy_section(report)
    return lines
