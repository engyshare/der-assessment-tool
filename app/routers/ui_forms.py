"""화면의 폼이 실제로 눌리게 하는 라우터 — FR-201-AC1 · FR-504-AC3.

## 왜 이 파일이 R62/WP-6 에 생겼는가

WP-5 가 브라우저로 눌러 보고 잡은 것이 이것이다. 템플릿의 폼 셋은
`method="post"` 로 **`application/x-www-form-urlencoded`** 를 보내는데, 그
`action` 이 가리키던 `app/routers/models.py`·`regulation.py` 는 **JSON 본문을
받는 API** 였다. 눌리면 사람이 받는 것은 화면이 아니라 영어 `422` 였다.

    POST /models/x/resources (urlencoded)
      → 422 {"detail":[{"type":"model_attributes_type", ...}]}

게다가 폼 둘은 `?_method=DELETE`·`?_method=PATCH` 를 달고 있었고 **그것을 푸는
미들웨어는 없었다.** 즉 화면은 처음부터 눌린 적이 없다.

## 고치는 방향 — API 를 무르게 하지 않는다

`models.py`·`regulation.py` 는 **JSON API 계약**이고 다른 소비자가 있다. 화면
때문에 그 둘이 폼도 받고 JSON 도 받게 만들면, 계약이 「무엇을 받는가」를
말하지 못하게 된다. 그래서 **화면 전용 출구를 여기 따로 둔다.**

## 경로 이름을 이렇게 정한 근거

    POST /ui/model-composer/resources/{이름}/duplicate
    POST /ui/model-composer/resources/{이름}/delete
    POST /ui/regulation-admin/profiles/{이름}/clone

① **`/ui/<화면>/…` 로 시작한다.** 그 화면이 여는 주소(`/ui/model-composer`)의
   아래에 있으므로, 주소만 보고 *「이것은 사람이 누른 것이고 돌아갈 화면이
   어디인가」* 를 알 수 있다. JSON API(`/models/…`·`/regulation/profiles/…`)와
   **접두사부터 갈라져** 한쪽 계약이 다른 쪽을 물들이지 않는다.
② **동사를 마지막 구간에 적는다** — `?_method=DELETE` 를 되살리지 않기 위해서다.
   그 관례는 **미들웨어 하나**를 요구하고, 그 미들웨어는 모든 `POST` 의 뜻을
   질의 문자열에 맡긴다. HTML 폼이 낼 수 있는 것은 `GET`·`POST` 둘뿐이라는
   제약을 숨기는 대신 **경로에 드러낸다.**

## ★★★ 상태는 **API 라우터가 이미 들고 있는 그 서비스 하나**를 쓴다

두 번째 `ModelCompositionService()` 를 여기 만들면 같은 모델에 대한 저장소가
둘이 되고 화면과 API 가 서로 다른 답을 낸다 — 그리고 **그 어긋남은 아무 오류도
내지 않는다.** 그렇다고 `models._service` 를 뚫지도 않는다(모듈 사설 이름이다).
**그 라우터의 공개 함수**를 부른다 — 그 함수들이 같은 `_service` 를 닫아 두고
있고, 그것이 이 모듈이 쓸 수 있는 유일한 공개 통로다.

## 성공하면 303, 실패하면 3요소 HTML

성공은 **`303 See Other`** 로 화면에 되돌린다(PRG). 그래야 새로고침이 방금 한
조작을 다시 하지 않는다 — 자원 복제 화면에서 그것은 「복제본이 하나 더」다.

실패는 **`/ui/run` 이 쓰는 그 통로**로 낸다(`web/render.py::error_context` →
`run_result.html` 의 `#validation`). 새 오류 화면을 또 만들면 3요소를 그리는
자리가 둘이 되고, 한쪽만 고쳐지는 날 어느 쪽이 맞는지 아무 검사도 말하지 않는다.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routers import models as models_api
from app.routers import regulation as regulation_api
from app.security.authorization import ADMIN_ROLE
from core.contracts.regulation import RegulationItem
from core.model.schemas import DERConfig, ModelConfig
from web.render import DEMO_MODEL, error_context, render_run_result

router = APIRouter(tags=["ui"])

#: 화면이 여는 주소 — 성공한 조작이 되돌아갈 자리다.
COMPOSER_URL = "/ui/model-composer"
REGULATION_URL = "/ui/regulation-admin"

#: 화면이 그리는 **데모 프로파일**의 이름과 첫 항목. `RegulationProfileAdminService`
#: 는 빈 상태로 시작하므로(편집이 파일을 건드리지 않는 것이 FR-504-AC3 이다)
#: 뿌리에서 화면을 열면 그릴 것이 없다. 새 대장을 만들지 않고
#: `tests/app/test_regulation_admin_router.py` 가 지나는 것과 **같은 경로**로
#: 한 벌 만든다.
DEMO_PROFILE_NAME = "현행"
_DEMO_PROFILE_VERSION = "v2026.1"
_DEMO_PROFILE_ITEM = RegulationItem(
    key="supply_duty.required_ratio",
    value=0.70,
    unit="비율",
    source="분산법 시행령",
)

#: 폼의 빈 칸. HTML 폼은 «비었다» 를 보내지 않는 것이 아니라 **빈 문자열**로
#: 보낸다 — 그대로 넘기면 `date` 칸이 «'' 는 날짜가 아니다» 로 터지고, 사람이
#: 받는 것은 「적지 않았다」가 아니라 형식 오류다.
_EMPTY = ""


def _blank_to_none(value: str) -> str | None:
    return value or None


# ── 상태 — 화면이 그리는 것은 **서비스가 보관하는 것**이다 ──────────────────


def composer_config() -> ModelConfig:
    """화면이 그릴 모델 구성 — **없으면 등록하고, 있으면 그대로 쓴다.**

    ⚠ 열 때마다 `DEMO_MODEL` 을 덮어쓰지 않는다. 덮어쓰면 사용자가 방금 복제한
    자원이 다음 새로고침에 사라지고, 그 사라짐은 **아무 오류도 내지 않는다** —
    사용자는 자기가 잘못 눌렀다고 생각한다.

    ⚠ `models._service` 를 직접 읽지 않는다. 공개 함수 둘(`list_resources`·
    `register_model`)이 같은 `_service` 를 닫아 두고 있으며, 「보관된 적이
    없다」는 그 공개 함수가 내는 **404** 로 안다.
    """
    try:
        composition = models_api.list_resources(DEMO_MODEL.name)
    except HTTPException:
        composition = models_api.register_model(DEMO_MODEL)
    return _config_of(composition)


def _config_of(composition: dict[str, Any]) -> ModelConfig:
    """JSON 응답 모양을 화면 문맥이 요구하는 `ModelConfig` 로 되돌린다.

    ⚠ 여기서 자원을 **거르거나 정렬하지 않는다.** 순서가 GUI 목록의 순서이며
    (`core/model/composition.py::resource_names`), 복제본이 원본 **바로 뒤**에
    놓이는 것이 조항이 정한 동작이다.
    """
    resources = [
        DERConfig(tag=str(item["tag"]), params=dict(item["params"]))
        for item in composition["resources"]
    ]
    return ModelConfig(name=str(composition["name"]), resources=resources)


def regulation_view(name: str) -> dict[str, Any]:
    """화면이 그릴 제도 프로파일 — 데모 한 벌은 **처음 열 때** 만든다.

    ⚠ `when` 을 생략해 부르지 않는다. `get_profile` 의 `when` 기본값은
    `Query(None)` **객체**이며(모듈 수준 단일값으로 둔 것이 `ruff` 의 `B008`
    회피다), 파이썬에서 그대로 부르면 그 객체가 날짜 자리로 들어가 유효기간
    비교에서 터진다. HTTP 로 올 때만 FastAPI 가 그것을 풀어 준다.
    """
    try:
        return regulation_api.get_profile(name, None)
    except HTTPException:
        if name != DEMO_PROFILE_NAME:
            raise
    return _publish_demo_profile()


def _publish_demo_profile() -> dict[str, Any]:
    """데모 프로파일을 **admin 편집 경로 그대로** 한 벌 발행한다.

    ⚠ `RegulationProfileDraft` 로 여기서 지어 화면에만 건네지 않는다 — 그러면
    화면이 그리는 프로파일이 서비스에 **없는** 것이 되고, 그것을 복제·개정하는
    폼이 「없는 프로파일」로 거부된다. 실제로 R62/WP-5 이전의 화면이 그 상태였다.
    """
    regulation_api.create_profile(
        regulation_api.ProfileRequest(
            name=DEMO_PROFILE_NAME, version=_DEMO_PROFILE_VERSION
        ),
        role=ADMIN_ROLE,
    )
    return regulation_api.upsert_profile_item(
        DEMO_PROFILE_NAME,
        regulation_api.ItemRequest(
            key=_DEMO_PROFILE_ITEM.key,
            value=_DEMO_PROFILE_ITEM.value,
            unit=_DEMO_PROFILE_ITEM.unit,
            source=_DEMO_PROFILE_ITEM.source,
            version=_DEMO_PROFILE_VERSION,
        ),
        role=ADMIN_ROLE,
    )


# ── 거부 — `/ui/run` 과 **같은 통로**로 낸다 ────────────────────────────────


def refusal(exc: HTTPException, *, field: str, action: str) -> HTMLResponse:
    """라우터가 낸 거부를 **필드·사유·조치 셋을 그린 화면**으로 낮춘다.

    `detail` 이 두 모양으로 온다 — 그 둘을 여기서 가른다.

    | 어디서 | `detail` | 이 함수가 하는 일 |
    |---|---|---|
    | `ValidationError` (400) | 3요소 사전 | **그대로 옮긴다** |
    | `KeyError`·`PermissionError` | 문자열 한 줄 | 사유로 삼고 `field`·`action` |
    |  (404·403) |  | 을 부르는 쪽이 채운다 |

    ⚠ 뒤 칸에서 **사유 문면을 새로 짓지 않는다.** 라우터가 적은 그 문장이
    「무엇이 없는가」를 이미 말한다 — 다시 지으면 같은 거부가 JSON 출구와
    화면에서 다른 말을 하게 된다.
    """
    detail = exc.detail
    if isinstance(detail, dict):
        context = error_context(
            field=str(detail["field"]),
            reason=str(detail["reason"]),
            action=str(detail["action"]),
            rule=detail.get("rule"),
        )
    else:
        context = error_context(field=field, reason=str(detail), action=action)
    return HTMLResponse(render_run_result(context), status_code=exc.status_code)


def _see_other(url: str) -> RedirectResponse:
    """성공을 **303** 으로 되돌린다 — 새로고침이 조작을 되풀이하지 않게.

    ⚠ `307`·`302` 가 아니다. `307` 은 `POST` 를 그대로 되풀이하고, `302` 는
    브라우저마다 메서드를 달리 바꾼다. `303 See Other` 만이 *「결과를 GET 으로
    보라」* 를 규격으로 말한다.
    """
    return RedirectResponse(url, status_code=303)


# ── 자원 구성 화면의 단추 셋 (FR-201-AC1) ──────────────────────────────────


@router.post("/ui/model-composer/resources")
def add_resource_form(tag: str = Form(...), name: str = Form(_EMPTY)) -> Any:
    """자원 추가 — 화면의 「자원 추가」 단추.

    자원 이름은 **파라미터로 내려간다**(`core/model/composition.py` 의
    `RESOURCE_NAME_KEY`). 여기서 이름 규칙을 판정하지 않는다 — 빈 이름 거부는
    `resource_name()` 이 이미 3요소로 말하고, 여기서 또 재면 같은 규칙이 두
    곳에 산다.
    """
    try:
        models_api.add_resource_endpoint(
            DEMO_MODEL.name,
            models_api.AddResourceRequest(tag=tag, params={"name": name}),
        )
    except HTTPException as exc:
        return refusal(
            exc,
            field="model.resource_tag",
            action="화면의 자원 종류 목록에서 고르십시오",
        )
    return _see_other(COMPOSER_URL)


@router.post("/ui/model-composer/resources/{resource_name}/duplicate")
def duplicate_resource_form(
    resource_name: str, new_name: str = Form(_EMPTY)
) -> Any:
    """자원 복제 — 행마다 붙은 「자원 복제」 단추."""
    try:
        models_api.duplicate_resource_endpoint(
            DEMO_MODEL.name,
            resource_name,
            models_api.DuplicateResourceRequest(new_name=new_name),
        )
    except HTTPException as exc:
        return refusal(
            exc,
            field="model.resource_name",
            action="구성에 있는 자원을 지목하십시오",
        )
    return _see_other(COMPOSER_URL)


@router.post("/ui/model-composer/resources/{resource_name}/delete")
def delete_resource_form(resource_name: str) -> Any:
    """자원 삭제 — 행마다 붙은 「자원 삭제」 단추.

    ⚠ 경로 끝의 `delete` 가 동사다. `?_method=DELETE` 를 되살리지 않는 근거는
    이 모듈 머리말 ② 에 적었다.
    """
    try:
        models_api.delete_resource_endpoint(DEMO_MODEL.name, resource_name)
    except HTTPException as exc:
        return refusal(
            exc,
            field="model.resource_name",
            action="구성에 있는 자원을 지목하십시오",
        )
    return _see_other(COMPOSER_URL)


# ── 제도 관리 화면의 폼 셋 (FR-504-AC3) ────────────────────────────────────


def _regulation_url(name: str) -> str:
    """조작한 **그 프로파일**의 화면으로 되돌린다.

    ⚠ 늘 데모 프로파일로 되돌리지 않는다. 되돌리면 방금 만든 프로파일이 화면
    어디에도 나타나지 않고, 사용자에게는 「생성이 안 됐다」와 구별되지 않는다.
    """
    return f"{REGULATION_URL}?profile={name}"


@router.post("/ui/regulation-admin/profiles")
def create_profile_form(
    role: str = Query(...), name: str = Form(_EMPTY), version: str = Form(_EMPTY)
) -> Any:
    """프로파일 생성 — 「프로파일 생성」 폼.

    ⚠ 역할을 여기서 `ADMIN_ROLE` 로 박지 않는다. 인가 판정의 정본은
    `app/security/authorization.py` 이고, 화면 출구가 역할을 스스로 정하면
    **가드가 있는 채로 늘 통과**한다 — 거부를 재는 검사가 초록불이 된다.
    """
    try:
        regulation_api.create_profile(
            regulation_api.ProfileRequest(name=name, version=version), role=role
        )
    except HTTPException as exc:
        return refusal(
            exc,
            field="regulation.profile_name",
            action="admin 권한으로 이름과 버전을 채워 다시 제출하십시오",
        )
    return _see_other(_regulation_url(name))


@router.post("/ui/regulation-admin/profiles/{source_name}/clone")
def clone_profile_form(
    source_name: str,
    role: str = Query(...),
    name: str = Form(_EMPTY),
    version: str = Form(_EMPTY),
) -> Any:
    """프로파일 복제 — 「프로파일 복제」 폼."""
    try:
        regulation_api.clone_profile(
            source_name,
            regulation_api.ProfileRequest(name=name, version=version),
            role=role,
        )
    except HTTPException as exc:
        return refusal(
            exc,
            field="regulation.profile_name",
            action="복제할 프로파일이 있는지 확인하고 새 이름·버전을 채우십시오",
        )
    return _see_other(_regulation_url(name))


@router.post("/ui/regulation-admin/profiles/{name}/items")
def upsert_item_form(
    name: str,
    # ⚠ `*` 로 끊는다 — 이 폼이 받는 칸이 여섯이고, 자리로 넘길 수 있게 두면
    # `unit` 과 `source` 처럼 **같은 타입의 이웃 칸**이 뒤바뀌어도 아무 오류가
    # 나지 않는다. FastAPI 는 키워드 전용 인자를 그대로 읽는다.
    *,
    role: str = Query(...),
    key: str = Form(_EMPTY),
    value: str = Form(_EMPTY),
    unit: str = Form(_EMPTY),
    source: str = Form(_EMPTY),
    valid_from: str = Form(_EMPTY),
    version: str = Form(_EMPTY),
) -> Any:
    """항목 추가·개정 — 「항목 추가·개정」 폼 (FR-504-AC3 「수정」).

    ⚠ **값을 수로 바꾸지 않는다.** `ItemRequest.value` 가 `Any` 인 것이 조항
    (FR-504-AC2 「스키마 변경 없이 항목을 추가」)이고, 화면 출구가 여기서
    「수처럼 보이면 수로」를 하면 배타 규칙 집합이나 요금표 참조를 담는 항목이
    그 변환에 걸린다. 폼이 보낸 것은 글자이며 글자로 보관된다.

    ⚠ 빈 `valid_from` 을 오늘로 채우지 않는다. 「적지 않았다」가 그대로
    내려가야 유효기간 없는 항목이 «늘 유효» 로 남는다 — 여기서 채우면 그
    기본값이 두 곳에 산다.
    """
    try:
        starts = date.fromisoformat(valid_from) if valid_from else None
    except ValueError as exc:
        # `date.fromisoformat` 이 내는 것은 `HTTPException` 이 아니다 — 폼이
        # 보낸 날짜 글자가 형식에 안 맞는 경우이며, 이것도 사람이 고칠 수 있는
        # 입력이므로 같은 3요소 화면으로 낸다.
        return refusal(
            HTTPException(status_code=400, detail=str(exc)),
            field="regulation.valid_from",
            action="유효 시작을 `YYYY-MM-DD` 로 적거나 비워 두십시오",
        )
    try:
        regulation_api.upsert_profile_item(
            name,
            regulation_api.ItemRequest(
                key=key,
                value=value,
                unit=_blank_to_none(unit),
                source=_blank_to_none(source),
                valid_from=starts,
                version=version,
            ),
            role=role,
        )
    except HTTPException as exc:
        return refusal(
            exc,
            field="regulation.item_key",
            action="admin 권한으로 항목키와 새 버전을 채워 다시 제출하십시오",
        )
    return _see_other(_regulation_url(name))
