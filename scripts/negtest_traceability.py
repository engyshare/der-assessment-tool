"""gen_traceability.py 음성 테스트 — 감지 능력 확인.

통과만 보고 끝내면 아무것도 검사하지 않는 장치일 수 있다 (spec §13.0.1 ④).
이 저장소는 그 이유로 도구마다 음성 테스트를 요구한다.

여기서 확인하는 것은 **2.7 게이트 활성화가 실제로 무엇을 막는가**이다.
게이트를 켜기 전에, 켰을 때 잡히기를 기대하는 상황을 하나씩 심어 본다.
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
REPO = HERE.parent
GEN = HERE / "gen_traceability.py"
SPEC = next((REPO / "rslt").glob("spec-*.md"))
MANUAL = REPO / "docs/manual-checks.yaml"
TMP_ROOT = HERE / "_tmp_negtrace"


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


def run(tests_dir: Path, manual: Path = MANUAL, out: Path | None = None,
        spec: Path = SPEC):
    with workspace() as td:
        target = out or (td / "out.md")
        p = subprocess.run(
            [sys.executable, str(GEN), "--spec", str(spec),
             "--manual", str(manual), "--tests", str(tests_dir),
             "--out", str(target)],
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


# ── 기준 상태 ─────────────────────────────────────────────────────────
def baseline(d: Path):
    return run(d / "empty")


# 1 — manual 스텁이 `자동`으로 표시되던 구멍 (NFR-107-AC1.manual)
#
#     v0.9까지 정규식이 @pytest.mark.req 만 긁어, 아무것도 실행하지 않는
#     skip 스텁이 "실행·통과 확인" 칸에 앉았다. 이제는 수동으로 세고,
#     대장 기록이 없으면 결함으로 막는다.
def c_stub_no_record(d: Path):
    t = d / "t1"
    t.mkdir()
    write(t, "test_stub.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "@pytest.mark.manual\n"
        "def test_spec_stub():\n"
        "    pytest.skip('명세 스텁')\n"
    ))
    return run(t)
case("manual 스텁인데 수행 기록 없음", c_stub_no_record, "수행 기록 없는 수동 스텁")


# 2 — 클래스 데코레이터로 붙은 manual 도 상속되어야 한다
def c_stub_class(d: Path):
    t = d / "t2"
    t.mkdir()
    write(t, "test_cls.py", (
        "import pytest\n\n"
        "@pytest.mark.manual\n"
        "class TestUI:\n"
        "    @pytest.mark.req('FR-101-AC2')\n"
        "    def test_x(self):\n"
        "        pass\n"
    ))
    return run(t)
case("클래스 수준 manual 상속", c_stub_class, "수행 기록 없는 수동 스텁")


# 3 — 모듈 수준 pytestmark 도 상속되어야 한다
def c_stub_module(d: Path):
    t = d / "t3"
    t.mkdir()
    write(t, "test_mod.py", (
        "import pytest\n\n"
        "pytestmark = [pytest.mark.manual]\n\n"
        "@pytest.mark.req('FR-101-AC3')\n"
        "def test_y():\n"
        "    pass\n"
    ))
    return run(t)
case("모듈 pytestmark manual 상속", c_stub_module, "수행 기록 없는 수동 스텁")


# 4 — 진짜 자동 테스트는 자동으로 세어야 한다 (양성 확인)
#
#     음성만 보면 "전부 결함으로 보고하는" 장치도 만점을 받는다.
def c_auto_ok(d: Path):
    t = d / "t4"
    t.mkdir()
    write(t, "test_auto.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_real():\n"
        "    assert True\n"
    ))
    rc, out = run(t)
    # 미매핑이 남아 있으므로 종료 코드는 1이지만, 결함(2)이면 안 된다
    return (0 if rc == 1 and "자동 1건" in out else 9), out
case("정상 자동 테스트는 통과 (양성)", c_auto_ok, "")


# 5 — 같은 조항에 자동 테스트와 스텁이 함께 있으면 자동이다
def c_auto_wins(d: Path):
    t = d / "t5"
    t.mkdir()
    write(t, "test_both.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "def test_real():\n"
        "    assert True\n\n"
        "@pytest.mark.req('FR-101-AC1')\n"
        "@pytest.mark.manual\n"
        "def test_stub():\n"
        "    pytest.skip('x')\n"
    ))
    rc, out = run(t)
    return (0 if rc == 1 and "자동 1건" in out and "수동 스텁 0건" in out else 9), out
case("자동+스텁 공존 시 자동 우선 (양성)", c_auto_wins, "")


# 6 — 파싱 실패를 조용히 건너뛰면 마커가 통째로 사라진다
def c_syntax(d: Path):
    t = d / "t6"
    t.mkdir()
    write(t, "test_broken.py", "def test_x(:\n    pass\n")
    return run(t)
case("테스트 파일 구문 오류", c_syntax, "파싱 실패")


# 7 — 게이트 자기참조 (NFR-107-AC5 ⓒ)
#
#     수동 예외 경로를 정당화하는 조항 자신이 그 경로로 "검증됨" 처리되면
#     아무것도 검증되지 않은 채 미매핑 0건 초록불이 뜬다.
def c_self_ref(d: Path):
    t = d / "t7"
    t.mkdir()
    m = write(d, "self-ref.yaml", (
        "version: 1\n"
        "checks:\n"
        "  - id: 'MC-X'\n"
        "    requirement: 'NFR-107'\n"
        "    criterion_id: 'NFR-107-AC1.manual'\n"
        "    why_manual: '게이트 자신을 수동으로 처리'\n"
        "    blocking_dod: false\n"
        "    status: '수행'\n"
        "    verdict: '통과'\n"
        "    performed_at: '2026-08-10'\n"
        "    performed_by: 'x'\n"
        "    result_note: 'x'\n"
    ))
    return run(t, manual=m)
case("게이트 자신을 수동 대장에 등재", c_self_ref, "게이트 자신을 수동 대장에")


# 8 — 폐기된 조항을 가리키는 테스트 마커 (매달린 참조)
def c_dangling(d: Path):
    t = d / "t8"
    t.mkdir()
    write(t, "test_ghost.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-402-AC3')\n"   # v0.9에서 폐기된 조항
        "def test_ghost():\n"
        "    pass\n"
    ))
    return run(t)
case("폐기된 조항을 가리키는 마커", c_dangling, "해당 수용기준이 spec에 없음")


# ── blocking_dod (WP-24C) ────────────────────────────────────────────
#
# `blocking_dod` 를 읽는 코드가 하나도 없었다. 사람이 적어 둔 "이건 차단이다"가
# 기계에는 주석과 같았다는 뜻이다. 아래 넷은 그 구멍을 닫는 검사가 실제로
# 감지하는지 확인한다.

# 9 — blocking_dod 칸을 지운다
def c_missing_blocking_dod(d: Path):
    t = d / "t9"
    t.mkdir()
    m = write(d, "missing-blocking.yaml", (
        "version: 1\n"
        "checks:\n"
        "  - id: MC-Z1\n"
        "    requirement: FR-101\n"
        "    criterion_id: FR-101-AC1\n"
        "    why_manual: x\n"
        "    status: '미수행'\n"
    ))
    assert "blocking_dod" not in m.read_text(encoding="utf-8")
    return run(t, manual=m)
case("blocking_dod 칸이 없는 항목", c_missing_blocking_dod, "blocking_dod 칸 누락")


# 10 — status: 수행인데 performed_at 이 비어 있다
def c_incomplete_record(d: Path):
    t = d / "t10"
    t.mkdir()
    m = write(d, "incomplete-record.yaml", (
        "version: 1\n"
        "checks:\n"
        "  - id: MC-Z2\n"
        "    requirement: FR-101\n"
        "    criterion_id: FR-101-AC2\n"
        "    why_manual: x\n"
        "    blocking_dod: false\n"
        "    status: '수행'\n"
        "    performed_at: null\n"
        "    performed_by: '홍길동'\n"
        "    result_note: '통과'\n"
    ))
    body = m.read_text(encoding="utf-8")
    assert "status: '수행'" in body and "performed_at: null" in body
    return run(t, manual=m)
case("수행인데 performed_at 기록 없음", c_incomplete_record, "수행 기록 불완전")


# 11 — 차단 미수행이 있으면 「판정불가」로 표기되는가 (양성)
#
#     ★★★ 2026-09-05(R61) — **이 케이스가 실제 대장을 fixture 로 쓰고 있었고,
#     그래서 MC-1 이 닫히는 날 CI 가 빨간불이 됐다.** 종전 주석은
#     *「이 저장소의 실제 docs/manual-checks.yaml 에는 이미 MC-1
#     (blocking_dod: true, status: 미수행)이 있다. 이것을 fixture 로 새로 심을
#     필요가 없다 — 이미 심겨 있다」* 였다.
#
#     ⚠⚠ **그 문장이 「대장은 앞으로도 그 상태일 것이다」를 가정한다.**
#     MC-1 은 언젠가 반드시 수행되는 항목이고(그것이 이 저장소의 목표다),
#     수행되는 순간 이 케이스가 MISS 로 뒤집힌다 — **검사 대상이 좋아지면
#     검사가 빨간불이 되는** 형태다. 실제로 그렇게 됐다.
#
#     ★ 이 저장소는 같은 형태를 이미 두 번 적어 두었다 — 「검사가 자기 검사
#     대상에서 정본을 읽어 오면 공허해진다」(R35) · 「대장이 좋아지면 음성
#     사례가 조용히 죽는다」(R52). **여기는 조용히 죽는 대신 시끄럽게 죽었다**
#     (CI 가 잡았다). 그것이 나은 쪽이지만, 애초에 실제 대장을 볼 이유가 없다.
#
#     ⇒ **자족적인 합성 대장으로 바꾼다.** 재는 것은 그대로다 — 차단 미수행이
#     있을 때 gen_traceability.py 가 그것을 조용히 지나치지 않고 「판정불가」로
#     표기하는가. 표기 로직이 빠지면(회귀) 이 케이스가 MISS 로 드러난다.
def c_blocking_marked_positive(d: Path):
    t = d / "t11"
    t.mkdir()
    write(t, "test_auto.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-1-AC1')\n"
        "def test_real():\n"
        "    assert True\n"
    ))
    spec = write(d, "mini-spec-11.md", MINI_SPEC)
    m = write(d, "blocking-unperformed.yaml", (
        "version: 1\n"
        "checks:\n"
        "  - id: MC-Z11\n"
        "    requirement: FR-1\n"
        "    criterion_id: FR-1-AC1\n"
        "    why_manual: x\n"
        "    blocking_dod: true\n"
        "    status: '미수행'\n"
    ))
    rc, out = run(t, manual=m, spec=spec)
    # rc 는 0 이 아닐 수 있다 — 차단 미수행이 있으면 그 자체로 rc 가 움직인다.
    # 여기서 확인하는 것은 **결함(rc=2)이 아니면서** 판정불가 표기가 그 항목의
    # ID 와 함께 실제로 나오는가다.
    ok = rc != 2 and "판정불가" in out and "MC-Z11" in out
    return (0 if ok else 9), out
case("차단 미수행이 있으면 판정불가로 표기됨 (양성)",
     c_blocking_marked_positive, "")


# 12 — 차단 미수행이 하나도 없는 대장은 rc=0 (오탐 없음을 고정)
#
#     1~3만 있으면 판정 로직이 "항상 참"을 내도 초록불이다. 실제 spec은
#     항상 어딘가 미매핑이 남아 있어(다른 레인이 동시에 채우는 중) rc를
#     그것으로 오염시키므로, **자족적인 미니 spec**을 심어 rc=0을
#     literal하게 고정한다.
#     ⚠ 종전 이 줄은 *「여기만」* 이라 적었는데 **R61 이 케이스 11 도 이 spec 을
#     쓰게 바꿨다** — 그 케이스가 실제 대장을 보다가 MC-1 이 닫히자 깨졌다.
MINI_SPEC = (
    "## 1. 요구사항\n\n"
    "- **FR-1** 샘플 요구사항\n"
    "  - Priority: **Must-have** / Phase 1\n"
    "  - Acceptance Criteria:\n"
    "    - **AC1** 샘플 수용기준\n\n"
    "## 9. 보안\n\n"
    "| ID | 항목 | 우선순위 | Phase | 요구사항 |\n"
    "|---|---|---|---|---|\n"
    "| **SC-1** | 샘플 | Should-have | 2 | 설명 |\n"
)


def c_no_blocking_unperformed(d: Path):
    t = d / "t12"
    t.mkdir()
    write(t, "test_auto.py", (
        "import pytest\n\n"
        "@pytest.mark.req('FR-1-AC1')\n"
        "def test_real():\n"
        "    assert True\n"
    ))
    spec = write(d, "mini-spec.md", MINI_SPEC)
    m = write(d, "no-blocking.yaml", (
        "version: 1\n"
        "checks:\n"
        "  - id: MC-Z3\n"
        "    requirement: FR-1\n"
        "    criterion_id: FR-1-AC1\n"
        "    why_manual: x\n"
        "    blocking_dod: false\n"
        "    status: '미수행'\n"
    ))
    rc, out = run(t, manual=m, spec=spec)
    ok = rc == 0 and "차단 미수행(판정불가) 0건" in out
    return (0 if ok else 9), out
case("차단 미수행이 하나도 없으면 rc=0 (오탐 없음을 고정)", c_no_blocking_unperformed, "")


def main() -> int:
    fails = 0
    with workspace() as d:
        (d / "empty").mkdir()

        rc, out = baseline(d)
        if rc == 2:
            print("기준 상태가 이미 결함입니다 — 음성 테스트를 신뢰할 수 없습니다")
            print(out)
            return 2

        for name, fn, expect in CASES:
            rc, out = fn(d)
            # 양성 케이스는 expect 가 비어 있고, fn 이 판정해 0을 돌려준다
            hit = (expect in out) if expect else (rc == 0)
            mark = "OK  " if hit else "MISS"
            if not hit:
                fails += 1
            print(f"  {mark} {name}")
            if not hit:
                print(f"       기대 {expect!r} / 종료 {rc}")
                for ln in out.splitlines()[:12]:
                    print(f"         {ln}")

    print()
    print(f"음성·양성 테스트 {len(CASES)}종 — 통과 {len(CASES)-fails} / 실패 {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
