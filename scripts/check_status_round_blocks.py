#!/usr/bin/env python
"""`status.md` 「지금 할 일」에 **라운드 종료 블록이 몇 판 쌓였는가** — R43-J 신설.

왜 이 검사가 필요한가
---------------------
`status.md` 는 머리에서 스스로 이렇게 적어 두었다 — *「라운드가 끝날 때 이전
「지금 할 일」 블록을 내린다」* · *「이력을 이 파일에 쌓지 않는 것이 규칙이다」*.
**그 규칙을 재는 것이 하나도 없었다.**

그래서 R43 이 열어 보니 블록이 **아홉 판**이었다. 한 라운드에 한 판씩 밀렸고
매번 조용했다. 그 결과 파일이 **1,638줄**까지 자랐고, 같은 파일이 스스로
진단한 대로 **아무도 끝까지 읽지 않아 「산출물 현황」 절이 두 판본 뒤처졌다** —
이 저장소는 그것을 *「길이가 낡음을 만든다」* 고 적었다.

즉 이것은 서식 취향이 아니라 **낡은 수가 다음 라운드의 계획으로 따라 들어가는
경로**이며, 그 경로를 만든 것은 「내렸는가」를 아무도 세지 않은 것이다.

무엇을 판정하는가 — **한 판이 밀린 상태를 빨간불로 본다**
---------------------------------------------------------
상한은 **1** 이다. 규칙이 정한 정상 상태가 정확히 그것이기 때문이다 — 「지금 할
일」에는 **직전 라운드 하나**가 서 있고, 다음 라운드가 닫힐 때 그것이 내려간다.

상한을 2 로 두는 쪽도 정당하다(라운드를 닫는 도중 잠깐 둘이 될 수 있다). 그런데
아홉까지 쌓인 경로가 정확히 **한 판씩 밀리는 것이 조용했던 것**이고, 2 로 두면
그 상태가 **언제나 초록불**이다. 닫는 도중의 둘은 순서로 피할 수 있다 —
규칙이 적은 순서가 이미 *「옛 블록을 내린다 → 새 블록을 세운다」* 이다.

**대상이 0판이어도 통과가 아니다(종료 코드 2).** 「지금 할 일」 절을 못 찾았다면
그것은 「깨끗하다」가 아니라 **이 검사가 아무것도 보지 않았다**는 뜻이다 —
§13.0.1 ④ 가 그 둘을 같게 읽지 말라고 한 자리다.

돌리는 법
---------
    python scripts/check_status_round_blocks.py            # 종료 코드 1 = 상한 초과
    python scripts/check_status_round_blocks.py <경로>     # 음성 테스트가 쓰는 갈래

경로 인자를 받는 이유는 `scripts/negtest_status_round_blocks.py` 가 **지어낸
문면으로 종료 코드까지** 몰기 위해서다. 실물을 변이시키지 않는다.

고치는 법
---------
초과분을 오래된 것부터 `status-history.md` 로 옮긴다. **받는 자리는 머리가
아니라 시간 역순이 지켜지는 자리**다(R43-A 판정).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS = REPO_ROOT / "status.md"

#: 상한. 사유는 위 독스트링에 있다 — 여기서 다시 정하지 않는다.
MAX_BLOCKS = 1

#: 라운드 종료 블록의 머리. 인용 블록 안의 최상위 제목이며, 실물에는
#: `> # ⏹⏹` 처럼 표지가 둘인 판도 있어 하나 이상으로 받는다.
_BLOCK_HEAD = re.compile(r"^> # ⏹+ ")

#: 「지금 할 일」 절의 머리. 뒤에 부제가 붙는다(`(우선순위 순)`).
_SECTION_HEAD = re.compile(r"^## 지금 할 일")

#: 절의 끝 — 인용 블록 안의 `## ` 는 `> ` 로 시작하므로 여기 걸리지 않는다.
_NEXT_SECTION = re.compile(r"^## ")


def round_blocks(text: str) -> tuple[list[str], bool]:
    """(「지금 할 일」 절 안의 블록 제목들, 절을 찾았는가). **순수 함수**다.

    검사기를 `main()` 안에 다 적으면 그 검사기를 검사할 방법이 없어진다
    (`scripts/check_precommit_installed.py` 의 `hook_state` 와 같은 모양).

    절 **밖**의 블록은 세지 않는다. `status-history.md` 로 내린 블록은 이력이며
    위반이 아니고, 파일 전체를 세면 「내렸는데도 빨간불」이 되어 검사가 꺼진다.
    """
    heads: list[str] = []
    inside = False
    found = False
    for line in text.splitlines():
        if _SECTION_HEAD.match(line):
            inside = True
            found = True
            continue
        if inside and _NEXT_SECTION.match(line):
            inside = False
            continue
        if inside and _BLOCK_HEAD.match(line):
            heads.append(line[2:].strip())
    return heads, found


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else STATUS

    line = "─" * 74
    print("「지금 할 일」 라운드 종료 블록 수 — 이력이 쌓이고 있는가")
    print(f"  대상 — {target}")
    print(line)

    if not target.is_file():
        print(f"  ✗ `{target}` 이 없습니다 — 잴 대상이 없습니다")
        print(line)
        print("보류 — 대상이 없는 것을 통과로 읽지 않습니다")
        return 2

    heads, found = round_blocks(target.read_text(encoding="utf-8"))
    if not found:
        print("  ✗ `## 지금 할 일` 절을 찾지 못했습니다 — 절 제목이 바뀌었습니까?")
        print(line)
        print("보류 — **이 검사가 아무것도 보지 않았습니다**")
        return 2

    for head in heads:
        print(f"  · {head}")
    print(line)
    print(f"블록 {len(heads)}판 · 상한 {MAX_BLOCKS}판")

    if len(heads) <= MAX_BLOCKS:
        print("통과 — 이력이 이 파일에 쌓이고 있지 않습니다")
        return 0

    print()
    print(f"**상한을 {len(heads) - MAX_BLOCKS}판 넘었습니다.** 오래된 것부터")
    print("`status-history.md` 로 내리십시오 — 받는 자리는 머리가 아니라")
    print("**시간 역순이 지켜지는 자리**입니다(R43-A 판정).")
    print()
    print("  이 파일이 길어지면 아무도 끝까지 읽지 않고, 그때 낡은 수가")
    print("  다음 라운드의 계획으로 따라 들어갑니다 — 실제로 두 번 일어났습니다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
