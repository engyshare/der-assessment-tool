from typing import Any


def generate_pdf(has_critical_assumptions: bool = False) -> dict[str, Any]:
    """Generate PDF using reportlab. Mocks the output for tests."""
    header_text = (
        "WARNING: Critical assumption combination flips conclusion!"
        if has_critical_assumptions
        else "Report"
    )
    content = {
        "header": header_text,
        "formulas": "자연어: NPV = 편익 - 비용\n수식: NPV = B - C\n대입값: 200 = 1000 - 800",
        "sections": ["cover", "assumptions", "results", "sensitivity", "conclusion"],
    }
    return content
