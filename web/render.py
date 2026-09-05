"""Jinja2 rendering entry points for the WP-12 web UI."""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.security.authorization import can_edit_regulation_profile
from app.services.ui_charts import chart_description, chart_source, unwired_reason
from app.services.ui_run import golden_scenario_names
from core.cba.baseline import (
    POOL_PREREQUISITE_METERING,
    POOL_PREREQUISITE_TRANSFER,
    BaselineArrangement,
    PoolMeteringDeclaration,
)
from core.contracts.regulation import RegulationProfile
from core.contracts.units import Money
from core.contracts.validation import ValidationError
from core.model.composition import available_resource_tags, resource_name
from core.model.parameters import ParameterKind, ParameterSpec, resource_parameters
from core.model.schemas import DERConfig, ModelConfig
from core.report._format import NO_VALUE, _won, _years
from core.report.case_influences import CONCLUSION_METRIC, HEADLINE_METRIC
from core.report.case_report import CaseReport
from core.report.charts import chart_registry

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


def baseline_arrangement_choices() -> tuple[str, ...]:
    """고를 수 있는 갈래의 **값 문면** — `BaselineArrangement` 를 열거해 얻는다.

    ⚠ **목록을 소스에 박지 않는다.** 박으면 여덟 번째 갈래가 서는 날 화면만
    셋을 그린 채 남고, 그 상태는 사람이 없는 칸을 찾을 때까지 드러나지 않는다
    (`advanced_mode_fields` 가 같은 판단을 적어 두었다).

    ⚠ 값 문면 그대로인 이유: 시나리오 yaml 의 `baseline_arrangement` 필드가
    **문면 그대로**를 받는다 (`resolve_baseline_arrangement` 독스트링).
    """
    return tuple(item.value for item in BaselineArrangement)


#: ⓒ 전제 둘의 **화면 문면**. 이름은 `PoolMeteringDeclaration` 의 필드에서,
#: 문면은 `core.cba.baseline` 의 상수에서 온다 — 어느 쪽도 여기서 짓지 않는다.
#: 거부 메시지와 화면이 **같은 문자열**을 봐야 사람이 *「어느 쪽이 빠졌는가」*
#: 를 대조할 수 있다(그 상수들의 ⚠ 주석이 같은 이유를 적는다).
#: ⚠ 읽기 전용으로 둔다 — 모듈 수준 가변 컨테이너는 `NFR-205` 가 막는 것이다
#: (`scripts/check_hardcoded_params.py` 는 `web/` 를 훑지 않지만 규칙은 같다).
#: `BASELINE_DECLARATIONS` 가 같은 자리에서 같은 모양을 쓴다.
_POOL_PREREQUISITE_LABELS = MappingProxyType({
    "ownership_or_operation_transferred": POOL_PREREQUISITE_TRANSFER,
    "metering_separated": POOL_PREREQUISITE_METERING,
})


def pool_prerequisite_fields() -> tuple[dict[str, str], ...]:
    """ⓒ 전제 둘의 **화면 칸** — 이름은 자료형이, 문면은 상수가 정본이다.

    ⚠ 전제가 하나 늘면 여기서 `KeyError` 로 **멈춘다.** 조용히 빠지는 대신인
    이유: 안 그리면 새 전제를 아무도 선언할 수 없고, 그 상태는 화면에서
    「ⓒ 를 고를 수 없다」로만 보인다 — 왜 못 고르는지는 보이지 않는다.
    """
    return tuple(
        {"name": field.name, "label": _POOL_PREREQUISITE_LABELS[field.name]}
        for field in dataclasses.fields(PoolMeteringDeclaration)
    )


def chart_query(
    *,
    scenario: str,
    arrangement: str,
    ownership_or_operation_transferred: bool,
    metering_separated: bool,
) -> str:
    """그림 주소에 붙일 질의 문자열 — **결과 화면과 같은 실행을 그리게 한다.**

    ⚠ 손으로 잇지 않는다(`urlencode`). 갈래 문면은 한국어라 그대로 이으면
    주소가 깨지고, 깨진 주소는 브라우저가 기본 갈래로 되돌아간 그림을 가져온다 —
    화면의 수는 ⓒ 인데 그림은 ⓑ 인 상태가 나오고 **둘 다 그럴듯해 보인다**.

    ⚠ 참·거짓 문면을 파이썬 것(`True`)으로 두지 않는다 — 받는 쪽은 FastAPI 의
    불리언 파서다.
    """
    return urlencode({
        "scenario": scenario,
        "arrangement": arrangement,
        "ownership_or_operation_transferred": (
            "true" if ownership_or_operation_transferred else "false"
        ),
        "metering_separated": "true" if metering_separated else "false",
    })


