"""`CaseReport` 를 **심의보고서**로 그린다 — 양식은 `docs/report-form-심의보고서.md`.

## 이 파일이 지키는 것은 **양식**이다

양식은 우수사례 셋을 대조해 뽑았다(NSPM for DERs · 예비타당성조사 표준지침 ·
분산에너지 특화지역 가이드라인). 셋이 공통으로 요구하는 것이 절의 순서로 서 있다 —
**관점과 전제를 결과보다 먼저**, **민감도를 본문에**, **하지 못한 것을 적기**,
**본문은 짧게 근거는 붙임으로**.

    【본문 4~5쪽】
    1. 요약                  ← 심의위원이 이 절만 읽고도 뼈대를 잡는다
    2. 평가 개요             ← 대상 요약 · 구성 · 사업 조건 · 전제
    3. 평가 방법             ← 계산 절차 · 규약 · 관점 · 하지 않은 것
    4. 평가 결과             ← 지표 · 지원 유무 비교 · 자원별 수지 · 적정 용량
    5. 결론을 좌우하는 요인   ← 5.1 불확실 인자(단독 + 결합) / 5.2 정책 설정값
    6. 종합                  ← 판정 · 전환 조건 · 미해소 항목
    【붙임】
    1. 전제 대장 (주제별)   2. 영향도 산출 상세    3. 산식 3중 표기
    4. 제원 상세            5. 재현 절차          6. 디스패치 규칙
    7. 시간대별 운전        8. 미반영 항목        9. 용어 설명
    10. 적정 용량 검토 상세

## ★★ 이 보고서는 **정형 출력이다 — 해설을 싣지 않는다** (양식 0절 · 2026-08-15)

종전 이 파일은 표마다 인용문(`>`)으로 *「이 표는 단독 기여다」*·*「사업을
실제보다 어렵게 판단하게 된다」* 같은 문장을 붙였다. **그 문장을 쓴 것은
계산이 아니라 작성자이며**, 산출물 안에서는 둘이 구별되지 않는다 — 검토자는
계산 결과와 작성자의 해석을 같은 무게로 읽게 된다.

그래서 규칙을 뒤집었다. 하던 말을 **표의 칸으로** 옮긴다.

    「이 표는 단독 기여다」          → `산출` 열에 `1변수 스윕`
    「영향 없음으로 읽지 말 것」     → `산출` 열에 `파이프라인 미반영`
    「그만큼 결과에 관대하다」       → 붙임 8 `방향` 열에 `반영 시 결과 나빠짐`

**판정은 사람이 한다.** 이 파일이 하는 일은 판단에 필요한 값을 빠짐없이,
읽을 수 있는 자리에 놓는 것까지다.

⚠ **절의 순서와 본문/붙임의 경계를 여기서만 고치지 말 것.** 양식 문서와 함께
움직여야 「양식대로 썼다」가 성립한다.

## ★ 왜 마크다운인가

`MC-1` 은 *「리포트만 준다 — 구두 설명·부연 금지」* 다. 즉 산출물이 **혼자
서야** 하고, 검토자가 열어 보는 데 도구가 필요하면 그 순간 「설명을 보탠」
것이 된다. 마크다운은 편집기·브라우저·인쇄 어디서도 같은 것을 보여 주고
**형상관리에 그대로 들어간다**(`MC-1` 의 `evidence` 칸이 파일 경로를 요구한다).

PDF(`FR-1003-AC2`)는 같은 `CaseReport` 를 받는 **다른 렌더러**의 몫이다.
"""
from __future__ import annotations

from core.report._format import NO_VALUE, _num, _recovery, _unit_head, _won, _years
from core.report.appendix_sections import (
    appendix_section,
    formula_section,
    glossary_section,
    influence_section,
    reproduction_section,
)
from core.report.capacity import (
    capacity_appendix,
    capacity_section,
    capacity_summary,
)
from core.report.case_report import (
    BASELINE_VARIANT,
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    CaseReport,
)
from core.report.combined import MOVED_LEVELS, CombinedPoint, CoupledSweep
from core.report.dispatch_sections import (
    dispatch_profile_section,
    dispatch_rule_section,
)
from core.report.method_sections import (
    cost_benefit_section,
    method_section,
    model_section,
    resource_detail_section,
)
from core.report.unreflected import (
    build_unreflected,
    unreflected_direction_tally,
    unreflected_section,
)

