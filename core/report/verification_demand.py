"""검증 1단계 — 수요 입력마다 **여섯 속성**을 세우고, 대장이 갖지 않은 것은
**「갖지 않았다」고 적는다** (R68/WP-7 · 검토서 §3.1 · §4.2 · §4.4).

## 무엇이 없었나

옛 1단계는 두 표를 갖고 있었다 — 「이 실행이 받은 입력」(값과 통로)과 대장 전건
목록(값·단위·기준연도·출처·신뢰도·최종확인일). 검토서 §3.1 이 요구하는 것은
그 둘의 교집합이 아니라 **수요 입력마다의 여섯 속성**이다:

    값 · 단위 · 출처 · 계측 경계 · 산출식 · 변경 경로

앞의 셋과 마지막 하나는 두 표에 흩어져 있었고, **계측 경계와 산출식은 어느
표에도 없었다.** 그래서 *「이 3,289 가 무엇을 재고 무엇을 재지 않는가」* 는
산출물이 아니라 대장 파일을 열어야만 답되는 물음이었다.

⇒ 수요 입력 셋(일반용 전력 · 히트펌프 · 전기차)을 **한 표에 여섯 열로** 세운다.

## ★ 다섯은 읽고, 하나만 짓는다

| 속성 | 어디서 오나 |
|---|---|
| 값 | **이 실행이 쓴 값** — 실행 입력이 이기고 안 적으면 대장이 답한다 |
| 단위 | 대장 `value_unit` (`AssumptionRow.value_unit`) |
| 출처 | 대장 `source` |
| 계측 경계 | 대장 `applicable_scope` — R68/WP-7 이 `AssumptionRow` 에 태웠다 |
| 산출식 | ★ **여기만 다르다** — 아래 ⛔ 절 |
| 변경 경로 | 대장 키 자체. 사용자가 바꾸는 통로가 그것이다 |

## ⛔ 왜 「산출식」만 대장에서 «뽑지» 않는가

대장의 `derivation_method` 는 **산문**이다 — 히트펌프의 것은 수천 자이고 산식
한 줄이 그 안 어딘가에 있다. 정규식으로 그 줄을 뽑으면 **산문이 바뀌는 날 조용히
틀린다**(그리고 틀린 산식은 「검증했다」로 읽힌다).

⇒ 두 갈래로 나눈다.

- **꼴이 조항으로 정해진 것**(전기차 — 검토서 §3.1 이 `대수 × 연간 주행거리 ÷
  전비 ÷ 충전효율` 로 못 박았다)은 **꼴만** 세우고 **총계는 대장에서 읽는다.**
  항의 수(대수·주행거리·전비)는 대장 **항목이 아니라** 산출근거 안이므로
  **여기 리터럴로 박지 않고 가리킨다.**
- 그 밖은 `LEDGER_DERIVATION_REFERENCE` — **「대장 참조」와 그 키**다.

## ★★ R71/WP-1 — 「÷ 충전효율」이 **이제 곱해진다. 그래서 보여야 한다**

종전에는 그 항이 `[충전효율: 미반영]` 으로 서 있고 어떤 수도 곱해지지 않았다.
대장이 스스로 *「⛔ 손실 계수를 지어내 곱하지 않았다」* 고 적었기 때문이다.
R71/WP-1 이 그 결손을 **별도 대장 항목**으로 닫았다 —
`load.ev.charging_loss`(0.10 · `confidence: 가정`)이며, 환산은
`core/casegrid/appliance_load.py::with_ledger_defaults` 가
`대장 값 ÷ (1 − 손실률)` 로 한다.

⇒ **이 표의 「값」 칸이 대장 `load.ev.annual` 의 값과 다르다** — 2,784(배터리
투입) 가 아니라 3,093(계통 수전)이다. ⚠⚠ **그 차이를 산식이 글자로 보여야
한다.** 계산에는 들어가는데 표에는 안 보이면, 읽는 사람은 두 수의 차이를
「어느 쪽이 오타인가」로 읽는다. 그래서 산식 문면이 나눈 수를 **그대로 인쇄**하고,
아래 계측 경계 절이 **어느 경계에서 어느 경계로 옮겼는지**를 적는다.

⛔ **대장의 조사값은 한 글자도 바뀌지 않았다.** 조사값(2,784)과 가정(0.10)이
**서로 다른 두 행**으로 서고, 1단계 ⓑ 부분 표가 그 둘을 나란히 싣는다 —
한 수로 섞으면 어느 쪽이 조사이고 어느 쪽이 가정인지 산출물이 말해 주지 않는다.

⚠ 대장이 *「배터리 투입 기준」* 이라는 말을 거두면 이 모듈의 계측 경계 절이
**거짓말이 된다.** 문면을 파싱해 인쇄하는 대신 **시험이 대장을 붙든다**
(`tests/report/test_verification_demand.py::test_ledger_still_says_the_ev_value_is_battery_side`).
파싱은 인쇄를 산문에 매달고, 시험은 **어긋나는 날 사람을 부른다** — 다른 일이다.

## ★★ 멈춘 자리 둘 — 이 모듈이 «인쇄하지 않는» 것

- **히트펌프의 난방·냉방·급탕 분해**(검토서 §3.1). 그 셋은 대장 **항목이 아니다**
  — `load.heatpump.annual` **하나**의 산출근거 안에만 있다(실측: 대장의
  `load.heatpump*` 키는 그 하나뿐이다). 표로 만들지 않고 **가리키고 멈춘다.**
- **검증 상태**(계산됨 · 출처 확인 · 조사 인용 · 가정 — 검토서 §4.4). 대장이 갖는
  축은 `confidence`(확정·추정·가정) **하나**이며 「원문을 열었는가」를 묻지 않는다.
  셋을 넷으로 재해석해 인쇄하면 **근거 등급의 승격**이고, 이 저장소가 실물로 밟은
  결함이다.

둘 다 **대장 편집**이 필요하고 대장 편집은 이 자리의 권한 밖이므로, 산출물에
**「없다」를 글자로 적고** 판정을 사람에게 올린다. 빈칸은 「없다」와 「싣지
못했다」를 가르지 못한다.

## ⚠ 사람이 읽는 자리의 낱말

열 제목에 「전제」를 세우지 않는다 — 그 낱말은 사람이 읽는 자리에서 0건이
규약이고(판정 R63b §1 · `tests/app/test_screen_words.py`), 이 표의 머리는
`/ui/verify` 에서 `th` 가 된다. 대장을 부르는 말은 「분석 설정 대장」이다.
"""

