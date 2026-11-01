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

from core.report._format import NO_VALUE, _recovery, _won, _years
from core.report.appendix_sections import (
    appendix_section,
    formula_section,
    glossary_section,
    ledger_confidence_note,
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
    MAX_SUBSIDY_RATE,
    CaseReport,
)
from core.report.dispatch_sections import (
    dispatch_profile_section,
    dispatch_rule_section,
)
from core.report.ess_sizing_section import ess_daily_sizing_section
from core.report.method_sections import (
    PERSPECTIVE_QUALIFIER,
    cost_benefit_section,
    method_section,
    model_section,
    resource_detail_section,
)
from core.report.perspective_section import perspective_section
from core.report.policy_warnings import policy_warning_section
from core.report.shortfall import (
    SECTION_NUMBER as SHORTFALL_SECTION,
)
from core.report.shortfall import (
    build_shortfall,
    shortfall_section,
)
from core.report.sizing import self_sufficiency_section
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
#: 「찾았으나 없다」 — **검토 범위 안에서** 없다는 뜻이다. 요약 칸과 6.2 표가
#: 같은 문면을 써야 두 자리가 같은 사실을 말하는 것으로 읽힌다.
NONE_IN_RANGE = "없음 (검토 범위 내)"

#: 결론 축이 0 선에서 떨어진 **방향** 두 라벨 (5.1 · `_gap_lines`).
#:
#: 거리는 절대값 하나이고 방향은 회수 여부가 정한다. 라벨을 두 자리에서 각각
#: 적으면 「결손」과 「부족액」처럼 갈리고, 표를 훑는 눈은 그것을 서로 다른
#: 값으로 읽는다.
GAP_SHORTFALL = "결손"
GAP_MARGIN = "여유"

#: 5.1 의 전환 지원율 줄이 **「지원만으로는 안 된다」로 서 있을 때**의 머리.
#: 전환되는 갈래에서는 같은 줄이 `- 결론 전환 지원율 — **52.6%** …` 로 선다 —
#: `⚠` 한 글자가 **값 자리에 백분율이 서지 않는다**는 표시다. 검사가 이 이름으로
#: 줄을 집는다(`test_conclusion_gap.py`).
FULL_SUPPORT_LINE_HEAD = "- 결론 전환 지원율 — ⚠"


def _support_alone_note(report: CaseReport) -> str:
    """★ **「지원만으로는 안 된다」 — 네 자리가 함께 지는 한 문면** (판정 §2).

    1. 요약 · 5.1 · 6.2 · 붙임 3 이 같은 사실을 말해야 하고, 자리마다 다시
    지으면 네 문면이 갈린다 — 같은 물음에 자리가 늘수록 한 곳이 스스로 짓는
    위험이 커진다는 것은 이 저장소가 전환 지원율에서 이미 만난 형태다
    (`test_narrative.py::test_the_break_even_subsidy_rate_is_one_number_in_four_places`).

    판정 §2 가 요구한 **셋을 담는다**:

    1. 전액(100%) 지원해도 전환되지 않는다는 **사실**
    2. **얼마나 모자라는가** — 원 단위 (`residual_gap_at_full_support_won`)
    3. 그러므로 **지원율 외의 수단이 필요하다**

    ⚠ *무엇이* 필요한지는 여기서 말하지 않는다 — 그것은 적자 구조를 가르는
    **5.3** 이 답한다(판정 §3 ⓐ · R49/WP-3 이 세웠다). 여기가 지는 것은 그
    자리를 **가리키는 것까지**이며, 번호는 `shortfall.SECTION_NUMBER` 한 곳이
    소유한다 — 자리마다 적으면 절을 옮길 때 한 곳만 고쳐진다.
    """
    residual = report.residual_gap_at_full_support_won
    return (
        f"전액({MAX_SUBSIDY_RATE:.0%}) 지원해도 결론이 전환되지 않는다 — 남는 "
        f"{GAP_SHORTFALL} **{_won(abs(residual))}** · 전환 지원율 환산값 "
        f"{report.break_even_subsidy_rate:.1%}는 지원 상한 "
        f"{MAX_SUBSIDY_RATE:.0%}(사업비 전액)를 넘어 답으로 성립하지 않는다 · "
        # ★ **「무엇이 필요한가」의 자리를 가리킨다** (R49/WP-3 · 판정 §2·§3 ⓐ).
        # 여기서 처방을 적지 않는 이유는 종전 그대로다 — 적자 구조를 가르는
        # 것은 이 문면이 아니라 그 절이며, 두 곳이 같은 말을 하면 갈린다.
        f"전환에는 지원율 외의 수단이 필요하다 · 무엇이 얼마나 모자란지는 "
        f"{SHORTFALL_SECTION} 이 항목별로 가른다"
    )