#: 1변수 스윕으로 낸 줄임을 밝히는 표기 (`FR-1002-AC2`). 문장 대신 이 라벨이
#: 「단독 기여」를 말한다 — 위 머리말 참조.
SOLO_SWEEP = "1변수 스윕"
#: 묶음 전건을 함께 옮긴 줄.
COUPLED_SWEEP = "결합 스윕"


def _summary_section(report: CaseReport) -> list[str]:
    """【1】 요약 — 한 표.

    양식이 요구하는 여섯 행(결론 · 주 지표 · 결론 축 · 전환 인자 · 결합 전환
    조건 · 미반영 항목)을 **행 이름과 값으로만** 낸다.
    """
    metrics = report.metrics
    unreflected = build_unreflected(report)
    horizon = report.basis.horizon_years
    lines = [
        "## 1. 요약",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 결론 | 분석기간 {horizon}년 내 "
        f"**{_recovery(report.recovers_within_horizon)}** |",
        f"| 주 지표 · 할인 회수기간 | **{_years(metrics[HEADLINE_METRIC])}** |",
        f"| 결론 축 · 순현재가치 | **{_won(metrics[CONCLUSION_METRIC])}** |",
        f"| 결론 전환 인자 (단독) | {_flip_names(report)} |",
        f"| 결론 전환 조건 (결합) | {_summary_combined(report)} |",
        f"| 미반영 항목 | {unreflected_direction_tally(unreflected)} |",
        f"| 적정 용량 | {capacity_summary(report.capacity_review)} |",
        f"| 잠정성 | {_provisional_cell(report)} |",
        "",
    ]
    return lines


def _flip_names(report: CaseReport) -> str:
    """전환 인자 요약 칸 — 이름 · 임계값 · 신뢰도."""
    if not report.flipping:
        return f"없음 ({SOLO_SWEEP} 범위 내)"
    return " · ".join(
        f"`{entry.variable}` {_num(entry.threshold or 0)}"
        f"{_unit_suffix(entry.value_unit)} (신뢰도 {entry.confidence})"
        for entry in report.flipping
    )


def _unit_suffix(value_unit: str) -> str:
    head = _unit_head(value_unit)
    return f" {head}" if head else ""


def _summary_combined(report: CaseReport) -> str:
    """결합 전환 조건 칸.

    ⚠ **여기서 새 수를 만들지 않는다.** 5.1 의 결합 표가 이미 낸 행을 그대로
    가리킨다 — 요약이 스스로 계산하면 두 절의 수가 갈라지고, 그 어긋남은
    검토자가 두 표를 대조할 때에야 드러난다.
    """
    cells: list[str] = []
    for sweep in report.coupled_sweeps:
        for point in sweep.points:
            if point.is_combined and point.recovers:
                cells.append(
                    f"`{sweep.bundle}` 동반 `{point.level}` → "
                    f"{_won(point.npv)} (**회수**)"
                )
    return " · ".join(cells) if cells else "없음 (검토 범위 내)"


def _provisional_cell(report: CaseReport) -> str:
    if not report.provisional_warning:
        return "전환 인자에 신뢰도 `가정` 없음"
    names = " · ".join(f"`{e.variable}`" for e in report.provisional_warning)
    return f"전환 인자 중 신뢰도 `가정` — {names}"


