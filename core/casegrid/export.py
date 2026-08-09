from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from xml.sax.saxutils import escape

from core.casegrid.models import Case


@dataclass(frozen=True)
class ResultTable:
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "columns", tuple(self.columns))
        rows = tuple(MappingProxyType(dict(row)) for row in self.rows)
        object.__setattr__(self, "rows", rows)

    def to_csv(self) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=list(self.columns),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in self.rows:
            writer.writerow({column: row.get(column, "") for column in self.columns})
        return output.getvalue()

    def to_xlsx_bytes(self) -> bytes:
        rows: list[tuple[object, ...]] = [tuple(self.columns)]
        rows.extend(tuple(row.get(column, "") for column in self.columns) for row in self.rows)
        return _xlsx_workbook_bytes(tuple(rows))


def result_table(
    cases: Sequence[Case],
    metrics: Sequence[Mapping[str, float]],
) -> ResultTable:
    if len(cases) != len(metrics):
        raise ValueError("cases and metrics must have the same length")
    value_columns = sorted({name for case in cases for name in case.values})
    metric_columns = sorted({name for row in metrics for name in row})
    columns = ("case_index", *value_columns, *metric_columns)

    rows: list[Mapping[str, object]] = []
    for case, metric_row in zip(cases, metrics, strict=True):
        row: dict[str, object] = {"case_index": case.index}
        row.update(case.values)
        row.update(metric_row)
        rows.append(row)
    return ResultTable(columns=columns, rows=tuple(rows))


def _xlsx_workbook_bytes(rows: tuple[tuple[object, ...], ...]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", _xlsx_content_types_xml())
        workbook.writestr("_rels/.rels", _xlsx_root_relationships_xml())
        workbook.writestr("xl/workbook.xml", _xlsx_workbook_xml())
        workbook.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_relationships_xml())
        workbook.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet_xml(rows))
    return buffer.getvalue()


def _xlsx_content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )


def _xlsx_root_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _xlsx_workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="results" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )


def _xlsx_workbook_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )


def _xlsx_sheet_xml(rows: tuple[tuple[object, ...], ...]) -> str:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(
            _xlsx_cell_xml(row_index=row_index, column_index=column_index, value=value)
            for column_index, value in enumerate(row, start=1)
        )
        row_xml.append(f'<row r="{row_index}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        f"{''.join(row_xml)}"
        "</sheetData>"
        "</worksheet>"
    )


def _xlsx_cell_xml(*, row_index: int, column_index: int, value: object) -> str:
    reference = f"{_xlsx_column_name(column_index)}{row_index}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{reference}"><v>{value}</v></c>'
    return (
        f'<c r="{reference}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
    )


def _xlsx_column_name(column_index: int) -> str:
    if column_index < 1:
        raise ValueError("xlsx column index is one-based")
    name = ""
    current = column_index
    while current:
        current, remainder = divmod(current - 1, 26)
        name = f"{chr(65 + remainder)}{name}"
    return name