def _support_answer(report: CaseReport) -> str:
    """전환 지원율 자리의 **값 머리** — 1. 요약 · 5.1 · 6.2 가 함께 쓴다.

    ## ★ 상한을 넘으면 **백분율이 이 자리에 서지 않는다** (R49/WP-2-fix)

    종전에는 굵은 `132.2%` 를 먼저 싣고 뒤에 단서를 붙였다. 그것은 판정 §2 가
    적은 *「그 숫자를 **답으로 제시하지 않는다**」* 가 아니라 **제시한 뒤에
    단서를 붙인** 형태다 — 그리고 이 저장소는 그 위험을 이미 한 번 겪었다:
    **발췌돼 인용되는 것은 행의 말이 아니라 그 굵은 수**이고(R43-G ·
    `_subsidy_flip_row` 독스트링), 심의회 자료에서 「지원율 132.2%」 한 칸만
    떼어 가면 **줄 수 없는 지원율이 달성 조건으로 나간다.**

    그래서 값 머리를 통째로 바꾼다 — 굵은 수가 서던 자리에 **진술**이 선다.
    환산값 자체는 그 진술 **안에서** 「답으로 성립하지 않는다」와 함께만
    나오고, 어디서 온 수인지는 붙임 3 이 대입값으로 진다(`MC-1` 의 첫 물음).

    ⚠ **전환되는 갈래는 종전 그대로 백분율이다.** 보조율이 오르거나 사업비가
    바뀌면 다시 그 갈래가 되고, 그때 132.2% 는 **정당한 답**이다.
    """
    if report.support_alone_can_flip:
        return f"**{report.break_even_subsidy_rate:.1%}**"
    return f"⚠ {_support_alone_note(report)}"