from __future__ import annotations

from core.casegrid.appliance_load import (
    APPLIANCE_LOAD_UNIT,
    APPLIANCE_LOAD_UNSPECIFIED,
    EV_CHARGING_LOSS_LEDGER_KEY,
    EV_CHARGING_LOSS_TITLE,
    EV_LOAD_LEDGER_KEY,
    EV_LOAD_TITLE,
    HEATPUMP_LOAD_LEDGER_KEY,
    HEATPUMP_LOAD_TITLE,
)
from core.report._format import _cell
from core.report.case_report import AssumptionRow, CaseReport
from core.report.verification_ledger import ledger_table, rows_with_prefix
from core.report.verification_scaleup import (
    ESTATE_LOAD_UNIT,
    HOUSEHOLD_LOAD_LEDGER_KEY,
    household_base_kwh,
)

#: **1단계가 대장에서 읽는 접두** — 부하와 단지 설계 (R69/WP-1 · 검토서 §3.1).
#:
#: ⚠ 이 목록을 여기서 정하는 근거는 **대장 자신**이다: `docs/assumptions.yaml` 의
#: `group_titles` 가 `load` 를 「전기사용자 부하」로 `design` 을 「단지 설계」로
#: 이미 갈라 두었다. 여기서 주제를 새로 짓지 않고 그 갈래를 **접두로** 읽는다.
#:
#: ⛔ **`capex.*` 를 넣지 않는다.** 설비 단가는 2단계에 남는다 — 초기투자가
#: 그것으로 계산되기 때문이다(R68 판정 · 검토서 §3.1 은 *「PV·ESS 단가도 경제성
#: 입력으로」* 라 적었으나 그 판정이 정본이다).
#:
#: ⚠⚠ **4단계의 접두 목록과 겹치지 않아야 한다.** 겹치면 같은 대장 항목이 두
#: 단계에서 「이 단계가 읽은 값」으로 서고, 그때 어느 단계가 그 값을 정했는지
#: 산출물이 말해 주지 않는다. 그 사실을 시험이 붙든다
#: (`tests/report/test_verification.py`).
DEMAND_LEDGER_PREFIXES: tuple[str, ...] = ("load.", "design.")

