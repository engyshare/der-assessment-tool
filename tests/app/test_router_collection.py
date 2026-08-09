"""14.6 — 라우터 자동 수집 (NFR-207-AC1).

**«파일을 놓으면 실제로 라우트가 는다» 를 검증한다.** 수집기가 고정 목록을
들고 있으면 파일을 놓아도 늘지 않는다 — 6.7 이 자원에서 만난 형태다.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import app.routers as routers_pkg
from app.routers.collect import (
    RouterCollectionError,
    assert_routers_present,
    collect_routers,
    count_routes,
)


@pytest.mark.req("NFR-207-AC1")
def test_existing_routers_collected_automatically() -> None:
    """``app/routers/`` 의 기존 라우터(health·auth·scenarios)가 자동 수집된다.

    오라클: 순위 4 (정의 항등식). 중앙 등록 파일 없이 패키지 스캔으로.
    """
    routers = collect_routers(routers_pkg)
    # health, auth, scenarios — 최소 3개의 APIRouter
    assert len(routers) >= 3, f"라우터 자동 수집이 안 됐다: {len(routers)}건"
    assert count_routes(routers) > 0


def test_dropping_a_router_file_shrinks_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """«파일을 놓으면 늘고, 빼면 준다» — 고정 목록이 아님을 증명.

    임시 패키지에 라우터 2개 → 수집 2건. 하나를 빼고 다시 수집 → 1건.
    """
    # 임시 패키지 생성
    pkg_dir = tmp_path / "tmp_routers"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "a.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n"
        "@router.get('/a')\ndef a(): return {}\n",
        encoding="utf-8",
    )
    (pkg_dir / "b.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n"
        "@router.get('/b')\ndef b(): return {}\n",
        encoding="utf-8",
    )

    # tmp_path 를 패키지로 import 가능하게
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        pkg = importlib.import_module("tmp_routers")
        routers = collect_routers(pkg)
        assert len(routers) == 2
        assert count_routes(routers) == 2

        # b.py 제거 → 재수집 → 1건
        (pkg_dir / "b.py").unlink()
        # 캐시된 모듈 제거
        sys.modules.pop("tmp_routers.b", None)
        sys.modules.pop("tmp_routers", None)
        pkg = importlib.import_module("tmp_routers")
        routers = collect_routers(pkg)
        assert len(routers) == 1, "파일을 빼도 라우터가 안 줄면 고정 목록이다 (NFR-207 위반)"
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("tmp_routers", None)


def test_private_module_skipped(tmp_path: Path) -> None:
    """``_`` 로 시작하는 모듈은 건너뛴다 — 내부 도우미 자리."""
    pkg_dir = tmp_path / "_skip_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "_internal.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n",
        encoding="utf-8",
    )
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        sys.modules.pop("_skip_pkg", None)
        pkg = importlib.import_module("_skip_pkg")
        routers = collect_routers(pkg)
        assert routers == [], "_internal 은 수집되면 안 된다"
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("_skip_pkg", None)


def test_assert_routers_present_catches_empty_collection(
    tmp_path: Path,
) -> None:
    """수집이 0건이면 예외 — «구현이 없다» 로 읽지 않는다 (§13.0.1 ④)."""
    pkg_dir = tmp_path / "empty_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        sys.modules.pop("empty_pkg", None)
        pkg = importlib.import_module("empty_pkg")
        routers = collect_routers(pkg)
        with pytest.raises(RouterCollectionError, match="한 건도"):
            assert_routers_present(routers)
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("empty_pkg", None)


def test_non_package_rejected() -> None:
    """패키지가 아닌 모듈을 넘기면 예외."""
    import math
    with pytest.raises(RouterCollectionError, match="패키지가 아닙니다"):
        collect_routers(math)
