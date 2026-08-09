"""라우터 자동 수집 — 작업 14.6 / NFR-207-AC1.

**중앙 등록 파일을 만들지 않는다** (브리프 14.6). ``core/contracts/registry.py``
의 ``discover()`` 가 같은 원리를 구현했고, 여기서는 APIRouter 인스턴스를
``app/routers/`` 패키지에서 자동 수집한다.

    app/routers/<name>.py   →   router = APIRouter(...)
                               ↑ 이 인스턴스를 자동으로 찾는다

라우터를 추가하려면 ``app/routers/`` 에 새 ``.py`` 파일을 놓기만 하면 된다 —
어느 «등록 파일» 도 고치지 않는다 (§16.1 W-3).

**«파일을 놓으면 실제로 라우트가 는다» 를 검증 케이스가 확인한다.**
수집기가 고정 목록을 들고 있으면 파일을 놓아도 늘지 않는다 — 6.7 이 자원에서
만난 형태다. ``tests/app/test_router_collection.py`` 가 그것을 잡는다.
"""
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from fastapi import APIRouter


class RouterCollectionError(Exception):
    """라우터 자동 수집이 성립하지 않는다 — 기동을 막는다 (NFR-207-AC2 정신)."""


def collect_routers(package: ModuleType) -> list[APIRouter]:
    """``package`` (예: ``app.routers``) 의 APIRouter 인스턴스를 자동 수집.

    원리는 ``registry.discover`` 와 같다:
        1. ``pkgutil.iter_modules`` 로 모듈 이름을 얻는다
        2. ``importlib.import_module`` 로 각 모듈을 import (인스턴스가 정의되어야 한다)
        3. ``APIRouter`` 인스턴스를 찾아 모은다

    ``_`` 로 시작하는 모듈은 건너뛴다 — 내부 도우미 자리.
    """
    if not hasattr(package, "__path__"):
        raise RouterCollectionError(
            f"{package.__name__} 은 패키지가 아닙니다. 스캔 대상은 "
            "`app/routers/` 처럼 모듈을 담는 패키지입니다"
        )

    routers: list[APIRouter] = []
    seen_ids: set[int] = set()
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, APIRouter) and id(obj) not in seen_ids:
                seen_ids.add(id(obj))
                routers.append(obj)
    return routers


def count_routes(routers: list[APIRouter]) -> int:
    """수집된 라우터의 총 경로 수 — 검증 케이스가 «늘었는가» 를 볼 때 쓴다."""
    return sum(len(r.routes) for r in routers)


def assert_routers_present(routers: list[APIRouter]) -> None:
    """«수집이 성립하지 않은 것» 을 «구현이 없다» 로 읽지 않는다 (§13.0.1 ④)."""
    if not routers:
        raise RouterCollectionError(
            "수집된 라우터가 한 건도 없다 — 이것이 «라우터가 없다» 인지 "
            "«수집이 망가졌다» 인지 결과만으로는 알 수 없다. app/routers/ 에 "
            "최소 1개의 APIRouter 인스턴스가 있어야 한다 (NFR-207)"
        )
