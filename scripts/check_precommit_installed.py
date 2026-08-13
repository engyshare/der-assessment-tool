#!/usr/bin/env python
"""pre-commit 훅이 **이 작업 사본에 실제로 설치돼 있는가** — 작업 2.3 / SC-3·SC-5·SC-8.

왜 이 검사가 따로 필요한가
--------------------------
`tests/ci/test_ci_gates.py::test_private_data_scan_runs_in_both_pre_commit_and_ci`
가 이미 있고 초록불이다. 그런데 **그 테스트가 보는 것은 `.pre-commit-config.yaml`
에 훅이 선언돼 있는가**이지, 그 훅이 이 작업 사본에서 **도는가**가 아니다.
둘은 다르며, 다른 줄 모르고 읽으면 「커밋 전에 멈추는 장치가 있다」로 읽힌다.

**실측으로 갈렸다 (R25).** 이 저장소에서 `.git/hooks/` 에는 표본 파일밖에 없었고
(`pre-commit install` 을 한 적이 없다), 그 상태에서 로컬 절대 경로가 담긴
`status.md` 가 **아무 저항 없이 커밋됐다.** 잡은 것은 훅이 아니라 사람이 손으로
돌린 `check_disclosure.py` 였고, 그때는 이미 이력에 들어간 뒤였다 — 미푸시라
커밋을 다시 써서 지웠지만, 푸시 뒤였다면 그것으로 늦다.

즉 **선언과 설치 사이가 아무 검사도 보지 않는 자리**였다. 이 저장소가 반복해
만난 형태 그대로다 — 게이트는 있는데 아무도 부르지 않는다.

왜 CI 에서 켜지 않는가
----------------------
CI 는 저장소를 새로 받아 돌므로 **로컬 훅이 구조적으로 없다.** 거기서 켜면
조항이 요구하지 않은 영구 실패가 되고, 그런 검사는 곧 무시된다
(`check_source_rules.py --require-vault` 와 같은 이유). 그래서 이 검사는
**사람이 커밋하는 기계에서** 도는 것이고, CI 에서는 스스로 판단을 보류한다.

돌리는 법
---------
    python scripts/check_precommit_installed.py     # 종료 코드 1 = 설치 안 됨

고치는 법 (`.pre-commit-config.yaml` 머리말과 같다)
    pip install pre-commit
    pre-commit install
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 설치된 훅이 pre-commit 프레임워크의 것임을 알아보는 표지. 프레임워크가 쓰는
#: 훅 파일에는 자기 이름이 들어간다. 파일이 있기만 하면 통과시키면, 손으로 만든
#: 빈 훅이나 다른 도구의 훅도 「설치됨」이 된다.
_MARKER = "pre-commit"


def hook_state(repo_root: Path) -> tuple[bool, str]:
    """(설치됐는가, 사람이 읽을 사유). **순수 함수** — 테스트가 임시 경로로 몬다.

    검사기를 `main()` 안에 다 적으면 그 검사기를 검사할 방법이 없어진다.
    `tests/ci/test_precommit_installed.py` 가 세 상태(없음·다른 훅·정상)를
    각각 만들어 이 함수가 실제로 가르는지 본다.
    """
    config = repo_root / ".pre-commit-config.yaml"
    if not config.is_file():
        return False, f"`.pre-commit-config.yaml` 이 없습니다: {config}"

    hook = repo_root / ".git" / "hooks" / "pre-commit"
    if not hook.is_file():
        return False, (
            "`.git/hooks/pre-commit` 이 없습니다 — 설정은 선언돼 있으나 "
            "**이 작업 사본에서는 아무것도 막지 않습니다.**"
        )

    body = hook.read_text(encoding="utf-8", errors="replace")
    if _MARKER not in body:
        return False, (
            "`.git/hooks/pre-commit` 이 있으나 pre-commit 프레임워크의 훅이 "
            "아닙니다 — 다른 도구의 훅이거나 손으로 만든 파일입니다. "
            "`.pre-commit-config.yaml` 의 검사(gitleaks·비공개 유입)는 돌지 "
            "않습니다."
        )
    return True, "`.git/hooks/pre-commit` 이 pre-commit 프레임워크 훅입니다"


def main() -> int:
    line = "─" * 74
    print("pre-commit 훅 설치 검사 — 선언이 아니라 **설치**를 본다")
    print(line)

    if os.environ.get("CI"):
        print("  · CI 에서는 판단하지 않습니다 — 로컬 훅이 구조적으로 없습니다.")
        print(line)
        print("보류 — 이 검사가 도는 곳은 **사람이 커밋하는 기계**입니다")
        return 0

    ok, why = hook_state(REPO_ROOT)
    print(f"  {'·' if ok else '✗'} {why}")
    print(line)
    if ok:
        print("통과 — 커밋 전에 멈추는 장치가 실제로 걸려 있습니다")
        print()
        print("  이 검사는 훅이 **걸려 있는지**만 봅니다. 훅은 `--no-verify` 한 줄로")
        print("  우회되므로, 그것까지 막는 것은 CI 쪽 몫입니다(SC-5 gitleaks 잡).")
        return 0

    print("설치되지 않음 — 비공개 유입이 **커밋되는 것을 아무것도 막지 않습니다**")
    print()
    print("  pip install pre-commit")
    print("  pre-commit install")
    print()
    print("  **커밋된 뒤에는 파일을 지워도 이력에 남습니다.** 지우려면 저장소")
    print("  이력을 다시 써야 하고, 공개된 뒤라면 그것으로도 늦습니다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
