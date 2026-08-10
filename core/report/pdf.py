"""PDF 심의자료 생성 — FR-1001-AC2~AC4 · FR-1002-AC3·AC5·AC6 · FR-1003-AC2.

이전 구현(16줄)은 산식 3중 표기(자연어·수식·대입값)를 문자열로 박아 두고
`reportlab` 은 이름만 적혀 있었다(`rslt/inspect-phase1-final.md:19`). 그
결과 테스트는 구현이 심어 둔 단어를 구현에 되물어 항상 참인 동어반복이었다.

여기서는 대입값 줄을 **인자로 받은 실제 편익·비용에서 계산**하고,
`reportlab` 으로 **실제 PDF 바이트**를 산출한다. 본문이 한글이므로
표준 Latin-1 폰트(Helvetica)로는 자연어 줄을 그릴 수 없어, 한글이 섞인
줄에는 reportlab 내장 CID 폰트(`HYSMyeongJo-Medium`, 외부 폰트 파일 불요)를
쓴다. 헤더·섹션명은 영문(ASCII)이라 Helvetica로 그린다 — 그래서 경고
문구(FR-1002-AC6)가 실제 PDF 바이트에서도 그대로 검색된다.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any, Final

from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from core.contracts.units import to_won

_KOREAN_FONT: Final[str] = "HYSMyeongJo-Medium"
_LATIN_FONT: Final[str] = "Helvetica"
_SECTIONS: Final[tuple[str, ...]] = (
    "cover",
    "assumptions",
    "results",
    "sensitivity",
    "conclusion",
)
_WARNING_HEADER: Final[str] = "WARNING: Critical assumption combination flips conclusion!"
_DEFAULT_HEADER: Final[str] = "Report"

pdfmetrics.registerFont(UnicodeCIDFont(_KOREAN_FONT))


def _build_formulas(benefit_won: Decimal | int, cost_won: Decimal | int) -> str:
    """산식 3중 표기를 실제 편익·비용 값에서 만든다. 대입값은 to_won() 결과다."""
    benefit = to_won(benefit_won)
    cost = to_won(cost_won)
    npv = to_won(benefit - cost)
    lines = (
        "자연어: NPV = 편익 - 비용",
        "수식: NPV = B - C",
        f"대입값: {npv} = {benefit} - {cost}",
    )
    return "\n".join(lines)


def _render_pdf_bytes(header: str, formulas: str, sections: tuple[str, ...]) -> bytes:
    """헤더·산식·섹션 목록으로 실제 PDF 바이트를 그린다."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    _, height = A4
    y = height - 50.0

    pdf.setFont(f"{_LATIN_FONT}-Bold", 14)
    pdf.drawString(50, y, header)
    y -= 30.0

    pdf.setFont(_KOREAN_FONT, 11)
    for line in formulas.splitlines():
        pdf.drawString(50, y, line)
        y -= 18.0
    y -= 12.0

    pdf.setFont(_LATIN_FONT, 11)
    for section in sections:
        pdf.drawString(50, y, f"- {section}")
        y -= 16.0

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def generate_pdf(
    benefit_won: Decimal | int = Decimal("1000"),
    cost_won: Decimal | int = Decimal("800"),
    has_critical_assumptions: bool = False,
) -> dict[str, Any]:
    """PDF 심의자료를 만든다. `pdf_bytes` 는 reportlab이 실제로 그린 결과다.

    산식 3중 표기의 대입값 줄은 `benefit_won`·`cost_won` 에서 계산되며,
    호출부가 값을 바꾸면 `formulas` 와 `pdf_bytes` 모두 그에 따라 바뀐다.
    """
    header_text = _WARNING_HEADER if has_critical_assumptions else _DEFAULT_HEADER
    formulas = _build_formulas(benefit_won, cost_won)
    sections = list(_SECTIONS)
    pdf_bytes = _render_pdf_bytes(header_text, formulas, _SECTIONS)
    return {
        "header": header_text,
        "formulas": formulas,
        "sections": sections,
        "pdf_bytes": pdf_bytes,
    }
