#!/usr/bin/env python3
"""check_doc_line_citations.py 음성 테스트 — **줄번호 인용 검사가 실제로 잡는가.**

## 이 파일이 생긴 이유

새 검사가 실물에서 초록불이 되는 순간, 그 초록불이 *「지킨다」* 인지
*「못 잡는다」* 인지는 결과만으로 구분되지 않는다. 이 저장소의 게이트
스크립트는 전부 `negtest_*` 짝을 갖는다 — 감지 능력이 증명되지 않은 검사는
고장나도 아무도 모른다.

## 실물 변이 방식을 쓰는 이유

검사기는 **CLI 인자를 받지 않는다** — 대상 문서 목록도 저장소 루트도 상수로
고정돼 있다. 임시 디렉터리를 겨냥할 길이 없으므로 **실물 파일을 잠깐
변이시키고 되돌리는** 방식을 쓴다. `.orch/mutate.py` 의 원칙을 따른다:
임시 백업 → 변이 → 실행 → `finally` 원복. **원복에 실패하면 정본 문서에
변이가 남으므로 요란하게 실패한다** — R34 가 그것을 실물로 밟았다.

## 붙드는 것 여덟

| 갈래 | 무엇을 잡는가 |
|---|---|
| ① 양성 기준선 | 지금 저장소 그대로 rc=0 |
| ② 저장소 안 경로 | 본문에 심으면 rc=1 |
| ③ 저장소 밖 경로 | 참조 구현 스냅숏은 거짓 양성이 아니다 → rc=0 |
| ④ 머리말 면제 | 같은 인용을 머리말에 심으면 rc=0 (면제 건수가 는다) |
| ⑤ 바탕 이름 해석 | 디렉터리 없이 파일명만 적어도 유일하면 rc=1 |
| ⑥ 절 번호·포트 | 확장자 없는 것은 애초에 경로가 아니다 → rc=0 |
| ⑦ 대상 문서 없음 | 대상을 없는 이름으로 바꾸면 rc=2 |
| ⑧ 인용 0건 | 인용이 하나도 없는 문서를 겨냥하면 rc=2 (검사 미수행) |

②③ 은 짝이다 — ② 만 있으면 「전부 잡는다」로도 통과하고, ③ 만 있으면
「하나도 안 잡는다」로도 통과한다. ④⑤ 도 같은 형태의 짝이다.

사용:
    python scripts/negtest_doc_line_citations.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKER = REPO / "scripts" / "check_doc_line_citations.py"

SPEC = REPO / "rslt" / "spec-분산특구-경제성평가.md"
TASK = REPO / "rslt" / "task-분산특구-경제성평가.md"

FAILURES: list[str] = []

#: 이 스위트가 실제로 변이시킨 파일. 원복 확인은 **이 목록만** 본다 —
#: 저장소 전체 diff 를 보면 스위트와 무관한 미커밋 변경이 원복 실패로 둔갑한다.
MUTATED: list[Path] = []

#: 시작 시점의 바이트. 원복 확인은 `git diff` 가 아니라 이것과 대조한다 —
#: 사유는 「원복 확인」 절의 주석에 있다.
ORIGINALS: dict[str, bytes] = {}

#: 변이 문면. 코드가 아니라 **자료**로 둔다 — 주석이나 독스트링에 백틱으로
#: 적으면 `check_docstring_references.py` 가 그 문면을 판정 대상으로 집는다.
INSIDE_CITE = "core/der/heatpump.py:446"
BASENAME_CITE = "heatpump.py:446"
OUTSIDE_CITE = "storagevet/storagevet/Params.py:928"
NON_PATH_CITE = "§16.5.2 와 localhost:8000 과 v0.21"


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
    그러면 심지 않은 파일을 검사에 넣고 「위반을 못 잡았다」는 결과를 받는다.
    """
    out = text.replace(old, new, 1)
    if out == text:
        print(f"  FAIL 심기 실패 — 파일에서 {old!r} 를 찾지 못했다")
        print("       **검사가 고장난 것이 아니라 심기가 고장난 것이다.**")
        FAILURES.append(f"심기 실패: {old!r}")
        return text
    return out