#: 부분 표의 제목. ⚠ 「전제」를 쓰지 않는다(판정 R63b §1).
DEMAND_LEDGER_TITLE = (
    "**이 단계가 분석 설정 대장에서 읽은 값 — 부하와 단지 설계** "
    "(접두 `load.*` · `design.*`)"
)


def demand_ledger_lines(report: CaseReport) -> list[str]:
    """1단계 ⓑ — 대장 **부분 표**. 전건 표는 4단계가 갖는다 (R69/WP-1).

    ## ⛔ 행을 고르는 것이지 새로 만드는 것이 아니다

    같은 `report.assumptions` 행을 접두로 걸러 인쇄한다 — 값을 다시 계산하거나
    행을 짓지 않는다. 인쇄 규칙은 `core/report/verification_ledger.py` 하나가
    갖고 이 함수는 **무엇을 고를지**만 정한다.

    ## ⚠ 전건 표를 여기 두지 않은 이유

    옛 1단계는 대장 **전건**을 실었다. 그것을 주제별로 쪼개 여러 단계에 흩으면
    어느 단계에도 안 실리는 접두가 생기고 **행이 조용히 사라진다.** ⇒ 전건은
    4단계에 **한 덩어리로** 남기고, 1단계는 *「이 단계가 읽은 것」* 만 부분
    표로 앞세운다. 두 표가 같은 행을 싣는 것은 사본이 아니라 **다른 진술**이다:
    앞은 「수요를 이 값으로 돌았다」이고 뒤는 「대장이 무엇을 갖고 있는가」다.
    """
    rows = rows_with_prefix(report, DEMAND_LEDGER_PREFIXES)
    return [
        "",
        DEMAND_LEDGER_TITLE,
        "",
        *ledger_table(rows),
        "",
        f"- 이 표는 대장 **전건이 아니다** — {len(rows)}건이며 전건 "
        f"{len(report.assumptions)}건은 4단계 ⓑ 가 한 덩어리로 싣는다. 접두를 "
        "이렇게 가른 근거는 대장 자신의 `group_titles`(「전기사용자 부하」 · "
        "「단지 설계」)다",
        "- ⛔ 설비 단가(`capex.*`)는 이 표에 **없다** — 2단계에 남는다. 초기투자가 "
        "그것으로 계산되므로 자원 구성과 같은 자리에 서야 한다",
    ]

#: 일반용 전력의 사람용 이름. 히트펌프·전기차는 `core/casegrid/appliance_load.py`
#: 가 이름을 갖는데(`HEATPUMP_LOAD_TITLE`·`EV_LOAD_TITLE`) 일반용은 대장 항목이라
#: 그 파일에 이름이 없다. **1단계의 기존 표가 쓰는 낱말과 같아야** 읽는 눈이 두
#: 표의 같은 행을 같은 것으로 본다.
HOUSEHOLD_LOAD_TITLE = "일반용 전력"

#: 산출식 칸의 「뽑지 않았다」 문면. ⛔ 산문을 갈라 넣는 대신 **키를 가리킨다.**
LEDGER_DERIVATION_REFERENCE = "대장 참조 — 산출근거가 대장 `{key}` 안에 있다"