def chart_figures(*, query: str = "") -> tuple[dict[str, Any], ...]:
    """결과 그림 칸 — **레지스트리로 편다.**

    ⚠⚠ **제목을 손으로 적지 않는다.** 종전 `visual-grid` 는 `<h3>` 여섯 개를
    박아 두었고 그림은 하나도 없었다. 박아 두면 차트가 늘 때 그 목록이 낡고,
    낡은 것은 사람이 없는 칸을 찾을 때까지 드러나지 않는다
    (`advanced_mode_fields` 가 같은 판단을 적었다).

    ⚠ **못 그리는 칸을 빼지 않는다.** 빼면 「그릴 수 없다」와 「그런 그림이
    없다」가 화면에서 같아진다 — §13.0.1 ④ 가 금지한 형태다. 칸은 남기고
    사유를 글자로 싣는다.
    """
    suffix = f"?{query}" if query else ""
    figures: list[dict[str, Any]] = []
    for tag, chart in sorted(chart_registry().items()):
        reason = unwired_reason(tag)
        figures.append({
            "tag": tag,
            "label": chart.label,
            "wired": reason is None,
            "reason": reason,
            "src": f"/ui/chart/{tag}.png{suffix}",
            # `alt` 는 라벨 + **무엇을 보여 주는 그림인지**다. 라벨만 넣으면
            # 그림을 못 보는 사람에게 남는 것이 제목뿐이고, `UI-6` 이 막으려는
            # 것이 정확히 그 상태다 — 그림은 색으로만 말한다.
            "alt": f"{chart.label} — {chart_description(tag)}" if reason is None else "",
            "source": chart_source(tag) if reason is None else "",
        })
    return tuple(figures)


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


def run_result_context(
    report: CaseReport, *, scenario_text: str, chart_query: str = ""
) -> dict[str, Any]:
    """실행 결과 화면의 문맥 — `UI-7-AC1` · `FR-705-AC2`.

    ## ⚠⚠⚠ **여기서 계산을 새로 하지 않는다**

    `CaseReport` 가 준 값을 **옮겨 적기만** 한다. 화면이 인쇄하는 수가
    리포트와 어긋나면 **그것이 새 결함**이다 — 이 저장소가 `cost_benefit_
    section` 에서 이미 한 번 밟은 형태다(1년차 값으로 결손을 되지었더니 합이
    맞지 않았다).

    ⚠ 서식은 **`core/report/_format.py` 의 것을 그대로 쓴다.** 문면을 여기서
    다시 지으면 「500,000원」과 「500000원」이, 「분석기간 내 미회수」와 다른
    문면이 같은 저장소에 섞인다 — 그 파일이 존재하는 이유가 정확히 그것이다.
    반올림·부호 뒤집기·단위 환산은 하지 않는다.

    ⚠ **지표 키를 문자열로 박지 않는다** — `CONCLUSION_METRIC`(npv)·
    `HEADLINE_METRIC`(payback_years) 이 정본이다.

    ★ `npv_raw` 를 **날값 그대로** 함께 싣는다. 서식을 입힌 문면만 두면
    「화면의 수가 리포트의 수와 같은가」를 기계가 대조할 수 없고, 그때 그
    검사는 서식 문자열을 다시 짜 맞추게 된다.
    """
    return {
        "error": None,
        "scenario_name": report.scenario_name,
        # ★ 영향도 순위 — 화면 **최상단**이다 (`UI-7-AC1`).
        "influences": tuple(
            {
                "rank": rank,
                "name": entry.variable,
                "ledger_key": entry.ledger_key or NO_VALUE,
                "impact": _won(entry.delta_won),
                "flips": entry.flips_conclusion,
            }
            for rank, entry in enumerate(report.influences, start=1)
        ),
        # ★ 어느 갈래로 돌았나 — 갈래를 고르게 해 놓고 결과가 그것을 안 적으면
        # 확인할 방법이 없다. 선언 다섯을 함께 싣는다(`CaseReport.
        # baseline_branch` 의 ⚠ — 이름만 실으면 검토자가 그 이름이 뜻하는
        # 기준선을 저장소 밖에서 찾아야 한다).
        "arrangement": report.baseline_arrangement.value,
        "branch": {
            "without": report.baseline_branch.without_description,
            "with": report.baseline_branch.with_description,
            "viability": report.baseline_branch.viability_condition or NO_VALUE,
            "self_consumption": (
                report.baseline_branch.self_consumption_treatment.value
            ),
            "clause": report.baseline_branch.clause,
        },
        "npv": _won(report.metrics[CONCLUSION_METRIC]),
        "npv_raw": report.metrics[CONCLUSION_METRIC],
        "payback": _years(report.metrics[HEADLINE_METRIC]),
        "annual_benefit": _won(report.basis.annual_benefit_won),
        "annual_cost": _won(report.basis.annual_cost_won),
        "benefits": tuple(
            {"label": line.label, "annual": _won(line.annual_won)}
            for line in report.basis.benefits
        ),
        "costs": tuple(
            {"label": line.label, "annual": _won(line.annual_won)}
            for line in report.basis.costs
        ),
        "scenario_text": scenario_text,
        # ★ 그림은 **이 실행의** 질의를 달고 나간다. 기본값으로 그리면 위의 수와
        # 아래 그림이 서로 다른 실행이 되고, 그 어긋남은 아무 오류도 내지 않는다.
        "charts": chart_figures(query=chart_query),
    }