def _summary_section(report: CaseReport) -> list[str]:
    """【1】 요약 — 한 표. **행 이름과 값으로만** 낸다.

    ⚠ **행 목록을 여기 세지 않는다** — 양식 【1】이 그것의 소유자이고
    `test_form_conformance.py::test_summary_rows_match_the_form` 이 둘을
    대조한다. 종전 이 자리는 *「여섯 행」* 이라 적어 두었는데 실물은 이미
    여덟 행이었고, **그 낡은 사본이 두 라운드의 계획으로 따라 들어갔다**
    (「양식 6행 · 실물 8행이 어긋나 있다」 — 어긋난 것은 이 주석뿐이었다).
    """
    metrics = report.metrics
    unreflected = build_unreflected(report)
    horizon = report.basis.horizon_years
    lines = [
        "## 1. 요약",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        # ★ **관점 한정을 결론 옆에 붙인다 (R43-H · 문의사항 나-6).**
        #
        # 3.3 은 관점을 사업주로 두고 사회적 편익을 계상하지 않는다고 적는데
        # **요약에는 그 한정이 없었다.** 요약은 발췌돼 인용되는 절이므로,
        # 한정이 없으면 *「이 사업의 값어치가 마이너스」* 라는 진술이 되어
        # 나간다 — 지자체가 지원하는 근거는 정확히 그 「계상하지 않은」 쪽에
        # 있다. **문면은 3.3 이 소유한다**(`PERSPECTIVE_QUALIFIER`) — 여기서
        # 새로 지으면 두 곳에 적히고 한쪽만 고쳐진다.
        #
        # ★ **아래 「결론 축」 행에도 병기한다 (R43-L · WP-H 판정 요구 1).**
        # 실제로 발췌돼 인용되는 수는 「결론」 행의 말이 아니라 **그 아래 줄의
        # −숫자원**이다. 한정을 「결론」 행에만 붙이면 그 수만 떼어 간 인용은
        # 여전히 한정 없이 나간다 — 나-6 이 지적한 것이 정확히 그 형태다.
        # **행 이름은 건드리지 않는다**(양식 【1】이 소유자이며 위 독스트링의
        # 검사가 대조한다) — 값 칸에만 붙인다.
        f"| 결론 | 분석기간 {horizon}년 내 "
        f"**{_recovery(report.recovers_within_horizon)}** "
        f"({PERSPECTIVE_QUALIFIER}) |",
        f"| 주 지표 · 할인 회수기간 | **{_years(metrics[HEADLINE_METRIC])}** |",
        f"| 결론 축 · 순현재가치 | **{_won(metrics[CONCLUSION_METRIC])}** "
        f"({PERSPECTIVE_QUALIFIER}) |",
        f"| 결론 전환 인자 (단독) | {_flip_names(report)} |",
        # ★ 값을 여기서 계산하지 않는다 — `break_even_subsidy_rate` 한 함수를
        # 본문 5.1 · 붙임 3 과 **함께** 쓴다. 요약이 스스로 환산하면 같은
        # 물음에 세 자리가 다른 수를 낸다. 자리수도 5.1 과 같은 `:.1%` 다.
        # ★ **상한을 넘으면 값 자리에 백분율을 두지 않는다** (판정 §2 ·
        # R49/WP-2-fix). **행 이름은 건드리지 않는다**(양식 【1】이 소유자다) —
        # 바뀌는 것은 **값 칸이 무엇으로 시작하는가**이며, 그 갈래를
        # `_support_answer` 한 곳이 짓는다.
        #
        # ⚠ **`(현 지원율 …%)` 는 두 갈래 모두 남긴다.** 그것은 **실제로 적용된
        # 값**이지 달성 조건이 아니다 — 빼면 검토자가 *어느 지원 수준의 사업을
        # 보고 있는지* 알 수 없고, 두 시나리오의 요약 행이 서로 바뀌어도 매끈해진다.
        f"| 결론 전환 지원율 | {_support_answer(report)} "
        f"(현 지원율 {report.subsidy_rate:.1%} · 산식은 붙임 3) |",
        f"| 결론 전환 조건 (결합) | {_summary_combined(report)} |",
        f"| 미반영 항목 | {unreflected_direction_tally(unreflected)} |",
        f"| 적정 용량 | {capacity_summary(report.capacity_review)} |",
        f"| 잠정성 | {_provisional_cell(report)} |",
        "",
    ]
    return lines


def _flip_names(report: CaseReport) -> str:
    """전환 인자 요약 칸."""
    return f"없음 (결손의 구조는 {SHORTFALL_SECTION})"


def _summary_combined(report: CaseReport) -> str:
    """결합 전환 조건 칸."""
    return NONE_IN_RANGE


def _provisional_cell(report: CaseReport) -> str:
    """1. 요약 「잠정성」 · 6.1 「전환 인자의 신뢰도」 칸."""
    return ledger_confidence_note(report)


