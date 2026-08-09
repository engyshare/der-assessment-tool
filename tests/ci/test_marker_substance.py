"""조항 마커 검증 내용 검사 — CI 게이트 검증.

**왜 게이트에 테스트가 붙는가.** 게이트는 그것이 실제로 무언가를 막을 때만
게이트다. 스크립트가 저장소에 있다는 사실과 CI가 그것을 부른다는 사실은 다르고,
CI가 부른다는 사실과 그것이 결함을 잡는다는 사실도 다르다.

여기서는 검사 논리를 시험합니다 — 판정 논리가 위반을 잡는가, 정당한
테스트를 오판하지 않는가.

`NFR-107-M1`을 자동 매핑으로 다는 이유: 이 조항은 게이트 자신이므로
`docs/manual-checks.yaml`에 등재하는 것이 **금지**되어 있다 (NFR-107-AC5 ⓒ).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_marker_substance.py"


def _script(stem: str):
    """`scripts/`는 패키지가 아니므로 경로로 불러온다."""
    import importlib.util

    scripts = str(REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    name = f"_gate_{stem}"
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / f"{stem}.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _judge(files: dict[str, str]):
    """`{경로: 소스}`를 테스트 디렉토리로 보고 판정한다."""
    mod = _script("check_marker_substance")

    # 임시 디렉토리 만들기
    import shutil
    import tempfile
    td = Path(tempfile.mkdtemp())
    try:
        tests = td / "tests"
        tests.mkdir()

        for path, source in files.items():
            f = tests / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(source, encoding="utf-8")

        violations, exit_code = mod.check_marker_substance(tests)
        # violations는 이미 (path, lineno, func_name, reqs) 형식
        # path를 tests/에 상대적인 경로로 변환
        violation_list = [(Path(p).relative_to(tests), lineno, func, reqs)
                          for p, lineno, func, reqs in violations]
        return exit_code, violation_list
    finally:
        shutil.rmtree(td, ignore_errors=True)


# ── 위반을 잡는다 ─────────────────────────────────────────────────────


@pytest.mark.req("NFR-107-M1")
def test_req_marker_with_pass_body_is_a_violation() -> None:
    """req 마커가 있는데 본문이 pass만 있으면 위반."""
    exit_code, violations = _judge({
        "test_violation.py": (
            "import pytest\n\n"
            "@pytest.mark.req('FR-101-AC1')\n"
            "def test_violation():\n"
            "    pass\n"
        ),
    })
    assert exit_code == 1
    assert len(violations) == 1
    assert violations[0][2] == "test_violation"
    assert violations[0][3] == ["FR-101-AC1"]


@pytest.mark.req("NFR-107-M1")
def test_req_marker_with_only_print_is_a_violation() -> None:
    """req 마커가 있는데 본문에 print만 있으면 위반."""
    exit_code, violations = _judge({
        "test_print.py": (
            "import pytest\n\n"
            "@pytest.mark.req('FR-101-AC1')\n"
            "def test_violation():\n"
            "    print('hello')\n"
        ),
    })
    assert exit_code == 1
    assert len(violations) == 1


@pytest.mark.req("NFR-107-M1")
def test_req_marker_with_unconditional_skip_is_a_violation() -> None:
    """req 마커가 있는데 무조건 pytest.skip()만 하면 위반.

    「판정 못 한다」면서 매핑표에는「검증했다」로 세어집니다.
    """
    exit_code, violations = _judge({
        "test_skip.py": (
            "import pytest\n\n"
            "@pytest.mark.req('FR-101-AC1')\n"
            "def test_violation():\n"
            "    pytest.skip('always skip')\n"
        ),
    })
    assert exit_code == 1
    assert len(violations) == 1


# ── 정당한 테스트를 오판하지 않는다 ───────────────────────────────────


@pytest.mark.req("NFR-107-M1")
def test_manual_marker_with_pass_is_allowed() -> None:
    """manual 마커가 있으면 본문이 pass라도 정상."""
    exit_code, violations = _judge({
        "test_manual.py": (
            "import pytest\n\n"
            "@pytest.mark.manual\n"
            "@pytest.mark.req('FR-101-AC1')\n"
            "def test_stub():\n"
            "    pass\n"
        ),
    })
    assert exit_code == 0
    assert len(violations) == 0


@pytest.mark.req("NFR-107-M1")
def test_with_pytest_raises_counts_as_verification() -> None:
    """with pytest.raises(...)는 검증으로 인정."""
    exit_code, violations = _judge({
        "test_raises.py": (
            "import pytest\n\n"
            "@pytest.mark.req('FR-101-AC1')\n"
            "def test_valid():\n"
            "    with pytest.raises(ValueError):\n"
            "        raise ValueError()\n"
        ),
    })
    assert exit_code == 0
    assert len(violations) == 0


@pytest.mark.req("NFR-107-M1")
def test_mock_assertion_counts_as_verification() -> None:
    """mock.assert_*() 형태는 검증으로 인정."""
    exit_code, violations = _judge({
        "test_mock.py": (
            "import pytest\n"
            "from unittest.mock import MagicMock\n\n"
            "@pytest.mark.req('FR-101-AC1')\n"
            "def test_valid():\n"
            "    m = MagicMock()\n"
            "    m.method.assert_called_once()\n"
        ),
    })
    assert exit_code == 0
    assert len(violations) == 0


@pytest.mark.req("NFR-107-M1")
def test_module_level_pytestmark_is_inherited() -> None:
    """모듈 수준 pytestmark는 상속됩니다."""
    exit_code, violations = _judge({
        "test_module.py": (
            "import pytest\n\n"
            "pytestmark = [pytest.mark.req('FR-101-AC1')]\n\n"
            "def test_violation():\n"
            "    pass\n"
        ),
    })
    assert exit_code == 1
    assert len(violations) == 1


@pytest.mark.req("NFR-107-M1")
def test_class_decorator_is_inherited() -> None:
    """클래스 데코레이터는 상속됩니다."""
    exit_code, violations = _judge({
        "test_class.py": (
            "import pytest\n\n"
            "@pytest.mark.req('FR-101-AC1')\n"
            "class TestClass:\n"
            "    def test_violation(self):\n"
            "        pass\n"
        ),
    })
    assert exit_code == 1
    assert len(violations) == 1


@pytest.mark.req("NFR-107-M1")
def test_no_req_marker_is_not_a_target() -> None:
    """req 마커가 없으면 대상이 아닙니다."""
    exit_code, violations = _judge({
        "test_no_marker.py": (
            "def test_no_marker():\n"
            "    pass\n"
        ),
    })
    assert exit_code == 0
    assert len(violations) == 0


@pytest.mark.req("NFR-107-M1")
def test_assert_in_for_loop_is_detected() -> None:
    """for 루프 안의 assert도 검증으로 인정 (결함 고정 케이스).

    검사 결함: 본문을 한 겹만 보고 for/if/while 안의 assert를 놓친다.
    """
    exit_code, violations = _judge({
        "test_for.py": (
            "import pytest\n\n"
            "@pytest.mark.req('FR-101-AC1')\n"
            "def test_valid():\n"
            "    for i in range(3):\n"
            "        assert i < 5\n"
        ),
    })
    assert exit_code == 0
    assert len(violations) == 0


# ── 에러 처리 ─────────────────────────────────────────────────────────


@pytest.mark.req("NFR-107-M1")
def test_parsing_error_returns_exit_code_2(tmp_path: Path) -> None:
    """파싱 실패는 종료 코드 2를 낸다 (종료 코드 0이 아니어야 함)."""
    tests = tmp_path / "tests"
    tests.mkdir()

    (tests / "broken.py").write_text("def test_x(:\n    pass\n", encoding="utf-8")

    import subprocess
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--tests", str(tests)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2, (
        f"파싱 실패인데 종료 코드 {result.returncode} 입니다. "
        "0이면 게이트가 조용히 무력화됩니다"
    )
    assert "파싱 실패" in result.stderr or "파싱 실패" in result.stdout
