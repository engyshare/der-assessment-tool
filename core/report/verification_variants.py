"""10단계 **비교표** — 9단계의 복사가 아니라 변형 사이의 «차이»를 낸다
(R68/WP-5 · 검토서 §3.7).

## 무엇이 되풀이되고 있었나 (실물 확인)

R68/WP-5 착수 시점의 산출물에서 `08-지표.md` 와 `09-변형(지원율).md` 가
**「결론 전환 지원율」과 「전액 지원 시 잔여 결손」 두 산식을 글자까지 똑같이**
싣고 있었다(같은 `Formula` 객체를 두 단계가 각각 폈다 — 자연어·표현식·대입
문면 세 줄이 전부 같다). 검토서 §3.7 이 그것을 짚었다:

> `08-지표.md`와 `09-변형(지원율).md`는 NPV와 지원율 산식을 반복한다. 9단계는
> 8단계의 복사가 아니라, 기준 구성과 대안 구성의 차이를 보여야 한다.

⚠ **위 인용의 번호와 파일 이름은 «승격 전» 배열이다** — R69/WP-1 이 단계를
아홉에서 열로 올려 그 둘이 이제 **9단계(지표)와 10단계(변형)**다. 검토서 문면은
고쳐 적지 않는다(고치면 거짓 인용이다): 대응은 이 줄이 진다.

⇒ **산식은 9단계에 남기고**(9단계 ⓓ 가 `report.formulas` 전건을 편다) 10단계는
**비교표만** 갖는다. 10단계 ⓓ 는 그 산식이 어디 있는지 가리킨다
(`STAGE9_FORMULA_POINTER`).

## ⚠ 같은 수가 두 줄로 서는 것을 **말없이 두지 않는다**

지원율 0% 실행에서 「무지원 기준선」과 「입력 지원안」은 **같은 사업**이라 네 칸이
전부 같은 수다. 같은 수를 두 줄로 인쇄하고 아무 말도 안 하면 독자가 **오류로
읽는다.** ⇒ `_sameness_line()` 이 「같다」와 그 사유를 글자로 적는다 — 사유는
실행에서 판정한다(지원율이 0 이면 그 사유이고, 0 이 아닌데 같으면 그것은 이
리포트가 사유를 갖고 있지 않은 이상이다).

## ⛔ 없는 열을 지어내지 않는다

검토서 §3.7 은 각 행에 *「구성, PV 용량, ESS 용량, 물리 충족률, 연간 수전량,
초기투자, NPV, 필요한 지원율」* 을 요구한다. 이 저장소의 변형 지표
(`CaseReport.variants`)가 나르는 것은 **셋뿐**이다(`npv` · `payback_years` ·
`initial_outlay_won`). 나머지는 아래 `_COLUMNS` 가 «어디서 오는가»를 함께 들고,
올 자리가 없는 열은 **「미산출」로 글자로** 선다 — 그 목록을 10단계 판단 게이트가
읽는다(`core/report/verification_gates.py::_stage9_gate`).
"""
from __future__ import annotations

from dataclasses import dataclass

from core.report._format import _won, _years
from core.report.case_influences import break_even_subsidy_rate
from core.report.case_report import (
    BASELINE_VARIANT,
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    MAX_SUBSIDY_RATE,
    CaseReport,
)
from core.report.verification_inputs import run_used_values


@dataclass(frozen=True)
class _Column:
    """비교표의 열 하나 — 이름과 **그 값이 오는 자리**.

    `metric_key` 가 `None` 이면 변형 지표가 아니라 다른 자리에서 온다(구성 칸 ·
    환산값). 지표에서 와야 하는데 그 키가 없으면 **미산출**이며 `why` 가 그
    사유를 글자로 든다 — 빈칸으로 두면 「0 이었다」로 읽힌다.
    """

    name: str
    metric_key: str | None = None
    why: str = ""


#: 값이 **변형 지표에서 오지 않는** 두 열의 이름 — 아래 `_cells()` 가 이 둘만
#: 따로 다룬다. 낱말을 한 자리에서만 정한다(문자열을 여러 곳에 적으면 열 이름을
#: 고치는 날 한쪽만 고쳐지고, 그때 그 칸이 조용히 「미산출」이 된다).
_CONFIGURATION, _NEEDED_RATE = "구성", "필요한 지원율"

