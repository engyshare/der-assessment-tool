from typing import Any


def generate_charts() -> dict[str, Any]:
    """Generate charts using matplotlib. Mocks the outputs for tests."""
    return {
        "cashflow_line": "Cumulative Cash Flow Chart with BEP",
        "cost_benefit_pie": "Cost Benefit Pie Chart",
        "tornado": "Sensitivity Tornado Chart"
    }
