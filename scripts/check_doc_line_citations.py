#!/usr/bin/env python3
"""spec·작업목록이 **저장소 안 파일을 줄 번호로** 가리키는가 — 낡을 좌표.

## 왜 이 검사가 필요한가

`rslt/` 의 두 정본 문서는 근거를 적으면서 **소스의 자리**를 함께 든다. 그
자리를 `경로:줄번호` 로 적으면 **다음 편집에 조용히 낡는다** — 코드가 한 줄
늘면 인용은 그대로인 채 딴 것을 가리키고, 문서도 코드도 아무 오류를 내지
않는다. 실측으로 셋이 이미 그렇게 낡아 있었다.

    spec 본문  core/contracts/valuestream.py:60   그 줄은 지금 열거형 안이다
    spec 본문  core/casegrid/e2e_runner.py:470    그 줄은 지금 구분선이다
    작업 목록  heatpump.py:446                    그 줄은 지금 딴 주석이다

셋 다 **한 라운드가 만든 것이 아니라 여러 라운드에 걸쳐 밀린 것**이며, 밀린
것을 아무도 재지 않았다. spec §16.5.2 가 정본 인용에서 내린 결론이 여기에도
그대로 선다 — *「인용 좌표는 “지금 존재하는가”가 아니라 “판본을 넘어
살아남는가”로 골라야 한다」*. 그래서 고칠 방향은 **맞는 줄 번호**가 아니라
**그 자리를 소유한 이름**이다.

    core/contracts/valuestream.py 의 ValueStream.payer
    core/casegrid/e2e_runner.py 의 run_single_case_e2e()

## 무엇을 재는가

`<경로>:<줄번호>` 꼴 문면 중 **그 경로가 이 저장소에 실재하는 것**만 잡는다.
경로의 실재 여부는 `git ls-files` 가 답하고, 줄 번호가 붙었는지는 문면이
답한다 — **검사가 스스로 판정 기준을 만들지 않는다.**

## 면제는 목록이 아니라 **규칙이다**

「이 인용들은 봐준다」는 목록을 두면 다음 사람이 거기에 한 줄을 더 붙여
통과시킨다. 그래서 면제 사유는 둘뿐이고, 둘 다 **규칙으로 판정한다.**

**① 저장소에 없는 경로는 우리가 고칠 수 없다.** 두 문서는 참조 구현
스냅숏(`storagevet` · `dervet`)을 인용하는데 그 트리는 이 저장소에 없다.
없는 파일의 「그 자리를 소유한 이름」을 우리가 확인할 방법이 없으므로 고치라고
요구할 수 없다 — 요구하면 지어내게 된다.

**② 머리말 판본 이력은 기록이다.** YAML 머리말의 `version:` 줄은
*「그 판본이 그때 무엇을 보았나」* 를 적는다. 그 시점의 수치를 그대로 드는
자리이므로(옛 결론축 수치를 그대로 드는 것과 같다) 좌표만 지금 것으로 고치면
**이력이 거짓이 된다.** 그래서 머리말 블록은 통째로 판정 밖이다.

절 번호(`§16.5`)·포트 번호는 **애초에 잡히지 않는다** — 확장자 있는 경로만
경로로 보기 때문이며, 별도의 면제가 아니다.

사용법
------
    python scripts/check_doc_line_citations.py

종료 코드: 0 통과 / 1 낡을 좌표 존재 / 2 설정 오류(대상 0건·인용 0건)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 대상 문서. 저장소 상대 경로(POSIX)로 적는다.
DOCS: tuple[str, ...] = (
    "rslt/spec-분산특구-경제성평가.md",
    "rslt/task-분산특구-경제성평가.md",
)

#: 경로로 볼 확장자. **여기에 없는 것은 경로가 아니다** — `§16.5` 같은 절
#: 번호와 `localhost:8000` 같은 포트가 문턱에서 걸러지는 자리다.
_EXTS = (
    "py|md|yml|yaml|json|toml|cfg|ini|txt|csv|lock|sql|sh|ps1|html|css|js|ts|xlsx"
)

#: `<경로>:<줄번호>`. 경로 문자에 한글을 넣지 않는다 — 이 저장소가 인용하는
#: 소스 경로는 전부 ASCII 이고, 한글을 받으면 「§16.5 절」 같은 문장 조각이
#: 경로로 보이기 시작한다.
_CITE = re.compile(rf"(?<![\w./-])([A-Za-z0-9_][\w./-]*\.(?:{_EXTS})):(\d+)")


def tracked_files() -> list[str]:
    """`git ls-files` 로 저장소 안 파일 목록. `-z` 로 읽는다.

    한글 파일명을 따옴표로 감싸 이스케이프하는 기본 출력을 쓰면 두 대상
    문서 자신이 목록에서 어긋난다 — 작업 목록 2.3 이 실물로 밟은 자리다.
    """
    r = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True, cwd=str(ROOT), check=False,
    )
    if r.returncode != 0:
        return []
    return [p for p in r.stdout.decode("utf-8").split("\0") if p]


def frontmatter_span(lines: list[str]) -> int:
    """YAML 머리말이 끝나는 줄 번호(1-base). 머리말이 없으면 0.

    첫 줄이 `---` 일 때만 머리말로 본다.
    """
    if not lines or lines[0].rstrip() != "---":
        return 0
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return i + 1
    return 0


def main() -> int:
    print("문서 줄번호 인용 검사 — 저장소 안 파일을 `경로:줄번호` 로 가리키는가")

    tracked = tracked_files()
    if not tracked:
        print("ERROR: `git ls-files` 가 비었다 — 저장소 밖에서 돌렸다", file=sys.stderr)
        return 2

    tracked_set = set(tracked)
    #: 바탕 이름 → 그 이름을 가진 경로들. 유일할 때만 해석한다.
    by_base: dict[str, list[str]] = {}
    for p in tracked:
        by_base.setdefault(p.rsplit("/", 1)[-1], []).append(p)

    targets = [(d, ROOT / d) for d in DOCS]
    missing = [d for d, p in targets if not p.is_file()]
    if missing:
        print(f"ERROR: 대상 문서가 없다 — {missing}", file=sys.stderr)
        return 2

    scanned = 0
    outside = 0
    exempt_front = 0
    violations: list[str] = []

    for rel, path in targets:
        lines = path.read_text(encoding="utf-8").splitlines()
        front_end = frontmatter_span(lines)
        for no, line in enumerate(lines, start=1):
            for match in _CITE.finditer(line):
                scanned += 1
                cite, target = match.group(0), match.group(1)
                if no <= front_end:
                    # 면제 ② — 머리말 판본 이력은 기록이다.
                    exempt_front += 1
                    continue
                if target in tracked_set:
                    resolved = target
                elif "/" not in target and len(by_base.get(target, [])) == 1:
                    resolved = by_base[target][0]
                else:
                    # 면제 ① — 저장소에 없는 경로는 우리가 고칠 수 없다.
                    outside += 1
                    continue
                violations.append(
                    f"  {rel}:{no}  `{cite}`\n"
                    f"      -> {resolved} 는 저장소 안 파일이다. 줄 번호는 다음 편집에"
                    f" 조용히 낡는다 — 그 자리를 소유한 이름으로 적으라"
                )

    if scanned == 0:
        print("ERROR: 뽑힌 인용이 0건 — 검사를 수행하지 못했다", file=sys.stderr)
        return 2

    print(
        f"대상 문서 {len(targets)}개 · `경로:줄번호` 인용 {scanned}건 "
        f"(저장소 안 {len(violations)}건 · 밖 {outside}건 · 머리말 면제 {exempt_front}건)"
    )

    if violations:
        print(f"\n✗ 저장소 안 파일을 줄 번호로 가리키는 인용 {len(violations)}건:")
        print("\n".join(violations))
        print("─" * 78)
        print(
            f"의심 {len(violations)}건 — spec §16.5.2 「판본을 넘어 살아남는 좌표」를"
            " 따르십시오"
        )
        return 1

    print("─" * 78)
    print("통과 — 저장소 안 파일을 줄 번호로 가리키는 인용 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