#: 전기차 산식의 **꼴**. 검토서 §3.1 문면이 정본이며, `{total}` 만 대장에서 읽은
#: 수로 채워진다. ⚠⚠ 항의 수를 여기 박지 않는다 — 대수·주행거리·전비는 대장
#: **항목이 아니라** 산출근거 안이고, 박으면 대장이 바뀌는 날 이 줄만 옛말을 한다.
EV_DERIVATION_SHAPE = (
    "{total} = 대수 × 연간 주행거리 ÷ 전비 ÷ (1 − 충전 손실률 {loss})"  # noqa: RUF001
)

#: 대장이 손실률 항목을 **갖지 않을 때** 산식의 그 자리에 서는 문면. ⚠ 빈칸으로
#: 두지 않는다 — 빈칸은 「손실이 0 이다」와 「대장이 그 항목을 갖지 않는다」를
#: 가르지 못하고, 이 저장소가 반복해 밟은 결함이 그 혼동이다.
EV_CHARGING_LOSS_ABSENT = "**대장에 항목이 없어 미반영**"

#: 대장 `load.ev.annual` 의 산출근거가 여전히 이 문면을 갖는지 **시험이 붙든다.**
#: 이 상수는 인쇄되지 않는다 — 파싱의 씨앗이 아니라 **드리프트의 붙잡이**다.
EV_BOUNDARY_LEDGER_PHRASE = "배터리 투입 기준"

#: 여섯 속성 표의 머리. **단위가 표 제목과 열 제목 둘 다에 선다**(검토서 §4.2).
#: ⚠ 값 열의 단위는 **러너가 쓰는 상수**에서 오고 「단위」 열은 **대장**에서 온다 —
#: 두 통로가 갈리는 날 그 어긋남이 한 행 안에서 눈에 보인다(아래 `_unit_note`).
DEMAND_ATTRIBUTE_HEAD: tuple[str, ...] = (
    f"| 수요 입력 | 값 (`{APPLIANCE_LOAD_UNIT}`) | 단위 (대장 `value_unit`) "
    "| 출처 | 계측 경계 | 산출식 | 변경 경로 |",
    "|---|---|---|---|---|---|---|",
)


def _value_cell(value: float | None) -> str:
    """값 칸 — 단위는 **열 제목이 지므로** 수만 적는다 (검토서 §4.2).

    ⚠ `None` 은 빈칸이 아니라 진술이다 — 기존 1단계 표와 **같은 문면**을 쓴다
    (`APPLIANCE_LOAD_UNSPECIFIED`). 두 표가 같은 상태를 다른 말로 적으면 읽는
    사람이 다른 상태로 읽는다.
    """
    return APPLIANCE_LOAD_UNSPECIFIED if value is None else f"{value:,.0f}"


def _rows_by_key(report: CaseReport) -> dict[str, AssumptionRow]:
    return {row.key: row for row in report.assumptions}


def _attribute_row(
    *,
    title: str,
    value: float | None,
    ledger: AssumptionRow | None,
    key: str,
    derivation: str,
) -> str:
    """여섯 속성 한 줄.

    ⚠ `ledger` 가 `None` 인 것은 **대장에 그 키가 없다**는 뜻이며, 그때 단위·출처·
    계측 경계를 **지어내지 않고** 그 사실을 적는다. 이 실행은 셋 다 대장에 있으나
    시나리오가 대장을 갈아 끼울 수 있으므로 그 갈래를 남긴다.
    """
    absent = f"대장에 `{key}` 행이 없다"
    return (
        f"| {title} | {_value_cell(value)} "
        f"| {_cell(ledger.value_unit) if ledger else absent} "
        f"| {_cell(ledger.source) if ledger else absent} "
        f"| {_cell(ledger.applicable_scope) if ledger else absent} "
        f"| {derivation} "
        f"| 대장 키 `{key}` — 바꾸는 통로는 위 「이 실행이 받은 입력」 표 |"
    )


