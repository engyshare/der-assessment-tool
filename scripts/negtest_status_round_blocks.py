#!/usr/bin/env python
"""`check_status_round_blocks.py` 가 **실제로 가르는가** — R43-J 신설.

실물 `status.md` 는 지금 블록이 **한 판**이라 검사가 초록불이다. 그런데
**초록불이 「상한을 지킨다」는 뜻인지 「아무것도 세지 않는다」는 뜻인지 결과만
으로는 구분되지 않는다**(§13.0.1 ④). 그것이 이 파일의 몫이다.

지어낸 문면을 쓰지 않고 **실물을 읽어 변형한다** — 그래야 `status.md` 의 서식이
바뀌는 날 심기가 실패하고, 그 실패가 「검사가 죽었다」를 알린다. 실물 파일은
건드리지 않는다(임시 디렉터리에만 쓴다).

돌리는 법
---------
    python scripts/negtest_status_round_blocks.py     # 종료 코드 1 = 감지 실패
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS = REPO_ROOT / "status.md"
CHECKER = REPO_ROOT / "scripts" / "check_status_round_blocks.py"

_BLOCK_HEAD = re.compile(r"^> # ⏹+ .*$", re.MULTILINE)
_SECTION_HEAD = re.compile(r"^## 지금 할 일.*$", re.MULTILINE)


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(path)],
        capture_output=True,
        text=True,
    )


def _expect(name: str, path: Path, want: int) -> None:
    got = _run(path)
    if got.returncode != want:
        print(f"FAILED: {name} — 종료 코드 {want} 를 기대했으나 {got.returncode}")
        print(got.stdout)
        sys.exit(1)
    print(f"  · {name} — rc={got.returncode} (기대대로)")


def _planted(text: str, pattern: re.Pattern[str], what: str) -> re.Match[str]:
    """심을 자리를 **실제로 찾았는지 확인하고** 돌려준다.

    찾지 못했는데 조용히 지나가면, 심지 않은 문면을 검사에 넣고 「못 잡았다」는
    결과를 받는다 — 이 저장소가 반복해서 세는 형태다. 여기서 멈춘다.
    """
    match = pattern.search(text)
    if match is None:
        print(f"FAILED: 심기 실패 — `status.md` 에서 {what} 를 찾지 못했다.")
        print("  **검사가 고장난 것이 아니라 심기가 고장난 것이다** —")
        print("  `status.md` 의 서식이 바뀌었고 이 음성 테스트가 따라가지 않았다.")
        sys.exit(1)
    return match


def main() -> int:
    original = STATUS.read_text(encoding="utf-8")
    print("check_status_round_blocks 감지 능력 확인 (음성 3 + 양성 2)")
    print("─" * 74)

    with tempfile.TemporaryDirectory() as d:
        temp = Path(d)

        # 양성 ① 실물 그대로 — 지금 상태가 규칙을 지킨다
        intact = temp / "intact.md"
        intact.write_text(original, encoding="utf-8")
        _expect("양성 ① 실물 그대로", intact, 0)

        # 음성 ② 블록을 한 판 더한다 — **아홉까지 쌓인 그 한 걸음**이다
        head = _planted(original, _BLOCK_HEAD, "라운드 종료 블록 머리(`> # ⏹ `)")
        stacked = temp / "stacked.md"
        stacked.write_text(
            original[: head.start()]
            + "> # ⏹ 2026-01-01 **R00 완료 — 심어 둔 옛 블록이다**\n>\n> 본문.\n\n"
            + original[head.start() :],
            encoding="utf-8",
        )
        _expect("음성 ② 블록 한 판 추가", stacked, 1)

        # 양성 ③ 같은 블록을 **절 밖**에 두면 위반이 아니다 — 거짓 양성을 막는다.
        #   내린 블록까지 세면 「내렸는데도 빨간불」이 되고, 그런 검사는 꺼진다.
        outside = temp / "outside.md"
        outside.write_text(
            original
            + "\n## 다른 절\n\n> # ⏹ 2026-01-01 **R00 완료 — 내려놓은 블록이다**\n",
            encoding="utf-8",
        )
        _expect("양성 ③ 절 밖의 블록", outside, 0)

        # 음성 ④ 절 제목이 사라지면 **0판이 나온다** — 그것을 통과로 읽지 않는다
        section = _planted(original, _SECTION_HEAD, "`## 지금 할 일` 절 머리")
        headless = temp / "headless.md"
        headless.write_text(
            original[: section.start()] + "## 딴 이름" + original[section.end() :],
            encoding="utf-8",
        )
        _expect("음성 ④ 절 제목 소실", headless, 2)

        # 음성 ⑤ 파일이 없으면 보류다 — 「없다」와 「깨끗하다」를 같게 읽지 않는다
        _expect("음성 ⑤ 대상 파일 없음", temp / "없다.md", 2)

    print("─" * 74)
    print("통과 — 검사가 다섯 상태를 실제로 가릅니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
