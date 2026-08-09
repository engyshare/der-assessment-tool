"""Jinja2 rendering entry points for the WP-12 web UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_ROOT = Path(__file__).resolve().parent
_ENV = Environment(
    loader=FileSystemLoader(_ROOT / "templates"),
    autoescape=select_autoescape(("html", "xml")),
)


def demo_context() -> dict[str, Any]:
    """Return deterministic UI data used by template tests and early integration."""
    supported = 1_250_000
    baseline = 980_000
    return {
        "scenario_name": "에너지자립가구 기본안",
        "inputs": (
            {
                "id": "pv_kw",
                "label": "태양광 용량",
                "value": "12",
                "unit": "kW",
                "help": "설비 정격 출력입니다.",
                "source": "기술 카탈로그 기본값",
                "step": "0.1",
            },
            {
                "id": "annual_generation",
                "label": "연간 발전량",
                "value": "15800",
                "unit": "kWh",
                "help": "1년 동안 생산되는 전력량입니다.",
                "source": "시뮬레이션 결과",
                "step": "1",
            },
            {
                "id": "tariff",
                "label": "전력 단가",
                "value": "162",
                "unit": "원/kWh",
                "help": "자가소비 편익 계산에 쓰는 명목 단가입니다.",
                "source": "전제 대장",
                "step": "0.1",
            },
            {
                "id": "discount_rate",
                "label": "할인율",
                "value": "4.5",
                "unit": "%",
                "help": "현재가치 환산에 쓰는 사회적 할인율입니다.",
                "source": "전제 대장",
                "step": "0.1",
            },
            {
                "id": "analysis_years",
                "label": "분석 기간",
                "value": "20",
                "unit": "년",
                "help": "현금흐름을 계산하는 기간입니다.",
                "source": "사업 기본 설정",
                "step": "1",
            },
        ),
        "assumptions": (
            {
                "label": "전력 단가",
                "value": "162원/kWh",
                "impact": "+270,000원",
            },
            {
                "label": "할인율",
                "value": "4.5%",
                "impact": "-80,000원",
            },
        ),
        "result_cards": (
            {
                "metric": "NPV",
                "supported": supported,
                "baseline": baseline,
                "delta": supported - baseline,
                "unit": "원",
            },
            {
                "metric": "IRR",
                "supported": 8.2,
                "baseline": 6.7,
                "delta": 1.5,
                "unit": "%",
            },
        ),
        "influences": (
            {"rank": 1, "name": "전력 단가", "impact": 270_000},
            {"rank": 2, "name": "할인율", "impact": -80_000},
            {"rank": 3, "name": "초기 투자비", "impact": -55_000},
        ),
        "errors": (
            {
                "field": "태양광 용량",
                "reason": "0보다 커야 합니다.",
                "action": "설비 용량을 kW 단위 양수로 입력하십시오.",
            },
        ),
        "regulation_versions": (
            {"name": "재생에너지 우선공급", "version": "v2026.1", "diff": "의무공급 기준 갱신"},
        ),
    }


def render_dashboard(context: dict[str, Any] | None = None) -> str:
    """Render the main dashboard template."""
    template = _ENV.get_template("dashboard.html")
    return template.render(context or demo_context())

