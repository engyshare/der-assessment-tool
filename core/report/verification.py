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
싣는다(8단계). 이것도 **새 계산이 아니다** — 러너가 그 값을 만들 때 쓴 것과
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
from dataclasses import dataclass
from decimal import Decimal

from core.casegrid.models import (
    ONE_OFF_REPLACEMENT,
    CaseBasis,
    OneOffLine,
)
from core.contracts.schemas import CashFlowRow
from core.report._format import _num, _won, _years
from core.report.case_report import (
    CONCLUSION_METRIC,
    HEADLINE_METRIC,
    MAX_SUBSIDY_RATE,
    CaseReport,
)
from core.report.verification_benefit import benefit_pair_lines
from core.report.verification_demand import (
    demand_attribute_lines,
    demand_ledger_lines,
)
from core.report.verification_dispatch import (
    DISPATCH_TABLE_HEAD,
    SIGN_CONVENTION_NOTE,
    declaration_lines,
    dispatch_note_rows,
    resource_label,
)
from core.report.verification_economics import (
    economic_axis_lines,
    economic_ledger_lines,
    influence_lines,
    ledger_all_lines,
)
from core.report.verification_gates import (
    QUESTION_HEAD,
    gate_lines,
    run_identity_line,
    run_identity_rows,
    stage_gate,
    stage_question,
)
from core.report.verification_inputs import (
    capacity_review_lines,
    execution_input_lines,
    season_lines,
    unreflected_lines,
)
from core.report.verification_scaleup import scaleup_lines
from core.report.verification_variants import (
    STAGE9_FORMULA_POINTER,
    subsidy_axis_lines,
    variant_comparison_lines,
)


def _row_year1(row: CashFlowRow) -> int:
    return int(row.amounts.get(1, Decimal(0)))


def _year1_sum(rows: Iterable[CashFlowRow]) -> int:
    """행 목록의 1년차 금액 합 — 표시용 재집계다(위 머리말 참조)."""
    return sum(_row_year1(row) for row in rows)


def _named(name: str, basis: CaseBasis) -> str:
    """조인 키 → **「사람 이름 (`키`)」** — 5·7·8단계가 3단계와 같은 말을 쓴다.

    ## ★ R68/WP-9 — **한 산출물 안에서 같은 자원이 두 이름으로 불리던 것**

    검토서 §3.3(*「내부 식별자는 사람용 명칭과 함께」*)을 R68/WP-2·3 이 3단계에만
    걸었고, 그 결과 같은 `e2e-ess` 가 3단계에서는 「에너지저장장치 (신품)
    (`e2e-ess`)」인데 5단계 「자원별 몫」 표·7단계 일회성 흐름·8단계 대조 줄에서는
    **맨 키**였다(독립 검증 `.orch/R68/result_V.md` 결함 #1-b). 이 함수는 그 셋을
    같은 규약으로 데려올 뿐이며 **규칙 자체는 `resource_label()` 하나가 갖는다.**

    ⛔ **키를 갈아 끼우지 않는다 — 병기다.** 사유는 `resource_label()` 의 ⛔ 절이
    갖는다(같은 종류 자원이 둘이면 이름이 겹친다).
    """
    return resource_label(name, {r.name: r.kind for r in basis.resources})


def _match_note(label_a: str, value_a: int, label_b: str, value_b: int) -> str:
    if value_a == value_b:
        return f"✔ 일치 — {label_a} {_won(value_a)} = {label_b} {_won(value_b)}"
    return (
        f"⚠ 불일치 — {label_a} {_won(value_a)} ≠ {label_b} {_won(value_b)} "
        f"(차이 {_won(value_a - value_b)})"
    )