def _gap_lines(report: CaseReport) -> list[str]:
    """결론 축이 0 선에서 얼마나 떨어져 있는가 — **거리와 그 지원율 환산**.

    ⚠ **판정어를 쓰지 않는다.** 「부족하다」·「가깝다」는 작성자의 말이므로,
    거리의 방향은 `결손`·`여유` 라벨 한 칸이 지고 크기는 수가 진다.

    ★ **환산이 지원 상한을 넘으면 둘째 줄의 값 자리가 바뀐다** (판정 §2 ·
    R49/WP-2-fix) — 그 지원율은 넣어 돌릴 수 없는 값이므로(`DV-1`) 백분율을
    답으로 두지 않고, *「전액 지원해도 얼마가 남는가」* 를 원 단위로 대신
    싣는다. 갈래는 `_support_answer`, 문면은 `_support_alone_note` 한 곳이 짓는다.
    """
    # 환산을 **먼저** 부른다 — 총사업비가 0 이면 여기서 멈춘다(그 함수가
    # 사유를 말한다). 비율을 먼저 계산하면 같은 상태에서 `ZeroDivisionError`
    # 가 나고, 그 예외는 검토자에게 무엇이 잘못됐는지 말하지 않는다.
    # ⚠ 값은 `_support_answer` 가 다시 부른다 — 여기서는 **부르는 것 자체**가
    # 목적이므로 이름에 담지 않는다.
    _ = report.break_even_subsidy_rate
    gap = report.conclusion_gap_won
    total = report.total_project_cost_won
    direction = GAP_MARGIN if report.recovers_within_horizon else GAP_SHORTFALL
    lines = [
        # ⚠ **이 줄은 「거리」다 — 지원율이 아니다.** 총사업비 대비 결손의 크기를
        # 재며, 아래 전환 지원율과 수가 같아 보이는 것은 **무보조라 `s=0`**
        # 이기 때문이다(보조 80% 에서는 52.2% 와 132.2% 로 갈린다). 지원 상한을
        # 넘었다고 이 줄을 함께 걷어내면 **결손의 크기를 잴 자리가 사라진다.**
        f"- 결론까지 남은 거리 — **{_won(gap)}** ({direction} · 총사업비 "
        f"{_won(total)}의 {gap / total:.1%})",
        # ★ 값 머리는 `_support_answer` 가 짓는다 — 상한을 넘으면 이 줄은
        # **지원율 값 줄이 아니라 진술 줄**이 된다(위 독스트링).
        f"- 결론 전환 지원율 — {_support_answer(report)} (현 지원율 "
        f"{report.subsidy_rate:.1%} · 산출: t=0 일시 지원 환산 · 산식은 붙임 3)",
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
        # ★ **6.1 도 한정을 갖는다 (R43-H · 문의사항 나-6).** 요약과 같은
        # 이유이며 문면도 같은 곳에서 온다 — 「판정」 표에 관점이 없으면
        # 순현재가치 한 칸만 떼어 인용된다.
        f"| 평가 관점 | {PERSPECTIVE_QUALIFIER} |",
        "",
        "### 6.2 결론 전환 조건",
        "",
        "| 조건 | 값 | 산출 |",
        "|---|---|---|",
        # ★★ **지원 행이 맨 위다 (R43-G).** 아래 `_subsidy_flip_row()` 참조 —
        # 이 표에서 「없음」만 떼어 인용된 기록이 있다.
        _subsidy_flip_row(report),
        f"| 지원 외의 단일·결합 인자 | {NONE_IN_RANGE} | — |",
    ]

    lines += ["", "### 6.3 미해소 항목", "", "| 구분 | 항목 | 해소 조건 |", "|---|---|---|"]
    # ★★★ **미반영 항목의 해소 조건 «전문»을 여기 되풀이하지 않는다**
    # (R67/WP-N1d · 사용자 판정 P1 *「결론·주요 민감도·미반영 항목의 방향을
    # 본문에 남기고 상세 근거와 중복 내용을 붙임으로 재배치한다」*).
    #
    # 종전에는 `for item in unreflected:` 가 항목마다 한 줄씩
    # `| 미반영 | {label} | {resolves_when} |` 을 인쇄했다. 그 `resolves_when`
    # 은 **붙임 8 의 「해소 조건」 열과 글자 하나 다르지 않은 같은 문자열**이며
    # (`unreflected.unreflected_section()` 이 같은 항목을 인쇄한다), 그래서
    # 미반영 항목이 하나 늘 때마다 본문이 **두 줄**(3.4 표 + 여기) 자랐다.
    #
    # ⚠ **양식이 그 열을 붙임 8 에 배정한다** — `docs/report-form-심의보고서.md`
    # 두 곳이 그렇게 적는다:
    #
    #     :143  「본문에는 항목명 · 방향 · 판정 근거만 싣고
    #            크기·사유·**해소 조건**은 붙임 8 전문으로 내린다」
    #     :286  붙임 8 = 「미반영 항목 — 전문(항목·방향·크기·사유·**해소 조건**)
    #            … 본문 3.4 는 이름과 방향만」
    #
    # 그 절충안이 성립하는지를 기계가 그렇게 붙든다 —
    # `tests/report/test_unreflected.py::test_body_carries_only_the_name_and_direction`
    # 이 **본문 = 3.4 구간**만 잘라 `label`·`direction` 을 요구하고
    # `magnitude`·`resolves_when` 은 **붙임 8** 에서 요구한다.
    #
    # ⚠⚠ **같은 문서 :266 은 6.3 을 「미반영 항목의 해소 조건」으로도 적는다** —
    # 양식 안에서 어긋나는 자리다. 그래서 **행을 지우지 않았다** — 미반영 항목은
    # 6.3 에 그대로 서 있고(건수와 그 조건이 있는 자리), 항목별 전문은 붙임 8 이
    # 진다. 경위는 `.orch/R67/result_N1d.md` ② 가 갖는다.
    # ⛔ **항목의 «방향»을 지운 것이 아니다** — 3.4 표가 항목명·방향·판정을
    # 그대로 싣는다(`unreflected.unreflected_rows`).
    if unreflected:
        lines.append(
            f"| 미반영 | {len(unreflected)}건 (항목명 · 방향 · 판정은 3.4) | "
            "항목마다 다르다 — 붙임 8 「해소 조건」 열이 전문을 진다 |"
        )
    lines += ["", "- 상세 — 미반영 항목은 붙임 8", ""]
    return lines


