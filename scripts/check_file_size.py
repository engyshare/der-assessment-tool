"""NFR-206 파일 규모 검사 — 단일 소스 파일 500줄 상한.

**왜 저장소 전체를 훑는가.** v1.0 시점에 이 검사를 쓴 것은 WP-1e 하나뿐이었고
(`tests/der/test_load.py`·`test_thermal_load.py`), 그것도 **자기 파일 두 개만**
보았다. 나머지 네 자원은 감시 밖이었고, 계약 개정으로 상한을 넘긴 것이 정확히
그 넷이다. 자원마다 손으로 쓰는 검사는 반드시 빠진다 — 계약 테스트를 상속으로
따라오게 만든 것과 같은 이유다 (§16.2).

**경고이고 차단이 아니다.** NFR-206은 Should-have이고 측정 수단이 `M1 lint 경고`
로 규정되어 있다. 차단으로 켜면 조항이 요구하지 않은 강제력을 갖게 되고, 통과
시키려고 근거 주석을 지우는 압력이 생긴다 — 이 조항의 근거(DER-VET `Params.py`
1,830줄 유지보수 실패)는 **코드 스프롤**을 막으려는 것이지 설명을 줄이려는 것이
아니다.

    종료 코드 0  전건 상한 이내, 또는 초과분이 있으나 경고로만 보고
    종료 코드 2  검사 자체가 성립하지 않음 (대상 디렉터리 없음)

`--strict` 를 주면 초과분에서 1을 돌려준다. 파일 분할을 마친 뒤 회귀를 막으려면
그때 CI에서 이 옵션을 켠다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

LIMIT = 500

#: 검사 대상. 테스트는 제외한다 — 검증 케이스는 자원 하나에 수십 건이 붙으므로
#: 같은 상한을 걸면 케이스를 쪼개는 압력이 되고, 그것은 NFR-106(자원별 케이스
#: 의무)과 정면으로 부딪친다. NFR-206 이 말하는 것은 **소스 파일**이다.
TARGETS = ("core", "app", "infra", "scripts")

EXCLUDE_PARTS = {"__pycache__", ".venv", "migrations"}


def measure(root: Path) -> list[tuple[Path, int]]:
    found: list[tuple[Path, int]] = []
    for target in TARGETS:
        base = root / target
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if EXCLUDE_PARTS & set(path.parts):
                continue
            lines = len(path.read_text(encoding="utf-8").splitlines())
            found.append((path.relative_to(root), lines))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NFR-206 파일 규모 검사 (500줄)")
    parser.add_argument("--root", default=".", help="저장소 루트")
    parser.add_argument("--strict", action="store_true",
                        help="상한 초과 시 종료 코드 1 (기본은 경고만)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    measured = measure(root)
    if not measured:
        print(f"검사 대상 파일이 없습니다: {root} / {', '.join(TARGETS)}", file=sys.stderr)
        print("검사를 수행하지 못한 것을 통과로 읽지 않습니다 (§13.0.1 ④)", file=sys.stderr)
        return 2

    over = [(p, n) for p, n in measured if n > LIMIT]

    print(f"NFR-206 파일 규모 — 상한 {LIMIT}줄 / 대상 {len(measured)}개 파일")
    print("─" * 74)
    for path, lines in sorted(over, key=lambda t: -t[1]):
        print(f"경고  {lines:4d}줄  {path}  (+{lines - LIMIT})")
    if not over:
        widest = max(measured, key=lambda t: t[1])
        print(f"전건 상한 이내 — 최대 {widest[1]}줄 ({widest[0]})")
    print("─" * 74)

    if over:
        print(f"상한 초과 {len(over)}건. **줄 수를 맞추려고 근거 주석을 지우지 "
              "마십시오** — 조항의 근거는 코드 스프롤이며, 초과가 계속되면 "
              "파일을 쪼개는 것이 답입니다 (§16.3 파일 1개 = 자원 1종과의 "
              "긴장은 판단 사항으로 남깁니다)")
        return 1 if args.strict else 0

    print("통과")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