@dataclass(frozen=True)
class StageBlock:
    """단계 하나 — **완성된 줄들**과 그 단계의 **ⓒ 절** (R68/WP-4-fix · 검토서 §2.2).

    ## 왜 ⓒ 를 따로 나르는가

    목차(`00-목차.md`)가 **의존 연결표**를 세워야 하는데, 그 재료는 *「각 단계의
    ⓒ 다음 단계로 넘긴 값」* 이다(검토서 §2.2). 목차가 그 문면을 **다시 적으면**
    단계가 바뀌는 날 목차만 옛말을 한다 — 두 곳에 같은 말이 있으면 한쪽만
    고쳐진다.

    ⇒ 그래서 **완성된 마크다운을 되읽지 않는다**(그 갈래는 정규식으로 ⓒ 절을
    찾아야 하고, 절 이름을 고치는 날 조용히 빈 표가 된다). 단계를 지을 때 이미
    손에 있는 `c` 를 **그대로 함께 내보낸다** — 아래 `_stage()` 가 그 자리다.

    ⚠ **`lines` 안에 그 ⓒ 가 이미 들어 있다.** 둘은 사본이 아니라 **같은 조각**
    이며(`_stage()` 가 한 번 받아 두 자리에 넣는다), 시험이 그 동일성을 잰다
    (`tests/report/test_verification.py`).
    """

    number: int
    title: str
    #: 이 단계의 마크다운 전문 — `## N단계 — 제목` 부터.
    lines: tuple[str, ...]
    #: **ⓒ 다음 단계로 넘긴 값** 절의 줄들. 표 행(`|` 로 시작)도 그대로 든다 —
    #: 거르는 판단은 **읽는 쪽**이 한다(`core/report/verification_chain.py`).
    handoff: tuple[str, ...]


def _stage(
    report: CaseReport,
    number: int,
    title: str,
    *,
    a: list[str],
    b: list[str],
    c: list[str],
    d: list[str],
) -> StageBlock:
    """단계 하나의 **틀** — 열 단계가 전부 이 한 함수를 지난다.

    ## 무엇이 ⓐⓑⓒⓓ 를 둘러싸는가 (R68/WP-5)

        머리   그 단계가 **답하는 물음** 한 줄 (검토서 §2.1)
               이 단계가 나온 **실행 식별자** 한 줄 (검토서 §4.1)
        꼬리   **판단 게이트** 네 줄 (검토서 §4.7)

    셋 다 문면과 판정을 `core/report/verification_gates.py` 가 갖고 이 함수는
    **자리만 정한다.** ⛔ 열 군데에 같은 모양을 따로 쓰지 않는다 — 그러면 한
    단계만 게이트가 빠져도 조용히 지나간다.

    ⚠ **물음과 게이트를 인자로 받지 않고 번호로 조회한다.** 열 함수가 각자
    넘기게 하면 이 파일의 열 자리가 같은 모양을 되풀이하고, 빠뜨린 자리가
    보이지 않는다. 열을 한 줄로 세워 둔 자리는 그 모듈의 `_GATE_RULES` ·
    `STAGE_QUESTIONS` 이며 **번호가 열 밖이면 그쪽이 멈춘다.**

    ⚠ `report` 를 받는 이유는 머리말 한 줄과 게이트가 그 실행을 읽기 때문이다 —
    `basis` 만으로는 매니페스트도 대장 판도 알 수 없다.
    """
    lines = [f"## {number}단계 — {title}", ""]
    lines += [f"{QUESTION_HEAD} — {stage_question(number)}", ""]
    lines += [run_identity_line(report), ""]
    lines += ["**ⓐ 전제한 수치**", "", *a, ""]
    lines += ["**ⓑ 계산된 수치**", "", *b, ""]
    lines += ["**ⓒ 다음 단계로 넘긴 값**", "", *c, ""]
    lines += ["**ⓓ 계산 수식**", "", *d, ""]
    lines += [*gate_lines(stage_gate(report, number)), ""]
    return StageBlock(
        number=number, title=title, lines=tuple(lines), handoff=tuple(c)
    )


