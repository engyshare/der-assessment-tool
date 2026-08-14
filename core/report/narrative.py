"""`CaseReport` 를 **사람이 읽는 한 장**으로 그린다 — FR-1001 · FR-1002 · UI-7.

## 이 파일이 지키는 순서

`FR-1002-AC1` 은 *「리포트 첫 화면은 인자별 영향도 순위로 시작한다. 입력 순·분류
순 나열은 부록으로 보낸다」* 이고 `UI-7` 이 같은 것을 화면에 요구한다. 그래서
절의 순서 자체가 조항이다 — **가정 목록을 위로 올리면 그 순간 이 파일은 조항을
어긴다.** 순서를 바꾸려면 조항을 먼저 고쳐야 한다.

    ① 결론 한 줄            ← 검토자가 가장 먼저 묻는 것
    ② 결론을 뒤집는 인자     ← FR-1002-AC4 「최상단에 별도 강조」
    ③ 영향도 순위 전체       ← FR-1002-AC1·AC3 (부기를 같은 행에 둔다)
    ④ 변형 비교와 증분       ← FR-607-AC1 · UI-4
    ⑤ 산식 3중 표기          ← FR-1001-AC2·AC3·AC4
    ⑥ 부록: 전 가정 목록     ← FR-1002-AC6
    ⑦ 재현 정보              ← FR-1005-AC1

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

from core.report.case_report import (
    BASELINE_VARIANT,
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    AssumptionRow,
    CaseReport,
    InfluenceEntry,
)

#: 부록에 몇 건이 있든 전부 싣는다. 잘라 내면 「재현·검증용」이 성립하지 않는다.
_NO_VALUE = "—"


def _won(value: float) -> str:
    return f"{value:,.0f}원"


def _num(value: float) -> str:
    """인자 값 — **지수 표기를 내지 않는다.**

    `1.6e+06` 은 검토자가 읽는 수가 아니다. `MC-1` 이 재는 것이 「리포트만 보고
    설명할 수 있는가」이므로, 읽으려면 변환이 필요한 표기는 그 자체로 미달
    사유가 된다.
    """
    if abs(value) >= 1000.0:
        return f"{value:,.0f}"
    # 1 미만 값에 여섯 자리를 찍으면 **없는 정밀도를 주장하게 된다** —
    # `0.0344389` 는 이진탐색의 수렴 자리이지 그만큼 아는 값이 아니다.
    return f"{value:.4g}"


def _years(value: float) -> str:
    return "분석기간 내 미회수" if value == float("inf") else f"{value:.2f}년"


def _date(value: object) -> str:
    return str(value) if value else _NO_VALUE


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
    lines = ["## 1. 결론을 뒤집는 인자", ""]
    if not report.flipping:
        lines += [
            "검토한 변동 범위 안에서 결론을 뒤집는 인자는 **없다.** 아래 3절의",
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
        margin = f"{entry.margin_pct:.1f}%" if entry.margin_pct is not None else _NO_VALUE
        threshold = (
            _num(entry.threshold) if entry.threshold is not None else _NO_VALUE
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


def _influence_row(entry: InfluenceEntry) -> str:
    flips = "**뒤집힘**" if entry.flips_conclusion else "—"
    if entry.unread_by_pipeline:
        flips = "⚠ 미반영 의심"
    return (
        f"| {entry.variable} | {entry.ledger_key or '—'} | {_num(entry.used_value)} | "
        f"{entry.value_unit or _NO_VALUE} | {_num(entry.low)}~{_num(entry.high)} | "
        f"{_won(entry.delta_won)} | {flips} | {entry.confidence} | "
        f"{entry.source} | {entry.base_year or _NO_VALUE} | "
        f"{_date(entry.verified_at)} |"
    )


def _influence_section(report: CaseReport) -> list[str]:
    """`FR-1002-AC1`·`AC2`·`AC3` — 순위·산출 방식·인자별 부기."""
    lines = [
        "## 2. 영향도 순위",
        "",
        "각 인자를 **대장이 밝힌 변동 범위**에서 혼자 움직여 파이프라인을 다시",
        "돌리고, 결론이 움직인 폭으로 순위를 매겼다 (`FR-1002-AC2` 1변수 스윕).",
        "",
        "| 인자 | 대장 키 | 사용값 | 단위 | 변동 범위 | 결론 변동폭 | 전환 "
        "| 신뢰도 | 출처 | 기준연도 | 최종확인 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [_influence_row(entry) for entry in report.influences]
    lines.append("")
    if report.unread_variables:
        names = " · ".join(e.variable for e in report.unread_variables)
        lines += [
            f"> ⚠ **{names} 의 변동폭이 정확히 0원이다.** 범위를 끝에서 끝까지",
            "> 흔들어도 결론이 한 원도 움직이지 않는 일은 경제적으로 일어나지",
            "> 않는다 — **계산이 이 인자를 읽지 않고 있을 가능성이 크다.**",
            "> 「영향이 없다」로 읽지 말 것. 확인 전까지 이 인자에 대한 판단은",
            "> 이 리포트로 내릴 수 없다.",
            "",
        ]
    return lines


def _variant_section(report: CaseReport) -> list[str]:
    """`FR-607-AC1`(무지원 기준선 자동 포함) · `UI-4`(증분 병기)."""
    lines = [
        "## 3. 지원 유무 비교",
        "",
        "| 변형 | 초기지출 | 순현재가치 | 할인 회수기간 | 무지원 대비 증분 |",
        "|---|---|---|---|---|",
    ]
    base_npv = report.baseline_metrics[CONCLUSION_METRIC]
    for tag, label in report.variant_labels:
        metrics = report.variants[tag]
        delta = (
            _NO_VALUE
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


def _formula_section(report: CaseReport) -> list[str]:
    """`FR-1001-AC2`·`AC3` — 산식을 자연어·수식·대입값 셋으로."""
    lines = [
        "## 4. 이 값이 어떻게 나왔는가",
        "",
        "각 산식을 **자연어 · 수식 · 대입값** 셋으로 적는다. 대입값의 각 인자는",
        "2절 표에서 출처·기준연도·신뢰도를 확인할 수 있다 (`FR-1001-AC4`).",
        "",
    ]
    for formula in report.formulas:
        lines += [
            f"**{formula.label}**",
            "",
            f"- 자연어 — {formula.natural}",
            f"- 수식 — `{formula.expression}`",
            f"- 대입값 — {formula.substituted}",
            "",
        ]
    lines += [
        "> **회수기간과 순현재가치는 같은 판정의 두 얼굴이다.** 분석기간 말",
        "> 누적 할인 현금흐름이 초기투자를 넘으면 순현재가치가 0 이상이고, 그것이",
        "> 곧 「분석기간 안에 회수된다」이다. 위 1·2절이 순현재가치(원)로 전환을",
        "> 재는 이유는 회수기간에는 **뒤집힐 부호가 없기 때문**이다 — 회수하지",
        "> 못하면 값이 존재하지 않아 「얼마나 못 미쳤는지」를 말할 수 없다.",
        "",
    ]
    return lines


def _appendix_row(row: AssumptionRow) -> str:
    return (
        f"| {row.key} | {row.value} | {row.value_unit or _NO_VALUE} | "
        f"{row.confidence} | {row.source} | {row.base_year or _NO_VALUE} | "
        f"{_date(row.verified_at)} |"
    )


def _appendix_section(report: CaseReport) -> list[str]:
    """`FR-1002-AC6` — 전 가정 목록. **영향도 순위와 별개로** 부록에 둔다."""
    lines = [
        "## 부록. 전 가정 목록",
        "",
        f"재현·검증용이다. 전제 대장 `{report.assumption_set_name}` "
        f"판 {report.assumption_set_version} 의 **전 항목**이며, 위 순위에",
        "오르지 않은 것도 포함한다.",
        "",
        "| 대장 키 | 값 | 단위 | 신뢰도 | 출처 | 기준연도 | 최종확인 |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [_appendix_row(row) for row in report.assumptions]
    lines.append("")
    return lines


def render_markdown(report: CaseReport) -> str:
    """검토자에게 그대로 건네는 한 장. 절의 순서는 조항이다(머리말 참조)."""
    lines = [
        f"# 경제성 평가 리포트 — {report.scenario_name}",
        "",
        _conclusion_line(report),
        "",
        f"- 전제 대장: `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version} · 가격 기준 {report.price_basis}",
        f"- 분석기간 {report.basis.horizon_years}년 · "
        f"할인율 {report.basis.discount_rate:.1%}",
        f"- 시나리오 파일: `{report.scenario_path}` — 이 파일에서 읽은 것은",
        f"  **보조율 {report.subsidy_rate:.0%} 하나**이며 나머지 값은 전부 위",
        "  전제 대장의 `base` 수준이다.",
        "",
        "---",
        "",
    ]
    lines += _flip_section(report)
    lines += ["---", ""]
    lines += _influence_section(report)
    lines += ["---", ""]
    lines += _variant_section(report)
    lines += ["---", ""]
    lines += _formula_section(report)
    lines += ["---", ""]
    lines += _appendix_section(report)
    lines += [
        "---",
        "",
        "## 재현 정보",
        "",
        f"- 실행 매니페스트 해시 `{report.manifest_hash}` — 같은 해시는 같은",
        "  입력을 뜻한다 (`FR-1005-AC1`).",
        "- 이 리포트의 수치는 위 전제 대장의 값으로 계산된 것이며, 신뢰도 `가정`",
        "  항목이 포함되어 있다. 대장이 갱신되면 수치가 바뀐다.",
        "",
    ]
    return "\n".join(lines)