#: 검토서 §3.7 이 10단계 비교표의 각 행에 요구한 것, **요구한 차례 그대로**.
#:
#: ⚠ PV 용량·ESS 용량을 따로 두지 않는다 — 「구성」 칸이 그 둘을 함께 나른다
#: (`core/report/verification_inputs.py::run_used_values` 가 설비마다 「이름 값
#: 단위」 한 조각을 낸다). 열을 셋으로 벌리면 같은 수가 세 칸에 서고, 그때
#: 한 칸만 고쳐진다.
#: ★ **단위를 열 제목이 진다** (R68/WP-8 · 검토서 §4.2). 이 표는 열마다 단위가
#: 다르므로(%· kWh/년 · 원 · 년) 표 제목이 질 수 없다 — 한 표의 열이 전부 같은
#: 단위일 때만 표 제목이 지며, 그 판정은
#: `core/report/dispatch_sections.py` 의 `LOAD_HEAD` 위에 있다.
#: ⛔ **값은 건드리지 않는다** — 칸을 짓는 `_cells()` 는 그대로다.
_COLUMNS: tuple[_Column, ...] = (
    _Column(_CONFIGURATION),
    _Column(
        "물리 충족률 (%)",
        "physical_sufficiency_rate",
        "이 실행이 «충족률»을 내는 계산을 갖고 있지 않다 — 3단계가 싣는 것은 "
        "계통 수전·송전 수량이다",
    ),
    _Column(
        "연간 수전량 (kWh/년)",
        "annual_grid_import_kwh",
        "변형별로 갈리지 않는다 — 지원은 t=0 초기지출 감액이라 운전을 바꾸지 "
        "않으며, 이 실행의 수전량은 3단계가 계절별로 싣는다",
    ),
    _Column("초기투자 (원)", "initial_outlay_won"),
    _Column("할인 회수기간 (년)", HEADLINE_METRIC),
    _Column("순현재가치 (원)", CONCLUSION_METRIC),
    _Column(_NEEDED_RATE),
)

#: 10단계 ⓓ — **산식을 다시 인쇄하지 않고 가리킨다**(머리말 참조).
STAGE9_FORMULA_POINTER = (
    "「결론 전환 지원율」과 「전액 지원 시 잔여 결손」의 산식은 **9단계 ⓓ 가 "
    "갖는다** — 이 단계는 그것을 다시 인쇄하지 않는다(검토서 §3.7 · 그 문면의 "
    "번호는 이 승격 전 배열이다: *「9단계는 8단계의 복사가 아니라, 기준 구성과 "
    "대안 구성의 차이를 보여야 한다」*). "
    "위 표의 「필요한 지원율」 칸이 그 첫 산식으로 나온 값이며, 두 축을 가른 "
    "표가 현재 지원율과 그 환산값을 나란히 싣는다."
)


def policy_variant_sentence(report: CaseReport) -> str:
    """목차 머리표에 설 **한 문장** — 「이 실행이 무슨 정책 변형인가」
    (R68/WP-9 · 검토서 §3.7 마지막 · 독립 검증 결함 #2).

    검토서 문면: *「이 시나리오가 어떤 정책 변형을 의미하는지 목차에서 한
    문장으로 설명할 필요가 있다」*. 착수 시점의 목차 머리표는 「평가 대상
    energy_independent_household」만 실었고 — 그것은 **평가 «대상»**이지
    **정책 «갈래»**가 아니다 — 지원 조건을 한 자도 적지 않았다.

    ## ⛔ 시나리오 이름을 글자로 박지 않는다

    이 목차는 **세 시나리오가 모두 쓴다**(`scenario_unsubsidized` ·
    `scenario_subsidy_20` · …). 그러므로 이 문장이 드는 수와 이름은 전부
    실행에서 온다 — 지원율은 `CaseReport.subsidy_rate`, 시나리오 슬러그는
    `scenario_name_slug`, 견주는 갈래의 이름은 `variant_labels` 다.
    ⛔ 한 시나리오의 말(「무지원」)을 여기서 지어 붙이면 지원 20% 실행의 목차가
    자기를 무지원이라고 적는다.

    ⚠ **낱말** — 이 문장은 사람이 읽는 자리이므로 「전제」를 쓰지 않는다
    (판정 R63b §1). 대장을 부르는 말은 머리표의 「전제 대장」이 이미 갖는다.
    """
    if report.subsidy_rate <= 0.0:
        stance = (
            "**지원이 없는 갈래**다 — 초기투자를 사업자가 전액 진다"
        )
    else:
        stance = (
            f"초기투자의 **{report.subsidy_rate:.0%}** 를 지원받는 갈래다"
        )
    compared = " · ".join(f"「{label}」" for _, label in report.variant_labels)
    return (
        f"이 실행(`{report.scenario_name_slug}`)은 {stance}. 10단계가 이것을 "
        f"{compared} · 「{_FULL_SUPPORT} (지원율 {MAX_SUBSIDY_RATE:.0%})」 와 "
        "견주고, 결론축을 0 으로 만드는 지원율은 9단계 ⓓ 가 환산한다."
    )


