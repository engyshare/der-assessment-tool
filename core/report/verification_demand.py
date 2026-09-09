"""검증 1단계 — 수요 입력마다 **여섯 속성**을 세우고, 대장이 갖지 않은 것은
**「갖지 않았다」고 적는다** (R68/WP-7 · 검토서 §3.1 · §4.2 · §4.4).

## 무엇이 없었나

1단계는 두 표를 갖고 있었다 — 「이 실행이 받은 입력」(값과 통로)과 대장 전건
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

## ⚠⚠ 「÷ 충전효율」은 보이되 곱해지지 않는다

대장이 스스로 적었다 — *「⛔ 손실 계수를 지어내 곱하지 않았다 … 이 값은 배터리
투입 기준이다」*. 그래서 산식 문면에는 그 항이 **`[충전효율: 미반영]` 으로 서
있고 어떤 수도 곱해지지 않는다.** `0.9` 로 나누면 조사값에 가정이 섞이고 그
사실이 산출물에서 사라진다 — **없는 것은 없는 채로** 두는 것이 사람 몫으로
남은 판정이다.

⚠ 그 문면이 대장에서 사라지면 이 모듈의 계측 경계 절이 **거짓말이 된다.** 문면을
파싱해 인쇄하는 대신 **시험이 대장을 붙든다**
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
    EV_LOAD_LEDGER_KEY,
    EV_LOAD_TITLE,
    HEATPUMP_LOAD_LEDGER_KEY,
    HEATPUMP_LOAD_TITLE,
)
from core.report._format import _cell
from core.report.case_report import AssumptionRow, CaseReport
from core.report.verification_scaleup import (
    ESTATE_LOAD_UNIT,
    HOUSEHOLD_LOAD_LEDGER_KEY,
    household_base_kwh,
)

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
    "{total} = 대수 × 연간 주행거리 ÷ 전비 ÷ [충전효율: **미반영**]"  # noqa: RUF001
)

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
            derivation=EV_DERIVATION_SHAPE.format(total=ev_total),
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
        *_ev_boundary_lines(ev_total),
        *_heatpump_breakdown_lines(),
        *_verification_state_lines(),
    ]


def _ev_boundary_lines(ev_total: str) -> list[str]:
    """전기차 — 산식과 **계측 경계**를 글자로 못 박는다 (검토서 §3.1)."""
    return [
        f"**{EV_LOAD_TITLE} — 산식과 계측 경계** (검토서 §3.1)",
        "",
        "```",
        EV_DERIVATION_SHAPE.format(total=ev_total).replace("**", ""),
        "```",
        "",
        "- **계측 경계 — 배터리 투입 기준이다.** 전비는 배터리에서 나간 전기로 "
        "주행거리를 나눈 수이고, 벽면 콘센트에서 배터리까지의 **충전 손실이 빠져 "
        "있다** — 그래서 이 값은 가구가 계통에서 사는 전기보다 **작다**",
        "- ⛔ **충전효율을 지어내 나누지 않았다.** **이 단지의** 충전 손실을 잰 값이 "
        "없다 — 완속·급속 비율과 충전기 효율을 아무도 모르며, 계수를 곱하면 조사값에 "
        "가정이 섞이고 **섞였다는 사실이 산출물에서 사라진다.** 그래서 산식에 그 항이 "
        "**보이되 어떤 수도 곱해지지 않는다**",
        # ★ R68/WP-9 — **문면을 좁힌다** (독립 검증 결함 #5). 「재료가 없다」는
        #   넓은 말이 *저장소에 같은 이름의 수가 있다는 사실*을 가렸다. 그
        #   사실을 적되 ⛔ **그 수를 끌어다 쓰지 않는다** — 경계가 다르다.
        "- ⚠ **저장소에 `charge_efficiency` 라는 이름의 수는 있다** — "
        "`core/der/ev_v2g.py` 의 기본값 0.92 다. 그러나 그것은 **V2G 자원의 배터리 "
        "왕복 효율 기본값**이지 이 부하의 계측 경계가 아니고 대장 항목도 아니다 — "
        f"이 산식이 나눌 수는 벽면 콘센트에서 배터리까지의 손실이며 대장 "
        f"`{EV_LOAD_LEDGER_KEY}` 에 곱해질 것이다. ⛔ 이름이 같다고 끌어다 쓰면 "
        "**다른 경계의 수가 조사값에 섞이고, 섞였다는 사실이 사라진다**",
        "- ⇒ 충전효율의 계측 경계가 정해지지 않아 **미해결**이다. 정해지는 날 곱하는 "
        f"자리는 이 표가 아니라 대장 `{EV_LOAD_LEDGER_KEY}` 다",
        "- 항의 수(대수 · 연간 주행거리 · 전비)는 **대장 항목이 아니라** 그 키의 "
        "산출근거 안에 있다 — 여기 옮겨 적으면 대장이 바뀌는 날 이 줄만 옛말을 하므로 "
        "**꼴만 세우고 수는 가리킨다**",
        "",
    ]


def _heatpump_breakdown_lines() -> list[str]:
    """히트펌프 분해가 **왜 이 표에 없는가** — 멈춘 자리 (검토서 §3.1)."""
    return [
        f"**{HEATPUMP_LOAD_TITLE} — 난방·냉방·급탕 분해는 이 표에 없다** "
        "(검토서 §3.1 · 사람의 판정 대기)",
        "",
        f"- 그 셋은 **대장 항목이 아니다.** 대장에 선 히트펌프 부하 항목은 "
        f"`{HEATPUMP_LOAD_LEDGER_KEY}` **하나**이고, 난방·냉방·급탕은 그 한 항목의 "
        "**산출근거 안에만** 있다",
        "- ⛔ **그 산문을 갈라 표로 만들지 않았다.** 문면이 바뀌는 날 표는 조용히 "
        "틀리고, 틀린 표가 「분해해서 검증했다」로 읽힌다",
        "- 열량 · COP · 전력량을 서로 다른 열로 두는 것(검토서 §3.1)도 같은 자리에서 "
        "멈춘다 — COP 역시 그 산출근거 안이며 대장 항목이 아니다",
        "- ⇒ **대장에 하위 셋을 세울 것인가**는 대장 편집이고 민감도 세 수준이 함께 "
        "걸리므로, 인쇄하지 않고 **사람의 판정으로 남긴다**",
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
        "묻지 않는다 — 위 ⓑ 표의 「신뢰도」 열이 그 축이다",
        "- ⛔ **셋을 넷으로 재해석해 인쇄하지 않았다.** 「가정」을 「조사 인용」으로, "
        "「추정」을 「출처 확인」으로 옮겨 적는 것은 **근거 등급의 승격**이며, 승격된 "
        "등급은 검토자에게 **확인된 사실**로 읽힌다 — 그 확인은 일어나지 않았다",
        "- ⇒ **대장에 검증 상태 칸을 세울 것인가**는 부기 항목의 확장이므로, 인쇄하지 "
        "않고 **사람의 판정으로 남긴다**",
    ]
