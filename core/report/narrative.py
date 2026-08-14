"""`CaseReport` 를 **사람이 읽는 한 장**으로 그린다 — FR-1001 · FR-1002 · UI-7.

## 이 파일이 지키는 순서

`FR-1002-AC1` 은 *「리포트 첫 화면은 인자별 영향도 순위로 시작한다. 입력 순·분류
순 나열은 부록으로 보낸다」* 이고 `UI-7` 이 같은 것을 화면에 요구한다. 그래서
절의 순서 자체가 조항이다 — **가정 목록을 위로 올리면 그 순간 이 파일은 조항을
어긴다.** 순서를 바꾸려면 조항을 먼저 고쳐야 한다.

    결론 한 줄               ← 검토자가 가장 먼저 묻는 것
    0. 무엇을 평가했는가      ← R33 검토 지적 1 (`method_sections`)
    1. 어떻게 계산했는가      ← R33 검토 지적 3 (`method_sections`)
    2. 자원별 비용·편익       ← R33 검토 지적 2 (`method_sections`)
    3. 결론을 뒤집는 인자     ← FR-1002-AC4 「최상단에 별도 강조」
    4. 영향도 순위            ← FR-1002-AC1·AC3 (부기를 같은 행에 둔다)
    5. 정책 설정값 감도       ← R33 검토 지적 4 (할인율은 불확실성이 아니다)
    6. 지원 유무 비교         ← FR-607-AC1 · UI-4
    7. 산식 3중 표기          ← FR-1001-AC2·AC3·AC4
    부록 A. 전 가정 목록      ← FR-1002-AC6
    부록 B. 재현 절차         ← R33 검토 지적 5 · FR-1005-AC1

**0~2 절이 3 절보다 앞에 오는 것은 `FR-1002-AC1` 위반이 아니다.** 그 조항이
부록으로 보내라는 것은 *「입력 순·분류 순 나열」* 이고, 0~2 절은 나열이 아니라
**대상과 방법의 규정**이다 — 무엇을 평가했는지 모르면 영향도 순위를 읽을 수
없다. 부록으로 밀려난 것은 그대로 전 가정 목록(부록 A)이다.

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
from core.report.method_sections import (
    cost_benefit_section,
    method_section,
    model_section,
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
    lines = ["## 3. 결론을 뒤집는 인자", ""]
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
        "## 4. 영향도 순위",
        "",
        "각 인자를 **대장이 밝힌 변동 범위**에서 혼자 움직여 파이프라인을 다시",
        "돌리고, 결론이 움직인 폭으로 순위를 매겼다 (`FR-1002-AC2` 1변수 스윕).",
        "",
        "여기 있는 것은 **틀릴 수 있는 값**뿐이다 — 즉 이 표는 *「어느 자료를 먼저",
        "확보해야 하는가」* 에 답한다. 평가자가 정하는 값(할인율 등)은 불확실성이",
        "아니라 선택이므로 5절에서 따로 본다.",
        "",
        "| 인자 | 대장 키 | 사용값 | 단위 | 변동 범위 | 결론 변동폭 | 전환 "
        "| 신뢰도 | 출처 | 기준연도 | 최종확인 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [_influence_row(entry) for entry in report.uncertain_influences]
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
        "## 5. 정책 설정값이 결론에 미치는 영향",
        "",
        "아래는 **모르는 값이 아니라 정해 놓고 쓰는 값**이다. 4절의 순위와 성격이",
        "다르므로 갈라 싣는다 — 4절은 「무엇을 더 알아봐야 하는가」이고, 여기는",
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
        "## 6. 지원 유무 비교",
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
        "## 7. 이 값이 어떻게 나왔는가",
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
        "## 부록 A. 전 가정 목록",
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
    lines += model_section(report)
    lines += ["---", ""]
    lines += method_section(report)
    lines += ["---", ""]
    lines += cost_benefit_section(report.basis)
    lines += ["---", ""]
    lines += _flip_section(report)
    lines += ["---", ""]
    lines += _influence_section(report)
    lines += ["---", ""]
    lines += _policy_section(report)
    lines += ["---", ""]
    lines += _variant_section(report)
    lines += ["---", ""]
    lines += _formula_section(report)
    lines += ["---", ""]
    lines += _appendix_section(report)
    lines += ["---", ""]
    lines += _reproduction_section(report)
    return "\n".join(lines)


def _reproduction_section(report: CaseReport) -> list[str]:
    """부록 B — **다른 사람(또는 다른 에이전트)이 이 결과를 다시 낼 수 있는가**
    (R33 검토 지적 5).

    지적 원문은 *「타 에이전트가 보고서의 내용을 보고 분석결과를 재현할 수
    있도록 자세한 정보가 기재되어야 함」* 이었다. 첫 판에는 매니페스트 해시
    한 줄뿐이었는데, **해시는 같은지 다른지만 말하고 어떻게 만드는지는 말하지
    않는다** — 재현의 근거가 아니라 재현 뒤의 대조 수단이다.

    그래서 ⓐ 명령 ⓑ 입력의 좌표 ⓒ 계산이 서 있는 규약 ⓓ 대조할 해시를 함께
    적는다. 넷이 다 있어야 「해 보았더니 다른 수가 나왔다」가 **어디서** 갈렸는지
    말할 수 있다.
    """
    basis = report.basis
    return [
        "## 부록 B. 재현 절차",
        "",
        "### 같은 결과를 다시 내는 명령",
        "",
        "```bash",
        "PYTHONUTF8=1 python -m app.run.report_cli \\",
        f"    --scenario {report.scenario_name_slug} \\",
        "    --out <출력경로>",
        "```",
        "",
        "### 이 결과를 만든 입력",
        "",
        "| 입력 | 좌표 · 값 |",
        "|---|---|",
        f"| 시나리오 파일 | `{report.scenario_path}` (읽는 것은 `subsidy_rate` 하나) |",
        f"| 전제 대장 | `docs/assumptions.yaml` 판 **{report.assumption_set_version}** |",
        f"| 보조율 | {report.subsidy_rate:.0%} |",
        f"| 분석기간 | {basis.horizon_years}년 (`analysis.period_years`) |",
        f"| 할인율 | {basis.discount_rate:.4g} (모형 파라미터 — 대장 항목 아님) |",
        f"| 가격 기준 | {report.price_basis} |",
        f"| 초기투자 | {_won(basis.initial_investment_won)} (지원 반영 전 총사업비) |",
        f"| 1년차 편익 | {_won(basis.annual_benefit_won)} |",
        f"| 1년차 운영비 | {_won(basis.annual_cost_won)} |",
        "",
        "설비 제원은 0절 표가 전부이며 그 값의 소유자는",
        "`core/casegrid/e2e_runner.py` 의 모듈 상수다 — 대장이 아니다(설비 제원은",
        "금액이 아니기 때문이다). 단가·분석기간만 대장에서 온다.",
        "",
        "### 대조",
        "",
        f"- 실행 매니페스트 해시 **`{report.manifest_hash}`**",
        "- 위 입력이 전부 같으면 해시가 같고, 하나라도 다르면 달라진다",
        "  (`FR-1005-AC1`). **해시가 같은데 수치가 다르면 코드가 바뀐 것**이다.",
        "- 골든 회귀는 `fixtures/golden/` 이 따로 붙든다 — 그쪽 기준값은 대장",
        "  가정에 묶여 있어 **대장을 갱신하면 재산출이 필요하다.** 회귀 실패가",
        "  곧 결함은 아니다.",
        "",
        "### 이 수치의 유효기간",
        "",
        "부록 A 에 신뢰도 `가정` 항목이 포함되어 있다. **대장이 갱신되면 이",
        "리포트의 모든 수치가 바뀐다** — 리포트를 손으로 고치지 말고 위 명령을",
        "다시 돌려 새로 뽑을 것.",
        "",
    ]
