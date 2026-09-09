"""대장 행을 **표로 인쇄하는 한 자리** — 전건 표와 부분 표가 같은 서식을 쓴다
(R69/WP-1 · 검토서 §3.1).

## 왜 이 모듈이 생겼나

단계 승격 9 → 10 이 옛 1단계를 **1「가구 수요」와 4「경제성 입력」으로 갈랐고**,
그 결과 같은 `report.assumptions` 표가 **세 번** 인쇄된다:

    1단계 ⓑ   접두 `load.*` · `design.*` 의 **부분 표**
    4단계 ⓐ   접두 `tariff.*` · `benefit.rec*` 의 **부분 표** (요금 · REC 단가)
    4단계 ⓑ   **전건 표** — 「1 의 나머지」이며 한 자리에 모여 있어야 한다

세 자리가 각자 f-문자열로 일곱 열을 적으면 열이 갈리는 날 한 표만 낡고, 갈려도
표는 멀쩡해 보인다. ⇒ **인쇄 규칙은 여기 하나**이고 **고르는 규칙은 부르는
쪽**이 갖는다(수요는 `verification_demand.py` · 경제성은
`verification_economics.py`).

## ⛔ 행을 짓지도 값을 다시 계산하지도 않는다

부분 표는 **「고르는 것」이지 「새로 만드는 것」이 아니다** — 같은
`report.assumptions` 행을 접두로 걸러 인쇄한다. 값·단위·기준연도·출처·신뢰도·
최종확인일은 전부 `AssumptionRow` 가 이미 나른 것이며, 여기서 한 칸도 짓지
않는다. 지으면 같은 대장 항목이 두 단계에서 다른 수로 인쇄될 수 있다.

## ⚠⚠ `_cell()` 접기를 **모든 칸에** 건다

대장 `source` · `derivation_method` 의 산문에 **줄바꿈이 들어 있어** 표의 그
행이 마크다운에서 여러 줄로 쪼개져 **표에서 튕겨 나간 적이 있다**(R68/WP-7
실측 · `docs/assumptions.yaml::load.heatpump.annual`). 대장은 고치지 않는다 —
값의 문제가 아니라 «인쇄»의 문제이고, 접는 자리는
`core/report/_format.py::_cell` 하나다.

⚠ **값 칸에도 건다** — 대장의 값은 스칼라이나 참조형이 문자열로 올 수 있고,
그 문자열이 `|` 를 물면 같은 자리에서 표가 깨진다.

## ⚠ 부분 표가 **비면 그 사실을 적는다**

빈 표를 인쇄하면 머리 두 줄만 서고, 읽는 눈은 그것을 「대장에 그 접두가 없다」와
「거르는 규칙이 틀렸다」로 구별할 수 없다(`core/report/_format.py::NO_VALUE` 가
같은 사유를 적는다).
"""
from __future__ import annotations

from collections.abc import Sequence

from core.report._format import _cell, _date, _num
from core.report.case_report import AssumptionRow, CaseReport

#: 대장 표의 머리 두 줄 — **일곱 열이 여기 한 곳에서만 정해진다.**
LEDGER_TABLE_HEAD: tuple[str, str] = (
    "| 키 | 값 | 단위 | 기준연도 | 출처 | 신뢰도 | 최종확인일 |",
    "|---|---|---|---|---|---|---|",
)

#: 접두에 걸리는 행이 없을 때의 줄. **빈 표를 세우지 않는다**(머리말 ⚠).
NO_LEDGER_ROW = (
    "이 실행의 분석 설정 대장에 이 접두로 시작하는 항목이 없다 — 값이 비어 있는 "
    "항목은 애초에 이 목록에 오지 않으므로, 대장이 그 항목을 갖지 않았거나 값을 "
    "아직 채우지 않았다는 뜻이다"
)


def _value_cell(row: AssumptionRow) -> str:
    """값 칸 — 수는 `_num` 이 서식하고 그 밖은 접는다(머리말 ⚠)."""
    if isinstance(row.value, int | float):
        return _num(row.value)
    return _cell(str(row.value))


def ledger_row(row: AssumptionRow) -> str:
    """대장 한 행 — 일곱 칸. **여기서 값을 고치지 않는다.**"""
    return (
        f"| `{row.key}` | {_value_cell(row)} "
        f"| {_cell(row.value_unit or '')} | {_cell(str(row.base_year or ''))} | "
        f"{_cell(row.source or '')} | {_cell(row.confidence)} | "
        f"{_date(row.verified_at)} |"
    )


def ledger_table(rows: Sequence[AssumptionRow]) -> list[str]:
    """대장 표 하나 — 행이 없으면 **표 대신 문장**이다(머리말 ⚠)."""
    if not rows:
        return [NO_LEDGER_ROW]
    return [*LEDGER_TABLE_HEAD, *(ledger_row(row) for row in rows)]


def rows_with_prefix(
    report: CaseReport, prefixes: Sequence[str]
) -> tuple[AssumptionRow, ...]:
    """접두로 고른 대장 행 — **대장이 준 차례 그대로**다.

    ⚠ 다시 정렬하지 않는다. 전건 표(4단계 ⓑ)와 부분 표가 같은 행을 다른 차례로
    싣으면 두 표를 맞대 보는 눈이 같은 행을 두 번 찾아야 한다.
    """
    return tuple(
        row for row in report.assumptions if row.key.startswith(tuple(prefixes))
    )