def _subsidy_flip_row(report: CaseReport) -> str:
    """6.2 의 **지원 행** — 「전환 조건 없음」이 홀로 인용된 자리다 (R43-G).

    ## 무엇이 어긋나 있었나

    6.2 는 *「없음 (검토 범위 내)」* 한 줄이었다. 같은 자료의 1. 요약과 5.1 은
    **지원율 64.2% 면 전환된다**고 적는데, 종합만 떼어 인용하는 사람에게는
    그 표가 *「무엇을 해도 회수 못 한다」* 로 읽힌다 — 지방정부 담당자가 실제로
    그렇게 읽었다(`docs/evidence/문의사항-지방정부담당자-2026-08-29.md` 나-2).
    담당자가 심의회에서 답해야 하는 것이 정확히 그 지원율이다.

    ⚠ **여기서 새 수를 만들지 않는다.** 1. 요약·5.1·붙임 3 이 쓰는
    `break_even_subsidy_rate` **한 함수**를 그대로 부른다. 자리수도 같은
    `:.1%` 다 — 네 자리가 같은 물음에 다른 수를 내면 그 어긋남은 검토자가
    표를 대조할 때에야 드러난다.

    ## ★ 환산이 지원 상한을 넘으면 **답이 아니라는 것을 함께 싣는다** (판정 §2)

    같은 이유가 반대로 선다 — 줄 수 있는 지원율이 아닌 수를 「전환 조건」 칸에
    홀로 실으면, 그것만 떼어 인용한 검토자는 *「132% 를 지원하면 된다」* 로
    읽는다. 문면은 `_support_alone_note` 한 곳이 짓는다.
    """
    # ★ **상한을 넘은 자리에서 이 행이 가장 위험하다** (판정 §2 · R49/WP-2-fix).
    # 6.2 는 **떼어 인용되는 표**이므로 값 칸이 굵은 「132.2%」로 시작하면
    # 담당자가 심의회에서 **줄 수 없는 지원율**을 답으로 읽는다 — 위 독스트링이
    # 적은 나-2 오독의 **반대 방향**이다. 갈래는 `_support_answer` 가 짓는다.
    return (
        f"| 지원 (보조율) | {_support_answer(report)} "
        f"(현 지원율 {report.subsidy_rate:.1%}) | 붙임 3 · {SHORTFALL_SECTION} |"
    )


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
    # ★ **정책 가정 경고가 요약보다 위다** (`FR-404-AC1` — 「리포트 상단에」).
    # 결론 뒤에 두면 결론을 먼저 읽고 발췌해 가는 눈이 그것을 지나친다.
    # 경고가 없으면 빈 목록이므로 이 줄은 아무것도 더하지 않는다
    # (`policy_warning_section` 독스트링 — 「해당 없음」 줄을 세우지 않는다).
    lines += policy_warning_section(report.basis.resources)
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
    lines += self_sufficiency_section(report.self_sufficiency)
    # ★ ESS 역산은 **PV 역산과 같은 붙임, 같은 층**에 선다 (R64/WP-8b · 요구 4).
    # ⛔ 새 붙임을 만들지 않는다 — 붙임 10 이 이미 설계 변수마다 역산 결과를
    # 적는 자리이고 PV 가 거기 있다(`ess_daily_sizing_section` 독스트링).
    lines += ess_daily_sizing_section(report.ess_sizing)
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
    lines += perspective_section(report)
    return lines


def _driver_section(report: CaseReport) -> list[str]:
    """【5】 결론을 좌우하는 요인 — 결손을 가른다."""
    lines = ["## 5. 결론을 좌우하는 요인", ""]
    lines += _gap_lines(report)
    lines += shortfall_section(build_shortfall(report))
    return lines
