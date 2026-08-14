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
from core.model.parameters import ParameterKind, ParameterSpec, resource_parameters
from core.model.schemas import DERConfig, ModelConfig

_ROOT = Path(__file__).resolve().parent
_ENV = Environment(
    loader=FileSystemLoader(_ROOT / "templates"),
    autoescape=select_autoescape(("html", "xml")),
)


#: 고급 모드 화면이 그리는 데모 구성. **자원 종류와 파라미터를 여기서 짓지
#: 않는다** — 종류는 레지스트리가, 파라미터는 `core.model.parameters` 카탈로그가
#: 정본이며 여기는 「어떤 자원을 몇 개 놓았는가」만 정한다.
DEMO_MODEL = ModelConfig(
    name="에너지자립가구 기본안",
    resources=[
        DERConfig(tag="PV", params={"name": "옥상 태양광", "capacity_kw": 12.0}),
        DERConfig(tag="ESS", params={"name": "공용 ESS", "capacity_kwh": 30.0}),
    ],
)


def advanced_mode_fields(config: ModelConfig) -> tuple[dict[str, Any], ...]:
    """고급 모드 화면의 **전체 파라미터** — UI-1-AC1.

    「전체」의 기준은 `core.model.parameters` 가 갖는다(레지스트리에 등록된 자원의
    생성자 시그니처). **이 함수는 그 목록을 줄이지 않는다** — 줄이면 화면이
    「전체」라고 적은 채 일부만 그리게 되고, 그 상태는 사용자가 없는 칸을 찾을
    때까지 드러나지 않는다.

    자원 **인스턴스마다** 한 벌씩 편다. 같은 `PV` 를 둘 놓으면 파라미터도 두
    벌이며, 종(種) 단위로 한 벌만 그리면 둘째 자원의 값을 고칠 방법이 없다.
    """
    fields: list[dict[str, Any]] = []
    for index, resource in enumerate(config.resources):
        for spec in resource_parameters(resource.tag):
            fields.append(_field(index, resource, spec))
    return tuple(fields)


def _field(index: int, resource: DERConfig, spec: ParameterSpec) -> dict[str, Any]:
    configured = resource.params.get(spec.name)
    if configured is not None:
        value, source = str(configured), "구성값"
    elif spec.required:
        value, source = "", "필수 입력 — 기본값 없음"
    else:
        value, source = spec.default_text, f"{spec.tag} 자원 기본값"
    return {
        # **화면 식별자는 자원 이름이 아니라 순번으로 짓는다** — 자원 이름은
        # 사용자가 짓는 자유 문자열이라 HTML id 로 쓸 수 없고, 같은 이름이 두 번
        # 나오지 않는다는 보장도 `composition` 안에서만 성립한다.
        "id": f"res{index}-{spec.name}",
        "parameter": f"{index}.{spec.name}",
        "label": f"{resource_name(resource)} · {spec.name}",
        "kind": str(spec.kind),
        "unit": spec.unit,
        "value": value,
        "source": source,
        "help": f"{spec.tag} 자원의 {spec.name} 입니다. 형식 {spec.type_text}.",
        # 정수·실수를 가리지 않고 `any` 다. 형식별로 가르면 그 규칙이 카탈로그의
        # 형식 판정과 갈리고, 갈린 뒤에도 화면은 멀쩡해 보인다.
        "step": "any",
        "scalar": spec.kind is ParameterKind.NUMBER,
    }


def demo_context() -> dict[str, Any]:
    """Return deterministic UI data used by template tests and early integration.

    ⚠ **`inputs` 와 `parameters` 는 다른 것이다.** `parameters` 는 고급 모드가 그리는
    **전체 파라미터**(카탈로그가 정본)이고, `inputs` 는 결과 화면의 「입력값 부록」이
    그리는 **결과를 낸 주요 입력의 요약**이다. 부록에 133개를 늘어놓으면 그것은
    부록이 아니다.
    """
    supported = 1_250_000
    baseline = 980_000
    return {
        "parameters": advanced_mode_fields(DEMO_MODEL),
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
