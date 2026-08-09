#!/usr/bin/env python3
"""check_marker_substance.py 음성 테스트 — 감지 능력 확인.

통과만 보고 끝내면 아무것도 검사하지 않는 장치일 수 있다 (spec §13.0.1 ④).
이 저장소는 그 이유로 도구마다 음성 테스트를 요구한다.

여기서 확인하는 것은 **검사가 실제로 위반을 잡는가**이다. 8종 케이스로
잡히는 것과 잡히지 않는 것을 모두 확인한다.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "check_marker_substance.py"
TMP_ROOT = HERE / "_tmp_neg_marker"


@contextmanager
def workspace() -> Iterator[Path]:
    TMP_ROOT.mkdir(exist_ok=True)
    path = TMP_ROOT / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        if path.resolve().is_relative_to(TMP_ROOT.resolve()):
            shutil.rmtree(path, ignore_errors=True)


def run(tests_dir: Path) -> tuple[int, str]:
    """검사를 실행하고 (종료 코드, 출력)을 돌려준다."""
    p = subprocess.run(
        [sys.executable, str(CHECKER), "--tests", str(tests_dir)],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def write(d: Path, name: str, body: str) -> Path:
    f = d / name
    f.write_text(body, encoding="utf-8")
    return f


CASES: list[tuple[str, callable, str]] = []


def case(name, fn, expect):
    CASES.append((name, fn, expect))


# ── 위반 케이스 (잡혀야 함) ─────────────────────────────────────────────

# 1 — req 마커 + 본문 pass
def c_req_with_pass(d: Path):
    t = d / "t1"
    t.mkdir()
    write(t, "test_pass.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_violation():\n"
        "    pass\n"
    ))
    return run(t)
case("req 마커 + 본문 pass", c_req_with_pass, "req")


# 2 — req 마커 + print 만
def c_req_with_print(d: Path):
    t = d / "t2"
    t.mkdir()
    write(t, "test_print.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_violation():\n"
        "    print('hello')\n"
    ))
    return run(t)
case("req 마커 + print 만", c_req_with_print, "req")


# 3 — req 마커 + 무조건 pytest.skip()
def c_req_with_unconditional_skip(d: Path):
    t = d / "t3"
    t.mkdir()
    write(t, "test_skip.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_violation():\n"
        "    pytest.skip('always skip')\n"
    ))
    return run(t)
case("req 마커 + 무조건 pytest.skip()", c_req_with_unconditional_skip, "req")


# ── 정당 케이스 (잡히면 안 됨) ───────────────────────────────────────────

# 4 — req + manual 마커 + 본문 pass
def c_manual_with_pass(d: Path):
    t = d / "t4"
    t.mkdir()
    write(t, "test_manual.py", (
        "import pytest\n\n"
        "@pytest.mark.manual\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_stub():\n"
        "    pass\n"
    ))
    return run(t)
case("req + manual 마커 + 본문 pass", c_manual_with_pass, "")


# 5 — req 마커 + with pytest.raises(...)
def c_with_pytest_raises(d: Path):
    t = d / "t5"
    t.mkdir()
    write(t, "test_raises.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_valid():\n"
        "    with pytest.raises(ValueError):\n"
        "        raise ValueError()\n"
    ))
    return run(t)
case("req 마커 + with pytest.raises(...)", c_with_pytest_raises, "")


# 6 — req 마커 + 같은 모듈 헬퍼가 assert
def c_helper_with_assert(d: Path):
    t = d / "t6"
    t.mkdir()
    write(t, "test_helper.py", (
        "import pytest\n\n"
        "def helper():\n"
        "    assert True\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_valid():\n"
        "    helper()\n"
    ))
    return run(t)
case("req 마커 + 같은 모듈 헬퍼가 assert", c_helper_with_assert, "")


# 7 — 마커 없음 + 본문 pass
def c_no_marker_pass(d: Path):
    t = d / "t7"
    t.mkdir()
    write(t, "test_no_marker.py", (
        "def test_no_marker():\n"
        "    pass\n"
    ))
    return run(t)
case("마커 없음 + 본문 pass", c_no_marker_pass, "")


# 8 — req 마커 + for 루프 안의 assert (결함 고정 케이스)
def c_req_with_assert_in_for_loop(d: Path):
    """검사 결함: 본문을 한 겹만 보고 for/if/while 안의 assert를 놓친다.

    이 케이스는 결함을 고정한다 — for 루프 안에 assert가 있으면
    잡히면 안 된다 (잡히면 오탐).
    """
    t = d / "t8"
    t.mkdir()
    write(t, "test_for_assert.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_valid():\n"
        "    for i in range(3):\n"
        "        assert i < 5\n"
    ))
    return run(t)
case("req 마커 + for 루프 안의 assert", c_req_with_assert_in_for_loop, "")


def main() -> int:
    fails = 0
    for name, fn, expect in CASES:
        with workspace() as d:
            rc, out = fn(d)
            # 양성 케이스는 expect가 비어 있고, fn이 판정해 0을 돌려준다
            # 위반 케이스는 expect가 "req"가 들어 있고, 종료 코드가 1이어야 한다
            hit = (expect in out) if expect else (rc == 0)
            mark = "OK  " if hit else "MISS"
            if not hit:
                fails += 1
            print(f"  {mark} {name}")
            if not hit:
                print(f"       기대 '{expect}' in output / 종료 {rc}")
                for ln in out.splitlines()[:8]:
                    print(f"         {ln}")

    print()
    print(f"음성·양성 테스트 {len(CASES)}종 — 통과 {len(CASES)-fails} / 실패 {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