def _unit_note(rows: dict[str, AssumptionRow], keys: tuple[str, ...]) -> str:
    """대장 단위와 러너 단위가 갈렸는지 **세어서** 적는다 (검토서 §4.2 · ⓔ).

    ⚠⚠ **갈렸으면 맞추지 않는다.** 리포트가 조용히 한쪽으로 맞추면 그 어긋남이
    산출물에서 사라지고, 사라진 어긋남은 아무도 고치지 않는다. 여기서 하는 일은
    **드러내는 것**뿐이다.
    """
    off = [
        f"`{key}` 는 `{rows[key].value_unit}`"
        for key in keys
        if key in rows and rows[key].value_unit != APPLIANCE_LOAD_UNIT
    ]
    if off:
        return (
            "- ⚠⚠ **단위가 갈렸다 — 맞추지 않고 적는다.** 러너가 쓰는 상수는 "
            f"`{APPLIANCE_LOAD_UNIT}` 인데 " + " · ".join(off) + " 다. 어느 쪽이 "
            "정본인지는 사람이 정한다"
        )
    return (
        "- 단위 — 대장 `value_unit` 과 러너가 쓰는 상수가 세 행 모두 "
        f"`{APPLIANCE_LOAD_UNIT}` 로 **같다.** 값 열의 단위는 러너 상수에서 오고 "
        "「단위」 열은 대장에서 오므로, 갈리는 날 이 줄이 그 사실로 바뀐다"
    )


def demand_attribute_lines(report: CaseReport) -> list[str]:
    """1단계 — **수요 입력의 여섯 속성** 표와 그 아래 세 절 (검토서 §3.1·§4.2·§4.4).

    아래 세 절이 표 뒤에 붙는다 — 앞의 하나는 인쇄하고 뒤의 둘은 **멈춘 자리**다.

    1. 전기차 산식과 계측 경계 (§3.1)
    2. 히트펌프 분해가 **왜 이 표에 없는가** (§3.1 — 판정 대기)
    3. 검증 상태가 **왜 이 표에 없는가** (§4.4 — 판정 대기)
    """
    rows = _rows_by_key(report)
    loads = report.appliance_loads
    keys = (HOUSEHOLD_LOAD_LEDGER_KEY, HEATPUMP_LOAD_LEDGER_KEY, EV_LOAD_LEDGER_KEY)
    ev_row = rows.get(EV_LOAD_LEDGER_KEY)
    ev_total = _value_cell(loads.ev_kwh)
    ev_loss = _charging_loss_cell(rows)
    ev_formula = EV_DERIVATION_SHAPE.format(total=ev_total, loss=ev_loss)
    return [
        "",
        f"**수요 입력의 여섯 속성 — 값의 단위는 `{APPLIANCE_LOAD_UNIT}`** "
        "(검토서 §3.1 · §4.2)",
        "",
        *DEMAND_ATTRIBUTE_HEAD,
        _attribute_row(
            title=HOUSEHOLD_LOAD_TITLE,
            value=household_base_kwh(report),
            ledger=rows.get(HOUSEHOLD_LOAD_LEDGER_KEY),
            key=HOUSEHOLD_LOAD_LEDGER_KEY,
            derivation=LEDGER_DERIVATION_REFERENCE.format(key=HOUSEHOLD_LOAD_LEDGER_KEY),
        ),
        _attribute_row(
            title=HEATPUMP_LOAD_TITLE,
            value=loads.heatpump_kwh,
            ledger=rows.get(HEATPUMP_LOAD_LEDGER_KEY),
            key=HEATPUMP_LOAD_LEDGER_KEY,
            derivation=LEDGER_DERIVATION_REFERENCE.format(key=HEATPUMP_LOAD_LEDGER_KEY),
        ),
        _attribute_row(
            title=EV_LOAD_TITLE,
            value=loads.ev_kwh,
            ledger=ev_row,
            key=EV_LOAD_LEDGER_KEY,
            derivation=ev_formula,
        ),
        "",
        "- 「값」은 **이 실행이 쓴 값**이고 「단위 · 출처 · 계측 경계」는 **대장이 적은 "
        "것**이다 — 시나리오가 값을 덮어써도 그 값이 무엇을 재는가는 대장이 정한다",
        _unit_note(rows, keys),
        f"- 단지 합계의 단위는 `{ESTATE_LOAD_UNIT}` 이다 — 위 칸들의 "
        f"`{APPLIANCE_LOAD_UNIT}` 과 나란히 서므로 **호당인지 단지인지**를 낱말이 "
        "스스로 말한다(검토서 §4.2). ⚠ **분모가 바뀐 것이 아니라 이름이 바뀐 "
        "것**이다 — 값도 곱하는 자리도 그대로다",
        "",
        *_ev_boundary_lines(ev_formula, rows),
        *_heatpump_breakdown_lines(),
        *_verification_state_lines(),
    ]