def _stage1_demand(report: CaseReport) -> StageBlock:
    """1단계 「가구 수요」 — 옛 1단계의 **앞 절반** (R69/WP-1 · 검토서 §3.1).

    ## 무엇이 여기 서고 무엇이 4단계로 갔나

    검토서 §3.1: *「1단계에는 가구 수, 가구원 수, EV 대수, 일반용 전력, 히트펌프,
    EV 충전전력, 계절·시간대 형상만 둔다. REC 단가, PV·ESS 단가, 할인율, 지원율은
    경제성 입력 파일로 이동한다」*. ⇒ 이 단계는 **수요만** 갖는다.

    ⛔ **대장 전건 표를 여기 두지 않는다** — 4단계 ⓑ 가 한 덩어리로 갖고, 이
    단계는 접두 `load.*` · `design.*` 의 **부분 표**만 앞세운다. 쪼개 흩으면
    어느 단계에도 안 실리는 접두가 생기고 행이 조용히 사라진다.

    ⛔ **없는 값을 지어 넣지 않는다** — 히트펌프 난방·냉방·급탕 분해 · 충전효율 ·
    검증 상태 축은 대장이 그 항목을 갖고 있지 않다. `demand_attribute_lines()` 가
    그 셋을 **「없다」로 글자에 적고** 판정을 사람에게 올린다(R63 관용구).
    """
    a = [
        *execution_input_lines(report),  # ★ 요구 1·2·3 — 대장 밖에서 온 실행 입력
        # ★ 수요 입력의 여섯 속성 (R68/WP-7 · 검토서 §3.1) — 위 표가 「값과 통로」를
        # 적고 이것이 「그 값이 무엇을 재고 어디서 왔는가」를 적는다. 두 표를 합치지
        # 않는 이유: 위 표에는 대장 항목이 «아닌» 행(가구 수 · 계절 몫)이 함께
        # 서고, 그 행들에 계측 경계·출처를 요구하면 빈 칸이 다섯 열 생긴다.
        *demand_attribute_lines(report),
    ]
    # ★ 대장 **부분 표** — 접두를 고르는 규칙은 `verification_demand.py` 가 갖고
    # 일곱 열을 인쇄하는 규칙은 `verification_ledger.py` 가 갖는다. 산문 칸 접기
    # (`_cell`)도 그 모듈 하나가 건다 — 여기서 f-문자열로 표를 다시 짜지 않는다.
    b = demand_ledger_lines(report)
    c = [
        "이 단계가 낸 가구 총 전력·단지 총 전력이 2단계 용량 역산과 3단계 운전의 "
        "부하이고, 계절 몫과 옮길 수 있는 비율이 3단계 계절별 운전의 형상이다. "
        "⚠ 이 수에 금액을 매기는 단가는 이 단계에 없다 — 4단계가 갖는다.",
    ]
    d = [
        "수요 입력의 산출식은 위 ⓐ 의 두 표가 각자 싣는다 — 「이 실행이 받은 입력」 "
        "표 아래의 산식 세 줄(추가 부하 소계 · 가구 총 전력 · 단지 총 전력)과 "
        "「수요 입력의 여섯 속성」 표의 「산출식」 열(전기차는 꼴을 세우고 그 밖은 "
        "대장 산출근거를 가리킨다). **여기서 다시 인쇄하지 않는다** — 두 곳에 같은 "
        "산식이 있으면 한쪽만 고쳐진다.",
        "",
        "⚠ 히트펌프의 난방·냉방·급탕 분해와 전기차 충전효율은 **이 단계에 없다** — "
        "대장이 그 하위 항목을 갖고 있지 않아 재료가 없고, 지어내지 않는다. 위 ⓐ 의 "
        "두 절이 그 사실과 사유를 글자로 적으며 판정은 사람 몫이다.",
    ]
    return _stage(report, 1, "가구 수요", a=a, b=b, c=c, d=d)