def _flip_section(report: CaseReport) -> list[str]:
    """`FR-1002-AC4` — 결론이 뒤집히는 인자를 **최상단에 별도로**."""
    lines = ["### 5.1 불확실 인자 — 값이 틀릴 수 있는 것", ""]
    if not report.flipping:
        lines += [
            f"- 단독 전환 인자 — 없음 (산출: {SOLO_SWEEP} · 범위는 대장 "
            "`sensitivity` 의 low~high · 전건은 붙임 2)",
            "",
        ]
    else:
        lines += [
            "| 인자 | 사용값 | 단위 | 결론 전환값 | 여유 | 신뢰도 | 산출 |",
            "|---|---|---|---|---|---|---|",
        ]
        for entry in report.flipping:
            margin = (
                f"{entry.margin_pct:.1f}%"
                if entry.margin_pct is not None
                else NO_VALUE
            )
            threshold = (
                _num(entry.threshold) if entry.threshold is not None else NO_VALUE
            )
            lines.append(
                f"| `{entry.variable}` | {_num(entry.used_value)} | "
                f"{_unit_head(entry.value_unit) or NO_VALUE} | {threshold} | "
                f"{margin} | {entry.confidence} | {SOLO_SWEEP} |"
            )
        lines.append("")
    lines += _combined_lines(report)
    return lines


def _combined_lines(report: CaseReport) -> list[str]:
    """5.1 — **함께 움직이는 인자를 함께 흔든 표** (검토 「1차 의견」 1).

    묶음은 **여기서 정하지 않는다.** `core/casegrid/grid.py` 의 프리셋이 이미
    선언한 것을 읽어 온다 — 케이스 그리드는 결합으로 흔드는데 리포트만 독립인
    상태가 이 절이 생긴 이유이므로, 리포트가 묶음을 따로 적으면 같은 어긋남이
    반대 방향으로 다시 생긴다.
    """
    if not report.coupled_sweeps:
        return []
    # ⚠ **단위를 열 머리에 넣는다.** 이 표는 서로 다른 단위의 단가를 **나란히**
    # 싣는 첫 자리다(원/kW 와 원/kWh). 숫자만 두면 검토자는 1,600,000 과
    # 500,000 을 같은 자로 견주게 된다.
    units = {entry.variable: entry.value_unit for entry in report.influences}
    lines: list[str] = []
    for sweep in report.coupled_sweeps:
        heads = [
            f"`{name}` ({_unit_head(units[name])})"
            if units.get(name)
            else f"`{name}`"
            for name in sweep.variables
        ]
        lines += [
            f"#### 결합 시나리오 — `{sweep.bundle}`",
            "",
            f"- 묶음 구성 — {' · '.join(f'`{n}`' for n in sweep.variables)} "
            "(선언: `FR-801` 구성표 · 케이스 그리드)",
            f"- 이동 수준 — `{MOVED_LEVELS[0]}` · `{MOVED_LEVELS[1]}` "
            "(대장 `sensitivity` · 붙임 2 와 같은 범위)",
            f"- 산출 — {COUPLED_SWEEP}",
            "",
            "| 시나리오 | " + " | ".join(heads) + " | 순현재가치 | 기준 대비 | 회수 |",
            "|---|" + "---|" * (len(sweep.variables) + 3),
        ]
        for point in sweep.points:
            values = " | ".join(
                _num(point.values[name]) for name in sweep.variables
            )
            delta = NO_VALUE if point.is_base else _won(point.delta_won)
            lines.append(
                f"| {_point_label(point)} | {values} | {_won(point.npv)} | "
                f"{delta} | {_recovery(point.recovers)} |"
            )
        lines.append("")
        lines += _combined_note(sweep)
    return lines


def _point_label(point: CombinedPoint) -> str:
    if point.is_base:
        return "기준 (전건 `base`)"
    level = "하락" if point.level == "low" else "상승"
    if point.is_combined:
        return f"**동반 {level}** (전건 `{point.level}`)"
    return f"`{point.moved[0]}` 단독 {level}"


