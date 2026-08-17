#!/usr/bin/env python3
"""확장점 소비 검사의 **감지 능력**을 확인한다 — `check_unread_extension_points`.

「검사가 있다」와 「검사가 붙들고 있다」는 다르다. 이 검사가 하는 일은
*「계약이 내놓은 훅을 배포 코드가 읽는가」* 인데, 판정을 조금만 잘못 짜도
**아무것도 잡지 않으면서 초록불**이 된다.

## 두 방향을 **둘 다** 고정한다

    빨간불이어야 하는 것   새 훅이 늘어도 · 읽히기 시작해도 목록과 어긋난다
    초록불이어야 하는 것   주석에 이름만 적은 것은 「읽는다」가 아니다

둘째가 이 저장소가 6.7·2.6 에서 만난 형태다. 「읽는가」를 **문자열 포함**으로
검사하면 *「`stream.exclusions()` 를 예로 들면」* 이라고 적은 주석이 **소비자로
세어져 게이트가 조용히 초록불**이 된다. 그 실패는 «시끄러운» 오탐보다 나쁘다 —
위반이 통과로 보고되기 때문이다.

    python scripts/negtest_unread_extension_points.py     rc=0 이면 전건 확인

**원복은 자동이다** (`finally`). 실패해도 원본이 돌아온다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = "scripts/check_unread_extension_points.py"

_NEW_HOOK = (
    "class _NegcheckHook:  # NEGCHECK\n"
    "    def negcheck_unread_hook(self) -> int:  # NEGCHECK\n"
    "        return 0\n"
    "\n"
    "\n"
    "class ValueStream"
)

_NEW_READER = (
    "def _negcheck_reader(stream) -> object:  # NEGCHECK\n"
    "    return stream.exclusions()  # NEGCHECK\n"
    "\n"
    "\n"
    "def render_markdown(report: CaseReport) -> str:"
)

_MENTION_ONLY = (
    '"""`stream.exclusions()` · `der.value_streams()` 를 예로 들면 — NEGCHECK\n'
    "\n"
    "`CaseReport` 를 **심의보고서**로 그린다"
)

#: **빨간불이어야 하는 변이** — (이름, 파일, 찾을 문면, 넣을 문면, 왜)
CASES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "아무도 읽지 않는 훅을 계약에 새로 낸다",
        "core/contracts/valuestream.py",
        "class ValueStream",
        _NEW_HOOK,
        "새 훅이 부채 목록에 없으므로 「늘었다」로 잡혀야 한다",
    ),
    (
        "부채 목록에 있는 훅을 배포 코드가 읽기 시작한다",
        "core/report/narrative.py",
        "def render_markdown(report: CaseReport) -> str:",
        _NEW_READER,
        "읽히기 시작했는데 목록에 남아 있으면 래칫이 조용히 느슨해진다",
    ),
)

#: **초록불이어야 하는 것** — 반대 방향의 실패를 막는다 (위 머리말).
GUARDS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "주석·독스트링에 이름만 적은 것은 읽기가 아니다",
        "core/report/narrative.py",
        '"""`CaseReport` 를 **심의보고서**로 그린다',
        _MENTION_ONLY,
        "문자열은 후보가 아니므로 판정이 달라지지 않아야 한다",
    ),
)


def _run() -> int:
    return subprocess.run(
        [sys.executable, CHECKER], cwd=ROOT, capture_output=True
    ).returncode


def _mutate(label: str, target: str, old: str, new: str) -> int | None:
    """문면을 바꿔 검사를 한 번 돌리고 **반드시 되돌린다**.

    대상 문면을 못 찾으면 `None` 이다 — 미성립을 통과로 읽지 않는다.
    """
    path = ROOT / target
    original = path.read_text(encoding="utf-8")
    if old not in original:
        print(f"✗ [{label}] 대상 문면을 찾지 못했습니다: {target}")
        print("  미성립을 통과로 읽지 않습니다")
        return None
    try:
        path.write_text(original.replace(old, new, 1), encoding="utf-8")
        return _run()
    finally:
        path.write_text(original, encoding="utf-8")


def main() -> int:
    if _run() != 0:
        print("✗ 변이를 심기 전부터 빨간불입니다 — 부채 목록을 먼저 맞추십시오")
        return 2

    failures = 0
    for label, target, old, new, why in CASES:
        code = _mutate(label, target, old, new)
        if code is None:
            failures += 1
        elif code == 0:
            print(f"✗ [{label}] 초록불 — 붙들지 않습니다")
            print(f"  기대: {why}")
            failures += 1
        else:
            print(f"✓ [{label}] 빨간불")

    for label, target, old, new, why in GUARDS:
        code = _mutate(label, target, old, new)
        if code is None:
            failures += 1
        elif code != 0:
            print(f"✗ [{label}] 빨간불 — 정당한 서술을 위반으로 봅니다")
            print(f"  기대: {why}")
            failures += 1
        else:
            print(f"✓ [{label}] 초록불 (오판하지 않음)")

    print()
    if failures:
        print(f"✗ {failures}건이 기대와 다릅니다")
        return 1
    print(
        f"통과 — 변이 {len(CASES)}건 전건 빨간불 · "
        f"오판 방지 {len(GUARDS)}건 전건 초록불"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
