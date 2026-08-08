"""`check_file_size.py` 의 감지 능력 확인 — 음성 6 + 양성 2종.

**왜 필요한가.** 실제 저장소에서 이 검사는 「코드 스프롤 0건」을 보고한다. 그
보고가 *코드 스프롤이 없다* 는 뜻인지 *검사가 코드 스프롤을 못 잡는다* 는 뜻인지
결과만 보고는 구분할 수 없다 (§13.0.1 ④ — 통과만 보고 끝내면 아무것도 검사하지
않는 장치일 수 있다).

특히 위험한 것은 **독스트링 계산이 과대해지는 방향**이다. 독스트링을 실제보다
많이 세면 코드 줄 수가 작아지고, 진짜 코드 스프롤이 「설명 밀도」로 분류되어
경고가 무해해 보인다. 음성 3·4가 그 방향을 겨눈다.

    실행: python scripts/negtest_file_size.py
    종료 코드 0 = 전건 기대대로 · 1 = 감지 실패
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_file_size import LIMIT, main, measure_file


def write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def code_file(n: int) -> str:
    """코드 `n` 줄 — 독스트링도 주석도 공백도 없다."""
    return "\n".join(f"x{i} = {i}" for i in range(n)) + "\n"


def prose_file(code: int, doc: int) -> str:
    """코드 `code` 줄 + 모듈 독스트링 `doc` 줄."""
    lines = ['"""'] + [f"설명 {i}" for i in range(doc - 2)] + ['"""']
    lines += [f"y{i} = {i}" for i in range(code)]
    return "\n".join(lines) + "\n"


def run(root: Path, *args: str) -> int:
    return main(["--root", str(root), *args])


CASES: list[tuple[str, str]] = []
FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    CASES.append((label, "통과" if ok else "**실패**"))
    if not ok:
        FAILED.append(f"{label} — {detail}")


def main_negtest() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # ── 음성 1: 코드만 501줄 → 코드 스프롤로 분류되고 --code-strict 가 잡는다
        sprawl_root = root / "case1"
        write(sprawl_root, "core/big.py", code_file(LIMIT + 1))
        m = measure_file(sprawl_root / "core/big.py")
        check("음성1 코드 501줄 → 코드 스프롤",
              m.over_total and m.over_code and m.kind == "코드 스프롤",
              f"총 {m.total} 코드 {m.code} 분류 {m.kind}")
        check("음성1 --code-strict 가 차단", run(sprawl_root, "--code-strict") == 1)
        check("음성1 --strict 도 차단", run(sprawl_root, "--strict") == 1)

        # ── 음성 2: 총 501줄이지만 코드는 이내 → 설명 밀도. --code-strict 는 통과
        prose_root = root / "case2"
        write(prose_root, "core/prose.py", prose_file(code=200, doc=320))
        m = measure_file(prose_root / "core/prose.py")
        check("음성2 총 초과·코드 이내 → 설명 밀도",
              m.over_total and not m.over_code and m.kind == "설명 밀도",
              f"총 {m.total} 코드 {m.code} 독스 {m.doc}")
        check("음성2 --strict 는 차단", run(prose_root, "--strict") == 1)
        check("음성2 --code-strict 는 통과 (성질이 다르다)",
              run(prose_root, "--code-strict") == 0)

        # ── 음성 3: 코드 501줄 + 큰 독스트링 → **여전히** 코드 스프롤이다.
        #    독스트링을 과대 계산하면 여기서 「설명 밀도」로 새고, 진짜 스프롤이
        #    무해해 보인다. 이 검사가 그 방향을 막는다.
        mixed_root = root / "case3"
        write(mixed_root, "core/mixed.py", prose_file(code=LIMIT + 1, doc=300))
        m = measure_file(mixed_root / "core/mixed.py")
        check("음성3 코드 501 + 독스 300 → 코드 스프롤 유지",
              m.over_code and m.kind == "코드 스프롤",
              f"코드 {m.code} 독스 {m.doc} 분류 {m.kind}")

        # ── 음성 4: 코드 안의 문자열 리터럴을 독스트링으로 세지 않는다.
        #    정규식으로 세면 삼중 인용 리터럴이 전부 독스트링이 되어 코드 줄
        #    수가 조용히 줄어든다.
        lit_root = root / "case4"
        write(lit_root, "core/lit.py",
              'MSG = """\n' + "\n".join(f"줄 {i}" for i in range(50)) + '\n"""\n'
              + code_file(10))
        m = measure_file(lit_root / "core/lit.py")
        check("음성4 문자열 리터럴은 독스트링이 아니다", m.doc == 0, f"독스 {m.doc}")

        # ── 음성 5: 대상 디렉터리가 비면 종료 코드 2. 검사를 수행하지 못한 것을
        #    통과로 읽지 않는다.
        empty_root = root / "case5"
        empty_root.mkdir()
        check("음성5 대상 0개 → 종료 코드 2", run(empty_root) == 2)

        # ── 음성 6: 테스트 디렉터리는 대상이 아니다. 넣으면 NFR-106(자원별
        #    케이스 의무)과 부딪친다.
        test_root = root / "case6"
        write(test_root, "core/ok.py", code_file(10))
        write(test_root, "tests/huge_test.py", code_file(LIMIT + 200))
        check("음성6 tests/ 는 대상 밖", run(test_root, "--strict") == 0)

        # ── 양성 1·2: 상한 이내는 통과한다. 음성만 보면 「전부 위반으로
        #    보고하는」 장치도 만점을 받는다.
        ok_root = root / "case7"
        write(ok_root, "core/small.py", code_file(LIMIT - 1))
        write(ok_root, "scripts/tool.py", prose_file(code=100, doc=100))
        check("양성1 상한 이내 → 종료 코드 0", run(ok_root, "--strict") == 0)
        m = measure_file(ok_root / "core/small.py")
        check("양성2 경계값 499줄은 초과가 아니다",
              not m.over_total and m.total == LIMIT - 1, f"총 {m.total}")

    print("check_file_size 감지 능력 — 음성 6 + 양성 2종")
    print("─" * 62)
    for label, verdict in CASES:
        print(f"  {verdict:8s} {label}")
    print("─" * 62)
    if FAILED:
        print(f"감지 실패 {len(FAILED)}건:")
        for line in FAILED:
            print(f"  · {line}")
        return 1
    print("전건 기대대로 — 이 검사는 무언가를 검사한다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_negtest())