def _charging_loss_cell(rows: dict[str, AssumptionRow]) -> str:
    """산식의 「충전 손실률」 자리 — **대장에서 읽은 수**이거나 「없다」다.

    ⛔ **여기서 0.10 을 짓지 않는다.** 이 모듈이 기본값을 가지면 대장을 비운
    실행이 *「손실을 반영했다」* 로 인쇄되고, 그때 인쇄된 수는 **계산에 쓰인 수와
    다르다** — 환산은 `core/casegrid/appliance_load.py::with_ledger_defaults` 가
    하며 그쪽도 대장이 없으면 나누지 않는다. 두 자리가 **같은 통로 하나**(대장)를
    본다.
    """
    row = rows.get(EV_CHARGING_LOSS_LEDGER_KEY)
    if row is None or not isinstance(row.value, int | float):
        return EV_CHARGING_LOSS_ABSENT
    return f"{row.value:g} · 대장 `{EV_CHARGING_LOSS_LEDGER_KEY}`"


def _ev_boundary_lines(ev_formula: str, rows: dict[str, AssumptionRow]) -> list[str]:
    """전기차 — 산식과 **계측 경계**를 글자로 못 박는다 (검토서 §3.1 · R71/WP-1)."""
    loss_row = rows.get(EV_CHARGING_LOSS_LEDGER_KEY)
    ledger_row = rows.get(EV_LOAD_LEDGER_KEY)
    battery_side = (
        f"{ledger_row.value:,.0f}"
        if ledger_row is not None and isinstance(ledger_row.value, int | float)
        else f"대장에 `{EV_LOAD_LEDGER_KEY}` 행이 없다"
    )
    return [
        f"**{EV_LOAD_TITLE} — 산식과 계측 경계** (검토서 §3.1)",
        "",
        "```",
        ev_formula.replace("**", "").replace("`", ""),
        "```",
        "",
        "- **계측 경계 — 이 표의 값은 「계통 수전 기준」이다.** 전비는 배터리에서 "
        "나간 전기로 주행거리를 나눈 수여서 대장의 조사값은 **배터리 투입 기준**이고, "
        "벽면 콘센트에서 배터리까지의 **충전 손실만큼 가구는 계통에서 더 산다** — "
        f"그래서 이 표의 값은 대장 `{EV_LOAD_LEDGER_KEY}`({battery_side})보다 "
        "**크다**",
        *_loss_applied_lines(loss_row),
        # ★ R68/WP-9 — **문면을 좁힌다** (독립 검증 결함 #5). 「재료가 없다」는
        #   넓은 말이 *저장소에 같은 이름의 수가 있다는 사실*을 가렸다. 그
        #   사실을 적되 ⛔ **그 수를 끌어다 쓰지 않는다** — 경계가 다르다.
        "- ⚠ **저장소에 `charge_efficiency` 라는 이름의 수도 있다** — "
        "`core/der/ev_v2g.py` 의 기본값 0.92 다. 그러나 그것은 **V2G 자원의 배터리 "
        "왕복 효율 기본값**이지 이 부하의 계측 경계가 아니고 대장 항목도 아니다 — "
        "이 산식이 나누는 수는 **벽면 콘센트에서 배터리까지**의 편도 손실이다. "
        "⛔ 이름이 같다고 끌어다 쓰면 **다른 경계의 수가 섞이고, 섞였다는 사실이 "
        "사라진다**",
        "- 항의 수(대수 · 연간 주행거리 · 전비)는 **대장 항목이 아니라** 그 키의 "
        "산출근거 안에 있다 — 여기 옮겨 적으면 대장이 바뀌는 날 이 줄만 옛말을 하므로 "
        "**꼴만 세우고 수는 가리킨다**. ⚠ **충전 손실률만 다르다** — 그것은 "
        f"대장 항목 `{EV_CHARGING_LOSS_LEDGER_KEY}` 이므로 수를 그 행에서 읽어 "
        "인쇄한다",
        "",
    ]


