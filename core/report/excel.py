from typing import Any


def generate_excel() -> dict[str, Any]:
    """Generate Excel with openpyxl. Mocks the workbook structure for tests."""
    return {
        "IRR": {
            "type": "value_with_comment",
            "value": 0.05,
            "comment": "Formula: IRR calculations are replaced with value + comment per TU-7"
        }
    }
