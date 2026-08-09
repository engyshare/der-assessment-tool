from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

_BASE = Path(__file__).resolve().parent / "_tmp_pytest"
collect_ignore = ["_tmp_pytest"]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    _BASE.mkdir(exist_ok=True)
    path = _BASE / f"case_{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        if path.resolve().is_relative_to(_BASE.resolve()):
            shutil.rmtree(path, ignore_errors=True)