def unbuilt_variant_columns(report: CaseReport) -> tuple[str, ...]:
    """검토서가 요구한 열 중 **변형 지표가 나르지 않는** 것의 이름.

    ⚠ 「지금은 없다」를 글자로 박지 않는다 — 변형 지표에 그 키가 서는 날 이 열이
    저절로 차고 10단계 게이트의 미충족도 함께 사라진다. 그 이름들은 **있어야 할
    자리의 이름**이지 이 저장소가 쓰는 필드 이름이 아니다.
    """
    return tuple(
        column.name
        for column in _COLUMNS
        if column.metric_key is not None
        and any(
            column.metric_key not in metrics for metrics in report.variants.values()
        )
    )


def _subsidy_rate_of(report: CaseReport, tag: str) -> float:
    """그 변형이 **쓴** 지원율. 기준선은 언제나 0 이다(`BASELINE_VARIANT`).

    ⚠ 변형이 셋 이상으로 늘면 이 짝짓기를 늘려야 한다 — 지금 이 저장소가 세우는
    변형은 둘뿐이고(`core/report/case_report.py` 의 조립부), 늘리는 자리가
    거기이므로 그때 이 함수가 함께 바뀐다.
    """
    return 0.0 if tag == BASELINE_VARIANT else report.subsidy_rate


def _needed_rate(report: CaseReport, tag: str) -> float:
    """그 변형에서 **결론축을 0 으로 만드는** 지원율.

    ⚠ 이 환산의 근거는 `CaseReport.break_even_subsidy_rate` 독스트링 하나가
    갖는다(지원 1원이 결론축을 정확히 1원 올린다). 여기서 다시 세우지 않고 그
    함수를 부른다 — 두 곳에서 세우면 9단계 산식과 10단계 칸이 갈릴 수 있다.
    """
    return break_even_subsidy_rate(
        subsidy_rate=_subsidy_rate_of(report, tag),
        npv_won=float(report.variants[tag][CONCLUSION_METRIC]),
        total_project_cost_won=report.total_project_cost_won,
    )


def _cells(report: CaseReport, tag: str, configuration: str) -> list[str]:
    """한 행의 칸들 — 열 차례는 `_COLUMNS` 가 정한다."""
    metrics = report.variants[tag]
    cells: list[str] = []
    for column in _COLUMNS:
        if column.name == _CONFIGURATION:
            cells.append(configuration)
        elif column.name == _NEEDED_RATE:
            cells.append(f"{_needed_rate(report, tag):.1%}")
        elif column.metric_key is None or column.metric_key not in metrics:
            cells.append("미산출")
        elif column.metric_key == HEADLINE_METRIC:
            cells.append(_years(metrics[column.metric_key]))
        else:
            cells.append(_won(metrics[column.metric_key]))
    return cells