def run_error_context(exc: ValidationError) -> dict[str, Any]:
    """거부 화면의 문맥 — **필드·사유·조치 3요소** (`NFR-303`).

    ⚠ **예외 문면을 여기서 새로 짓지 않는다.** `exc.field`·`exc.reason`·
    `exc.action` 을 옮긴다 — 새로 지으면 같은 거부가 JSON 출구
    (`app/routers/models.py::_bad_request`)와 화면에서 다른 말을 하게 되고,
    그때 어느 쪽이 맞는지는 아무 검사도 말하지 않는다.

    `rule` 도 함께 싣는다. ⓒ 거부는 `DV-15` 이며, 대장 ID 가 붙은 거부와
    일반 입력 검증을 화면이 가려 보여야 사람이 *「제도가 막은 것인가」* 를
    안다(`ValidationError` 독스트링의 「`rule` 은 선택이다」 절).
    """
    return error_context(
        field=exc.field, reason=exc.reason, action=exc.action, rule=exc.rule
    )


def error_context(
    *, field: str, reason: str, action: str, rule: str | None = None
) -> dict[str, Any]:
    """거부 화면의 문맥 — **3요소를 실은 사전 하나** (`NFR-303`).

    `ValidationError` 가 아닌 거부도 이 통로로 온다. 화면 폼이 없는 프로파일을
    가리키거나(`KeyError` → 404) 권한 없이 눌렀을 때(`PermissionError` → 403)
    라우터가 내는 것은 **문자열 한 줄**이며, 그것을 그대로 브라우저에 던지면
    사람에게 남는 것은 「무엇을 하라」가 없는 문장이다 — 그것이 `NFR-303` 이
    막으려는 상태다. 그래서 부르는 쪽이 셋을 갖춰 여기로 보낸다.

    ⚠ **새 거부 화면을 만들지 않는다.** 낼 것은 `run_result.html` 의
    `#validation` 절 하나이며, 이 함수는 그 절이 읽는 사전을 지을 뿐이다.
    """
    return {
        "error": {
            "field": field,
            "reason": reason,
            "action": action,
            "rule": rule or NO_VALUE,
        }
    }


def render_run_result(context: dict[str, Any]) -> str:
    """실행 결과(또는 거부) 화면을 그린다 — `FR-705-AC2` · `NFR-303`.

    ⚠ **거부를 다른 템플릿으로 가르지 않는다.** 가르면 결과 화면이 머리·
    탐색을 고칠 때마다 거부 화면만 낡고, 그 낡음은 사람이 실제로 거부당할
    때까지 보이지 않는다.
    """
    template = _ENV.get_template("run_result.html")
    return template.render(context)
