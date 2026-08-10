"""엑셀 심의자료 생성 — FR-1003-AC1.

이전 구현(12줄)은 워크북을 만들지 않고 `IRR` 결과를 리터럴 딕셔너리로
박아 두고 있었다(`.orch/R13-WP24E-대장.md`). 여기서는 `openpyxl`로
**실제 워크북**을 만들고, 조항이 요구하는 대로 시트를 분리하며(입력·
프로포마·시계열·결과), 주요 계산(현재가치·NPV 합계)은 **셀 수식**으로
쓴다 — 값만 박으면 「기존 엑셀 검토 방식과 병행」(조항 원문)이 성립하지
않는다.

`IRR`은 예외다. spec §15.4 TU-7 결정("수식 포함 XLSX 생성 시 복잡 산식
(IRR·할인회수기간)의 셀 수식 표현 한계 → 표현 불가 항목은 값 + 산식
주석 병기로 대체")에 따라 순환 계산인 IRR은 셀 수식이 아니라 **값 +
셀 주석**으로 담는다.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Final

from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.comments import Comment  # type: ignore[import-untyped]

from core.contracts.units import to_won

_SHEET_INPUT: Final[str] = "입력"
_SHEET_PROFORMA: Final[str] = "프로포마"
_SHEET_TIMESERIES: Final[str] = "시계열"
_SHEET_RESULTS: Final[str] = "결과"

_PROFORMA_FIRST_DATA_ROW: Final[int] = 2


def _write_input_sheet(ws: Any, discount_rate: float) -> None:
    ws["A1"] = "할인율"
    ws["B1"] = discount_rate


def _write_proforma_sheet(ws: Any, annual_cashflows_won: Sequence[Decimal | int]) -> int:
    """연도별 현금흐름과 현재가치(셀 수식)를 쓰고, NPV 합계 행 번호를 반환한다."""
    ws["A1"], ws["B1"], ws["C1"] = "연도", "현금흐름(원)", "현재가치(원)"

    for offset, cashflow in enumerate(annual_cashflows_won):
        row = _PROFORMA_FIRST_DATA_ROW + offset
        year = offset + 1
        ws.cell(row=row, column=1, value=year)
        ws.cell(row=row, column=2, value=int(to_won(cashflow)))
        # 현재가치 = 현금흐름 / (1+할인율)^연도 — 입력 시트의 할인율을 참조하는 실제 셀 수식
        ws.cell(row=row, column=3, value=f"=B{row}/(1+{_SHEET_INPUT}!$B$1)^A{row}")

    last_data_row = _PROFORMA_FIRST_DATA_ROW + len(annual_cashflows_won) - 1
    npv_row = last_data_row + 2
    ws.cell(row=npv_row, column=2, value="NPV 합계")
    ws.cell(
        row=npv_row, column=3, value=f"=SUM(C{_PROFORMA_FIRST_DATA_ROW}:C{last_data_row})"
    )
    return npv_row


def _write_timeseries_sheet(ws: Any, hourly_dispatch_kwh: Sequence[float]) -> None:
    ws["A1"], ws["B1"] = "시간(h)", "전력량(kWh)"
    for offset, kwh in enumerate(hourly_dispatch_kwh):
        row = _PROFORMA_FIRST_DATA_ROW + offset
        ws.cell(row=row, column=1, value=offset + 1)
        ws.cell(row=row, column=2, value=kwh)


def _write_results_sheet(ws: Any, npv_row: int, irr: float) -> None:
    ws["A1"], ws["B1"] = "NPV(원)", f"={_SHEET_PROFORMA}!C{npv_row}"

    ws["A2"] = "IRR"
    irr_cell = ws["B2"]
    irr_cell.value = irr
    irr_cell.comment = Comment(
        "spec §15.4 TU-7: IRR은 순환 계산이라 셀 수식으로 표현할 수 없어 "
        "값 + 주석으로 대체한다. 산식: 현금흐름의 NPV가 0이 되는 할인율.",
        "core.report.excel",
    )


def generate_excel(
    annual_cashflows_won: Sequence[Decimal | int],
    discount_rate: float,
    irr: float,
    hourly_dispatch_kwh: Sequence[float] = (),
) -> bytes:
    """CBA 결과로 실제 엑셀 워크북 바이트를 만든다 (FR-1003-AC1).

    시트: 입력·프로포마·시계열·결과. NPV는 프로포마 시트의 현재가치
    합계를 참조하는 셀 수식이고, IRR만 TU-7 결정에 따라 값+주석이다.
    호출부가 파일 경로 대신 `tmp_path`나 `io.BytesIO`로 이 바이트를
    받아 검증하면 저장소에 파일이 남지 않는다.
    """
    workbook = Workbook()
    input_ws = workbook.active
    input_ws.title = _SHEET_INPUT
    _write_input_sheet(input_ws, discount_rate)

    proforma_ws = workbook.create_sheet(_SHEET_PROFORMA)
    npv_row = _write_proforma_sheet(proforma_ws, annual_cashflows_won)

    timeseries_ws = workbook.create_sheet(_SHEET_TIMESERIES)
    _write_timeseries_sheet(timeseries_ws, hourly_dispatch_kwh)

    results_ws = workbook.create_sheet(_SHEET_RESULTS)
    _write_results_sheet(results_ws, npv_row, irr)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
