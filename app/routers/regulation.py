"""제도 프로파일 admin 라우터 — 웹에서 생성·복제·수정. FR-504-AC3.

조항이 말하는 「웹 UI 에서」의 서버 쪽 절반이다. 화면은 `web/templates/
regulation_admin.html` 이고 그 화면이 누르는 경로가 여기 셋이다.

**권한 없는 요청은 403 이고, 그 사유가 어느 조작인지 말한다.** 세 경로가 같은
인가 함수를 지나므로 사유가 조작을 말하지 않으면 한 경로에서 가드가 빠져도
이웃 경로의 같은 메시지에 묻힌다 (R22 실측 형태).

**역할을 질의 파라미터로 받는 것은 이 라운드의 범위다.** 세션에서 역할을 끌어오는
것은 `FR-901` 인증 층의 일이고, 그 층이 아직 역할을 들고 있지 않다. 여기서
세션 파싱을 흉내내면 **인증이 붙는 순간 두 곳이 역할을 판정**하게 된다.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.regulation_admin import RegulationProfileAdminService
from core.contracts.regulation import RegulationItem
from core.contracts.validation import ValidationError
from core.regulation.profile import VerifiedRegulationItem

router = APIRouter(prefix="/regulation/profiles", tags=["regulation"])

#: 조회 시점 질의 파라미터를 **모듈 수준 단일값**으로 둔다. `ruff` 의 `B008` 이
#: 날짜 타입 인자의 기본값 자리 호출을 잡는다 — 문자열 인자에는 면제가 적용되지만
#: `date` 에는 적용되지 않으므로, 조항 취지대로 여기에 한 번만 만든다.
_WHEN_QUERY = Query(None)

_service = RegulationProfileAdminService()


class ProfileRequest(BaseModel):
    """프로파일 생성·복제 요청."""

    name: str
    version: str


class ItemRequest(BaseModel):
    """항목 추가·개정 요청 — FR-504-AC2 의 `(항목키, 값, 단위, 적용범위, 근거, 유효기간)`.

    **`value` 를 `Any` 로 두는 것이 조항이다.** 수치로 좁히면 배타 규칙 집합이나
    요금표 참조를 담을 수 없고, 그때 스키마를 고치는 것이 곧 「스키마 변경 없이
    항목을 추가」(FR-504-AC2)의 위반이다.
    """

    key: str
    value: Any
    unit: str | None = None
    source: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    verified_at: date | None = None
    #: 개정 결과를 실을 새 버전 — 제자리 수정을 하지 않는다 (FR-504-AC4).
    version: str = Field(...)

    def to_item(self) -> RegulationItem:
        """계약 항목으로 옮긴다 — 최종확인일이 있으면 `VerifiedRegulationItem`.

        최종확인일은 `RegulationItem` 계약에 없고 `core/regulation/` 의 하위
        클래스가 들고 있다 (FR-504-AC6). 웹 편집 경로가 그 필드를 실을 수
        없으면 조항이 화면에서 닫히지 않는다.
        """
        common = {
            "key": self.key,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
        }
        if self.verified_at is None:
            return RegulationItem(**common)  # type: ignore[arg-type]
        return VerifiedRegulationItem(**common, verified_at=self.verified_at)  # type: ignore[arg-type]


def _view(profile: Any, *, when: date | None = None) -> dict[str, object]:
    """프로파일 응답 — 항목을 유효기간 적용 상태로 낸다."""
    as_of = when or date.today()
    return {
        "name": profile.name,
        "version": profile.version,
        "items": [
            {
                "key": item.key,
                "value": item.value,
                "unit": item.unit,
                "source": item.source,
            }
            for item in profile.items(when=as_of)
        ],
    }


def _forbidden(exc: PermissionError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc))


@router.get("/{name}")
def get_profile(name: str, when: date | None = _WHEN_QUERY) -> dict[str, object]:
    """프로파일 조회 — 읽기에는 admin 권한을 요구하지 않는다.

    `when` 은 **분석연도에 맞는 값**을 고르는 자리다 (FR-504-AC5). 없으면 오늘로
    본다 — 화면이 「지금 유효한 제도」를 보여 주는 것이 기본이다.
    """
    profile = _service.get(name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"제도 프로파일이 없습니다: {name!r}")
    return _view(profile, when=when)


@router.post("")
def create_profile(request: ProfileRequest, role: str = Query(...)) -> dict[str, object]:
    """프로파일 생성 (FR-504-AC3 「생성」)."""
    try:
        created = _service.create(role=role, name=request.name, version=request.version)
    except PermissionError as exc:
        raise _forbidden(exc) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.as_dict()) from exc
    return _view(created)


@router.post("/{name}/clone")
def clone_profile(
    name: str, request: ProfileRequest, role: str = Query(...)
) -> dict[str, object]:
    """프로파일 복제 (FR-504-AC3 「복제」)."""
    try:
        cloned = _service.clone(
            role=role, source_name=name, name=request.name, version=request.version
        )
    except PermissionError as exc:
        raise _forbidden(exc) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.as_dict()) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _view(cloned)


@router.patch("/{name}/items")
def upsert_profile_item(
    name: str, request: ItemRequest, role: str = Query(...)
) -> dict[str, object]:
    """항목 추가·개정 (FR-504-AC3 「수정」)."""
    try:
        updated = _service.upsert_item(
            role=role, name=name, item=request.to_item(), version=request.version
        )
    except PermissionError as exc:
        raise _forbidden(exc) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.as_dict()) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _view(updated, when=request.valid_from)
