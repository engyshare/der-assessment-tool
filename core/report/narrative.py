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
    UNREAD_BY_PIPELINE,
    UNREAD_NOTE,
    appendix_section,
    formula_section,
    glossary_section,
    influence_section,
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
    InfluenceEntry,
)
from core.report.combined import MOVED_LEVELS, CombinedPoint, CoupledSweep
from core.report.dispatch_sections import (
    dispatch_profile_section,
    dispatch_rule_section,
)
from core.report.method_sections import (
    PERSPECTIVE_QUALIFIER,
    cost_benefit_section,
    method_section,
    model_section,
    resource_detail_section,
)
from core.report.policy_warnings import policy_warning_section
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

    ⚠ *무엇이* 필요한지는 여기서 말하지 않는다. 그것은 적자 구조를 가르는
    절이 답하며(판정 §3 ⓐ) **아직 없다** — 없는 절 번호를 가리키면 검토자는
    있지도 않은 자리를 찾는다.
    """
    residual = report.residual_gap_at_full_support_won
    return (
        f"전액({MAX_SUBSIDY_RATE:.0%}) 지원해도 결론이 전환되지 않는다 — 남는 "
        f"{GAP_SHORTFALL} **{_won(abs(residual))}** · 전환 지원율 환산값 "
        f"{report.break_even_subsidy_rate:.1%}는 지원 상한 "
        f"{MAX_SUBSIDY_RATE:.0%}(사업비 전액)를 넘어 답으로 성립하지 않는다 · "
        "전환에는 지원율 외의 수단이 필요하다"
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
    return " · ".join(cells) if cells else NONE_IN_RANGE


def _provisional_cell(report: CaseReport) -> str:
    """1. 요약 「잠정성」 · 6.1 「전환 인자의 신뢰도」 칸.

    ## ★★ 「없음」이 **거꾸로 읽힌 자리다** (R43-G)

    종전 이 칸은 전환 인자가 0건일 때 *「전환 인자에 신뢰도 `가정` 없음」*
    한 줄이었다. 참이지만 **검토자가 그것을 「이 결론은 가정에 기대지
    않는다」로 읽었다** — 사유와 근거는 `ledger_confidence_note()` 에 있다.

    그래서 두 사실을 **함께** 싣는다. 앞은 *전환 인자가 없다*, 뒤는 *대장은
    대부분 `가정` 이다* 이며, 둘 다 관측이지 판정이 아니다.

    ⚠ **뒤 절을 여기서 짓지 않는다** — 붙임 1 을 세는 함수가 그것의 소유자다.
    """
    if not report.provisional_warning:
        return (
            "검토 범위 안에서 결론을 뒤집는 인자가 없다. "
            f"{ledger_confidence_note(report)}"
        )
    names = " · ".join(f"`{e.variable}`" for e in report.provisional_warning)
    return (
        f"전환 인자 중 신뢰도 `가정` — {names}. "
        f"{ledger_confidence_note(report)}"
    )


def _flip_section(report: CaseReport) -> list[str]:
    """`FR-1002-AC4` — 결론이 뒤집히는 인자를 **최상단에 별도로**.

    ## ★★ 전환 인자가 **0건일 때도 본문이 답한다** (2026-08-17)

    종전 이 절은 전환 인자가 없으면 *「단독 전환 인자 — 없음」* 한 줄이었다.
    그 한 줄은 참이지만 **검토자가 묻는 것에 답하지 않는다** — 「없음」은
    *「조금 모자란다」* 와 *「두 배 모자란다」* 를 같은 글자로 적는다. 5.1 이
    양식에서 지는 물음이 *「무엇이 얼마가 되면 뒤집히는가」* 이므로, 뒤집히는
    인자가 없을 때 그 물음은 **「그럼 얼마나 모자란가」** 로 남는다.

    그래서 셋을 싣는다 — 어느 것도 새 판정이 아니라 **환산과 관측**이다.

        결론까지 남은 거리      결론 축의 절대값 (총사업비 대비 비율 병기)
        결론 전환 지원율        그 거리를 t=0 지원으로 환산한 값 (붙임 3 이 산식)
        전환까지 남는 거리 표   인자를 검토 범위 끝까지 밀었을 때 남는 거리

    ⚠ **「없음」 줄을 지우지 않았다.** 거리가 실렸다고 전환 인자의 존부가
    말해지는 것은 아니며, 1절 요약이 그 사실을 같은 문면으로 이미 싣는다.
    """
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
    # ★ 거리는 **전환 표 다음**이다. `FR-1002-AC4` 가 「뒤집히는 인자를 최상단에
    # 별도 강조」라고 못 박으므로, 거리 두 줄을 위에 두면 강조가 한 칸 밀린다.
    # 읽는 순서도 그쪽이 맞다 — *「뒤집히는가」* 다음에 *「얼마나 모자란가」* 다.
    lines += _gap_lines(report)
    lines += _remaining_gap_table(report)
    lines += _combined_lines(report)
    return lines


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


def _remaining_gap_table(report: CaseReport) -> list[str]:
    """전환하지 못한 인자마다 **끝까지 밀었을 때 남는 거리**.

    붙임 2 의 `변동폭` 과 다른 것을 재는 표다. 변동폭은 *「이 인자가 결론 축을
    얼마나 흔드는가」* 이고 이 표는 *「그 흔들림을 최대한 좋은 쪽으로 써도
    0 선까지 얼마가 남는가」* 다. 둘은 같은 순위를 만들지 않는다 — 변동폭이
    커도 반대 끝에서 시작하면 남는 거리가 더 클 수 있다.

    ⚠ **전환 인자를 이 표에 넣지 않는다.** 그쪽은 남는 거리가 0 인 지점
    (임계값)이 존재하므로 위 표의 `결론 전환값`·`여유` 열이 답이고, 여기 함께
    실으면 같은 인자가 두 표에서 다른 물음에 답하는 것처럼 읽힌다.
    """
    rows = [
        entry for entry in report.uncertain_influences if not entry.flips_conclusion
    ]
    if not rows:
        return []
    lines = [
        "#### 전환까지 남는 거리 — 검토 범위 끝까지 밀었을 때",
        "",
        "| 인자 | 사용값 | 단위 | 전환 방향 끝 | 그 끝의 남은 거리 | 신뢰도 | 산출 |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in rows:
        end_value, end_npv = _flip_direction_end(
            entry, recovers=report.recovers_within_horizon
        )
        # ⚠ **두 끝의 결론 축이 같으면 「전환 방향」이 없다.** 그때 어느 끝을
        # 적어도 *그쪽으로 밀면 0 선에 가까워진다* 를 함의하게 되는데, 그 인자는
        # 어느 쪽으로도 결론을 움직이지 않는다 — 방향 칸은 `NO_VALUE` 로 두고
        # 사실은 `산출` 열의 미반영 라벨이 나른다. 거리는 어느 끝이든 같다.
        moved = NO_VALUE if entry.npv_low == entry.npv_high else _num(end_value)
        method = UNREAD_BY_PIPELINE if entry.unread_by_pipeline else SOLO_SWEEP
        lines.append(
            f"| `{entry.variable}` | {_num(entry.used_value)} | "
            f"{_unit_head(entry.value_unit) or NO_VALUE} | {moved} | "
            f"{_won(abs(end_npv))} | {entry.confidence} | {method} |"
        )
    lines.append("")
    # ★ **라벨의 뜻을 표 바로 아래에 단다 (R43-G).** 종전에는 붙임 2 각주와
    # 붙임 8 에만 있었고, *「표를 인용해 가는 사람은 거기까지 가지 않는다」*
    # 가 실제로 일어났다(문의사항 2026-08-29 나-3). 문면의 소유자는
    # `UNREAD_NOTE` 한 곳이다 — 여기서 다시 적지 않는다.
    if any(entry.unread_by_pipeline for entry in rows):
        lines += [UNREAD_NOTE, ""]
    return lines


def _flip_direction_end(
    entry: InfluenceEntry, *, recovers: bool
) -> tuple[float, float]:
    """**결론이 뒤집히는 쪽** 끝의 (인자 값, 결론 축).

    방향을 결론에서 읽는다 — 미회수면 결론 축이 큰 끝, 회수면 작은 끝이 0 선에
    가깝다. 인자마다 부호를 적어 두는 안은 버렸다: 그 표는 편익·비용 인자가
    늘 때마다 낡고, 낡은 부호는 **반대 끝을 「가까운 끝」으로 싣는다.**
    """
    ends = ((entry.low, entry.npv_low), (entry.high, entry.npv_high))
    return min(ends, key=lambda end: end[1]) if recovers else max(
        ends, key=lambda end: end[1]
    )


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
    # ★ **행이 없으면 「없음」을 적는다 (R34 · 실물을 눈으로 읽고 찾았다).**
    #
    # 전환 인자가 0건이 되자 이 표가 **머리 두 줄만 남은 빈 표**로 인쇄됐다.
    # 검토자에게 빈 표는 *「없다」* 와 *「싣지 못했다」* 를 구별해 주지 않는다 —
    # 1절 요약은 같은 사실을 이미 「없음 (검토 범위 내)」로 적고 있으므로,
    # 여기만 비면 두 자리가 다른 말을 하는 것처럼 읽힌다.
    #
    # ⚠ **비었는지는 지원 행 위에서 잰다 (R43-G).** 지원 행이 늘 서므로 표는
    # 다시는 비지 않는데, 그렇다고 「단독·결합으로는 없음」이 사라지면 종전에
    # 「없음」이 말하던 사실이 표에서 지워진다.
    if lines[-1] == _subsidy_flip_row(report):
        lines.append(f"| 지원 외의 단일·결합 인자 | {NONE_IN_RANGE} | — |")

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
        f"(현 지원율 {report.subsidy_rate:.1%}) | 붙임 3 |"
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