def _sameness_line(report: CaseReport, rows: dict[str, list[str]]) -> list[str]:
    """두 변형의 수가 **같으면 「같다」와 그 사유**를 적는다 (검토서 §3.7).

    ⚠ 사유를 실행에서 판정한다. 지원율이 0 이면 두 변형은 같은 사업이라 같은
    수가 **정상**이다. 0 이 아닌데 같으면 그것은 이 리포트가 사유를 갖고 있지
    않은 상태이며, 그 사실을 적는다 — 조용히 지나가면 지원이 결론에 닿지 않는
    배선 결함이 「같아 보이는 표」로 남는다.
    """
    if len(rows) < 2:
        return []
    # ★ **수가 서는 칸만 견준다.** 구성 칸은 행마다 같도록 지은 것이고 미산출
    #   칸은 어느 행에서도 같으므로, 그 셋을 넣고 「같다」를 말하면 그것은 표를
    #   지은 방식을 말하는 것이지 이 실행의 사실이 아니다.
    unbuilt = set(unbuilt_variant_columns(report))
    valued = tuple(
        index + 1
        for index, column in enumerate(_COLUMNS)
        if column.name != _CONFIGURATION and column.name not in unbuilt
    )
    compared = {tuple(cells[index] for index in valued) for cells in rows.values()}
    if len(compared) != 1:
        return []
    if report.subsidy_rate == 0.0:
        why = (
            f"이 실행의 지원율이 {report.subsidy_rate:.0%} 라 「입력 지원안」이 "
            "무지원 기준선과 **같은 사업**이기 때문이다"
        )
    else:
        why = (
            f"이 실행의 지원율은 {report.subsidy_rate:.0%} 인데 두 변형의 수가 "
            "같다 — **사유를 이 리포트가 갖고 있지 않다.** 지원이 결론축에 닿는 "
            "경로를 확인해야 한다"
        )
    # ⚠ 「위 N개 행」이라고만 적으면 그 아래 「전액 지원」 환산 행이 표에 함께
    #   서므로 어느 둘을 견준 것인지 갈리지 않는다 — **돌린 변형끼리**임을 적는다.
    return [
        f"- **위 표의 «돌린» 변형 {len(rows)}개 행의 수가 전부 같다** — {why}. "
        "같은 수를 여러 줄로 인쇄하고 아무 말도 안 하면 독자가 오류로 읽으므로 "
        "적어 둔다",
    ]


#: 세 번째 행의 이름 — 검토서 §3.7 이 요구한 세 갈래의 마지막이다.
#: ⚠ 낱말을 한 자리에서만 정한다(위 `_CONFIGURATION` 과 같은 사유).
_FULL_SUPPORT = "전액 지원"


def _full_support_row(report: CaseReport, configuration: str) -> list[str]:
    """검토서 §3.7 의 세 번째 갈래 — **「전액 지원」 행** (R68/WP-9 · 결함 #3).

    ## ⛔ 이 수를 여기서 «다시 세우지» 않는다

    「전액 지원 시 잔여 결손」은 **9단계 ⓓ 가 이미 싣는 수**이고, 그 환산은
    `core/report/case_influences.py::residual_gap_at_full_support_won` **한
    곳**이 한다. 이 행의 순현재가치 칸은 그것을 `CaseReport` 의 같은 이름
    프로퍼티로 **읽어 올 뿐**이다 — 두 곳이 같은 수를 따로 지으면 산식이 바뀌는
    날 한쪽만 고쳐지고, 그때 9단계와 10단계가 서로 다른 결손을 말한다.
    필요한 지원율 칸도 마찬가지로 `break_even_subsidy_rate()` 를 부른다(다른
    두 행이 `_needed_rate()` 로 부르는 바로 그 함수다).

    ## ⚠⚠ 이 행은 **실행이 아니라 환산**이다 — 그래서 칸 둘이 「미산출」이다

    「무지원 기준선」·「입력 지원안」은 파이프라인이 **돌린** 변형이라 지표가
    딸려 있다(`CaseReport.variants`). 전액 지원은 그 변형이 아니고 9단계
    산식이 결론축 하나만 옮긴 것이므로, **초기투자와 할인 회수기간은 이 환산이
    내지 않는다.** 그 두 칸을 「0원」·「즉시」로 채우면 돌리지 않은 수를 돌린 수
    옆에 나란히 세우는 것이 되고, 독자는 그것을 실행 결과로 읽는다.
    ⇒ 「미산출」로 세우고 사유를 표 아래가 든다.
    """
    residual = report.residual_gap_at_full_support_won
    needed = break_even_subsidy_rate(
        subsidy_rate=MAX_SUBSIDY_RATE,
        npv_won=residual,
        total_project_cost_won=report.total_project_cost_won,
    )
    unbuilt = set(unbuilt_variant_columns(report))
    cells: list[str] = []
    for column in _COLUMNS:
        if column.name == _CONFIGURATION:
            cells.append(configuration)
        elif column.name == _NEEDED_RATE:
            cells.append(f"{needed:.1%}")
        elif column.metric_key == CONCLUSION_METRIC:
            cells.append(_won(residual))
        elif column.name in unbuilt:
            cells.append("미산출")
        else:
            cells.append("미산출(환산)")
    return [f"{_FULL_SUPPORT} (지원율 {MAX_SUBSIDY_RATE:.0%})", *cells]


