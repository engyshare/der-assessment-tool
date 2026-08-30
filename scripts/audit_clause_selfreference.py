#!/usr/bin/env python3
"""**그물 ③-2** — 한 조항의 인용 **전부**가 다른 조항만 적는 자리를 지목한다.

## 왜 `check_` 가 아니라 `audit_` 인가

⚠⚠ **이것은 판정이 아니라 지목이다.** R38 이 `FR-101-AC3` 에서 만난 결함의
뿌리는 **독스트링이 거짓이었던 것**이다(`.orch/R38/result_ac3_empty.md:341-353`).
거짓일 수 있는 문면으로 위반을 선고할 수 없다. 그래서 이 도구는 **사람이 볼
후보 목록만 만들고 종료 코드를 차단으로 올리지 않는다.**

`check_docstring_references.py` 에서 진짜 위반과 부채를 가른 것과 같은 판단이다
— *「경고가 차단이 되면 정당한 서술이 커밋을 막고, 사람이 검사를 끈다」*.
이름을 `check_` 로 두면 「게이트 전건」 습관에 쓸려 들어가 언젠가 차단이 된다.
그래서 `audit_` 로 둔다. **CI 에 배선하지 않는다** — 감지 능력만
`negtest_clause_nets.py` 가 CI 에서 잰다.

## 무엇을 지목하는가

    조항 X 의 인용이 1건 이상 있다
    그 인용 **어느 것도** 자기 문면에 X 를 적지 않는다
    그런데 **어떤 인용은 다른 조항 Y 를 적는다**
        → 후보

세 번째 조건이 중요하다. 조항 ID 를 **아무것도** 안 적는 인용만 있는 조항은
지목하지 않는다 — 그것은 「다른 조항을 잰다」는 신호가 아니라 그냥 문면이
조항을 안 적는 것이며, 실측 294건 중 120건이 그 상태다. 그것까지 지목하면
목록의 절반이 신호가 아니게 된다.

## 문면을 어디서 얻는가

`check_docstring_references.py::_chunks()` 의 방식대로 **`ast` 로 독스트링과
문자열 상수, `tokenize` 로 주석**을 얻는다 — 정규식으로 소스를 훑지 않는다.
범위는 **인용을 단 함수의 본문**이다(모듈·클래스 독스트링은 그 테스트의 말이
아니다). 데코레이터를 빼는 이유는 `_citations.py` 머리말에 적었다.

전개 부모·자식(`FR-601-AC2` ↔ `FR-601-AC2.cost`)은 「다른 조항」으로 세지
않는다 — `_citations.same_clause()` 가 그 판단을 소유한다.

## 종료 코드

    0  훑었다 (후보가 있어도 0 이다 — **차단이 아니다**)
    2  훑을 것이 없다 (인용 0건) — 검사 미수행

    python scripts/audit_clause_selfreference.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _citations import DEFAULT_TESTS, Citation, by_clause, collect, same_clause


def candidates(
    cited: dict[str, list[Citation]],
) -> list[tuple[str, int, list[str]]]:
    """(조항, 인용 건수, 인용들이 적은 다른 조항들). 조항 ID 순."""
    out: list[tuple[str, int, list[str]]] = []
    for cid, cites in sorted(cited.items()):
        if any(any(same_clause(cid, m) for m in c.mentions) for c in cites):
            continue
        others = sorted({m for c in cites for m in c.mentions})
        if not others:
            continue
        out.append((cid, len(cites), others))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="그물 ③-2 — 인용 전부가 다른 조항만 적는 조항을 지목한다 (차단 아님)"
    )
    ap.add_argument("--tests", type=Path, default=DEFAULT_TESTS)
    ap.add_argument("--verbose", action="store_true", help="후보마다 인용 자리를 함께 낸다")
    args = ap.parse_args()

    citations, defects = collect(args.tests)
    if defects:
        print(f"ERROR: 테스트 파싱 결함 {len(defects)}건 — 인용 목록을 믿을 수 없다",
              file=sys.stderr)
        for d in defects[:10]:
            print(f"  {d}", file=sys.stderr)
        return 2
    if not citations:
        print("ERROR: 인용 0건 — 훑을 것이 없다", file=sys.stderr)
        return 2

    cited = by_clause(citations)
    found = candidates(cited)

    print(f"인용 있는 조항 {len(cited)}건 · 인용 {len(citations)}건 · 후보 {len(found)}건")
    print("※ 지목이며 판정이 아니다 — 독스트링은 거짓일 수 있다. 사람이 대조하라.")
    for cid, count, others in found:
        shown = ", ".join(others[:4]) + (" …" if len(others) > 4 else "")
        print(f"  후보 {cid}  인용 {count}건  적힌 조항: {shown}")
        if args.verbose:
            for c in cited[cid]:
                print(f"        {c.path}:{c.lineno} {c.func}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
