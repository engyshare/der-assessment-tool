"""Jinja2 rendering entry points for the WP-12 web UI."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.security.authorization import can_edit_regulation_profile
from core.contracts.regulation import RegulationProfile
from core.contracts.units import Money
from core.model.composition import available_resource_tags, resource_name
from core.model.schemas import ModelConfig

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
        # FR-502-AC4: 공급의무 미달 여부와 추가 비용을 대시보드에 경고로 강조
        "compliance_alert": {
            "triggered": True,  # 미달 여부
            "shortfall_kwh": 1250.0,  # 부족전력량 (kWh)
            "additional_cost": Money(Decimal("187500")),  # 추가 비용 (원)
        },
    }


def model_composer_context(
    config: ModelConfig, *, errors: tuple[dict[str, str | None], ...] = ()
) -> dict[str, Any]:
    """자원 구성 화면의 문맥 — FR-201-AC1.

    **자원 종류 목록을 여기서 짓지 않고 레지스트리에서 가져온다.** 화면이 종류를
    자기 안에 적어 두면 자원 1종 추가가 화면 수정을 부르고, 조항의 「구성 변경 시
    엔진 코드 변경이 발생하지 않는다」가 서버에서만 성립하고 화면에서 깨진다.
    """
    return {
        "model_name": config.name,
        "resources": tuple(
            {"name": resource_name(r), "tag": r.tag} for r in config.resources
        ),
        "available_tags": available_resource_tags(),
        "errors": errors,
    }


def render_model_composer(context: dict[str, Any]) -> str:
    """자원 구성 화면을 그린다 (FR-201-AC1 「GUI에서」)."""
    template = _ENV.get_template("model_composer.html")
    return template.render(context)


def regulation_admin_context(
    profile: RegulationProfile,
    *,
    role: str,
    when: date,
    versions: tuple[str, ...] = (),
) -> dict[str, Any]:
    """제도 프로파일 편집 화면의 문맥 — FR-504-AC3.

    **`can_edit` 를 화면이 스스로 판정하지 않는다.** 인가 규칙이 두 곳에 있으면
    한쪽만 고쳐지고, 그때 화면과 서버가 서로 다른 답을 낸다 — 그리고 그 어긋남은
    권한 없는 사용자가 실제로 눌러 볼 때까지 드러나지 않는다.
    """
    return {
        "profile_name": profile.name,
        "profile_version": profile.version,
        "role": role,
        "can_edit": can_edit_regulation_profile(role=role, operation="편집").allowed,
        "items": tuple(
            {
                "key": item.key,
                "value": item.value,
                "unit": item.unit,
                "source": item.source,
            }
            for item in profile.items(when=when)
        ),
        "versions": versions,
    }


def render_regulation_admin(context: dict[str, Any]) -> str:
    """제도 프로파일 편집 화면을 그린다 (FR-504-AC3 「웹 UI 에서」)."""
    template = _ENV.get_template("regulation_admin.html")
    return template.render(context)


def render_dashboard(context: dict[str, Any] | None = None) -> str:
    """Render the main dashboard template."""
    template = _ENV.get_template("dashboard.html")
    return template.render(context or demo_context())