def _combined_note(sweep: CoupledSweep) -> list[str]:
    """표 아래 **잰 값**을 나열한다.

    상호작용 잔차가 0 인 것은 지금 구성에서 설비단가가 `t=0` CAPEX 로만 들어가
    서로 곱해지지 않기 때문이며 **모형의 일반 성질이 아니다.** 그 사실을
    문장으로 논하지 않고 **잔차 값 자체**를 싣는다 — 0 이 아니게 되는 날 값이
    스스로 달라진다.
    """
    residual = " · ".join(
        f"`{level}` {_won(value)}"
        for level, value in sorted(sweep.interaction_won.items())
    )
    lines = [
        f"- 상호작용 잔차 (결합에서 단독 합을 뺀 값) — {residual}",
        f"- 단독 합과 결합의 일치 — {'일치' if sweep.additive else '불일치'}",
    ]
    flips = sweep.flips_only_when_combined
    if flips:
        levels = " · ".join(f"`{point.level}`" for point in flips)
        lines.append(
            f"- 결합에서만 회수되는 수준 — {levels} (단독 이동으로는 전건 미회수)"
        )
    lines.append("")
    return lines


def _policy_section(report: CaseReport) -> list[str]:
    """5.2 — **평가자가 정하는 값**의 감도 (R33 검토 지적 4).

    영향도 순위가 답하려는 물음은 **「어느 자료를 먼저 확보할 것인가」**다.
    할인율은 확보할 자료가 아니라 정해 놓고 쓰는 규칙이므로 5.1 과 갈라 싣는다.
    """
    lines = [
        "### 5.2 정책 설정값 — 평가자가 정하는 것",
        "",
        "| 설정값 | 적용값 | 검토 범위 | 결론 전환값 | 결론 변동폭 | 산출 |",
        "|---|---|---|---|---|---|",
    ]
    for entry in report.policy_influences:
        threshold = (
            _num(entry.threshold) if entry.threshold is not None else "범위 내 없음"
        )
        lines.append(
            f"| `{entry.variable}` | {_num(entry.used_value)} | "
            f"{_num(entry.low)}~{_num(entry.high)} | {threshold} | "
            f"{_won(entry.delta_won)} | {SOLO_SWEEP} |"
        )
    lines += [
        "",
        "- 분류 — 대장 항목이 아닌 **모형 파라미터**다. 확보 대상(5.1)과 갈라 싣는다",
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
        f"- 지원 조건 — 보조율 {report.subsidy_rate:.0%} (융자·세액공제 없음)",
        "",
    ]
    return lines


def _judgement_section(report: CaseReport) -> list[str]:
    """【6】 종합 — 판정 · 전환 조건 · 미해소 항목.

    ⚠ **여기서 새 수를 만들지 않는다.** 앞 절이 낸 것만 모은다.
    ⚠ **정책 제언을 쓰지 않는다** (양식 0절). 무엇을 할 것인가는 심의·주관
    측의 판단이며, 여기서는 그 판단에 필요한 **목록**까지만 낸다.
    """
    basis = report.basis
    unreflected = build_unreflected(report)
    lines = [
        "## 6. 종합",
        "",
        "### 6.1 판정",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 분석기간 {basis.horizon_years}년 내 회수 | "
        f"**{_recovery(report.recovers_within_horizon)}** |",
        f"| 할인 회수기간 | {_years(report.metrics[HEADLINE_METRIC])} |",
        f"| 순현재가치 | {_won(report.metrics[CONCLUSION_METRIC])} |",
        f"| 전환 인자의 신뢰도 | {_provisional_cell(report)} |",
        f"| 지원이 순현재가치에 미친 폭 | "
        f"{_won(report.metrics[CONCLUSION_METRIC] - report.baseline_metrics[CONCLUSION_METRIC])}"
        f" (보조율 {report.subsidy_rate:.0%} · 4.2) |",
        "",
        "### 6.2 결론 전환 조건",
        "",
        "| 조건 | 값 | 산출 |",
        "|---|---|---|",
    ]
    for entry in report.flipping:
        direction = "이하" if (entry.threshold or 0) < entry.used_value else "이상"
        margin = (
            f"{entry.margin_pct:.1f}%" if entry.margin_pct is not None else NO_VALUE
        )
        lines.append(
            f"| `{entry.variable}` {_num(entry.threshold or 0)}"
            f"{_unit_suffix(entry.value_unit)} {direction} | "
            f"사용값 대비 {margin} | {SOLO_SWEEP} |"
        )
    for sweep in report.coupled_sweeps:
        for point in sweep.points:
            if point.is_combined and point.recovers:
                lines.append(
                    f"| `{sweep.bundle}` 전건 `{point.level}` 동반 | "
                    f"{_won(point.npv)} (회수) | {COUPLED_SWEEP} |"
                )
    lines += ["", "### 6.3 미해소 항목", "", "| 구분 | 항목 | 해소 조건 |", "|---|---|---|"]
    for entry in report.flipping:
        if entry.ledger_key:
            lines.append(
                f"| 자료 확보 | 전제 대장 `{entry.ledger_key}` | "
                f"신뢰도 `{entry.confidence}` → 실측·회신 |"
            )
    for item in unreflected:
        lines.append(f"| 미반영 | {item.label} | {item.resolves_when} |")
    lines += ["", "- 상세 — 자료 확보는 붙임 2, 미반영 항목은 붙임 8", ""]
    return lines