def _stage4_economics(report: CaseReport) -> StageBlock:
    """4단계 「경제성 입력」 — 옛 1단계의 **뒤 절반** (R69/WP-1 · 검토서 §3.1·§6-2).

    ## ⚠ 2·3단계 «뒤»에 서는 것이 이 배열의 뜻이다

    검토서 §3.6 · §6-2 가 *「물리 검증이 끝난 뒤에 편익·비용·현금흐름·지표를
    계산하는 흐름을 문서와 코드에서 동일하게 한다」* 를 요구했다. 2·3단계가
    실제로 쓰는 부하·설계 행은 1단계가 부분 표로 먼저 싣는다.

    ⛔ **설비 단가(`capex.*`)는 2단계에 남는다** — 초기투자가 그것으로 계산되므로
    자원 구성과 같은 자리에 서야 한다(R68 판정이 검토서 §3.1 의 그 한 줄을
    뒤집었고 이쪽이 정본이다).

    ## ⚠ 문면과 판정은 이 함수가 갖지 않는다

    네 칸의 재료 전부가 `core/report/verification_economics.py` 에 있다 — 이
    함수는 **자리만 정한다**(`_stage2_resources` 가 `scaleup_lines` 에,
    `_stage3_dispatch` 가 `dispatch_notes` 에 대해 하는 것과 같다).
    """
    a = [
        *economic_axis_lines(report),
        *economic_ledger_lines(report),
    ]
    b = ledger_all_lines(report)
    c = influence_lines(report)
    d = [
        "해당 없음 — 원시 입력이므로 이 단계에는 산식이 없다. 이 단가로 금액을 "
        "만드는 산식은 5단계(편익) · 6단계(운영비) · 9단계(지표) ⓓ 가 갖는다.",
    ]
    return _stage(report, 4, "경제성 입력", a=a, b=b, c=c, d=d)


def _stage2_resources(report: CaseReport) -> StageBlock:
    basis = report.basis
    total_capex = sum(r.capex_won for r in basis.resources)
    a = [
        "| 자원 | 용량 | 단가 문면 |",
        "|---|---|---|",
        *(f"| {r.kind} | {r.capacity} | {r.unit_capex} |" for r in basis.resources),
        # ★★ **위 용량이 어떻게 단지 규모가 되었는가** (R68/WP-4 · 검토서 §3.5).
        # 종전에는 단지 값만 서 있고 **확대 규칙이 산출물에 없었다** — 부하의
        # 확대는 1단계가 적고 설비의 확대는 어느 단계도 적지 않았다. 판정과
        # 문면의 정본은 `core/report/verification_scaleup.py` 가 갖는다.
        # ⛔ 여기서 곱하거나 나누지 않는다 — 그 모듈이 `report` 에서 읽는다.
        *scaleup_lines(report),
    ]
    b = [
        "| 자원 | 취득비 (원) | 고정 O&M (원/년) |",
        "|---|---|---|",
        *(
            f"| {r.kind} | {_won(r.capex_won)} | {_won(r.fixed_om_won_per_year)} |"
            for r in basis.resources
        ),
        f"| **자원별 취득비 합** | **{_won(total_capex)}** | — |",
        f"| **초기투자(`initial_investment_won`)** | "
        f"**{_won(basis.initial_investment_won)}** | — |",
        *capacity_review_lines(report),  # ★ 요구 4 — 진단이며 위 구성을 바꾸지 않는다
    ]
    c = [
        "자원 목록(용량·운전방식)은 3단계 디스패치가 그대로 받는다.",
        f"초기투자 {_won(basis.initial_investment_won)} 은 9단계 산식의 `I₀` 로 "
        "넘어간다 — 아래 9단계 ⓐ 와 대조.",
    ]
    d = [
        "자원별 취득비는 엔진이 이미 계산한 값이다(용량 x 단가 — 단가 문면은 "
        "위 ⓐ 표에 있다). 이 보고서는 다시 곱하지 않고 결과값을 그대로 싣는다.",
        f"자원별 취득비 합({_won(total_capex)})과 초기투자"
        f"({_won(basis.initial_investment_won)})이 다를 수 있다 — 반올림이 "
        "자원별로 먼저 일어나는가 합산 뒤에 일어나는가의 차이이며, 둘 다 "
        "부가세·지원 반영 전 금액이다.",
    ]
    return _stage(report, 2, "자원 구성과 초기투자", a=a, b=b, c=c, d=d)