def run_checker() -> tuple[int, str]:
    """검사기를 돌리고 `(종료코드, 출력)` 을 돌려준다. **파이프를 걸지 않는다.**"""
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
    """원복. `finally` 에서만 부른다. 실패하면 요란하게 남긴다."""
    if not backup.exists():
        return
    try:
        shutil.copy2(backup, path)
        backup.unlink()
    except OSError as exc:  # pragma: no cover - 원복 실패는 실물 사고다
        print(f"  FAIL 원복 실패 — {path} 를 {backup} 로 되돌리지 못했다: {exc}")
        print("       **정본 문서에 변이가 남았다. 손으로 되돌려라.**")
        FAILURES.append(f"원복 실패: {path}")


def run_with_body_plant(label: str, target: Path, injected: str) -> tuple[int, str]:
    """대상 문서 **본문 끝**에 한 줄을 붙이고 검사기를 돌린다.

    본문 끝에 붙이므로 머리말 면제 규칙과 섞이지 않는다. 붙이기는 실패할 수
    없으므로 `plant` 를 쓰지 않는다.
    """
    backup = target.with_suffix(target.suffix + ".mutbak")
    try:
        shutil.copy2(target, backup)
        MUTATED.append(target)
        src = target.read_text(encoding="utf-8")
        target.write_text(src + f"\n<!-- negtest {label} {injected} -->\n",
                          encoding="utf-8")
        return run_checker()
    finally:
        restore_file(target, backup)