def _loss_applied_lines(loss_row: AssumptionRow | None) -> list[str]:
    """충전 손실률이 **곱해졌는가** — 대장이 그 항목을 갖는지로 갈린다 (R71/WP-1).

    ⚠⚠ **두 갈래를 한 문장으로 뭉치지 않는다.** 「반영했다」와 「대장이 항목을
    갖지 않아 반영하지 않았다」는 산출물을 읽는 사람에게 **다른 사실**이고,
    한쪽 문면으로 둘을 덮으면 그 차이가 사라진다.
    """
    if loss_row is None:
        return [
            "- ⛔ **충전 손실률이 반영되지 않았다 — 대장에 "
            f"`{EV_CHARGING_LOSS_LEDGER_KEY}` 행이 없다.** 이 값은 배터리 투입 "
            "기준 그대로이며 가구가 계통에서 사는 전기보다 **작다.** ⚠ 이것은 "
            "「손실이 0 이다」가 아니라 **「아직 세우지 않았다」**이다",
        ]
    return [
        f"- ★ **충전 손실률 {loss_row.value:g} 이 반영됐다** — 대장 "
        f"`{EV_CHARGING_LOSS_LEDGER_KEY}`(「{EV_CHARGING_LOSS_TITLE}」 · "
        f"신뢰도 **{loss_row.confidence}**)에서 읽었고, 환산은 "
        "`core/casegrid/appliance_load.py::with_ledger_defaults` 가 "
        "`대장 값 ÷ (1 − 손실률)` 로 한다. ⚠ **곱하기가 아니라 나누기다** — "  # noqa: RUF001
        "손실이 있으면 같은 양을 배터리에 넣기 위해 계통에서 **더 사야** 한다",
        "- ⚠⚠ **그 수는 조사값이 아니라 관례치 가정이다.** **이 단지의** 충전 "
        "손실을 잰 값이 없다 — 완속·급속 비율과 충전기 효율을 아무도 모른다. "
        "그래서 그 수를 조사값에 곱해 넣지 않고 **자기 이름을 단 대장 항목**으로 "
        f"세웠다: 위 ⓑ 부분 표에 `{EV_LOAD_LEDGER_KEY}`(조사값)와 "
        f"`{EV_CHARGING_LOSS_LEDGER_KEY}`(가정)가 **두 행으로** 나란히 선다. "
        "한 수로 섞으면 어느 쪽이 조사이고 어느 쪽이 가정인지 사라진다",
        "- ⚠ **민감도 폭이 없다**(`low = base = high`). 폭을 적으면 그 폭이 "
        "관측에서 나온 것처럼 읽히는데 **관측이 없다** — 「민감하지 않다」가 "
        "아니라 **「폭을 주장할 근거가 없다」**이다. 충전 인프라 구성이 정해지면 "
        "그때 실측 범위가 폭을 준다",
    ]


