"""모델 구성 라우터 — GUI 자원 추가·삭제·복제. FR-201-AC1.

조항이 말하는 「GUI에서」의 서버 쪽 절반이다. 화면은 `web/templates/
model_composer.html` 이고 그 화면이 누르는 경로가 여기 넷이다.

**추가 가능한 자원 종류를 목록 응답에 함께 싣는다.** 화면이 종류 목록을 자기
안에 적어 두면 자원 1종 추가가 화면 수정을 부르고, 조항의 「엔진 코드 변경이
발생하지 않는다」가 서버에서만 성립하고 화면에서 깨진다.

**`ValidationError` 를 400 으로 내리되 3요소를 구조로 보낸다** (NFR-303).
문자열 한 줄로 내리면 화면이 그것을 다시 파싱해 「어느 칸이 틀렸는가」를
찾아야 한다.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import ModelCompositionService
from core.contracts.validation import ValidationError
from core.model.schemas import ModelConfig

router = APIRouter(prefix="/models", tags=["models"])

_service = ModelCompositionService()


class AddResourceRequest(BaseModel):
    """자원 추가 요청 — 종류(`tag`)와 파라미터."""

    tag: str
    params: dict[str, Any] = Field(default_factory=dict)


class DuplicateResourceRequest(BaseModel):
    """자원 복제 요청 — 복제본의 새 이름."""

    new_name: str


def _composition(config: ModelConfig) -> dict[str, object]:
    """구성 응답 — 자원 목록과 **추가 가능한 종류**를 함께 낸다."""
    return {
        "name": config.name,
        "resources": [
            {"tag": r.tag, "params": r.params} for r in config.resources
        ],
        "available_tags": list(_service.available_tags()),
    }


def _bad_request(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=exc.as_dict())


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post("")
def register_model(config: ModelConfig) -> dict[str, object]:
    """편집할 모델 구성을 등록한다."""
    return _composition(_service.register(config))


@router.get("/{model_name}/resources")
def list_resources(model_name: str) -> dict[str, object]:
    """자원 목록 + 추가 가능한 종류 (FR-201-AC1)."""
    config = _service.get(model_name)
    if config is None:
        raise HTTPException(status_code=404, detail=f"모델 구성이 없습니다: {model_name!r}")
    return _composition(config)


@router.post("/{model_name}/resources")
def add_resource_endpoint(
    model_name: str, request: AddResourceRequest
) -> dict[str, object]:
    """자원 추가 (FR-201-AC1 「추가」)."""
    try:
        return _composition(
            _service.add(model_name, tag=request.tag, params=request.params)
        )
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.delete("/{model_name}/resources/{resource_name}")
def delete_resource_endpoint(model_name: str, resource_name: str) -> dict[str, object]:
    """자원 삭제 (FR-201-AC1 「삭제」)."""
    try:
        return _composition(_service.remove(model_name, resource_name))
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.post("/{model_name}/resources/{resource_name}/duplicate")
def duplicate_resource_endpoint(
    model_name: str, resource_name: str, request: DuplicateResourceRequest
) -> dict[str, object]:
    """자원 복제 (FR-201-AC1 「복제」)."""
    try:
        return _composition(
            _service.duplicate(model_name, resource_name, new_name=request.new_name)
        )
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    except KeyError as exc:
        raise _not_found(exc) from exc