def main() -> int:
    print("check_doc_line_citations.py 음성 테스트 — 줄번호 인용 검사가 실제로 잡는가")

    for path in (SPEC, TASK, CHECKER):
        if not path.is_file():
            print(f"ERROR: 대상이 없다 — {path}", file=sys.stderr)
            return 2
        ORIGINALS[path.relative_to(REPO).as_posix()] = path.read_bytes()

    # ── ① 양성 기준선 ─────────────────────────────────────────────
    print("\n① 양성 기준선 (지금 저장소 그대로)")
    rc, out = run_checker()
    check("실물에 낡을 좌표가 없으므로 rc=0 이다", rc == 0, f"rc={rc}\n{out}")
    check("「통과」를 출력한다", "통과 —" in out, out)

    # ── ② 저장소 안 경로를 본문에 심으면 잡는가 ────────────────────
    print("\n② 저장소 안 경로 — 본문에 심어 잡히는가")
    rc, out = run_with_body_plant("inside", TASK, INSIDE_CITE)
    check("저장소 안 경로를 심으면 rc=1 이다", rc == 1, f"rc={rc}\n{out}")
    check("위반 출력에 그 인용 문면이 나온다", INSIDE_CITE in out, out)

    # ── ③ 저장소 밖 경로는 거짓 양성이 아닌가 ──────────────────────
    print("\n③ 저장소 밖 경로 — 참조 구현 스냅숏은 거짓 양성이 아닌가")
    rc, out = run_with_body_plant("outside", TASK, OUTSIDE_CITE)
    check("저장소 밖 경로는 위반이 아니다 (rc=0)", rc == 0, f"rc={rc}\n{out}")
    check("요약 줄의 「밖」 건수가 15건으로 는다", "밖 15건" in out, out)

    # ── ④ 머리말 면제 — 같은 인용을 머리말에 심으면 ────────────────
    print("\n④ 머리말 면제 — 판본 이력 줄의 같은 인용은 통과하는가")
    front_anchor = 'source_spec: "rslt/spec-분산특구-경제성평가.md v0.7"'
    front_new = f'source_spec: "rslt/spec-분산특구-경제성평가.md v0.7 {INSIDE_CITE}"'
    backup = TASK.with_suffix(TASK.suffix + ".mutbak")
    try:
        src = TASK.read_text(encoding="utf-8")
        mutated = plant(src, front_anchor, front_new)
        if mutated != src:
            shutil.copy2(TASK, backup)
            TASK.write_text(mutated, encoding="utf-8")
            MUTATED.append(TASK)
            rc, out = run_checker()
            check("머리말의 같은 인용은 위반이 아니다 (rc=0)", rc == 0, f"rc={rc}\n{out}")
            check("머리말 면제 건수가 2건으로 는다", "머리말 면제 2건" in out, out)
    finally:
        restore_file(TASK, backup)

    # ── ⑤ 바탕 이름만 적어도 유일하면 잡는가 ───────────────────────
    print("\n⑤ 바탕 이름 해석 — 디렉터리 없이 파일명만 적어도 잡히는가")
    rc, out = run_with_body_plant("basename", SPEC, BASENAME_CITE)
    check("유일한 바탕 이름은 잡힌다 (rc=1)", rc == 1, f"rc={rc}\n{out}")
    check("해석된 실제 경로를 출력에 적는다",
          "core/der/heatpump.py 는 저장소 안 파일이다" in out, out)

    # ── ⑥ 절 번호·포트 번호는 오탐이 아닌가 ────────────────────────
    print("\n⑥ 절 번호·포트 번호 — 확장자 없는 것은 경로가 아닌가")
    rc, out = run_with_body_plant("nonpath", SPEC, NON_PATH_CITE)
    check("절 번호·포트 번호는 잡지 않는다 (rc=0)", rc == 0, f"rc={rc}\n{out}")
    check("인용 총수가 15건 그대로다", "인용 15건" in out, out)

    # ── ⑦ 대상 문서가 없으면 rc=2 인가 ─────────────────────────────
    print("\n⑦ 대상 문서 없음 설정 오류 — rc=2 인가")
    old_docs = (
        'DOCS: tuple[str, ...] = (\n'
        '    "rslt/spec-분산특구-경제성평가.md",\n'
        '    "rslt/task-분산특구-경제성평가.md",\n'
        ')'
    )
    new_docs = 'DOCS: tuple[str, ...] = (\n    "rslt/없는문서_negcheck.md",\n)'
    backup_c = CHECKER.with_suffix(CHECKER.suffix + ".mutbak")
    try:
        src = CHECKER.read_text(encoding="utf-8")
        mutated = plant(src, old_docs, new_docs)
        if mutated != src:
            shutil.copy2(CHECKER, backup_c)
            CHECKER.write_text(mutated, encoding="utf-8")
            MUTATED.append(CHECKER)
            rc, out = run_checker()
            check("대상 문서가 없으면 rc=2 다 (검사 미수행)", rc == 2, f"rc={rc}\n{out}")
    finally:
        restore_file(CHECKER, backup_c)

    # ── ⑧ 인용이 0건이면 rc=2 인가 ─────────────────────────────────
    print("\n⑧ 인용 0건 설정 오류 — rc=2 인가")
    new_docs2 = 'DOCS: tuple[str, ...] = (\n    "LICENSE",\n)'
    backup_c2 = CHECKER.with_suffix(CHECKER.suffix + ".mutbak")
    try:
        src = CHECKER.read_text(encoding="utf-8")
        mutated = plant(src, old_docs, new_docs2)
        if mutated != src:
            shutil.copy2(CHECKER, backup_c2)
            CHECKER.write_text(mutated, encoding="utf-8")
            MUTATED.append(CHECKER)
            rc, out = run_checker()
            check("뽑힌 인용이 0건이면 rc=2 다", rc == 2, f"rc={rc}\n{out}")
    finally:
        restore_file(CHECKER, backup_c2)

    # ── 원복 확인 ──────────────────────────────────────────────
    #
    # **`git diff` 로 재지 않는다.** 이 스위트는 정본 문서를 변이시키는데, 그
    # 문서가 같은 작업에서 이미 고쳐져 미커밋 상태일 수 있다 — 그때 `git diff`
    # 는 비어 있지 않고, 원복은 멀쩡한데 실패로 보고된다. 시작 시점의 바이트를
    # 들고 있다가 그것과 대조하는 것이 **원복이 물어야 할 것**이다.
    print("\n원복 확인")
    touched = sorted({q.relative_to(REPO).as_posix() for q in MUTATED})
    check("여덟 갈래가 건드린 파일은 셋뿐이다", len(touched) == 3, str(touched))
    for rel, before in ORIGINALS.items():
        after = (REPO / rel).read_bytes()
        check(f"{rel} 가 시작 시점 바이트와 같다", after == before,
              f"len {len(before)} -> {len(after)}")
    mutbak_files = list(REPO.rglob("*.mutbak"))
    check(".mutbak 파일이 남아 있지 않다", len(mutbak_files) == 0, str(mutbak_files))

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(
        "전건 통과 — 줄번호 인용 검사 여덟 갈래가 실제로 잡고, "
        "저장소 밖 경로와 머리말 이력은 거짓으로 세지 않는다"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
