"""Jinja2 rendering entry points for the WP-12 web UI."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.security.authorization import can_edit_regulation_profile
from app.services.ui_run import golden_scenario_names
from core.contracts.regulation import RegulationProfile
from core.contracts.units import Money
from core.model.composition import available_resource_tags, resource_name
from core.model.parameters import ParameterKind, ParameterSpec, resource_parameters
from core.model.schemas import DERConfig, ModelConfig
from web.render_run import (
    baseline_arrangement_choices,
    chart_figures,
    chart_query,
    error_context,
    pool_prerequisite_fields,
    run_error_context,
    run_result_context,
)

#: 이 모듈이 밖에 내놓는 이름. **재수출한 넷(`chart_query`·`error_context`·
#: `run_error_context`·`run_result_context`)이 여기 적힌 이유**를 적어 둔다.
#:
#: `R62/WP-9` 가 `web/render.py` 를 `NFR-206`(소스 파일 500줄) 안으로 되돌리며
#: 실행 화면 문맥을 `web/render_run.py` 로 갈랐다. 그런데 부르는 쪽은
#: `app/routers/ui.py`·`ui_forms.py`·`tests/app/`·`tests/web/` 에 흩어져 있고,
#: 독스트링도 `web/render.py::run_error_context` 처럼 **이 자리를 가리킨다.**
#: 부르는 쪽을 전부 고치는 길은 한 군데를 빠뜨려도 조용하지만, 이름을 여기
#: 남겨 두는 길은 빠뜨릴 자리가 없다 — 그래서 **재수출**로 이름을 유지한다.
#:
#: ⚠ 그 넷은 이 파일 안에서 쓰이지 않아 `ruff` 의 `F401` 에 걸린다.
#: 억제 주석(`noqa`)으로 덮지 않고 **여기 적어** 푸는 것이 그 규칙이 뜻하는 바다 —
#: 「안 쓰는 import」가 아니라 「내놓는 이름」이라고 말하는 자리가 `__all__` 이다.
__all__ = (
    "DEMO_MODEL",
    "UNLABELLED",
    "baseline_arrangement_choices",
    "chart_figures",
    "chart_query",
    "demo_context",
    "equipment_setting_fields",
    "equipment_setting_groups",
    "error_context",
    "model_composer_context",
    "pool_prerequisite_fields",
    "regulation_admin_context",
    "regulation_admin_view_context",
    "render_dashboard",
    "render_model_composer",
    "render_regulation_admin",
    "render_run_result",
    "run_error_context",
    "run_result_context",
)

_ROOT = Path(__file__).resolve().parent
_ENV = Environment(
    loader=FileSystemLoader(_ROOT / "templates"),
    autoescape=select_autoescape(("html", "xml")),
)


#: 라벨이 카탈로그에 없을 때 화면이 **글자로 인쇄하는 것**.
#:
#: ⚠⚠ **파라미터 이름으로 되돌아가지 않는다.** 되돌아가면 사용자가 지적한 그
#: 자리(`옥상 태양광 · azimuth_deg`)가 **조용히** 다시 나오고, 조용한 것은 사람이
#: 그 칸을 실제로 볼 때까지 드러나지 않는다. 라벨 원천은
#: `core/model/parameters.py`(`LABEL_BY_NAME`·`resolve_label`)이며 앞 축(R63/P1)의
#: 검사가 빈 라벨 수를 **0** 으로 묶었으므로 **이 경로는 안 도는 것이 정상이다** —
#: 그래도 눈에 보이게 두는 것이 규약이다(빈칸과 「없다」는 다른 진술 · §13.0.1 ④).
UNLABELLED = "라벨 미등록"


#: 설비 설정 화면이 그리는 데모 구성. **자원 종류와 파라미터를 여기서 짓지
#: 않는다** — 종류는 레지스트리가, 파라미터는 `core.model.parameters` 카탈로그가
#: 정본이며 여기는 「어떤 자원을 몇 개 놓았는가」만 정한다.
DEMO_MODEL = ModelConfig(
    name="에너지자립가구 기본안",
    resources=[
        DERConfig(tag="PV", params={"name": "옥상 태양광", "capacity_kw": 12.0}),
        DERConfig(tag="ESS", params={"name": "공용 ESS", "capacity_kwh": 30.0}),
    ],
)


def equipment_setting_groups(config: ModelConfig) -> tuple[dict[str, Any], ...]:
    """설비 설정 화면의 **전체 파라미터** — **자원 인스턴스마다 한 묶음.** UI-1-AC1.

    「전체」의 기준은 `core.model.parameters` 가 갖는다(레지스트리에 등록된 자원의
    생성자 시그니처). **이 함수는 그 목록을 줄이지 않는다** — 줄이면 화면이
    「전체」라고 적은 채 일부만 그리게 되고, 그 상태는 사용자가 없는 칸을 찾을
    때까지 드러나지 않는다. `tests/web/test_dashboard.py::
    test_grouping_loses_not_a_single_field` 가 묶기 전후의 개수를 대조한다.

    ## ★ 왜 **인스턴스별**로 묶고 종류별로 묶지 않는가

    사용자 판정(`docs/decisions-2026-09-05-R63.md` §1 「디자인」)의 예시가
    *「태양광, ESS는 각각을 그룹화」* 여서 **종류별**로 읽을 수도 있다. 그런데
    같은 `PV` 를 둘 놓으면 파라미터도 두 벌이고, 종(種) 단위로 한 벌만 그리면
    **어느 자원의 값인지 알 수 없다** — 둘째 자원의 값을 고칠 방법이 없어진다.
    `resource_parameters` 가 같은 자리에서 같은 판단을 적어 두었다.
    ⇒ **인스턴스별로 묶고, 묶음마다 사용자가 지은 자원 이름을 인쇄한다.**

    ## ⚠ 묶음이 **자원 종류의 한국어 이름을 갖지 않는다** — 원천이 없다

    묶음이 내놓는 `tag` 는 레지스트리 키(`PV`·`ESS`)이며 **한국어 이름이 아니다.**
    저장소에 `tag` → 한국어 이름 사전이 **없다**(R63/WP-S1 이 실측했다).
    ⛔ **여기서 짓지 않는다** — 화면이 사전을 가지면 자원 1종 추가가 이 파일
    수정을 부르고, 고치지 않은 동안 화면은 낡은 이름을 인쇄한다(판정 ⓑ 와 같은
    사유). 원천이 서면 `core/model/parameters.py` 의 `LABEL_BY_NAME` 자리에
    같은 모양으로 서야 한다.
    ⇒ 그때까지 **묶음은 종류 이름을 사람에게 인쇄하지 않고** `tag` 를
    `data-resource-tag` 로만 실어 보낸다(기계가 읽는 자리다).
    """
    groups: list[dict[str, Any]] = []
    for index, resource in enumerate(config.resources):
        groups.append(
            {
                # **묶음 식별자도 자원 이름이 아니라 순번으로 짓는다** — 아래
                # `_field` 와 같은 사유이며 같은 접두사(`res{순번}`)를 쓴다.
                "id": f"res{index}",
                "index": index,
                "name": resource_name(resource),
                "tag": resource.tag,
                "fields": tuple(
                    _field(index, resource, spec)
                    for spec in resource_parameters(resource.tag)
                ),
            }
        )
    return tuple(groups)


def equipment_setting_fields(config: ModelConfig) -> tuple[dict[str, Any], ...]:
    """같은 목록을 **평평하게** — 묶음을 그리지 않는 쪽이 쓰는 모양이다.

    ⚠ **목록을 여기서 다시 짓지 않는다.** `equipment_setting_groups` 를 펴서
    낸다 — 두 곳에서 각자 지으면 한쪽이 순서나 개수를 달리해도 아무 검사도
    걸리지 않고, 그때 폼이 받는 칸 이름과 화면이 그린 칸 이름이 갈린다
    (`app/routers/ui_forms.py::_submissions` 가 그 사고를 적어 두었다).
    """
    return tuple(
        field for group in equipment_setting_groups(config) for field in group["fields"]
    )


def _field(index: int, resource: DERConfig, spec: ParameterSpec) -> dict[str, Any]:
    """칸 하나. **사람이 읽는 자리에 파라미터 이름을 넣지 않는다.**

    사용자 판정(`docs/decisions-2026-09-05-R63.md` §1 「용어」): *「"옥상 태양광 ·
    azimuth_deg" 와 같이 coding 상의 변수명을 병기하지 않음」*.
    ⇒ `label`·`help` 는 **카탈로그의 한국어 라벨**(`ParameterSpec.label`)에서
    오고, 파라미터 이름은 **`id`·`parameter` 에만** 남는다 — 폼 제출이 그것으로
    되므로 지우면 폼이 아무 값도 못 받은 채 성공을 낸다.
    """
    configured = resource.params.get(spec.name)
    if configured is not None:
        value, source = str(configured), "구성값"
    elif spec.required:
        value, source = "", "필수 입력 — 기본값 없음"
    else:
        value, source = spec.default_text, f"{spec.tag} 자원 기본값"
    label = spec.label or UNLABELLED
    return {
        # **화면 식별자는 자원 이름이 아니라 순번으로 짓는다** — 자원 이름은
        # 사용자가 짓는 자유 문자열이라 HTML id 로 쓸 수 없고, 같은 이름이 두 번
        # 나오지 않는다는 보장도 `composition` 안에서만 성립한다.
        "id": f"res{index}-{spec.name}",
        "parameter": f"{index}.{spec.name}",
        # ⚠ **자원 이름을 여기 다시 붙이지 않는다.** 묶음의 `<legend>` 가 이미
        # 인쇄하며, 붙이면 칸 50개가 같은 이름을 되풀이한다.
        "label": label,
        "kind": str(spec.kind),
        "unit": spec.unit,
        "value": value,
        "source": source,
        "help": f"{spec.tag} 자원의 「{label}」 입니다. 형식 {spec.type_text}.",
        # 정수·실수를 가리지 않고 `any` 다. 형식별로 가르면 그 규칙이 카탈로그의
        # 형식 판정과 갈리고, 갈린 뒤에도 화면은 멀쩡해 보인다.
        "step": "any",
        "scalar": spec.kind is ParameterKind.NUMBER,
    }


def demo_context() -> dict[str, Any]:
    """Return deterministic UI data used by template tests and early integration.

    ⚠ **`inputs` 와 `parameter_groups` 는 다른 것이다.** `parameter_groups` 는 설비
    설정이 그리는 **전체 파라미터**(카탈로그가 정본 · 자원 인스턴스마다 한 묶음)
    이고, `inputs` 는 결과 화면의 「입력값 부록」이 그리는 **결과를 낸 주요 입력의
    요약**이다. 부록에 133개를 늘어놓으면 그것은 부록이 아니다.
    """
    supported = 1_250_000
    baseline = 980_000
    return {
        "parameter_groups": equipment_setting_groups(DEMO_MODEL),
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
                "source": "분석 설정 대장",
                "step": "0.1",
            },
            {
                "id": "discount_rate",
                "label": "할인율",
                "value": "4.5",
                "unit": "%",
                "help": "현재가치 환산에 쓰는 사회적 할인율입니다.",
                "source": "분석 설정 대장",
                "step": "0.1",
            },
            {
                "id": "analysis_years",
                "label": "분석 기간",
                "value": "20",
                "unit": "년",
                "help": "현금흐름을 계산하는 기간입니다.",
                # ★★ **세 자리 모두 「분석 설정 대장」이다** — 판정 정본
                # (`docs/decisions-2026-09-05-R63b.md` §1)이 종전에 이 칸만
                # 「시나리오 기본값」으로 가르라고 적었으나 **그 판정이 자기
                # 조건에 걸려 무효가 됐다**(*「정말로 시나리오 값인지 확인하라.
                # 아니면 이 판정이 틀린 것이다」*). 확인 결과 **분석기간의
                # 소유자는 시나리오가 아니라 대장**이다: `docs/assumptions.yaml`
                # 이 `analysis.period_years` 로 갖고 `track: fixed` 로 들며,
                # `infra/orm/scenario.py` 는 `analysis_years` 를 Scenario
                # **금지 필드**로 열거한다(§7.1 O-1 · `DV-11`).
                # ⚠ 「시나리오 기본값」으로 적으면 화면이 `DV-11` 이 금지한
                # 소유를 인쇄하고, 그 낱말을 세우려면 손으로 지어내야 한다.
                # ⇒ 정본을 고치고 이 칸을 대장 쪽으로 합쳤다.
                "source": "분석 설정 대장",
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
        # ★ 실행 폼 — FR-705-AC2 「ⓐ·ⓑ·ⓒ 를 선택할 수 있어야 한다」.
        # **여기 셋은 데모 값이 아니다.** 위의 `inputs`·`result_cards` 와 달리
        # 실제 실행 경로(`GET /ui/run`)가 받는 값이며, 목록의 정본은 저장소다.
        "scenarios": golden_scenario_names(),
        "baseline_arrangements": baseline_arrangement_choices(),
        "pool_prerequisites": pool_prerequisite_fields(),
        # ★ 결과 그림 — 여기도 데모 값이 아니다. 주소는 실제 라우트를 가리키고,
        # 그 라우트가 그리는 수는 전부 `CaseReport` 에서 온다. 질의가 비어 있어
        # 라우트의 기본 시나리오·기본 갈래로 돈다.
        "charts": chart_figures(),
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
    return regulation_admin_view_context(
        {
            "name": profile.name,
            "version": profile.version,
            "items": [
                {
                    "key": item.key,
                    "value": item.value,
                    "unit": item.unit,
                    "source": item.source,
                }
                for item in profile.items(when=when)
            ],
        },
        role=role,
        versions=versions,
    )


def regulation_admin_view_context(
    view: dict[str, Any], *, role: str, versions: tuple[str, ...] = ()
) -> dict[str, Any]:
    """같은 화면을 **`app/routers/regulation.py` 가 낸 응답 모양**에서 짓는다.

    ## 왜 입구가 둘인가 — 그리고 왜 그것이 문맥을 둘로 만들지 않는가

    R62/WP-6 에서 화면이 실제로 상태를 바꾸게 되면서, 화면이 그릴 프로파일은
    더 이상 호출자가 손에 든 객체가 아니라 **admin 라우터가 보관하는 그것**이
    됐다. 그런데 그 라우터가 밖으로 내는 것은 프로파일 객체가 아니라
    `_view(...)` 가 지은 사전이다(모듈 사설 `_service` 를 뚫지 않는 것이
    이 라운드의 판정이다).

    그래서 **입구는 둘이되 문맥을 짓는 자리는 여기 하나**로 둔다.
    `regulation_admin_context` 는 유효기간을 적용해 이 모양으로 옮긴 뒤
    그대로 여기에 넘긴다 — 화면이 무엇을 받는가는 **이 함수만** 안다.
    두 곳에서 각자 짓게 두면 한쪽이 항목 열을 하나 빠뜨려도 아무 검사도
    걸리지 않는다.

    ⚠ **`when` 을 여기서 다시 적용하지 않는다.** 사전이 든 항목은 이미
    「그 시점에 유효한 것」이고, 여기서 또 거르면 어느 시점이 적용됐는지가
    두 곳에 살게 된다.
    """
    return {
        "profile_name": view["name"],
        "profile_version": view["version"],
        "role": role,
        "can_edit": can_edit_regulation_profile(role=role, operation="편집").allowed,
        "items": tuple(view["items"]),
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


def render_run_result(context: dict[str, Any]) -> str:
    """실행 결과(또는 거부) 화면을 그린다 — `FR-705-AC2` · `NFR-303`.

    ⚠ **거부를 다른 템플릿으로 가르지 않는다.** 가르면 결과 화면이 머리·
    탐색을 고칠 때마다 거부 화면만 낡고, 그 낡음은 사람이 실제로 거부당할
    때까지 보이지 않는다.
    """
    template = _ENV.get_template("run_result.html")
    return template.render(context)
