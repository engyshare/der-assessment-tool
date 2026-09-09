"""단계마다 **답하는 물음** · **어느 실행의 수인가** · **판단 게이트**
(R68/WP-5 · 검토서 §2.1 · §4.1 · §4.7).

## 왜 셋이 한 파일인가

세 요구는 서로 다른 절이 냈지만 **자리가 하나다** — 열 단계 전부의 머리와
꼬리이며, `core/report/verification.py::_stage()` 한 함수가 그 틀을 짓는다.
셋을 세 파일에 흩으면 그 함수가 세 곳을 부르고, 다음 사람은 「단계 하나가
무엇으로 둘러싸여 있는가」를 세 파일을 열어야 안다.

## ⓐ 물음 (검토서 §2.1)

*「각 파일은 ⓐ→ⓑ→ⓒ→ⓓ 틀을 반복한다. 이 형식은 계산 검증에는 유용하지만, **각
단계가 답하는 사업 질문을 드러내지 못한다**」*. ⇒ 그 틀 **위에** 물음 한 줄을
세운다.

⚠⚠ **검토서의 아홉 물음은 「검토서가 제안한 새 단계 배열」의 것이라 지금 배열과
번호가 맞지 않는다**(검토서 §5 가 그 재배치를 따로 적는다). 그래서 아래
`STAGE_QUESTIONS` 는 **번호가 아니라 내용으로** 짝지었고, 짝이 둘로 갈리거나
없는 자리는 그 사실을 주석이 적는다.

★★ **R69/WP-1 이 단계를 아홉에서 열로 올렸다**(`STAGE_COUNT` = **10**). 검토서
번호와 이 저장소의 번호가 **여전히 다르다** — 승격은 검토서 §5 의 재배치를 그대로
따른 것이 아니라 옛 1단계를 **새 1「가구 수요」와 새 4「경제성 입력」으로 가른
것**이기 때문이다(§3.1 · §6-2). 그래서 위 짝짓기 규약은 그대로다: **번호가 아니라
내용으로** 짝짓는다.

## ⓑ 실행 식별자 (검토서 §4.1)

*「목차에만 있는 매니페스트 해시와 대장 판을 각 파일의 머리말에도 표시하면
파일 하나만 열어도 어떤 실행인지 확인할 수 있다」*. 단계 파일 하나를 폴더 밖으로
꺼내면 어느 실행의 수인지 알 수 없던 자리다.

⚠ **값을 두 벌로 짓지 않는다.** 아래 `run_identity_rows()` 가 문서 머리말의 표
행을 짓고 `run_identity_line()` 이 단계마다 서는 한 줄을 짓는다 — **같은 필드와
같은 자릿수**(`MANIFEST_DIGITS`)를 읽는다. 목차(`app/run/report_cli.py::
_index_markdown`)가 같은 세 행을 손으로 갖고 있는데, 그 파일은 이 WP 가 바꿀 수
있는 자리가 아니라 **시험이 두 벌의 동일성을 잰다**
(`tests/report/test_verification.py`). 갈라지면 같은 것이 두 해시를 인쇄한다.

⚠ **한 덩어리 산출물에서는 이 줄이 열 번 선다.** `--split-stages` 없이 부르면
열 단계가 한 파일에 이어지기 때문이다. **분할일 때만 넣는 갈래를 고르지
않았다** — 렌더러는 자기 문면이 나뉠지 모르고(`render_verification_markdown` 이
분할 여부를 인자로 받지 않는다), 알게 하려면 서명을 바꿔야 하는데 그 서명에
`app/run/report_cli.py` 와 `app/services/verify_steps.py` 가 걸려 있다. ⇒ 대신
**한 줄로 짧게** 하여 되풀이가 읽히게 했다(WP-5 「오케 갱신」의 두 갈래 중 뒤).

## ⓒ 판단 게이트 (검토서 §4.7)

*「각 단계 끝에 판정 행을 넣는다 … 그러면 수요 자료가 불확실하거나 적정 용량이
실제 실행에 반영되지 않은 상태에서 경제성 결론으로 넘어가는 것을 막을 수
있다」*.

⚠⚠⚠ **네 값을 손으로 적지 않는다 — 실행에서 판정된다.** 아래 `_GATE_RULES` 의
열 함수가 각자의 규칙을 갖고, 규칙은 그 함수의 독스트링이 적는다. 규칙의
**축은 넷이 서로 다르다**:

    다음 단계 진행 가능 여부  이 단계가 «다음 단계로 넘기는 값»이 이 리포트
                             안에서 정해졌는가. 사람이 판단해야 정해지는 값을
                             넘기면 「불가」다
    미충족 조건               이 단계가 답해야 할 물음 중 재료가 없어 못 답한 것
    실제 적용 여부            이 단계가 «낸 수»가 이 실행의 결론에 들어갔는가.
                             들어가지 않는 진단을 싣는 단계는 「진단만」이다
    사람 판단 필요 여부       계산이 정할 수 없는 선택이 남아 있는가

⚠ **넷이 같은 답을 내지 않는다.** 미충족이 있어도 넘기는 값이 정해져 있으면
「가능」이고(3단계), 값이 정해져 있어도 그 근거가 리포트 밖이면 「불가」다
(2단계). 그래서 행이 넷이다 — 하나로 접으면 그 구별이 사라진다.

## ⚠ 사람이 읽는 자리에 「전제」를 새로 세우지 않는다 (판정 R63b §1)

물음 문장 · 게이트 행 이름 · 머리말 한 줄 — **이 파일이 새로 짓는 문면 전부**에
그 낱말이 없다. 다만 `RUN_IDENTITY_LABELS` 의 「전제 대장」은 **종전 표의 행
이름을 그대로 나른 것**이다(목차와 문서 머리말이 이미 그 낱말로 서 있고,
`tests/report/test_verification.py` 가 그 문면을 잰다). 여기서만 낱말을 바꾸면
같은 것이 두 이름을 갖는다.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields
from decimal import Decimal

from core.assumption.item import ConfidenceLevel
from core.casegrid.appliance_load import HEATPUMP_LOAD_LEDGER_KEY
from core.contracts.schemas import CashFlowRow
from core.report.case_report import MAX_SUBSIDY_RATE, AssumptionRow, CaseReport
from core.report.dispatch_notes import (
    NO_APPLIED_ALLOCATION,
    DispatchHour,
    applied_allocation,
    declared_operating_mode,
)
from core.report.ess_sizing_section import (
    CAPACITY_KIND_APPLIED,
    CAPACITY_KIND_DIAGNOSTIC,
    CAPACITY_KIND_RUNNING,
)
from core.report.verification_demand import DEMAND_LEDGER_PREFIXES
from core.report.verification_inputs import run_used_values
from core.report.verification_variants import unbuilt_variant_columns

#: 머리말 표의 행 이름과 매니페스트 자릿수 — **목차와 한 글자도 다르지 않다**
#: (`app/run/report_cli.py::_index_markdown` · stderr 보고의 12자리가 아니다).
RUN_IDENTITY_LABELS: tuple[str, str, str] = ("평가 대상", "전제 대장", "실행 매니페스트")
MANIFEST_DIGITS = 16


def run_identity_rows(report: CaseReport) -> list[str]:
    """문서 머리말의 「항목 | 값」 표 **데이터 행 셋** — 종전 문면 그대로다."""
    scenario, ledger, manifest = RUN_IDENTITY_LABELS
    return [
        f"| {scenario} | {report.scenario_name} |",
        f"| {ledger} | `{report.assumption_set_name}` 판 "
        f"{report.assumption_set_version} |",
        f"| {manifest} | `{report.manifest_hash[:MANIFEST_DIGITS]}` |",
    ]


def run_identity_line(report: CaseReport) -> str:
    """단계마다 서는 **한 줄** — 파일 하나만 열어도 어느 실행인지 알게 한다.

    ⚠ 위 표와 **같은 필드·같은 자릿수**를 읽는다. 낱말만 다르다 — 이 줄은 이 WP
    가 새로 짓는 문면이라 「전제」를 쓰지 않는다(머리말 마지막 절).
    """
    return (
        f"> 이 단계가 나온 실행 — 평가 대상 **{report.scenario_name}** · 대장 "
        f"`{report.assumption_set_name}` 판 {report.assumption_set_version} · "
        f"실행 매니페스트 `{report.manifest_hash[:MANIFEST_DIGITS]}`"
    )


#: 단계마다 **답하는 물음** — 차례가 단계 번호다(1단계가 첫 칸).
#:
#: ★ 짝짓기는 **번호가 아니라 내용**이다. 검토서 §2.1 의 표와 이 저장소의 지금
#: 배열이 다르기 때문이며, 어떻게 짝지었는지는 `.orch/R68/result_5.md` 의 표가
#: 적는다. 갈래는 셋이다:
#:
#:     그대로 옮긴 것        3·9·10단계 (검토서 4·7·9번)
#:     검토서 물음을 «반»씩  5·6단계가 검토서 5번을, 7·8단계가 검토서 6번을 나눈다
#:     검토서 1번을 «반»씩   1·4단계 — R69/WP-1 이 그 물음을 둘로 끊었다(아래 ★★)
#:     내가 쓴 것            2단계 — 검토서 2번(1가구 역산)과 3번(20가구 확대)을
#:                          한 단계가 함께 받고, 그 위에 초기투자까지 낸다.
#:                          검토서의 어느 한 물음으로도 이 단계가 답하는 것을
#:                          덮지 못한다
#:
#: ⚠ 검토서 8번(*「어떤 입력 변화가 경제성 결과를 움직이는가」*)에 짝이 되는
#: 단계는 **없다** — 영향도는 심의용 리포트 5.1 이 싣고 이 보고서에는 그 단계가
#: 서지 않는다. 없는 단계를 지어내지 않는다(`STAGE_COUNT` 는 **10** 이며 그 열은
#: 이 보고서가 실제로 내는 단계다).
#:
#: ★★ **R69/WP-1 — 옛 1단계의 물음 하나를 둘로 갈랐다.** 옛 물음은
#: *「한 호와 20호는 얼마의 전력을 언제 쓰는가 — 그리고 그 수는 어느 대장 항목에서
#: 왔는가?」* 였고 **앞 절반이 수요 · 뒤 절반이 대장**이었다. 단계가 갈리면서
#: 그 두 절반이 각자의 단계로 갔다(새 1 · 새 4) — 물음을 새로 지은 것이 아니라
#: **한 문장을 둘로 끊은 것**이다.
#: ⚠ 물음 문장에 「전제」를 쓰지 않는다(판정 R63b §1 · 머리말 마지막 절).
STAGE_QUESTIONS: tuple[str, ...] = (
    "한 호와 20호는 얼마의 전력을 언제 쓰는가?",
    "이 실행이 세운 자원 구성과 초기투자는 얼마이고, 그것은 수요를 만족하는 "
    "데 «필요한» 용량(역산 진단)과 같은가?",
    "그 구성이 계절·시간대별 수요를 실제로 충족하는가 — 계통에서 얼마를 받고 "
    "얼마를 내보내는가?",
    "금액을 매기기 전에 — 이 계산이 쓴 요금·REC 단가·할인율·지원율은 얼마이고, "
    "그 수는 어느 대장 항목에서 왔는가?",
    "3단계 운전이 낸 수량 중 무엇이 얼마의 편익으로 화폐화되는가?",
    "그 운전을 유지하는 데 한 해에 얼마가 드는가?",
    "분석기간 안에서 교체·잔존가치가 언제 얼마로 생기는가?",
    "5~7단계의 금액이 연도별 현금흐름 행으로 어떻게 서고, 단계 사이의 합이 "
    "같은 수인가?",
    "이 구성은 경제적으로 성립하는가 — 성립시키려면 지원율이 얼마여야 하는가?",
    "지원 시나리오를 바꾸면 경제성이 어떻게 달라지는가?",
)

#: 물음 줄의 머리. ⚠ 「전제」를 쓰지 않는다.
QUESTION_HEAD = "**이 단계가 답하는 물음**"

#: 게이트 표의 제목과 행 이름 — 검토서 §4.7 의 표 그대로다.
GATE_TITLE = "**판단 게이트** — 다음 단계로 넘어갈 수 있는가"
GATE_ROW_NAMES: tuple[str, str, str, str] = (
    "다음 단계 진행 가능 여부",
    "미충족 조건",
    "실제 적용 여부",
    "사람 판단 필요 여부",
)

#: 값 낱말 — 검토서가 정한 두 글자를 한 자리에서만 정한다.
GATE_YES, GATE_NO = "가능", "불가"
GATE_APPLIED, GATE_DIAGNOSTIC_ONLY = "적용", "진단만"
GATE_NEEDED, GATE_NOT_NEEDED = "필요", "불필요"
#: 미충족이 하나도 없을 때의 칸. **빈칸으로 두지 않는다** — 빈칸은 「없다」와
#: 「적지 않았다」를 구별해 주지 않는다(`core/report/_format.py::NO_VALUE`).
GATE_NONE = "없음"


@dataclass(frozen=True)
class StageGate:
    """단계 하나의 네 판정 — **값이 아니라 판정의 재료**를 든다.

    문면은 아래 `gate_lines()` 하나가 짓는다. 규칙 함수가 문장까지 지으면 열
    자리가 각자의 서식을 갖게 되고, 그때 표를 훑는 눈이 다른 판정으로 읽는다.
    """

    #: 이 단계가 답해야 할 것 중 **재료가 없어 못 답한 것**. 비면 「없음」.
    unmet: tuple[str, ...] = ()
    #: 다음 단계로 넘기는 값이 **이 리포트 안에서 정해지지 않았는가**.
    #: ⚠ `unmet` 과 다른 축이다 — 위 머리말의 표를 보라.
    blocking: bool = False
    #: 「진단만」인 사유. 비면 「적용」이다.
    diagnostic_only: str = ""
    #: 계산이 정할 수 없어 **사람에게 남는** 선택. 비면 「불필요」.
    human: tuple[str, ...] = ()


def gate_lines(gate: StageGate) -> list[str]:
    """게이트 네 줄 — 표 하나. 값 낱말은 위 상수가 갖는다."""
    proceed, unmet, applied, human = GATE_ROW_NAMES
    return [
        GATE_TITLE,
        "",
        "| 판정 | 값 |",
        "|---|---|",
        f"| {proceed} | {GATE_NO if gate.blocking else GATE_YES} |",
        f"| {unmet} | {' · '.join(gate.unmet) if gate.unmet else GATE_NONE} |",
        f"| {applied} | "
        + (
            f"{GATE_DIAGNOSTIC_ONLY} — {gate.diagnostic_only}"
            if gate.diagnostic_only
            else GATE_APPLIED
        )
        + " |",
        f"| {human} | "
        + (
            f"{GATE_NEEDED} — {' · '.join(gate.human)}"
            if gate.human
            else GATE_NOT_NEEDED
        )
        + " |",
    ]


def _year1_sum(rows: Sequence[CashFlowRow]) -> int:
    """행 목록의 1년차 금액 합 — **판정용**이다.

    ⚠ `core/report/verification.py::_year1_sum` 과 같은 합을 낸다. 사본이
    아니라 **읽는 자리가 둘**인 것이다 — 저쪽은 그 합을 «인쇄»하고 이쪽은 그
    합이 맞는가를 «판정»한다. 판정이 인쇄하는 쪽에서 값을 빌려 오면 「렌더러는
    렌더러가 계산한 값과 같다」만 확인하는 동어반복이 된다(`status.md`).
    """
    return sum(int(row.amounts.get(1, Decimal(0))) for row in rows)


def _assumed_rows(report: CaseReport, *, demand: bool) -> list[AssumptionRow]:
    """신뢰도 「가정」 대장 행을 **수요·설계 쪽과 그 밖으로** 가른다 (R69/WP-1).

    ⚠ 두 게이트가 같은 목록을 세면 같은 항목이 1단계와 4단계에서 **두 번**
    사람에게 넘어가고, 그때 사람은 어느 쪽을 처리해야 하는지 알 수 없다.
    ⇒ 접두로 나누고 합이 전건이 되게 한다 — 어느 쪽에서도 안 세지는 항목이
    없다는 것이 이 갈래의 조건이다(`tests/report/test_verification.py`).
    """
    prefixes = tuple(DEMAND_LEDGER_PREFIXES)
    return [
        row
        for row in report.assumptions
        if row.confidence == ConfidenceLevel.ASSUMED.value
        and row.key.startswith(prefixes) is demand
    ]


def _stage1_gate(report: CaseReport) -> StageGate:
    """1단계(가구 수요) — **값이 서 있는가**와 **그 값을 믿을 수 있는가**는 다르다.

    미충족   실행 입력(단지 규모·기기 부하) 중 「미지정」인 것. 값이 없으면
             2단계 용량 역산과 3단계 운전이 그 부하를 그대로 받을 수 없다
    진행      미충족이 있으면 불가 — 2·3단계가 이 단계의 부하를 **대입값으로** 쓴다
    적용      이 실행이 **수요·설계** 대장 값을 읽어 결론에 반영했는가
             (`uncertain_influences` 의 그 접두 항목이 증거다 — 비면 읽은
             자리가 없다). ⚠ 4단계 게이트는 같은 축을 **전건**으로 본다
    사람      ⓐ 신뢰도 「가정」인 수요·설계 항목의 출처·실측 — **값의 확실성은
             계산이 정하지 못한다** ⓑ 히트펌프 난방·냉방·급탕 분해가 대장에
             하위 항목으로 서지 않은 것(검토서 §3.1 · 대장 편집이 필요하다)

    ⚠⚠ **ⓑ 를 글자로 박지 않고 대장에서 센다.** 하위 항목이 서는 날 이 칸이
    저절로 사라져야 하고, 박아 두면 그 날 이 줄만 옛말을 한다 —
    `core/report/verification_demand.py` 의 「멈춘 자리」 절이 산출물에 같은
    사실을 적으며 그쪽도 대장을 다시 읽는다.
    """
    unmet: list[str] = []
    if report.household_count is None:
        unmet.append("단지 규모(가구 수) 미지정")
    if report.appliance_loads.heatpump_kwh is None:
        unmet.append("히트펌프 부하 미지정")
    if report.appliance_loads.ev_kwh is None:
        unmet.append("전기차 부하 미지정")
    assumed = _assumed_rows(report, demand=True)
    # ⚠ `ledger_key` 는 자료형이 `str | None` 이다 — `uncertain_influences` 가
    # 이미 `None` 을 걸렀으나 **자료형은 그 사실을 모른다.** 여기서 다시 걸러야
    # 검사가 통과하고, 그 한 줄이 「대장에 결선되지 않은 인자」를 이 칸에서도
    # 세지 않게 한다(같은 판정을 두 번 하지 않는다).
    prefixes = tuple(DEMAND_LEDGER_PREFIXES)
    demand_influences = [
        entry
        for entry in report.uncertain_influences
        if entry.ledger_key is not None and entry.ledger_key.startswith(prefixes)
    ]
    human: list[str] = []
    if assumed:
        human.append(
            f"신뢰도 「{ConfidenceLevel.ASSUMED.value}」 수요·설계 대장 항목 "
            f"{len(assumed)}건의 출처·실측 확인"
        )
    if not _heatpump_subitem_keys(report):
        human.append(
            f"히트펌프 난방·냉방·급탕을 대장 하위 항목으로 세울 것인가 — 지금은 "
            f"`{HEATPUMP_LOAD_LEDGER_KEY}` 하나뿐이라 분해를 인쇄할 재료가 없다"
        )
    return StageGate(
        unmet=tuple(unmet),
        blocking=bool(unmet),
        diagnostic_only=(
            ""
            if demand_influences
            else "이 실행이 수요·설계 대장 값을 읽어 결론에 반영한 자리가 없다"
        ),
        human=tuple(human),
    )


def _heatpump_subitem_keys(report: CaseReport) -> tuple[str, ...]:
    """`load.heatpump.annual` **밑의** 대장 항목 — 지금은 0건이다.

    ⛔ 「0건이다」를 글자로 박지 않는다. 대장에 난방·냉방·급탕이 서는 날
    이 함수가 그것을 세고 위 게이트의 사람 몫 칸이 **저절로** 사라진다.
    """
    stem = HEATPUMP_LOAD_LEDGER_KEY.rsplit(".", 1)[0] + "."
    return tuple(
        row.key
        for row in report.assumptions
        if row.key.startswith(stem) and row.key != HEATPUMP_LOAD_LEDGER_KEY
    )


def _stage2_gate(report: CaseReport) -> StageGate:
    """2단계 — **역산은 실행에 되먹이지 않는다**(그 규약이 이 게이트의 값이다).

    미충족   역산이 수를 냈는데 그 진단값을 실행에 반영한 자리가 없다
             (`core/report/ess_sizing_section.py::capacity_kind_lines` 의
             「채택 용량」 칸이 **규약의 진술**로 비어 있는 그 자리다) ·
             설계 변수가 서지 않아 실행 용량 자체가 없는 실행
    진행      **불가** — 3단계가 받는 것은 실행 용량인데, 그것이 왜 진단 용량과
             다른지가 이 리포트 안에 없다(검토서 §3.2 *「왜 다르게 적용했는가를
             사람 판단 항목으로 남겨야 한다」*)
    적용      「진단만」 — 아래 역산값은 결론축을 움직이지 않는다. ⚠ 실행 용량과
             초기투자는 «적용»된 값이므로 그 한정을 칸에 함께 적는다
    사람      실행 용량이 진단 용량과 다른 사유
    """
    diagnosed = report.ess_sizing.unmeasurable_reason is None
    running = run_used_values(report)
    unmet: list[str] = []
    if not running:
        unmet.append(f"이 실행에 설계 변수가 서지 않아 {CAPACITY_KIND_RUNNING}이 없다")
    if diagnosed:
        unmet.append(
            f"{CAPACITY_KIND_DIAGNOSTIC}이 실행에 반영되지 않았다 — "
            f"{CAPACITY_KIND_APPLIED} 없음"
        )
    return StageGate(
        unmet=tuple(unmet),
        blocking=bool(unmet),
        diagnostic_only=(
            f"역산이 낸 {CAPACITY_KIND_DIAGNOSTIC}은 이 실행에 반영되지 않았다"
            f"({CAPACITY_KIND_RUNNING}·초기투자는 적용)"
            if diagnosed
            else ""
        ),
        human=(
            (f"{CAPACITY_KIND_RUNNING}이 {CAPACITY_KIND_DIAGNOSTIC}과 다른 사유",)
            if diagnosed
            else ()
        ),
    )


#: 스텝 자료가 SOC 를 나르면 이름이 이 중 하나다. **자료형을 보고 판정한다** —
#: 「지금은 없다」를 글자로 박으면 SOC 가 실리는 날 이 줄만 옛말을 한다
#: (`core/report/verification_dispatch.py::SOC_NOT_CARRIED` 가 그 사실의 정본이며,
#: 이 게이트는 같은 사실을 **자료에서 다시 읽어** 판정한다).
_SOC_FIELD_NAMES = frozenset({"soc", "soc_kwh", "soc_ratio", "soc_percent"})


def _stage3_gate(report: CaseReport) -> StageGate:
    """3단계 — **미충족이 있어도 넘기는 값은 정해져 있다**(그래서 「가능」이다).

    미충족   선언한 운전방식과 본 실행이 실제로 적용한 배분이 갈린 자원
             (검토서 §3.3) · 스텝 자료가 SOC 를 나르지 않는다(검토서 §3.4 가
             요구한 열 하나가 미산출이다)
    진행      **가능** — 5·6단계가 받는 것은 스텝별 수량이고, 그것은 이 실행이
             실제로 낸 수다. 위 둘은 그 수를 못 정하게 하지 않는다
    적용      스텝별 수량이 5·6단계의 대입값이 됐다
    사람      갈린 자원이 있으면 «어느 쪽을 정본으로 볼 것인가» — 배분이 바뀌면
             5단계 편익이 함께 바뀐다(`verification_dispatch.py::LINKAGE_NOTE`)
    """
    allocations = {line.name: line.applied_allocation for line in report.basis.resources}
    diverged = [
        note.resource_name
        for note in report.dispatch_notes
        if applied_allocation(note, allocations)
        not in (NO_APPLIED_ALLOCATION, declared_operating_mode(note))
    ]
    carries_soc = bool(
        _SOC_FIELD_NAMES & {field.name for field in fields(DispatchHour)}
    )
    unmet: list[str] = []
    if diverged:
        unmet.append(f"선언한 운전방식과 본 실행 배분이 갈린 자원 {len(diverged)}건")
    if not carries_soc:
        unmet.append("스텝 자료가 SOC 를 나르지 않는다 — SOC 열 미산출")
    return StageGate(
        unmet=tuple(unmet),
        blocking=False,
        human=(
            ("갈린 자원의 배분 중 어느 쪽을 정본으로 볼 것인가(바꾸면 5단계 "
             "편익이 함께 바뀐다)",)
            if diverged
            else ()
        ),
    )


def _stage4_gate(report: CaseReport) -> StageGate:
    """4단계(경제성 입력) — **금액을 매기기 전에** 그 단가를 믿을 수 있는가.

    미충족   신뢰도 「가정」이면서 **결론을 뒤집는** 인자
             (`CaseReport.provisional_warning` 이 그 판정의 정본이다). 값은
             서 있으나 그 값이 결론을 뒤집으므로 5단계가 그대로 화폐화할 수 없다
    진행      미충족이 있으면 불가 — 5~10단계가 이 표의 단가를 **대입값으로** 쓴다
    적용      이 실행이 대장 값을 읽어 결론에 반영했는가 (`uncertain_influences`
             전건이 그 증거다 — 비면 읽은 자리가 없다)
    사람      신뢰도 「가정」인 **수요·설계 밖의** 항목의 출처·실측. 수요·설계
             쪽은 1단계 게이트가 이미 넘겼다 — 같은 항목을 두 번 넘기지 않는다

    ## ⚠ 이 단계가 2·3단계 «뒤»에 서는데 그 둘이 이 표의 키를 쓴다

    어긋남이 아니라 **이 배열의 뜻**이다(검토서 §3.6 · §6-2: *「물리 검증이 끝난
    뒤에 편익·비용·현금흐름·지표를 계산하는 흐름을 문서와 코드에서 동일하게
    한다」*). 대장 전건 표가 여기 서는 것은 그 표가 **「1 의 나머지」**이기
    때문이고, 2·3단계가 쓰는 부하·설계 행은 1단계가 **부분 표로 먼저** 싣는다.
    ⛔ 그렇다고 전건 표를 주제별로 쪼개 여러 단계에 흩지 않는다 — 흩으면 행이
    조용히 사라진다.
    """
    unmet: list[str] = []
    if report.provisional_warning:
        unmet.append(
            f"신뢰도 「{ConfidenceLevel.ASSUMED.value}」이면서 결론을 뒤집는 "
            f"인자 {len(report.provisional_warning)}건"
        )
    assumed = _assumed_rows(report, demand=False)
    return StageGate(
        unmet=tuple(unmet),
        blocking=bool(unmet),
        diagnostic_only=(
            ""
            if report.uncertain_influences
            else "이 실행이 대장 값을 읽어 결론에 반영한 자리가 없다"
        ),
        human=(
            (
                f"신뢰도 「{ConfidenceLevel.ASSUMED.value}」 대장 항목 "
                f"{len(assumed)}건(수요·설계 밖)의 출처·실측 확인",
            )
            if assumed
            else ()
        ),
    )


def _stage5_gate(report: CaseReport) -> StageGate:
    """5단계 — 편익 갈래가 **하나도 서지 않으면** 6단계로 넘길 수량이 없다.

    미충족·진행  편익 스트림이 0건이면 미충족이고 그때 진행도 불가다(넘길 값이
                 없다). ⚠ **금액이 0원인 것과 다르다** — 갈래가 서고 값이 0인
                 실행은 「재서 0」이고, 갈래가 없는 실행은 「재지 않았다」다
    적용          연 편익 합계가 8단계 현금흐름의 대입값이 됐다
    사람          불필요 — 단가는 대장이 갖고 수량은 3단계 운전이 정한다.
                 그 둘의 «확실성»은 1·4단계 게이트가 이미 사람에게 넘겼다
    """
    unmet = () if report.basis.benefits else ("편익 갈래 0건 — 화폐화한 항목이 없다",)
    return StageGate(unmet=unmet, blocking=bool(unmet))


def _stage6_gate(report: CaseReport) -> StageGate:
    """6단계 — 5단계와 **같은 규칙**이다(비용 갈래가 서 있는가).

    ⚠ 두 규칙을 한 함수로 묶지 않는다 — 묶으면 어느 단계의 판정인지 표에서
    되짚을 수 없고, 한쪽의 규칙이 바뀌는 날 다른 쪽이 조용히 따라 바뀐다.
    """
    unmet = () if report.basis.costs else ("비용 갈래 0건 — 화폐화한 항목이 없다",)
    return StageGate(unmet=unmet, blocking=bool(unmet))


def _stage7_gate(report: CaseReport) -> StageGate:
    """7단계 — 이 단계의 항목이 **8단계 현금흐름 행에 실제로 도착했는가**.

    미충족·진행  7단계가 든 일회성 흐름 중 (태그, 연차)로 짝지어지는 8단계
                 생애주기 행이 없는 것. 짝이 없으면 그 금액은 어디로도 가지
                 않으므로 8단계가 받을 수 없다 ⇒ 불가
    적용          짝지어진 금액이 현금흐름 행으로 섰다
    사람          불필요 — 수명과 잔존은 자원 제원이 정한다
    ⚠ 일회성 흐름이 **0건인 것은 미충족이 아니다** — 수명이 분석기간보다 길지도
      짧지도 않은 구성에서 정상이며, 그 사실을 7단계 ⓑ 가 글자로 적는다
    """
    landed = {
        (row.tag, year)
        for row in report.cashflows.lifecycle
        for year in row.amounts
    }
    missing = [
        f"{line.resource_name} {line.year}년차"
        for line in report.basis.one_off_flows
        if (line.tag, line.year) not in landed
    ]
    unmet = (
        (f"8단계 생애주기 행에 대응이 없는 항목 {len(missing)}건 — "
         f"{' · '.join(missing)}",)
        if missing
        else ()
    )
    return StageGate(unmet=unmet, blocking=bool(unmet))


def _stage8_gate(report: CaseReport) -> StageGate:
    """8단계 — **단계 사이의 합이 어긋나면 지표로 넘어가지 않는다.**

    미충족·진행  ⓓ 가 인쇄하는 세 대조(5단계 연 편익 ↔ 편익 행 1년차 합 ·
                 `annual_cost_won` ↔ (운영비+생애주기) 1년차 합 · 7단계 항목별
                 연차 금액)를 **여기서 다시 읽어** 판정한다. 어긋난 것이 있으면
                 그 수로 계산한 9단계 지표를 믿을 수 없다 ⇒ 불가
    적용          현금흐름 행 전체가 9단계 지표 계산의 입력이 됐다
    사람          불필요 — 대조는 수의 문제이고 사람이 고를 것이 없다
    """
    basis = report.basis
    cash = report.cashflows
    unmet: list[str] = []
    if _year1_sum(cash.benefit) != basis.annual_benefit_won:
        unmet.append("5단계 연 편익 합계와 8단계 편익 행 1년차 합이 다르다")
    opex = _year1_sum(cash.operating_cost) + _year1_sum(cash.lifecycle)
    if opex != basis.annual_cost_won:
        unmet.append("연 운영비와 8단계 (운영비+생애주기) 1년차 합이 다르다")
    return StageGate(unmet=tuple(unmet), blocking=bool(unmet))


def _stage9_gate(report: CaseReport) -> StageGate:
    """9단계 — **지원율로 답이 서지 않는 실행**이 있다(그것이 이 게이트의 값이다).

    미충족   환산한 결론 전환 지원율이 지원 상한 밖이면, *「얼마를 지원하면
             성립하는가」* 에 지원율로는 답이 없다
             (`CaseReport.support_alone_can_flip` 가 그 판정의 정본이다)
    진행      **가능** — 10단계가 받는 것은 지표이고 그 수는 확정돼 있다.
             지원율로 답이 서지 않는다는 사실도 함께 넘어간다
    적용      이 지표가 결론이며 10단계 비교표의 기준이다
    사람      상한 밖이면 «지원율 외의 수단을 쓸 것인가» — 계산이 정할 수 없다
    """
    if report.support_alone_can_flip:
        return StageGate()
    return StageGate(
        unmet=(
            f"지원 상한 {MAX_SUBSIDY_RATE:.0%} 안에서 결론이 서지 않는다 — "
            f"결론 전환 지원율 {report.break_even_subsidy_rate:.1%}",
        ),
        blocking=False,
        human=("지원율 외의 수단을 쓸 것인가(전액 지원에도 결손이 남는다)",),
    )


def _stage10_gate(report: CaseReport) -> StageGate:
    """10단계 — 검토서 §3.7 이 요구한 **비교 열 중 재료가 없는 것**을 센다.

    미충족   `core/report/verification_variants.py::unbuilt_variant_columns` 가
             변형 지표에서 **찾지 못한** 열 이름. ⛔ 지어내지 않는다 — 없는
             열은 「미산출」로 글자로 선다(검토서 §3.7 의 요구 그대로)
    진행      **가능** — 이 보고서의 마지막 단계이며, 넘기는 곳은 심의용 리포트
             4.2 절이다. 그 절이 받는 수(변형별 지표)는 확정돼 있다
    적용      이 비교가 심의용 리포트의 지원 비교로 나간다
    사람      «어느 지원 시나리오를 채택할 것인가» — 이 리포트는 비교만 낸다
    """
    unbuilt = unbuilt_variant_columns(report)
    return StageGate(
        unmet=(
            (f"검토서 §3.7 이 요구한 열 중 미산출 — {' · '.join(unbuilt)}",)
            if unbuilt
            else ()
        ),
        blocking=False,
        human=("어느 지원 시나리오를 채택할 것인가(이 리포트는 비교만 낸다)",),
    )


#: 단계 번호 → 그 단계의 판정 규칙. 차례가 단계 번호다(1단계가 첫 칸).
#:
#: ⚠ **번호로 고르는 이유** — 열 함수가 각자 자기 게이트를 인자로 넘기게 하면
#: `core/report/verification.py` 의 열 자리가 같은 모양을 되풀이하고, 그때
#: 「한 단계만 게이트를 안 넘겼다」가 조용히 지나간다. 여기서 열을 한 줄로
#: 세워 두면 **빠진 자리가 눈에 보인다.**
_GATE_RULES = (
    _stage1_gate,
    _stage2_gate,
    _stage3_gate,
    _stage4_gate,
    _stage5_gate,
    _stage6_gate,
    _stage7_gate,
    _stage8_gate,
    _stage9_gate,
    _stage10_gate,
)


def stage_question(number: int) -> str:
    """그 단계가 답하는 물음. 번호가 열 밖이면 **멈춘다.**"""
    if not 1 <= number <= len(STAGE_QUESTIONS):
        raise ValueError(
            f"물음이 없는 단계 번호다: {number} — 단계를 늘렸으면 "
            "`STAGE_QUESTIONS` 도 함께 늘려야 한다(빈 물음을 인쇄하지 않는다)"
        )
    return STAGE_QUESTIONS[number - 1]


def stage_gate(report: CaseReport, number: int) -> StageGate:
    """그 단계의 판정. 번호가 열 밖이면 **멈춘다** — 빈 게이트를 내지 않는다.

    빈 게이트는 「판정할 것이 없다」와 「판정 규칙을 안 썼다」를 구별해 주지
    않는다. 규칙 없이 「가능 / 불필요」가 찍히면 이 표가 무의미해진다.
    """
    if not 1 <= number <= len(_GATE_RULES):
        raise ValueError(
            f"판정 규칙이 없는 단계 번호다: {number} — 단계를 늘렸으면 "
            "`_GATE_RULES` 도 함께 늘려야 한다"
        )
    return _GATE_RULES[number - 1](report)
