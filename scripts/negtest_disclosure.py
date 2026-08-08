"""`check_disclosure.py` 음성·양성 테스트 — 작업 2.3 / §13.0.1 ④.

**이 검사는 「유입 0건」으로 통과한다. 그 통과가 무엇을 뜻하는지 스스로는 말하지
못한다** — 저장소가 깨끗하다는 뜻일 수도, 정규식이 아무것도 매치하지 않는다는
뜻일 수도 있다. 비밀 스캔은 특히 그렇다: 규칙이 조용히 무력해져도 **매일 초록불**
이고, 잘못을 알아차리는 시점은 이미 공개된 뒤다.

**양성을 함께 보는 이유가 여기서는 더 크다.** 오탐이 잦은 스캔은 «일단 통과
시키자»는 압력을 만들고, 그 압력은 규칙을 넓히는 방향으로만 작용한다. 넓어진
규칙은 진짜 유출도 통과시킨다. 그래서 「정당한 파일을 잡지 않는가」를 같은 무게로
검사한다.

실행: `python scripts/negtest_disclosure.py`
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_disclosure.py"


def _repo(files: dict[str, str]) -> Path:
    """파일을 심고 **git 에 추적시킨** 임시 저장소.

    추적시키는 것이 요점이다 — 이 검사의 대상은 작업 트리가 아니라 `git
    ls-files` 다. `.gitignore` 로 무시되는 파일은 애초에 커밋되지 않고,
    반대로 **이미 추적 중인 파일에는 무시 규칙이 적용되지 않는다.**
    """
    root = Path(tempfile.mkdtemp(prefix="negtest-disclosure-"))
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    for args in (["init", "-q"], ["config", "user.email", "t@example.com"],
                 ["config", "user.name", "t"], ["add", "-A", "-f"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def _run(root: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    return result.returncode, result.stdout + result.stderr


# (이름, 파일들, 차단되어야 하는가, 출력에 있어야 할 문자열)
CASES: list[tuple[str, dict[str, str], bool, str]] = [
    (
        "음성1 윈도우 로컬 경로",
        # 픽스처 경로도 **실제 폴더 이름을 쓰지 않는다.** 이 파일은 검사
        # 대상에서 면제되어 있어(`SELF_EXEMPT`) 자기 자신에는 걸리지 않지만,
        # 면제는 «검사에 안 걸린다» 는 뜻이지 «공개해도 된다» 는 뜻이 아니다.
        {"notes.md": 'python x.py --vault "D:\\Obsidian\\MyVault"\n'},
        True, "로컬 절대 경로",
    ),
    (
        "음성2 사용자 홈 경로",
        {"conf.py": 'ROOT = "/home/hong/der/data"\n'},
        True, "로컬 절대 경로",
    ),
    (
        "음성3 비공개 시드 파일",
        {"data/private/tariff.yaml": "x: 1\n"},
        True, "비공개 시드 경로",
    ),
    (
        "음성4 견적 엑셀",
        {"docs/견적.xlsx": "binary-ish\n"},
        True, "비공개 시드 경로",
    ),
    (
        "음성5 시드 yaml",
        {"config/assumption_seed.yaml": "capex: 1600000\n"},
        True, "비공개 시드 경로",
    ),
    (
        "음성6 주민등록번호 형태",
        {"fixture.md": "참여자 900101-1234567 확인\n"},
        True, "주민등록번호",
    ),
    (
        "음성7 전화번호",
        {"contact.md": "담당 010-1234-5678\n"},
        True, "전화번호",
    ),
    (
        "음성8 실제 이메일",
        {"README.md": "문의: hong@somewhere.co.kr\n"},
        True, "이메일",
    ),
    (
        "음성9 주석에 있어도 로컬 경로다",
        {"a.py": '# 내 볼트는 C:\\Users\\hong\\vault 에 있다\nX = 1\n'},
        True, "로컬 절대 경로",
    ),
    (
        "양성1 상대 경로는 정상",
        {"a.py": 'ROOT = "docs/assumptions.yaml"\n'},
        False, "",
    ),
    (
        "양성2 자리표시자 경로는 정상",
        {"README.md": '`--vault "<볼트 경로>"` 또는 `/home/<이름>/vault`\n'},
        False, "",
    ),
    (
        "양성3 example.com 예시는 정상",
        {"docs/x.md": "문의: someone@example.com\n"},
        False, "",
    ),
    (
        "양성4 골든 시나리오 구조는 공개다",
        {"fixtures/golden/case1.yaml": "shape: {}\n"},
        False, "",
    ),
    (
        "양성5 CI 빌드 경로는 사람 이름이 아니다",
        {"t.py": 'P = "/build/ci/x/core/der/pv.py"\n'},
        False, "",
    ),
    (
        "양성6 8760 같은 수치는 이 검사의 대상이 아니다",
        {"a.py": "HOURS = 8760\nWON = 1_600_000\n"},
        False, "",
    ),
]


def main() -> int:
    print("check_disclosure 음성·양성 테스트 (작업 2.3)")
    print("─" * 74)

    failures = 0
    for name, files, should_block, expect in CASES:
        root = _repo(files)
        try:
            code, out = _run(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        ok = (code == 1) == should_block and (not expect or expect in out)
        failures += not ok
        print(f"  {'통과' if ok else '**실패**':6s} {name}  (종료 {code})")
        if not ok:
            print(f"         기대: 차단={should_block} / 포함={expect!r}")
            for line in out.splitlines()[:10]:
                print(f"         | {line}")

    # 보고서가 새 유출 경로가 되면 안 된다 — CI 로그는 저장소보다 넓게 읽힌다
    root = _repo({"x.md": "참여자 900101-1234567\n"})
    try:
        _, out = _run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    ok = "900101-1234567" not in out
    failures += not ok
    print(f"  {'통과' if ok else '**실패**':6s} 경계1 찾은 값을 보고서에 그대로 싣지 않는다")

    # git 밖에서는 판정할 수 없다 — 0건을 통과로 읽지 않는다
    plain = Path(tempfile.mkdtemp(prefix="negtest-disclosure-nogit-"))
    (plain / "a.py").write_text("X = 1\n", encoding="utf-8")
    try:
        code, _ = _run(plain)
    finally:
        shutil.rmtree(plain, ignore_errors=True)
    ok = code == 2
    failures += not ok
    mark = "통과" if ok else "**실패**"
    print(f"  {mark:6s} 경계2 git 저장소가 아니면 종료 코드 2  (종료 {code})")

    print("─" * 74)
    total = len(CASES) + 2
    print(f"음성 9 + 양성 6 + 경계 2 — 통과 {total - failures} / 실패 {failures}")
    if failures:
        print("\n**검사가 기대대로 동작하지 않습니다.** 오탐을 없애려고 규칙을")
        print("넓히면 진짜 유출도 함께 통과합니다 — 예시를 고치는 쪽이 답입니다.")
        return 1
    print("전건 기대대로 — 이 검사는 무언가를 검사한다")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
