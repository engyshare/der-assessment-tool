"""NFR-105 게이트 ③ 커밋 순서 검사 — 작업 2.17.

조항 문면: *"PR 내에서 해당 기능의 테스트 커밋이 구현 커밋보다 선행하는지 확인.
위반 시 경고(차단 아님, 스쿼시 병합 등 예외 존재)"* (NFR-105 Measurement 3).

**이것이 `NFR-105-AC1` 의 순서를 재는 유일한 검사다.** 조항이 요구하는 것은
*"구현보다 그 구현을 규정하는 실패 테스트가 **먼저** 존재해야 한다"* 이며, 게이트
①(변경분 커버리지)과 ②(테스트 동반)는 **한 시점의 diff** 만 본다 — 거기에는
순서가 없다. R59 까지 그 조항을 인용하는 검사 24건이 전부 diff 를 재고 있었고,
매핑표는 초록불이었다(`docs/decisions-2026-09-04-R59.md`).

**재는 것과 재지 못하는 것을 가른다.**

    잰다     테스트가 구현보다 **먼저 커밋되었는가**
    못 잰다  테스트가 구현보다 **먼저 작성되었는가**

둘은 다르다. 사람은 테스트를 먼저 쓰고 나중에 함께 커밋할 수 있고, 반대로 구현을
먼저 쓰고 커밋만 순서대로 쪼갤 수도 있다. **이 검사가 잡는 것은 커밋 이력에
남은 흔적이지 사람의 작업 순서가 아니다.** 그래서 차단이 아니라 경고다 — 경고를
차단으로 올리면 조항을 넘고, 넘은 게이트는 꺼진다(이 저장소가 `NFR-206`·
`NFR-405` 에서 같은 판단을 두 번 했다).

**「해당 기능의 테스트」를 여기서 새로 정하지 않는다.** 짝 판정은 게이트 ②
(`scripts/check_test_accompaniment.py`)의 `check()` 가 이미 한다 — 그 함수가
돌려주는 `Accompanied` 하나하나가 *"이 구현의 대응 테스트는 이것"* 이라는 판정
이고, 인정 경로(import · 상위 패키지 · 파일명 규약)까지 담고 있다. 규약을 두 곳에
두면 한쪽만 고쳐지고, 갈린 쪽이 느슨하면 그 게이트가 조용히 무력화된다
(§16.1 W-4 단일 소유 — `_gitdiff` 를 한 곳에 모은 것과 같은 이유).

**거짓 경고를 만드는 자리 둘을 갈라 둔다.**

    한 커밋에 구현과 시험이 함께 있다
        위반이 아니다. 그 커밋 안에서는 순서를 말할 수 없고, 이 저장소의
        라운드가 실제로 그렇게 커밋한다. 「같은 자리」를 「나중」으로 읽으면
        정상 커밋 전부가 경고가 되고, 전부가 경고면 아무도 읽지 않는다.

    커밋이 하나뿐인 범위
        판정 불가(종료 코드 2)이지 통과가 아니다. 견줄 두 자리가 없으면
        「순서가 옳다」도 「그르다」도 말할 수 없다.

    종료 코드 0  위반 없음 **또는 위반 있음(경고)**
    종료 코드 2  판정할 수 없음 (기준 ref 없음 · 커밋 하나뿐 · 빈 범위)

**종료 코드 1 이 없는 것이 이 검사의 규격이다.** 조항이 *"차단 아님"* 이라고 못
박으므로 위반에 1 을 내면 조항을 넘는다. 대신 **2 를 반드시 둔다** — *"스캔이
돌지 않았다"* 와 *"깨끗하다"* 를 같게 읽지 않는 것이 이 저장소의 규약이고
(§13.0.1 ④), 경고만 내는 게이트일수록 그 구별이 사라지기 쉽다. 이 검사는 스스로
0 을 내므로 CI 에서 `|| true` 나 `continue-on-error` 가 **필요 없다**. 붙이면
종료 코드 2 까지 삼켜 *"판정하지 못했다"* 가 초록불로 보인다.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import check_test_accompaniment as gate2
from _gitdiff import (
    CheckError,
    Commit,
    base_reader,
    changed_files,
    commits_in_range,
    head_reader,
)


@dataclass(frozen=True)
class OutOfOrder:
    """구현이 그 대응 테스트보다 먼저 커밋된 짝 하나."""

    impl: str
    test: str
    impl_sha: str
    test_sha: str
    how: str


def first_touch(commits: list[Commit], path: str) -> int | None:
    """`path` 를 **처음** 만진 커밋의 자리. 아무도 안 만졌으면 `None`.

    마지막이 아니라 처음을 보는 이유: 조항이 묻는 것은 *"먼저 존재했는가"* 다.
    구현을 먼저 커밋하고 뒤에 여러 번 손본 이력에서 마지막을 보면 구현이
    나중으로 보여 **위반이 통과로 뒤집힌다.**
    """
    for index, commit in enumerate(commits):
        if path in commit.paths:
            return index
    return None


def check(commits: list[Commit], pairs: list[tuple[str, str, str]]) -> list[OutOfOrder]:
    """커밋 목록과 «구현 ↔ 대응 테스트» 짝을 받아 위반을 돌려준다.

    `pairs` 는 `(구현 경로, 테스트 경로, 인정 경로)` 셋이며 게이트 ②의
    `check()` 가 돌려준 `Accompanied` 에서 온다 — 짝 규약은 여기 없다.

    git 을 부르지 않는다. 게이트 ②의 판정 함수와 같은 이유로 이렇게 가른다 —
    검증 케이스가 실제 커밋을 만들지 않고도 판정 논리를 시험할 수 있어야 한다.
    `main()` 이 git 연결부를 맡고, `tests/ci/test_ci_gates.py` 가 이 함수를
    직접 부른다.

    **같은 자리는 위반이 아니다.** `impl_at == test_at` 이면 한 커밋이 둘을
    함께 담은 것이고, 그 안에서는 순서가 없다.
    """
    violations: list[OutOfOrder] = []
    for impl, test, how in pairs:
        impl_at = first_touch(commits, impl)
        test_at = first_touch(commits, test)
        if impl_at is None or test_at is None:
            # 범위 밖에서 온 짝이다 — 이 PR 이 만지지 않은 파일의 순서를
            # 이 PR 의 이력으로 판정할 수 없다.
            continue
        if test_at > impl_at:
            violations.append(
                OutOfOrder(
                    impl=impl,
                    test=test,
                    impl_sha=commits[impl_at].sha,
                    test_sha=commits[test_at].sha,
                    how=how,
                )
            )
    return violations


def pairs_from_gate2(changes, read, read_before) -> list[tuple[str, str, str]]:
    """게이트 ②의 판정을 «구현 ↔ 대응 테스트» 짝으로 옮긴다.

    게이트 ②가 **동반되었다**고 판정한 것만 짝이 된다. 동반되지 않은 구현
    변경은 게이트 ②가 이미 차단으로 잡으므로 여기서 다시 경고하지 않는다 —
    같은 사실을 두 게이트가 각자 세면 어느 쪽이 무엇을 잡았는지 흐려진다.
    """
    _, accompanied = gate2.check(changes, read, read_before)
    return [(a.path, a.by, a.how) for a in accompanied]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="NFR-105 게이트 ③ 커밋 순서 검사 (작업 2.17) — 경고이며 차단이 아니다"
    )
    parser.add_argument("--base", required=True,
                        help="비교 기준 ref (예: origin/main). PR 의 대상 브랜치")
    parser.add_argument("--root", default=".", help="저장소 루트")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    print(f"커밋 순서 검사 — 기준 {args.base}")
    print("─" * 78)

    try:
        commits = commits_in_range(args.base, root)
        changes = changed_files(args.base, root)
        read_before = base_reader(args.base, root)
    except CheckError as exc:
        print(f"판정할 수 없습니다: {exc}", file=sys.stderr)
        print("판정하지 못한 것을 통과로 읽지 않습니다 (§13.0.1 ④)", file=sys.stderr)
        return 2

    if len(commits) < 2:
        print(f"범위 안의 커밋이 {len(commits)}건입니다 — 순서를 판정할 수 없습니다.",
              file=sys.stderr)
        print("견줄 두 자리가 없으면 「순서가 옳다」도 「그르다」도 말할 수 "
              "없습니다. 이것은 통과가 아니라 **미판정**입니다 (§13.0.1 ④)",
              file=sys.stderr)
        return 2

    pairs = pairs_from_gate2(changes, head_reader(root), read_before)

    print(f"커밋 {len(commits)}건 · 구현↔테스트 짝 {len(pairs)}건")
    for index, commit in enumerate(commits):
        print(f"  {index + 1}. {commit.sha[:8]} {commit.subject[:60]}")

    violations = check(commits, pairs)
    print("─" * 78)

    if not pairs:
        print("판정 대상 짝이 없습니다 — `core/` 하위 구현 변경이 없거나 "
              "게이트 ②가 대응 테스트를 찾지 못했습니다")
        return 0

    for impl, test, how in pairs:
        flagged = any(v.impl == impl and v.test == test for v in violations)
        mark = "⚠" if flagged else "·"
        print(f"{mark} {impl}")
        print(f"    ↔ {test}  [{how}]")

    if violations:
        print()
        print(f"::warning::테스트가 구현보다 나중에 커밋된 짝 {len(violations)}건 "
              "— NFR-105 Measurement 3 (경고 · 차단 아님)")
        for v in violations:
            print(f"  · {v.impl}")
            print(f"      구현 커밋  {v.impl_sha[:8]}")
            print(f"      테스트 커밋 {v.test_sha[:8]}  ← 나중이다")
        print()
        print("  **이것은 차단이 아니다.** 스쿼시 병합·리베이스로 이력을 다시")
        print("  쓴 경우, 그리고 테스트를 먼저 **작성**하고 나중에 커밋한 경우")
        print("  이 경고는 사실과 다르다 — 이 검사는 작성 순서가 아니라 커밋")
        print("  순서를 잰다. 그 셋이 아니라면 다음 PR 에서는 실패하는 테스트를")
        print("  먼저 커밋하십시오 (NFR-105-AC1).")
        return 0

    print(f"통과 — 짝 {len(pairs)}건 모두 테스트가 구현보다 나중이 아니다")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