def render_markdown(report: CaseReport) -> str:
    """양식(`docs/report-form-심의보고서.md`) 대로 **본문 + 붙임**을 그린다.

    ⚠ **절의 순서와 본문/붙임의 경계가 곧 양식이다.** 양식 문서를 고치지 않고
    여기만 고치면 「양식대로 썼다」가 성립하지 않는다.
    """
    lines = [
        f"# 경제성 평가 심의보고서 — {report.scenario_name}",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 평가 대상 | {report.scenario_name} |",
        f"| 전제 대장 | `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version} |",
        f"| 분석기간 · 할인율 | {report.basis.horizon_years}년 · "
        f"{report.basis.discount_rate:.1%} |",
        f"| 가격 기준 | {report.price_basis} |",
        f"| 실행 매니페스트 | `{report.manifest_hash[:16]}` |",
        # ⚠ **작성일을 싣지 않는다** — 양식 【표제】가 정한 것이다. 생성 시점을
        # 찍으면 같은 입력이 같은 바이트를 내지 못해 `FR-1001-AC5`(비트 단위
        # 동일 재실행)가 깨진다. 「언제의 수인가」는 위 두 행이 답한다 —
        # 대장 판이 입력의 시점이고, 매니페스트 해시가 그 입력의 동일성이다.
        "| 작성 주체 | 경제성 평가 파이프라인 — "
        "`docs/report-form-심의보고서.md` 양식 · 자동 생성 "
        "(재생성 명령은 붙임 5) |",
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
    lines += dispatch_rule_section(report)
    lines += ["---", ""]
    lines += dispatch_profile_section(report)
    lines += ["---", ""]
    lines += unreflected_section(build_unreflected(report))
    lines += ["---", ""]
    lines += glossary_section()
    lines += ["---", ""]
    lines += capacity_appendix(report.capacity_review)
    return "\n".join(lines)


def _result_section(report: CaseReport) -> list[str]:
    """【4】 평가 결과 — 지표 · 지원 유무 비교 · 자원별 수지 · 적정 용량.

    ★ **4.4 는 검토 지적이 만든 절이다** (2026-08-15) — *「ESS, heatpump, p2h
    등은 적정 용량 검토가 선행되어야 함」*. 그때까지 용량은 러너의 모듈
    상수여서 리포트가 *「이 구성이 맞는가」* 를 묻지도 답하지도 못했다.
    """
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
        f"| 1년차 편익 | {_won(basis.annual_benefit_won)} |",
        f"| 1년차 운영비 | {_won(basis.annual_cost_won)} |",
        "",
    ]
    lines += _variant_section(report)
    lines += cost_benefit_section(basis)
    lines += capacity_section(report.capacity_review)
    return lines


def _driver_section(report: CaseReport) -> list[str]:
    """【5】 결론을 좌우하는 요인 — **두 종류를 갈라 싣는다.**"""
    lines = ["## 5. 결론을 좌우하는 요인", ""]
    lines += _flip_section(report)
    lines += _policy_section(report)
    return lines