def _heatpump_breakdown_lines() -> list[str]:
    """히트펌프 분해 — 대장 하위 항목 셋은 섰다. 열량·COP 별도 열은 여전히
    멈춘 자리다 (검토서 §3.1 · R71/WP-2).

    ⚠ **이 함수는 종전에 「그 셋은 대장 항목이 아니다」라고 적었다** — R71/WP-2 가
    `load.heatpump.{heating,cooling,hotwater}.annual` 을 세웠으므로 그 문장은
    이제 거짓이다. ⇒ 사실을 갱신하되, **열량·COP 를 별도 열로 두는 것**은 여전히
    막혀 있다 — 새 항목 셋은 **전력량만** 갖고 열량·COP 는 여전히 산문
    (`derivation_method`) 안에만 있어, 이 표에 그 둘을 열로 더하려면 새 대장
    필드나 새 표 구조가 필요하다(WP-2 §5 — 그 재설계는 이 WP 범위 밖이라 멈추고
    사람에게 물었다).
    """
    return [
        f"**{HEATPUMP_LOAD_TITLE} — 난방·냉방·급탕 분해** (검토서 §3.1 · R71/WP-2)",
        "",
        "- ★ **대장 하위 항목 셋이 섰다** — `load.heatpump.heating.annual`"
        "(2,075) · `load.heatpump.cooling.annual`(712.4) · "
        "`load.heatpump.hotwater.annual`(501.6). 값·단위·출처·계측 경계는 위 "
        "ⓑ 부분 표(접두 `load.*`)와 4단계 ⓑ 전건 표에 **이미 인쇄된다** — 그 "
        "표는 대장을 접두로 거를 뿐이므로 항목을 세우는 것만으로 저절로 세 줄이 "
        "늘었다(새 렌더 코드가 필요하지 않았다)",
        f"- ⛔ **계산 경로는 바뀌지 않았다.** 러너가 읽는 자리는 여전히 "
        f"`{HEATPUMP_LOAD_LEDGER_KEY}` 하나이고, 세 하위 항목은 **표시·독립 "
        "민감도 전용**이다 — 세 base 의 합이 그 항목의 값과 어긋나면 일관성 "
        "시험이 잡는다(`tests/casegrid/test_appliance_load.py::"
        "test_heatpump_subitem_sensitivities_sum_to_the_parent`)",
        "- ⛔ **열량 · COP 를 서로 다른 열로 두는 것(검토서 §3.1)은 여전히 "
        "멈춘 자리다.** 새로 세운 세 항목은 **전력량(kWh(e))만** 갖는다 — "
        "열량(kWh(th))과 COP 는 대장 항목이 아니라 여전히 산문 안에만 있다. "
        "이 표에 그 둘을 열로 더하려면 **새 대장 필드 또는 새 표 구조**가 "
        "필요해 「기존 칸만 채운다」는 이 WP 의 범위를 넘고, 그 설계는 **사람의 "
        "판정으로 남긴다**",
        "",
    ]


def _verification_state_lines() -> list[str]:
    """검증 상태가 **왜 이 표에 없는가** — 멈춘 자리 (검토서 §4.4)."""
    return [
        "**검증 상태(계산됨 · 출처 확인 · 조사 인용 · 가정)는 대장이 갖고 있지 않다** "
        "(검토서 §4.4 · 사람의 판정 대기)",
        "",
        "- 대장이 갖는 축은 부기의 `confidence` 하나이고 그 눈금은 **확정 · 추정 · "
        "가정** 셋이다. 그것은 *「얼마나 단단한가」*를 묻지 *「원문을 열어 대조했는가」*를 "
        "묻지 않는다 — 아래 ⓑ 부분 표와 4단계 ⓑ 전건 표의 「신뢰도」 열이 그 "
        "축이다",
        "- ⛔ **셋을 넷으로 재해석해 인쇄하지 않았다.** 「가정」을 「조사 인용」으로, "
        "「추정」을 「출처 확인」으로 옮겨 적는 것은 **근거 등급의 승격**이며, 승격된 "
        "등급은 검토자에게 **확인된 사실**로 읽힌다 — 그 확인은 일어나지 않았다",
        "- ⇒ **대장에 검증 상태 칸을 세울 것인가**는 부기 항목의 확장이므로, 인쇄하지 "
        "않고 **사람의 판정으로 남긴다**",
    ]
