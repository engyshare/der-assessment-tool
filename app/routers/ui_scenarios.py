"""시나리오·설정을 화면에서 저장·로드·적용하는 라우터 — `FR-902` · `FR-602`.

## 왜 이 파일이 R63/S2 에 생겼는가

저장 계층과 오버라이드 통로는 이미 섰다 — `app/services/scenario_store.py`
(프로토콜·소프트 삭제·버전 이력) · `app/services/scenario_store_file.py`
(파일 저장) · `core/assumption/scenario_overrides.py`(시나리오 필드 하나로 들어오는
전제 오버라이드). **없던 것은 사람이 화면에서 그것을 쓰는 통로**다. 사용자 문면
(`docs/decisions-2026-09-05-R63.md` §1)이 가리키는 자리가 정확히 그 구멍이다.

## ★★★ 상태는 **API 라우터가 이미 들고 있는 그 서비스 하나**를 쓴다

두 번째 `ScenarioService` 를 여기 만들면 같은 시나리오에 대한 저장소가 둘이 되고
화면과 JSON API 가 서로 다른 답을 낸다 — 그리고 **그 어긋남은 아무 오류도 내지
않는다.** 그렇다고 `scenarios._store` 를 뚫지도 않는다(모듈 사설 이름이다).
**그 라우터의 공개 함수**를 부른다 — `app/routers/ui_forms.py` 머리말이 같은
자리에서 같은 판단을 적었다.

⚠ 그래서 **저장이 프로세스를 넘어 사는가는 `DER_SCENARIO_STORE` 가 정한다**
(`app/services/scenario_store_file.py::resolve_scenario_store_dir`). 그 자리를
정하지 않은 배포는 인메모리이며, 그 되돌림의 사유는 `app/deps.py::DEFAULT_DB_URL`
주석이 갖는다. 여기서 자리를 다시 정하지 않는다 — 정하면 화면과 API 의 저장이
갈린다.

## 「설정」은 **이름 붙은 전제 오버라이드 집합**이다 — 새 자료형을 만들지 않는다

    설정               대장 위에 얹은 오버라이드 집합 (`AssumptionSet.override()`)
    저장·로드          `ScenarioRecord.definition_json`
    시나리오가 고른다  시나리오 정의의 `settings_id`
    기준선 갈래        시나리오 정의의 `baseline_arrangement` — **이미 그렇다**

두 종류가 **같은 저장소**에 산다. 저장소를 둘로 가르면 목록·버전·소프트 삭제
규칙이 두 벌이 되고, 한쪽만 고쳐지는 날 「설정은 되돌릴 수 없다」가 된다.
갈래는 정의 안의 `kind` 가 말한다 — 태그로 가르지 않는 이유는 태그가 사용자의
것이기 때문이다(`FR-902-AC1`).

## ⚠⚠ 대장을 무르게 만들지 않는다 (`NFR-202`)

화면은 **대장에 없는 키를 만들 수 없다.** 그 판정은 여기서 하지 않고
`resolve_assumption_overrides` 하나가 한다 — 규칙이 두 곳에 있으면 한쪽만
고쳐지고, 그때 어느 쪽이 맞는지 아무 검사도 말하지 않는다. 이 라우터가 하는
일은 **그 거부를 삼키지 않고 사람이 읽을 문면으로 그리는 것**이다.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routers import scenarios as scenarios_api
from app.services.scenario_store import SOFT_DELETE_RETENTION_DAYS
from app.services.ui_run import (
    DEFAULT_UI_SCENARIO,
    assumptions_path,
    golden_scenario_names,
    run_ui_case,
)
from core.assumption.provider import AssumptionSet
from core.assumption.scenario_overrides import (
    ASSUMPTION_OVERRIDES_FIELD,
    resolve_assumption_overrides,
)
from core.contracts.validation import ValidationError
from web.render import (
    baseline_arrangement_choices,
    chart_query,
    error_context,
    pool_prerequisite_fields,
    render_run_result,
    run_result_context,
)
from web.render_scenarios import (
    applied_settings_context,
    render_scenarios,
    render_settings,
    scenarios_context,
    settings_context,
)

router = APIRouter(tags=["ui"])

#: 화면이 여는 주소 — 성공한 조작이 되돌아갈 자리다.
SCENARIOS_URL = "/ui/scenarios"
SETTINGS_URL = "/ui/settings"

#: 화면이 쓰는 **데모 소유자**. 사용자는 아직 요청에서 오지 않는다 — 세션에서
#: 사용자를 끌어오는 것은 `FR-901` 인증 층의 일이고 그 층이 아직 사용자를 들고
#: 있지 않다. 여기서 세션 파싱을 흉내내면 **인증이 붙는 순간 두 곳이 사용자를
#: 판정한다** (`app/routers/ui.py` 머리말이 역할에 대해 같은 사유를 적었다).
DEMO_OWNER_ID = 0

#: 정의 안에서 **무엇으로 저장됐는지**를 말하는 필드.
_KIND = "kind"
KIND_SCENARIO = "scenario"
KIND_SETTINGS = "settings"

#: 시나리오 정의가 갖는 필드. 문면은 여기 한 곳이 갖는다 — 두 곳에 적으면
#: 저장한 값이 불러오기에서 조용히 빠진다.
_SCENARIO_NAME = "scenario"
_ARRANGEMENT = "baseline_arrangement"
_TRANSFERRED = "ownership_or_operation_transferred"
_METERED = "metering_separated"
_SETTINGS_ID = "settings_id"

#: 폼 칸 이름·접두사 — 대장 키가 칸 이름의 일부라 시그니처에 적을 수 없다.
_VALUE_PREFIX = "val-"
_REASON_PREFIX = "reason-"
_ARRANGEMENT_FORM = "arrangement"

#: 거부 문면의 `field` 경로 (`NFR-303` · 경로 관례 「`<도메인>.<필드>`」).
_FORM_FIELD = "settings.value"
_DEFINITION_FIELD = "scenario.definition_json"
_ID_FIELD = "scenario.id"


def _ledger() -> AssumptionSet:
    """전제 대장 한 벌. **매번 읽는다** — 쥐고 있으면 대장이 바뀌어도 화면이 낡는다.

    ⚠ 경로를 문자열로 여기 적지 않는다. `app/services/ui_run.py` 가 실행 경로에
    넘기는 그 대장과 **같은 파일**이어야 하며, 두 곳이 각자 경로를 지으면 한쪽만
    고쳐지는 날 화면과 실행이 서로 다른 대장을 본다.
    """
    return AssumptionSet.load_from_yaml(str(assumptions_path()))


def _see_other(url: str) -> RedirectResponse:
    """성공을 **303** 으로 되돌린다 — 새로고침이 조작을 되풀이하지 않게.

    근거는 `app/routers/ui_forms.py::_see_other` 가 적었다.
    """
    return RedirectResponse(url, status_code=303)


def _rejection(field: str, reason: str, action: str) -> ValidationError:
    """3요소를 갖춘 거부 하나 (`NFR-303`) — **던지는 것은 부르는 쪽이 한다.**"""
    return ValidationError(field=field, reason=reason, action=action)


def _refused(exc: ValidationError, *, status: int) -> HTMLResponse:
    """거부를 **`/ui/run` 이 쓰는 그 화면**으로 낸다 (`run_result.html` 의 `#validation`).

    ⚠ 새 거부 화면을 만들지 않는다. 만들면 3요소를 그리는 자리가 둘이 되고,
    한쪽만 고쳐지는 날 어느 쪽이 맞는지 아무 검사도 말하지 않는다
    (`web/render_run.py::error_context` 가 같은 사유를 적었다).
    """
    return HTMLResponse(
        render_run_result(
            error_context(
                field=exc.field, reason=exc.reason, action=exc.action, rule=exc.rule
            )
        ),
        status_code=status,
    )


# ── 정의 JSON — 저장된 것을 읽고, 저장할 것을 짓는다 ────────────────────────


def _definition(record: dict[str, Any]) -> dict[str, Any]:
    """레코드가 든 정의 한 벌. **못 읽으면 3요소로 거부한다** — 500 이 아니다.

    ⚠ 못 읽는 정의를 빈 사전으로 낮추지 않는다. 낮추면 「저장된 것이 없다」와
    「저장된 것을 못 읽는다」가 화면에서 같아지고, 사용자는 자기가 저장한 값이
    사라졌다고 읽는다.
    """
    raw = str(record.get("definition_json", "") or "")
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _rejection(
            _DEFINITION_FIELD,
            f"저장된 정의를 읽을 수 없습니다: {exc}",
            "이 레코드를 다시 저장하거나 삭제하십시오",
        ) from exc
    if not isinstance(loaded, dict):
        raise _rejection(
            _DEFINITION_FIELD,
            f"저장된 정의가 매핑이 아닙니다: {loaded!r}",
            "이 레코드를 다시 저장하십시오",
        )
    return loaded


def _record(scenario_id: int) -> dict[str, Any]:
    """저장된 레코드 하나 — **없으면 3요소로 거부한다.**"""
    try:
        return scenarios_api.get_scenario(scenario_id, DEMO_OWNER_ID, None)
    except HTTPException as exc:
        raise _rejection(
            _ID_FIELD,
            f"{scenario_id} 번을 열 수 없습니다: {exc.detail}",
            "화면의 목록에서 고르십시오",
        ) from exc


def _kind(definition: dict[str, Any]) -> str:
    return str(definition.get(_KIND, KIND_SCENARIO))


def _rows_of(definition: dict[str, Any]) -> object | None:
    """설정 정의가 든 **오버라이드 목록 그대로**. 여기서 검증하지 않는다.

    ⚠ 모양을 미리 걸러 내지 않는다 — 판정하는 자리를 하나로 두는 것이
    `core/assumption/scenario_overrides.py` 의 규약이며, 미리 거르면 거부 문면이
    두 곳에 생기고 그때 둘이 갈려도 아무 검사도 걸리지 않는다.
    """
    return definition.get(ASSUMPTION_OVERRIDES_FIELD)


def _overrides_for(definition: dict[str, Any]) -> object | None:
    """시나리오가 **고른 설정**의 오버라이드를 가져온다 (사용자 §1 「설정을 선택」)."""
    settings_id = int(definition.get(_SETTINGS_ID, 0) or 0)
    if not settings_id:
        return None
    return _rows_of(_definition(_record(settings_id)))


# ── 목록 — 시나리오와 설정을 가른다 ────────────────────────────────────────


def _listed() -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """활성 레코드를 **시나리오와 설정으로 가른다** — 정의의 `kind` 가 말한다.

    ⚠ 정의를 못 읽는 레코드에서 **멈추지 않는다.** 한 건이 깨졌다고 목록 전체가
    거부되면 사용자는 나머지를 손댈 방법이 없다. 그렇다고 숨기지도 않는다 —
    칸을 남기고 사유를 글자로 싣는다(§13.0.1 ④ · R62 가 차트 둘에 한 것과 같다).
    """
    scenarios: list[dict[str, Any]] = []
    settings: list[dict[str, Any]] = []
    for row in scenarios_api.list_scenarios(owner_id=DEMO_OWNER_ID):
        entry = dict(row)
        try:
            full = scenarios_api.get_scenario(int(row["id"]), DEMO_OWNER_ID, None)
            definition = _definition(full)
        except ValidationError as exc:
            entry["definition"] = {}
            entry["broken"] = exc.reason
            scenarios.append(entry)
            continue
        entry["definition"] = definition
        entry["broken"] = ""
        (settings if _kind(definition) == KIND_SETTINGS else scenarios).append(entry)
    return tuple(scenarios), tuple(settings)


# ── 시나리오 화면 ──────────────────────────────────────────────────────────


def _scenarios_screen(
    *,
    saved_id: int = 0,
    versions_of: int = 0,
    deleted_id: int = 0,
    deleted_name: str = "",
    error: dict[str, str] | None = None,
) -> str:
    scenarios, settings = _listed()
    versions = (
        tuple(scenarios_api.list_scenario_versions(versions_of)) if versions_of else ()
    )
    return render_scenarios(
        scenarios_context(
            scenarios=scenarios,
            settings=settings,
            golden=golden_scenario_names(),
            arrangements=baseline_arrangement_choices(),
            prerequisites=pool_prerequisite_fields(),
            versions=versions,
            versions_of=versions_of,
            saved_id=saved_id,
            deleted_id=deleted_id,
            deleted_name=deleted_name,
            retention_days=SOFT_DELETE_RETENTION_DAYS,
            error=error,
        )
    )


@router.get(SCENARIOS_URL, response_class=HTMLResponse)
def scenarios_screen(
    versions: int = Query(default=0, description="버전 이력을 펼칠 시나리오 번호"),
    deleted: int = Query(default=0, description="방금 삭제한 시나리오 번호"),
    deleted_name: str = Query(default="", description="방금 삭제한 시나리오 이름"),
    saved: int = Query(default=0, description="방금 저장한 시나리오 번호"),
) -> HTMLResponse:
    """시나리오 목록·저장·불러오기·버전·삭제 화면 — `FR-902-AC1`~`AC3`.

    ⚠ **삭제한 이름을 질의로 나르는 이유.** 소프트 삭제된 레코드는
    `get_scenario` 가 404 로 답한다(활성만 연다). 번호만 남은 알림은 사용자에게
    「무엇을 지웠는지」를 말하지 못하므로, 지우기 **전에** 읽은 이름을 함께
    나른다. 문면은 템플릿이 이스케이프한다.
    """
    try:
        body = _scenarios_screen(
            saved_id=saved,
            versions_of=versions,
            deleted_id=deleted,
            deleted_name=deleted_name,
        )
    except HTTPException as exc:
        return _refused(
            _rejection(
                _ID_FIELD, str(exc.detail), "화면의 목록에서 다시 고르십시오"
            ),
            status=exc.status_code,
        )
    return HTMLResponse(body)


@router.post(SCENARIOS_URL)
async def save_scenario_form(request: Request) -> Any:
    """시나리오 저장 — 새 것이면 만들고, 번호가 있으면 **버전을 올린다**.

    ⚠ `Form(...)` 로 칸을 받지 않는다. ⓒ 전제 칸의 이름이
    `PoolMeteringDeclaration` 의 필드에서 오므로(`pool_prerequisite_fields`),
    시그니처에 적으면 전제가 하나 늘 때 이 파일 수정을 부른다.

    ⚠ **빈 갈래를 기본 갈래 문면으로 바꾸지 않는다.** 화면의 「고르지 않음」이
    그대로 「필드를 적지 않았다」로 내려가야 `resolve_baseline_arrangement`
    하나가 기본값을 정한다 (`app/routers/ui.py::run_case` 가 같은 판단을 적었다).
    """
    form = await request.form()
    definition: dict[str, Any] = {
        _KIND: KIND_SCENARIO,
        _SCENARIO_NAME: str(form.get(_SCENARIO_NAME, "")),
        _ARRANGEMENT: str(form.get(_ARRANGEMENT_FORM, "")),
        _SETTINGS_ID: int(str(form.get(_SETTINGS_ID, "0") or "0")),
    }
    for field in pool_prerequisite_fields():
        definition[field["name"]] = bool(form.get(field["name"]))
    scenario_id = int(str(form.get("scenario_id", "0") or "0"))
    payload = {
        "name": str(form.get("name", "")),
        "description": str(form.get("description", "")),
        "tags": str(form.get("tags", "")),
        "definition_json": json.dumps(definition, ensure_ascii=False),
    }
    try:
        saved = (
            scenarios_api.update_scenario(scenario_id, **payload)
            if scenario_id
            else scenarios_api.create_scenario(owner_id=DEMO_OWNER_ID, **payload)
        )
    except HTTPException as exc:
        return _refused(
            _rejection(
                _ID_FIELD,
                str(exc.detail),
                "이름을 채우고 목록에 있는 시나리오를 고르십시오",
            ),
            status=exc.status_code,
        )
    return _see_other(f"{SCENARIOS_URL}?{urlencode({'saved': saved['id']})}")


@router.post(SCENARIOS_URL + "/{scenario_id}/delete")
def delete_scenario_form(scenario_id: int) -> Any:
    """소프트 삭제 — **되돌릴 수 있다는 것을 화면이 말한다** (`FR-902-AC3`).

    ⚠ 이름을 **지우기 전에** 읽는다. 지운 뒤에는 `get_scenario` 가 404 다.
    """
    try:
        name = str(_record(scenario_id)["name"])
        scenarios_api.delete_scenario(scenario_id)
    except ValidationError as exc:
        return _refused(exc, status=404)
    except HTTPException as exc:
        return _refused(
            _rejection(_ID_FIELD, str(exc.detail), "목록에 있는 시나리오를 지목하십시오"),
            status=exc.status_code,
        )
    query = urlencode({"deleted": scenario_id, "deleted_name": name})
    return _see_other(f"{SCENARIOS_URL}?{query}")


@router.post(SCENARIOS_URL + "/{scenario_id}/restore")
def restore_scenario_form(scenario_id: int) -> Any:
    """소프트 삭제 복원 (`FR-902-AC3`) — 보관 기간 안이면 되돌아온다."""
    try:
        scenarios_api.restore_scenario(scenario_id)
    except HTTPException as exc:
        return _refused(
            _rejection(
                _ID_FIELD,
                str(exc.detail),
                f"보관 기간({SOFT_DELETE_RETENTION_DAYS}일) 안인지 보십시오",
            ),
            status=exc.status_code,
        )
    return _see_other(SCENARIOS_URL)


@router.post(SCENARIOS_URL + "/{scenario_id}/restore_version")
async def restore_version_form(scenario_id: int, request: Request) -> Any:
    """이전 버전 복원 (`FR-902-AC2`) — 복원도 **새 버전으로** 이력에 남는다."""
    form = await request.form()
    text = str(form.get("version", ""))
    try:
        version = int(text)
    except ValueError:
        return _refused(
            _rejection(
                "scenario.version",
                f"버전은 정수인데 «{text}» 를 받았습니다",
                "이력 표에 있는 버전 번호를 고르십시오",
            ),
            status=400,
        )
    try:
        scenarios_api.restore_scenario_version(scenario_id, version)
    except HTTPException as exc:
        return _refused(
            _rejection(
                "scenario.version",
                str(exc.detail),
                "이력 표에 있는 버전 번호를 고르십시오",
            ),
            status=exc.status_code,
        )
    return _see_other(f"{SCENARIOS_URL}?{urlencode({'versions': scenario_id})}")


@router.get(SCENARIOS_URL + "/{scenario_id}/run", response_class=HTMLResponse)
def run_saved_scenario(scenario_id: int) -> HTMLResponse:
    """저장한 시나리오를 **불러와 실행 화면을 채운다** — `FR-902` 「불러오기」.

    ## ⚠ 새 결과 화면을 만들지 않는다

    그리는 것은 `/ui/run` 이 그리는 **그 화면**(`run_result.html`)이다. 결과를
    그리는 자리가 둘이 되면 한쪽만 고쳐지는 날 같은 실행이 화면마다 다르게
    보이고, 그때 어느 쪽이 맞는지 아무 검사도 말하지 않는다.

    ## ★ 저장된 값이 **전부** 실행에 실린다

    갈래 · ⓒ 전제 둘 · 고른 설정의 전제 오버라이드까지 간다. 하나라도 빠지면
    「저장됐다」와 「저장된 값이 실행에 안 실렸다」가 화면에서 구별되지 않는다.
    """
    arrangement = ""
    try:
        definition = _definition(_record(scenario_id))
        name = str(definition.get(_SCENARIO_NAME, ""))
        arrangement = str(definition.get(_ARRANGEMENT, ""))
        transferred = bool(definition.get(_TRANSFERRED, False))
        metered = bool(definition.get(_METERED, False))
        run = run_ui_case(
            name,
            arrangement=arrangement or None,
            ownership_or_operation_transferred=transferred,
            metering_separated=metered,
            assumption_overrides=_overrides_for(definition),
        )
    except ValidationError as exc:
        return _refused(exc, status=400)
    except KeyError as exc:
        # `app/routers/ui.py::_missing_scenario` 와 같은 판단이다 — `str(KeyError)`
        # 는 `repr` 이라 문면에 겹따옴표를 덧씌운다. `exc.args[0]` 이 저장소가
        # 실제로 적은 문장이며, 사유를 여기서 새로 짓지 않는다.
        return _refused(
            _rejection(
                "run.scenario",
                str(exc.args[0]),
                "저장한 시나리오를 화면의 목록에서 다시 고르십시오",
            ),
            status=404,
        )
    return HTMLResponse(
        render_run_result(
            run_result_context(
                run.report,
                scenario_text=run.scenario_text,
                chart_query=chart_query(
                    scenario=name,
                    arrangement=arrangement,
                    ownership_or_operation_transferred=transferred,
                    metering_separated=metered,
                ),
            )
        )
    )


# ── 설정 화면 ──────────────────────────────────────────────────────────────


def _value_of(base: object, key: str, text: str) -> object:
    """폼이 보낸 **글자 하나**를 대장 항목이 말하는 형으로 바꾼다.

    ⚠ 「수처럼 보이면 수로」 같은 추측을 하지 않는다. 정본은 **대장에 적힌 값의
    형**이며, 여기서 형을 다시 판정하면 대장이 바뀌는 날 조용히 갈린다
    (`app/routers/ui_forms.py::_value_of` 가 카탈로그에 대해 같은 판단을 적었다).

    ⚠ **대장에 없는 키는 글자 그대로 올린다.** 없는 항목의 형을 여기서 지어내면
    `resolve_assumption_overrides` 가 낼 거부(「전제 대장에 없는 키입니다」)를
    형 변환 오류가 가로챈다 — 사용자가 받는 말이 달라진다.
    """
    if base is None:
        return text
    if isinstance(base, bool):
        raise _rejection(
            _FORM_FIELD,
            f"{key} 는 참·거짓 항목이라 이 폼이 받을 수 있는 갈래가 아닙니다",
            "이 항목은 전제 대장에서 고치십시오",
        )
    if isinstance(base, int):
        try:
            return int(text)
        except ValueError as exc:
            raise _rejection(
                _FORM_FIELD,
                f"{key} 는 정수인데 «{text}» 를 받았습니다",
                f"{key} 를 정수로 적으십시오",
            ) from exc
    if isinstance(base, float):
        try:
            return float(text)
        except ValueError as exc:
            raise _rejection(
                _FORM_FIELD,
                f"{key} 는 실수인데 «{text}» 를 받았습니다",
                f"{key} 를 수로 적으십시오",
            ) from exc
    return text


def _submitted_rows(
    ledger: AssumptionSet, mine: dict[str, str], reasons: dict[str, str]
) -> list[dict[str, Any]]:
    """사람이 채운 칸만 **오버라이드 한 줄씩**으로 편다.

    ⚠ 빈 칸을 `0` 으로 읽지 않는다 — 빈 칸은 「대장 값 그대로」다. 넣으면 사람이
    손대지 않은 칸이 전부 오버라이드가 되고, 그때 붙임의 「기준 전제 대비 변경
    항목」은 아무것도 말하지 않는다.

    ⚠ **대장 순서로 편다.** 사전 순회 순서를 그대로 쓰면 같은 제출이 판마다 다른
    순서로 실리고, 저장된 정의를 눈으로 견주는 사람이 그 차이를 변경으로 읽는다.
    """
    items = ledger.items()
    ordered = [key for key in items if key in mine]
    ordered += sorted(key for key in mine if key not in items)
    rows: list[dict[str, Any]] = []
    for key in ordered:
        text = mine[key].strip()
        if not text:
            continue
        item = items.get(key)
        row: dict[str, Any] = {
            "key": key,
            "value": _value_of(None if item is None else item.value, key, text),
        }
        reason = reasons.get(key, "").strip()
        if reason:
            row["reason"] = reason
        rows.append(row)
    return rows


def _settings_screen(
    scenario: str,
    *,
    applied: dict[str, Any] | None = None,
    error: dict[str, str] | None = None,
    form: dict[str, Any] | None = None,
) -> str:
    _, settings = _listed()
    return render_settings(
        settings_context(
            _ledger(),
            scenario=scenario,
            saved=settings,
            applied=applied,
            error=error,
            form=form,
        )
    )


@router.get(SETTINGS_URL, response_class=HTMLResponse)
def settings_screen(
    scenario: str = Query(
        default=DEFAULT_UI_SCENARIO,
        description="골든 시나리오 이름 — 목록에 있는 것만 연다",
    ),
    applied: int = Query(default=0, description="적용해 볼 설정 번호"),
) -> HTMLResponse:
    """설정(전제) 보기·수정·저장·로드 — `FR-601`(대장 전건) · `FR-602`(오버라이드).

    ⚠⚠ **`applied` 가 없으면 돌리지 않는다.** 대장을 보러 온 사람에게 매번 한
    번의 전체 실행을 물리면 화면이 느려지고, 그 느림은 「고칠 것이 없는데도
    돌았다」는 뜻이다. 설정을 **골랐을 때만** 돌려 결론축을 보인다.

    ⚠ 기본 시나리오 문면이 `/ui/run` 과 같아야 한다 — 갈리면 「오버라이드 안 건
    실행의 결론축」이 두 화면에서 다른 수가 된다. 그래서 문면을 여기 적지 않고
    `app/services/ui_run.py::DEFAULT_UI_SCENARIO` 를 쓰며, 그 라우트의 질의
    기본값과 대조하는 검사가 `tests/app/test_ui_scenarios.py` 에 있다.
    """
    context: dict[str, Any] | None = None
    try:
        if applied:
            record = _record(applied)
            run = run_ui_case(
                scenario, assumption_overrides=_rows_of(_definition(record))
            )
            context = applied_settings_context(
                run.report, settings_id=applied, settings_name=str(record["name"])
            )
        body = _settings_screen(scenario, applied=context)
    except ValidationError as exc:
        return HTMLResponse(
            _settings_screen(
                scenario,
                error={"field": exc.field, "reason": exc.reason, "action": exc.action},
            ),
            status_code=400,
        )
    except KeyError as exc:
        return HTMLResponse(
            _settings_screen(
                scenario,
                error={
                    "field": "run.scenario",
                    "reason": str(exc.args[0]),
                    "action": "화면의 시나리오 목록에서 고르십시오",
                },
            ),
            status_code=404,
        )
    return HTMLResponse(body)


@router.post(SETTINGS_URL)
async def save_settings_form(request: Request) -> Any:
    """설정 저장 — 고친 칸만 **이름 붙은 오버라이드 집합**으로 담는다.

    ## ★ 거부를 삼키지 않는다 — 그리고 **값을 잃지 않는다**

    거부되면 3요소를 그리고 **사람이 넣은 값을 되돌려 그린다**(착수 목록 44번
    ⓑ · 오케스트레이터 판정 ⑥). 잃으면 사람은 그것을 「고칠 수 없다」로 읽는다.
    그래서 이 거부만은 `run_result.html` 이 아니라 **설정 화면 그대로**로 낸다 —
    폼이 없는 화면에 값을 되돌려 그릴 자리가 없다.

    ## ⚠ 거부된 값을 저장하지 않는다

    저장한 뒤에 실행에서 거부하면 그 설정은 **열 때마다** 거부되고, 사용자에게
    그것은 「지울 수만 있는 설정」이다. 그래서 저장 전에
    `resolve_assumption_overrides` 로 한 번 판정한다 — 규칙을 여기서 다시 적지
    않고 **그 함수를 부른다.**

    ⚠ `Form(...)` 로 칸을 받지 않는다. 칸 이름이 `val-<대장 키>` 라 대장이 늘고
    줄 때마다 시그니처를 고쳐야 하고, 대장을 데이터로 둔 이유가 그것을 막는
    것이다 (`app/routers/ui_forms.py::advanced_parameters_form` 과 같은 규약).
    """
    form = await request.form()
    mine = {
        key[len(_VALUE_PREFIX) :]: str(value)
        for key, value in form.items()
        if key.startswith(_VALUE_PREFIX)
    }
    reasons = {
        key[len(_REASON_PREFIX) :]: str(value)
        for key, value in form.items()
        if key.startswith(_REASON_PREFIX)
    }
    typed: dict[str, Any] = {
        "name": str(form.get("name", "")),
        "description": str(form.get("description", "")),
        "mine": mine,
        "reasons": reasons,
    }
    scenario = str(form.get(_SCENARIO_NAME, "") or DEFAULT_UI_SCENARIO)
    ledger = _ledger()
    known = ledger.items()
    # ⚠ 대장 밖 키도 **되돌려 그린다.** 지우면 무엇이 거부됐는지가 폼에서
    # 사라지고, 사람은 자기가 무엇을 적었는지 다시 지어내야 한다.
    typed["unknown"] = tuple(
        {"key": key, "value": text}
        for key, text in sorted(mine.items())
        if key not in known and text.strip()
    )
    try:
        rows = _submitted_rows(ledger, mine, reasons)
        resolve_assumption_overrides(rows, known_keys=known.keys())
    except ValidationError as exc:
        return HTMLResponse(
            _settings_screen(
                scenario,
                error={"field": exc.field, "reason": exc.reason, "action": exc.action},
                form=typed,
            ),
            status_code=400,
        )
    definition = {_KIND: KIND_SETTINGS, ASSUMPTION_OVERRIDES_FIELD: rows}
    saved = scenarios_api.create_scenario(
        name=str(typed["name"]),
        owner_id=DEMO_OWNER_ID,
        description=str(typed["description"]),
        definition_json=json.dumps(definition, ensure_ascii=False),
    )
    query = urlencode({"scenario": scenario, "applied": saved["id"]})
    return _see_other(f"{SETTINGS_URL}?{query}")