def _full_support_notes(report: CaseReport) -> list[str]:
    """「전액 지원」 행이 **무엇이고 무엇이 아닌가** — 표 아래 두 줄."""
    return [
        f"- **「{_FULL_SUPPORT}」 행은 돌린 변형이 아니라 «환산»이다** — 위 두 "
        "행은 파이프라인이 실제로 돌린 변형이고, 이 행은 **9단계 ⓓ 의 "
        "「전액 지원 시 잔여 결손」 산식**이 결론축 하나를 옮긴 값이다. "
        f"순현재가치 칸 {_won(report.residual_gap_at_full_support_won)}은 "
        "그 산식이 낸 바로 그 수이며 여기서 다시 세우지 않는다",
        "- **「미산출(환산)」 칸 둘** — 초기투자와 할인 회수기간은 그 환산이 "
        "내지 않는다(결론축만 옮긴다). 0원·즉시로 채우면 돌리지 않은 수가 "
        "돌린 수 옆에 실행 결과처럼 선다",
    ]


def variant_comparison_lines(report: CaseReport) -> list[str]:
    """10단계 ⓑ — **비교표 하나**와 그 아래 사실 셋.

    ★ 표 아래 셋: ⓐ 두 행의 수가 같은가와 그 사유 · ⓑ 구성 칸이 무엇을 나르는가
    · ⓒ 검토서가 요구했으나 재료가 없는 열과 그 사유. 셋 다 **적지 않으면**
    독자가 표를 잘못 읽는 자리다.
    """
    configuration = " · ".join(run_used_values(report)) or "설계 변수가 서지 않았다"
    rows = {
        tag: [label, *_cells(report, tag, configuration)]
        for tag, label in report.variant_labels
        if tag in report.variants
    }
    head = ["변형", *(column.name for column in _COLUMNS)]
    # ★ 「전액 지원」 행은 `rows` **밖**에 세운다 — `_sameness_line()` 이 견주는
    #   것은 「돌린 변형끼리 같은 수인가」이고, 환산 행을 그 비교에 넣으면
    #   지원율 0% 실행에서 늘 「같지 않다」가 되어 그 사유 줄이 통째로 사라진다.
    lines = [
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(cells) + " |" for cells in rows.values()),
        "| " + " | ".join(_full_support_row(report, configuration)) + " |",
    ]
    notes = [
        *_sameness_line(report, rows),
        *_full_support_notes(report),
        "- 「구성」 칸이 검토서 §3.7 의 **PV 용량·ESS 용량 열을 함께 나른다** — "
        "이 실행의 변형들은 지원율만 다르고 물리 구성은 하나이므로 그 칸이 "
        "행마다 같다",
        *(
            f"- **{column.name} — 미산출.** {column.why}"
            for column in _COLUMNS
            if column.name in unbuilt_variant_columns(report)
        ),
    ]
    return [*lines, "", *notes]


def subsidy_axis_lines(report: CaseReport) -> list[str]:
    """**현재 지원율과 결론 전환 지원율을 한 표에서 가른다** (검토서 §3.7).

    검토서 문면: *「현재 지원율과 결론 전환 지원율을 혼동하지 않는다」*. 둘은
    단위가 같아서(%) 나란히 읽으면 한 축으로 보이지만, 앞의 것은 **이 실행의
    입력**이고 뒤의 것은 **결론축을 0 으로 만드는 환산값**이다.

    ⚠ 상한 밖인지는 `CaseReport.support_alone_can_flip` 이 판정한다 — 여기서
    다시 비교하지 않는다.
    """
    if report.support_alone_can_flip:
        reach = (
            f"지원 상한 {MAX_SUBSIDY_RATE:.0%} 안이라 지원율로 답이 선다"
        )
    else:
        reach = (
            f"지원 상한 {MAX_SUBSIDY_RATE:.0%}(사업비 전액)을 넘어 **지원율로는 "
            "답이 성립하지 않는다**"
        )
    return [
        "**두 지원율은 다른 축이다** — 혼동하지 않게 갈라 적는다",
        "",
        "| 지원율 축 | 값 | 무엇인가 |",
        "|---|---|---|",
        f"| 현재 지원율 | {report.subsidy_rate:.1%} | 이 실행의 **입력** — "
        "위 표의 「입력 지원안」 행이 쓴 값 |",
        f"| 결론 전환 지원율 | {report.break_even_subsidy_rate:.1%} | 결론축을 "
        f"0 으로 만드는 **환산값**(9단계 ⓓ 의 산식) — {reach} |",
    ]
