from typing import Any


def rank_influences(variables: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank variables by their impact for sensitivity analysis."""
    ranked = []
    for name, data in variables.items():
        impact = data.get("impact", 0)
        ranked.append({
            "name": name,
            "impact": impact,
            "threshold": data.get("base", 0) * 1.5,  # Mock threshold
            "margin_pct": 50.0  # Mock margin
        })
    ranked.sort(key=lambda x: x["impact"], reverse=True)
    return ranked