def _stage3_dispatch(report: CaseReport) -> StageBlock:
    basis = report.basis
    hours = report.dispatch_hours
    total_export = sum(h.grid_export for h in hours)
    total_import = sum(h.grid_import for h in hours)
    a = [
        "2단계 자원 목록(용량·운전방식) + 엔진 규칙 순서:",
        "",
        # ★★ **선언과 실제가 두 열로 갈린다** (R68/WP-2 · 검토서 §3.3).
        # 종전에는 한 칸에 「전량 판매 (선언) · 본 실행 배분: 집 우선」이 함께
        # 적혀, 같은 문서의 「자가소비율 … (본 실행 실측)」과 **모순으로
        # 읽혔다.** 두 축은 실제로 둘 다 참이며 판정과 짝짓기 규칙은
        # `core/report/verification_dispatch.py` 가 갖는다.
        *DISPATCH_TABLE_HEAD,
        *dispatch_note_rows(report),
        # ★ 표 아래 세 줄 — 갈렸는가 · 이 실행에서 실현됐는가 · 무엇과
        # 이어지는가. **수는 실행에서 읽는다**(리터럴 0 을 박지 않는다).
        *declaration_lines(report, grid_export_kwh=total_export),
    ]
    b = [
        f"대표일 {len(hours)}스텝 운전 — 계통 송전 합계 {_num(total_export)}kWh · "
        f"계통 수전 합계 {_num(total_import)}kWh (붙임 7 이 스텝별 표를 싣는다).",
        *season_lines(report),  # ★ 요구 3·6 — 대표일은 연간등가 하루라 이것을 못 대신한다
    ]
    c = [
        "이 운전 결과의 스텝별 자가소비·송전·수전 수량이 5단계 편익 계산과 "
        "6단계 운영비 계산의 수량 근거다.",
    ]
    # ★ 부호 규약은 **ⓑ 에서 내려와 이 칸에 선다** (R68/WP-2 · 검토서 §4.3).
    d = [basis.dispatch_note or "—", "", SIGN_CONVENTION_NOTE]
    return _stage(report, 3, "대표일 운전(디스패치)", a=a, b=b, c=c, d=d)


def _stage5_benefits(report: CaseReport) -> StageBlock:
    # ⚠ `report` 를 받는다 — 머리말 한 줄과 판단 게이트가 실행을 읽는다(`_stage`).
    basis = report.basis
    a = [
        "4단계 단가 대장 + 3단계 운전결과(자가소비·송전 수량).",
        # ★★ **수량과 금액을 가른다** (R68/WP-8 · 검토서 §3.6). 종전 ⓑ 표는
        # 금액 셋뿐이라 「0원」이 *「팔 것이 없었다」* 인지 *「값이 0이었다」* 인지
        # 갈리지 않았고, 그 둘은 고치는 사람이 다르다(운전 · 단가).
        # ⛔ 여기서 곱하거나 나누지 않는다 — 그 모듈이 `report` 에서 읽는다.
        *benefit_pair_lines(report),
    ]
    b = [
        "| 편익 | 1년차 금액 (원) | 만든 자원 |",
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
            "| 편익 | 자원 | 몫 (원) |",
            "|---|---|---|",
            *(
                f"| {attr.tag} | "
                f"{_named(attr.resource_name, basis) if attr.resource_name else '(귀속 없음)'} | "
                f"{_won(attr.annual_won)} |"
                for attr in basis.benefit_attributions
            ),
        ]
    c = [
        f"연 편익 합계 {_won(basis.annual_benefit_won)}(1년차)는 8단계 편익 "
        "현금흐름 행의 1년차 합계와 같아야 한다 — 아래 8단계 ⓓ 에서 대조한다.",
    ]
    d = [f"- {line.label}: {line.formula}" for line in basis.benefits] or ["없음"]
    return _stage(report, 5, "편익 화폐화", a=a, b=b, c=c, d=d)


