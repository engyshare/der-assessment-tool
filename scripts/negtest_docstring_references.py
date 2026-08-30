#!/usr/bin/env python3
"""check_docstring_references.py 음성 테스트 — **문면 참조 검사가 실제로 잡는가.**

## 이 파일이 생긴 이유

`check_docstring_references.py` 는 CI 가 부르는 검사인데 **짝이 없었다** — 같은
부류의 게이트 스크립트 열 개가 전부 `negtest_*` 짝이 있는 가운데 이것만 없었다.
감지 능력이 증명된 적 없으므로 검사가 고장나도 아무도 모른다.

## 실물 변이 방식을 쓰는 이유

`check_docstring_references.py` 는 **CLI 인자를 받지 않는다** — `ROOT` 는
저장소 루트로 고정돼 있고 `SCAN_ROOTS` 도 실물 트리를 훑는다. 임시 디렉터리를
겨냥할 길이 없으므로 **실물 파일을 잠깐 변이시키고 되돌리는** 방식을 쓴다.
`.orch/mutate.py` 의 원칙(임시 백업 → 변이 → 실행 → `finally` 원복)을 따른다.

## 붙드는 것 여덟

| 갈래 | 무엇을 잡는가 |
|---|---|
| ① 양성 기준선 | 지금 저장소 그대로 `rc=0` |
| ② 없는 이름 위반 | 백틱 안에 없는 이름을 심으면 `rc=1` |
| ③ 재수출 거짓 양성 방지 | 재수출된 이름은 참으로 인정 → `rc=0` |
| ④ KNOWN_STALE 부채목록 | 목록에서 빼면 그 문면이 다시 위반으로 잡힘 |
| ⑤ 대상 0개 설정 오류 | `SCAN_ROOTS` 를 비우면 `rc=2` |
| ⑥ 클래스의 **없는** 메서드 | 클래스 수신자 점 표기를 판정하는가 → `rc=1` |
| ⑦ 클래스의 **있는** 메서드 | 직접 선언된 메서드는 거짓 양성이 아닌가 → `rc=0` |
| ⑧ **물려받은** 메서드 | 부모가 선언한 것을 자식 이름으로 가리켜도 참 → `rc=0` |

⑥⑦⑧ 은 R44 · WP-10 이 붙였다. 그 전까지 `_DOTTED` 의 왼쪽이 **소문자로
시작하는 것만** 잡아 클래스를 수신자로 쓴 문면 41건이 통째로 빠져 있었다.
⑧ 이 없으면 상속 해석을 지워도 이 스위트가 초록불이다 — 그러면 물려받은
메서드를 가리키는 정당한 문면이 전부 거짓 위반이 되는 변경을 못 붙든다.

사용:
    python scripts/negtest_docstring_references.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKER = REPO / "scripts" / "check_docstring_references.py"

FAILURES: list[str] = []

#: 이 스위트가 실제로 변이시킨 파일. 원복 확인은 **이 목록만** 본다.
#: 저장소 전체 `git diff` 를 보면 스위트와 무관한 미커밋 변경(이 파일을
#: 처음 붙이는 커밋의 워크플로 수정 등)이 원복 실패로 둔갑한다 — 실제로
#: 그렇게 한 번 빨간불이 났다.
MUTATED: list[Path] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}")
        for line in detail.splitlines()[:14]:
            print(f"       {line}")
        FAILURES.append(name)


def plant(text: str, old: str, new: str) -> str:
    """위반을 **실제로 심었는지 확인하고** 심는다.

    `str.replace` 는 대상이 없으면 아무 일도 하지 않고 원본을 돌려준다.
    그러면 **심지 않은 파일을 검사에 넣고 「위반을 못 잡았다」는 결과**를
    받는다 — `negtest_task_mapping.py:64-77` 의 판단을 그대로 가져왔다.
    """
    out = text.replace(old, new, 1)
    if out == text:
        print(f"  FAIL 심기 실패 — 파일에서 {old!r} 를 찾지 못했다")
        print("       **검사가 고장난 것이 아니라 심기가 고장난 것이다.**")
        FAILURES.append(f"심기 실패: {old!r}")
        return text
    return out


def run_checker() -> tuple[int, str]:
    """검사기를 돌리고 `(종료코드, 출력)` 을 돌려준다.

    **파이프를 걸지 않는다.** `subprocess.run(..., capture_output=True)` 로
    직접 불러 `rc` 를 읽는다.
    """
    r = subprocess.run(
        [sys.executable, str(CHECKER)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO),
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def restore_file(path: Path, backup: Path) -> None:
    """원복. `finally` 에서만 부른다."""
    if backup.exists():
        shutil.copy2(backup, path)
        backup.unlink()


def main() -> int:
    print("check_docstring_references.py 음성 테스트 — 문면 참조 검사가 실제로 잡는가")

    # ── ① 양성 기준선 ─────────────────────────────────────────────
    print("\n① 양성 기준선 (지금 저장소 그대로)")
    rc, out = run_checker()
    check("저장소 실물에 위반이 없으므로 rc=0 이다", rc == 0, f"rc={rc}\n{out}")
    check("「어긋난 문면 없음」을 출력한다", "어긋난 문면 없음" in out, out)

    # ── ② 없는 이름을 가리키는 위반을 심으면 잡는가 ─────────────────
    print("\n② 없는 이름 위반 — 실재하지 않는 이름을 심어 잡히는가")
    # core/casegrid/e2e_runner.py 에 주석으로 없는 이름을 심는다.
    # 검사기의 _SYMBOL 정규식이 `^([A-Za-z_][\w.]*)` 이므로 ASCII 이름을 쓴다.
    target = REPO / "core" / "casegrid" / "e2e_runner.py"
    inject_marker = "from core.casegrid.operating_lines import DAYS_PER_YEAR, net_operating_flows"
    inject_new = "# `operating_lines::nonexistent_negcheck_fn` 을 쓴다\n" + inject_marker
    backup = target.with_suffix(target.suffix + ".mutbak")
    try:
        src = target.read_text(encoding="utf-8")
        mutated = plant(src, inject_marker, inject_new)
        if mutated != src:
            shutil.copy2(target, backup)
            target.write_text(mutated, encoding="utf-8")
            MUTATED.append(target)
            rc, out = run_checker()
            check("없는 이름을 심으면 rc=1 이다", rc == 1, f"rc={rc}\n{out}")
            check("위반 출력에 「nonexistent_negcheck_fn」이 나온다",
                  "nonexistent_negcheck_fn" in out, out)
    finally:
        restore_file(target, backup)

    # ── ③ 재수출은 거짓 양성을 안 내는가 ─────────────────────────
    print("\n③ 재수출 거짓 양성 방지 — 재수출된 이름을 심어도 rc=0 인가")
    # e2e_runner 는 operating_lines 의 net_operating_flows 를 재수출한다.
    # e2e_runner 의 독스트링/주석에 `e2e_runner.net_operating_flows()` 를 심는다.
    target = REPO / "core" / "casegrid" / "e2e_runner.py"
    inject_marker2 = "from core.casegrid.operating_lines import DAYS_PER_YEAR, net_operating_flows"
    inject_new2 = "# `e2e_runner.net_operating_flows()` 를 부른다\n" + inject_marker2
    backup2 = target.with_suffix(target.suffix + ".mutbak")
    try:
        src = target.read_text(encoding="utf-8")
        mutated = plant(src, inject_marker2, inject_new2)
        if mutated != src:
            shutil.copy2(target, backup2)
            target.write_text(mutated, encoding="utf-8")
            MUTATED.append(target)
            rc, out = run_checker()
            check("재수출된 이름은 거짓 양성이 아니다 (rc=0)", rc == 0,
                  f"rc={rc}\n{out}")
    finally:
        restore_file(target, backup2)

    # ── ④ KNOWN_STALE 부채목록 규약 ─────────────────────────────
    print("\n④ KNOWN_STALE 부채목록 — 항목을 지우면 그 문면이 다시 위반으로 잡힘")
    checker_path = CHECKER
    # KNOWN_STALE 에서 첫 항목을 지운다 → 그 문면이 다시 위반으로 잡혀야 한다.
    # KNOWN_STALE 의 첫 키: ("tests/valuestream/test_settlement.py",
    #                         "core/model/settlement.py::SettlementEngine")
    old_stale = '''KNOWN_STALE: dict[tuple[str, str], str] = {
    (
        "tests/valuestream/test_settlement.py",
        "core/model/settlement.py::SettlementEngine",
    ): "R31 이 없앤 사본을 적는 경위 문장. 「종전 … 은」으로 시작한다.",
    (
        "tests/contract/test_payer_structure_contract.py",
        "core/model/settlement.py",
    ): "위와 같음 — R31 이 없앤 사본의 자리를 적는다.",
}'''
    new_stale = '''KNOWN_STALE: dict[tuple[str, str], str] = {
    (
        "tests/contract/test_payer_structure_contract.py",
        "core/model/settlement.py",
    ): "위와 같음 — R31 이 없앤 사본의 자리를 적는다.",
}'''
    backup_stale = checker_path.with_suffix(checker_path.suffix + ".mutbak")
    try:
        src = checker_path.read_text(encoding="utf-8")
        mutated = plant(src, old_stale, new_stale)
        if mutated != src:
            shutil.copy2(checker_path, backup_stale)
            checker_path.write_text(mutated, encoding="utf-8")
            MUTATED.append(checker_path)
            rc, out = run_checker()
            check("KNOWN_STALE 항목을 지우면 위반이 나온다 (rc=1)", rc == 1,
                  f"rc={rc}\n{out}")
            check("출력에 SettlementEngine 문면이 나온다",
                  "SettlementEngine" in out, out)
    finally:
        restore_file(checker_path, backup_stale)

    # ── ⑥ 클래스의 없는 메서드를 가리키면 잡는가 ─────────────────
    print("\n⑥ 클래스 수신자 — 없는 메서드를 심어 잡히는가")
    # `ESS` 는 core/der/ess.py 에 하나뿐이고 부모 사슬은 ESS→DER→ABC 로
    # 닫혀 있다(검사기의 _INERT_BASES). 그러므로 이 클래스는 판정 대상이다.
    target = REPO / "core" / "casegrid" / "e2e_runner.py"
    marker6 = "from core.casegrid.operating_lines import DAYS_PER_YEAR, net_operating_flows"
    inject_new6 = "# `ESS.nonexistent_negcheck_method()` 을 부른다\n" + marker6
    backup6 = target.with_suffix(target.suffix + ".mutbak")
    try:
        src = target.read_text(encoding="utf-8")
        mutated = plant(src, marker6, inject_new6)
        if mutated != src:
            shutil.copy2(target, backup6)
            target.write_text(mutated, encoding="utf-8")
            MUTATED.append(target)
            rc, out = run_checker()
            check("클래스의 없는 메서드를 심으면 rc=1 이다", rc == 1, f"rc={rc}\n{out}")
            check("위반 출력에 「nonexistent_negcheck_method」가 나온다",
                  "nonexistent_negcheck_method" in out, out)
    finally:
        restore_file(target, backup6)

    # ── ⑦ 클래스의 있는 메서드는 거짓 양성이 아닌가 ────────────────
    print("\n⑦ 클래스 수신자 — 직접 선언된 메서드는 거짓 양성이 아닌가")
    # salvage_value 는 core/der/ess.py 의 ESS 가 직접 선언한다.
    marker7 = "from core.casegrid.operating_lines import DAYS_PER_YEAR, net_operating_flows"
    inject_new7 = "# `ESS.salvage_value()` 을 부른다\n" + marker7
    backup7 = target.with_suffix(target.suffix + ".mutbak")
    try:
        src = target.read_text(encoding="utf-8")
        mutated = plant(src, marker7, inject_new7)
        if mutated != src:
            shutil.copy2(target, backup7)
            target.write_text(mutated, encoding="utf-8")
            MUTATED.append(target)
            rc, out = run_checker()
            check("직접 선언된 메서드는 거짓 양성이 아니다 (rc=0)", rc == 0,
                  f"rc={rc}\n{out}")
    finally:
        restore_file(target, backup7)

    # ── ⑧ 물려받은 메서드를 자식 이름으로 가리켜도 참인가 ──────────
    print("\n⑧ 클래스 수신자 — 부모가 선언한 메서드를 자식 이름으로 가리켜도 참인가")
    # TestESSContract(tests/der/test_ess.py)는 DERContractTests
    # (tests/contract/test_der_contract.py)를 상속하며 아래 이름을 스스로
    # 선언하지 않는다. 상속 해석이 없으면 이 문면은 거짓 위반이 된다.
    marker8 = "from core.casegrid.operating_lines import DAYS_PER_YEAR, net_operating_flows"
    inject_new8 = (
        "# `TestESSContract.test_dt_is_positive_seconds()` 을 물려받는다\n" + marker8
    )
    backup8 = target.with_suffix(target.suffix + ".mutbak")
    try:
        src = target.read_text(encoding="utf-8")
        mutated = plant(src, marker8, inject_new8)
        if mutated != src:
            shutil.copy2(target, backup8)
            target.write_text(mutated, encoding="utf-8")
            MUTATED.append(target)
            rc, out = run_checker()
            check("물려받은 메서드는 거짓 양성이 아니다 (rc=0)", rc == 0,
                  f"rc={rc}\n{out}")
    finally:
        restore_file(target, backup8)

    # ── ⑨ 저장소 밖 접두사의 경로는 위반이 아닌가 ───────────────────────
    print("\n⑨ 저장소 밖 경로 — OUT_OF_REPO_PREFIXES 로 시작하는 경로는 위반이 아닌가")
    marker9 = "from core.casegrid.operating_lines import DAYS_PER_YEAR, net_operating_flows"
    inject_new9 = "# `.orch/mutate.py` 의 원칙을 따른다\n" + marker9
    backup9 = target.with_suffix(target.suffix + ".mutbak")
    try:
        src = target.read_text(encoding="utf-8")
        mutated = plant(src, marker9, inject_new9)
        if mutated != src:
            shutil.copy2(target, backup9)
            target.write_text(mutated, encoding="utf-8")
            MUTATED.append(target)
            rc, out = run_checker()
            check("저장소 밖 접두사의 경로는 위반이 아니다 (rc=0)", rc == 0, f"rc={rc}\n{out}")
            check("요약 줄에 저장소 밖 참조 건수가 뜬다", "저장소 밖 참조" in out, out)
    finally:
        restore_file(target, backup9)

    # ── ⑩ 접두사가 아닌 실재하지 않는 경로는 여전히 잡히는가 ────────────────
    print("\n⑩ 없는 경로 — 접두사가 아닌 실재하지 않는 경로는 여전히 잡히는가")
    marker10 = "from core.casegrid.operating_lines import DAYS_PER_YEAR, net_operating_flows"
    inject_new10 = "# `scripts/nonexistent_negcheck.py` 파일\n" + marker10
    backup10 = target.with_suffix(target.suffix + ".mutbak")
    try:
        src = target.read_text(encoding="utf-8")
        mutated = plant(src, marker10, inject_new10)
        if mutated != src:
            shutil.copy2(target, backup10)
            target.write_text(mutated, encoding="utf-8")
            MUTATED.append(target)
            rc, out = run_checker()
            check("접두사가 아닌 실재하지 않는 경로는 잡힌다 (rc=1)", rc == 1, f"rc={rc}\n{out}")
            check("출력에 nonexistent_negcheck.py 가 나온다", "nonexistent_negcheck.py" in out, out)
    finally:
        restore_file(target, backup10)

    # ── ⑤ 대상 파일 0개 — rc=2 ─────────────────────────────────
    print("\n⑤ 대상 파일 0개 설정 오류 — rc=2 인가")
    # SCAN_ROOTS 를 존재하지 않는 이름으로 바꾼다.
    old_roots = 'SCAN_ROOTS: tuple[str, ...] = ("core", "app", "infra", "web", "scripts", "tests")'
    new_roots = 'SCAN_ROOTS: tuple[str, ...] = ("없는디렉터리_negcheck",)'
    backup_roots = checker_path.with_suffix(checker_path.suffix + ".mutbak")
    try:
        src = checker_path.read_text(encoding="utf-8")
        mutated = plant(src, old_roots, new_roots)
        if mutated != src:
            shutil.copy2(checker_path, backup_roots)
            checker_path.write_text(mutated, encoding="utf-8")
            MUTATED.append(checker_path)
            rc, out = run_checker()
            check("대상 파일 0개이면 rc=2 다 (검사 미수행)", rc == 2,
                  f"rc={rc}\n{out}")
    finally:
        restore_file(checker_path, backup_roots)

    # ── 원복 확인 ──────────────────────────────────────────────
    print("\n원복 확인")
    touched = sorted({q.relative_to(REPO).as_posix() for q in MUTATED})
    check("열 갈래가 건드린 파일은 둘뿐이다", len(touched) == 2, str(touched))
    r = subprocess.run(
        ["git", "diff", "--stat", "--", *touched],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO),
    )
    # **변이시킨 파일만** 본다 (`MUTATED` 머리말 참조).
    # .mutbak 는 어디에도 남아 있지 않아야 한다 — 이쪽은 저장소 전체를 본다.
    mutbak_files = list(REPO.rglob("*.mutbak"))
    check(f"변이시킨 파일 {len(touched)}개의 git diff 가 비어 있다",
          r.stdout.strip() == "", r.stdout)
    check(".mutbak 파일이 남아 있지 않다", len(mutbak_files) == 0,
          str(mutbak_files))

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(
        "전건 통과 — 문면 참조 검사 10갈래가 실제로 잡고, "
        "재수출·상속은 거짓으로 세지 않는다"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