def _stage6_costs(report: CaseReport) -> StageBlock:
    basis = report.basis
    a = ["3단계 운전결과(계통 수전 수량) + 4단계 요금 단가."]
    subtotal = sum(line.annual_won for line in basis.costs)
    b = [
        "| 비용 | 1년차 금액 (원) | 자원 |",
        "|---|---|---|",
        *(
            f"| {line.label} | {_won(line.annual_won)} | {line.resource_code or '—'} |"
            for line in basis.costs
        ),
        f"| **1년차 운영비 항목 합** | **{_won(subtotal)}** | — |",
        f"| **`CaseBasis.annual_cost_won`** | **{_won(basis.annual_cost_won)}** | "
        "7단계 생애주기 1년차분 포함(대개 0) |",
    ]
    c = [
        f"1년차 운영비 항목 합 {_won(subtotal)}은 8단계 운영비 현금흐름 행의 "
        "1년차 합계와 같아야 한다 — 아래 8단계 ⓓ 에서 대조한다.",
    ]
    d = [f"- {line.label}: {line.formula}" for line in basis.costs] or ["없음"]
    return _stage(report, 6, "운영비", a=a, b=b, c=c, d=d)


def _stage7_lifecycle(report: CaseReport) -> StageBlock:
    basis = report.basis
    a = [
        f"자원별 수명(`ResourceLine.lifetime_years`) + 분석기간"
        f"({basis.horizon_years}년):",
        "",
        "| 자원 | 수명 (년) |",
        "|---|---|",
        *(f"| {r.kind} | {r.lifetime_years}년 |" for r in basis.resources),
    ]
    if basis.one_off_flows:
        b = [
            "| 자원 | 종류 | 계상 연차 (년차) | 금액 (원) |",
            "|---|---|---|---|",
            *(
                f"| {_named(f.resource_name, basis)} | "
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
        "이 표의 항목이 8단계 생애주기 현금흐름 행과 그 연차·금액이 같아야 "
        "한다.",
    ]
    d = [
        f"- {_named(f.resource_name, basis)} {f.year}년차: {f.formula}"
        for f in basis.one_off_flows
    ] or ["해당 없음 — 일회성 흐름이 없다."]
    return _stage(report, 7, "생애주기(교체·잔존)", a=a, b=b, c=c, d=d)


def _row_table(rows: tuple[CashFlowRow, ...]) -> list[str]:
    if not rows:
        return ["없음"]
    return [
        "| 행 | 1년차 금액 (원) |",
        "|---|---|",
        *(f"| {row.label} | {_won(_row_year1(row))} |" for row in rows),
    ]


def _lifecycle_year_amounts(rows: tuple[CashFlowRow, ...]) -> dict[tuple[str | None, int], int]:
    """생애주기 행의 (태그, 발생 연차) → **그 연차** 금액.

    ⚠ 「1년차 금액」(`_row_year1`)으로는 안 된다 — `replacement_row`·
    `salvage_row`(`core/cba/proforma.py`)는 행마다 연차를 **정확히 하나만**
    채운다(교체·잔존은 그 정의상 한 해에만 일어난다,
    `core/casegrid/lifecycle.py::lifecycle_rows` 독스트링). 그 연차가 1년차가
    아닌 한 `_row_year1` 은 언제나 0원을 낸다 — 7단계와 대조하려면 행이 실제로
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
    """7단계 항목 순서 그대로, **각 항목이 실제로 발생한 연차의 금액**을 싣는다.

    (태그, 연차)로 짝짓는다 — `OneOffLine.tag` 와 `CashFlowRow.tag` 는
    `lifecycle_rows()` 가 같은 루프에서 함께 만든 것이라 같은 문자열이다.
    """
    if not basis.one_off_flows:
        return ["없음"]
    lines = ["| 행 | 발생 연차 (년차) | 그 연차 금액 (원) |", "|---|---|---|"]
    for f in basis.one_off_flows:
        amount = year_amounts.get((f.tag, f.year))
        cell = _won(amount) if amount is not None else "⚠ 대응 행 없음"
        lines.append(f"| {f.label} | {f.year}년차 | {cell} |")
    return lines


def _lifecycle_match_note(
    item: OneOffLine, actual: int | None, basis: CaseBasis
) -> str:
    """⚠ `basis` 는 **이름을 인쇄하려고만** 받는다 — 대조는 여전히 조인 키가 한다.

    7단계가 「에너지저장장치 (신품) (`e2e-ess`)」로 부르는 자원을 이 줄만 맨
    `e2e-ess` 로 부르던 것을 R68/WP-9 가 닫았다(`_named()` 참조).
    """
    named = _named(item.resource_name, basis)
    if actual is None:
        return (
            f"⚠ 불일치 — 7단계 {named} {item.year}년차 "
            f"{_won(item.amount_won)}에 대응하는 8단계 생애주기 행을 찾지 못했다"
        )
    return _match_note(
        f"7단계 {named} {item.year}년차", item.amount_won,
        f"8단계 생애주기 행 {item.year}년차", actual,
    )


def _stage8_cashflow(report: CaseReport) -> StageBlock:
    basis = report.basis
    cf = report.cashflows
    benefit_year1 = _year1_sum(cf.benefit)
    opex_year1 = _year1_sum(cf.operating_cost)
    lifecycle_year1 = _year1_sum(cf.lifecycle)
    lifecycle_year_amounts = _lifecycle_year_amounts(cf.lifecycle)
    a = [
        f"5단계 연 편익 {_won(basis.annual_benefit_won)} · 6단계 연 운영비 항목 · "
        f"7단계 생애주기 항목 {len(basis.one_off_flows)}건.",
    ]
    b = [
        "**편익 행**", "", *_row_table(cf.benefit), "",
        "**운영비 행**", "", *_row_table(cf.operating_cost), "",
        "**생애주기 행** — 「1년차 금액」이 아니라 실제 발생 연차의 금액이다",
        "", *_lifecycle_row_table(basis, lifecycle_year_amounts),
    ]
    c = [
        "이 행 전체(연도별)가 9단계 지표(할인 회수기간·순현재가치) 계산의 "
        "입력이다.",
    ]
    lifecycle_matches = [
        _lifecycle_match_note(
            f, lifecycle_year_amounts.get((f.tag, f.year)), basis
        )
        for f in basis.one_off_flows
    ] or ["해당 없음 — 일회성 흐름이 없다."]
    d = [
        f"1년차 편익 합 = Σ 편익 행의 1년차 값 = {_won(benefit_year1)}",
        _match_note(
            "5단계 연 편익 합계", basis.annual_benefit_won,
            "8단계 편익 행 1년차 합", benefit_year1,
        ),
        "",
        "1년차 운영비 합(생애주기 포함) = Σ (운영비 행 + 생애주기 행)의 1년차 값 "
        f"= {_won(opex_year1 + lifecycle_year1)}",
        _match_note(
            "`CaseBasis.annual_cost_won`", basis.annual_cost_won,
            "8단계 (운영비+생애주기) 행 1년차 합", opex_year1 + lifecycle_year1,
        ),
        "",
        "7단계 항목별 발생 연차·금액이 8단계 생애주기 행의 같은 연차와 맞는가"
        "(항목별 대조):",
        *lifecycle_matches,
    ]
    return _stage(report, 8, "현금흐름 행 — 이 보고서의 심장", a=a, b=b, c=c, d=d)


def _stage9_metrics(report: CaseReport) -> StageBlock:
    basis = report.basis
    metrics = report.metrics
    a = [
        f"8단계 현금흐름 행 전체 + 2단계 초기투자 "
        f"{_won(basis.initial_investment_won)} + 4단계 할인율 "
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
        "이 지표(할인 회수기간·순현재가치)가 10단계 변형별 비교와 심의용 리포트 "
        "5.1 영향도 분석의 기준값이다.",
    ]
    d = []
    for f in report.formulas:
        d += [f"**{f.label}**", f"- {f.natural}", f"- `{f.expression}`", f"- {f.substituted}", ""]
    return _stage(report, 9, "지표", a=a, b=b, c=c, d=d)


def _stage10_variants(report: CaseReport) -> StageBlock:
    a = [
        f"9단계 지표(무지원 기준선) + 현재 지원율 {report.subsidy_rate:.0%} + "
        f"지원 상한 {MAX_SUBSIDY_RATE:.0%}(사업비 전액).",
    ]
    # ★★ **비교표만 갖는다** (R68/WP-5 · 검토서 §3.7). 종전에는 이 칸이
    # 「변형 | 할인 회수기간 | 순현재가치」 세 열이었고, ⓓ 가 9단계의 산식 둘을
    # **글자까지 똑같이** 되풀이했다. 판정과 문면의 정본은
    # `core/report/verification_variants.py` 가 갖는다 — 행마다 구성·초기투자·
    # 순현재가치·필요한 지원율이 함께 서고, 재료가 없는 열은 「미산출」로 선다.
    b = [
        *variant_comparison_lines(report),
        "",
        # ★ 「현재 지원율」과 「결론 전환 지원율」을 **한 표에서 가른다**(§3.7).
        *subsidy_axis_lines(report),
    ]
    c = [
        "이 보고서의 마지막 단계다 — 이후 단계로 넘기는 값이 없다. 결과는 "
        "심의용 리포트 본문 4.2 절의 지원 비교로 나간다.",
    ]
    # ★ 산식을 **다시 인쇄하지 않고 가리킨다** — 9단계 ⓓ 가 `report.formulas`
    #   전건을 이미 편다(그 둘이 거기 있다).
    d = [STAGE9_FORMULA_POINTER]
    return _stage(report, 10, "변형(지원율)", a=a, b=b, c=c, d=d)


def stage_blocks(report: CaseReport) -> tuple[StageBlock, ...]:
    """열 단계를 **자료로** 낸다 — 문서와 목차가 같은 것에서 온다 (WP-4-fix).

    ## 왜 이 함수가 생겼나

    목차의 의존 연결표가 **각 단계의 ⓒ 절**을 재료로 쓴다(검토서 §2.2). 그
    문면을 목차가 다시 적으면 사본이 되고, 완성된 마크다운을 되읽으면 절
    이름에 매인다 — 그래서 **단계를 지은 그 자리에서 자료로 낸다.**

    ⚠ **순서가 문서의 순서다.** 아래 `render_verification_markdown` 이 이
    순서대로 이어 붙이므로 여기서 순서를 바꾸면 문서의 단계 순서가 바뀐다.
    단계 수는 `app/services/verify_steps.py::STAGE_COUNT`(10)와 짝이며,
    어긋나면 `app/services/verify_steps.py::split_stages` 가 멈춘다.

    ⚠ **엔진을 다시 돌리지 않는다** — 열 함수는 `CaseReport` 를 읽어 문면을
    짓기만 한다. 그래서 목차가 이 함수를 한 번 더 불러도 결론축이 움직일 수
    없다(값은 `report` 안에 이미 있다).
    """
    return (
        _stage1_demand(report),
        _stage2_resources(report),
        _stage3_dispatch(report),
        _stage4_economics(report),
        _stage5_benefits(report),
        _stage6_costs(report),
        _stage7_lifecycle(report),
        _stage8_cashflow(report),
        _stage9_metrics(report),
        _stage10_variants(report),
    )


def render_verification_markdown(report: CaseReport) -> str:
    """검증 보고서 — 10단계 전제·계산·인계·수식 (판정 §2).

    ⚠ **해설을 붙이지 않는다** — 판정 문장은 이 문서의 대상이 아니다(판정
    §6). 절 구성은 위 `stage_blocks` 의 단계 순서 자체가 양식이다.
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
        # ★ 이 세 행과 **단계마다 서는 머리말 한 줄**이 같은 자리에서 온다
        #   (R68/WP-5 · 검토서 §4.1). 문면은 종전 그대로다 — 목차
        #   (`app/run/report_cli.py::_index_markdown`)가 같은 세 행을 손으로
        #   갖고 있고, 갈라지면 같은 것이 두 해시를 인쇄한다.
        *run_identity_rows(report),
        "",
        "---",
        "",
    ]
    # ★ 단계마다 `---` 를 뒤에 둔다 — 종전에 아홉 번 손으로 적던 그 구분선이며
    # 문면은 한 글자도 바뀌지 않는다(10단계 뒤의 `---` 도 그대로 선다).
    for block in stage_blocks(report):
        lines += [*block.lines, "---", ""]
    # ★ 미반영 항목 — 새 단계가 아니라 10단계 뒤의 `###` 절이다(단계 정규식 밖).
    lines += unreflected_lines(report)
    return "\n".join(lines)
