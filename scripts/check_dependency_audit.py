#!/usr/bin/env python3
"""의존성 취약점 판정 대조 — `audit.txt` ↔ `docs/accepted-vulnerabilities.yaml`

무엇을 막는가
-------------
`pip-audit` 는 **찾기만 한다.** 종전 CI 는 그 결과를 `::warning::` 하나로
흘렸고, 조항(`NFR-405`)이 Should-have 라 차단하지 않는 것 자체는 옳았다.
문제는 그 다음이다 — **경고는 상태를 갖지 않는다.** 어제 있던 한 건과 오늘
생긴 두 건이 같은 노란 줄로 보이고, 아무도 보지 않으면 영영 그대로다.
이 저장소가 반복해서 만난 「빨간불이 아닌 방식으로 죽는 것」이며, 여기서는
**취약점이 초록불 안에 숨는** 형태로 나타났다(R42 가 실제로 그렇게 두 라운드
지난 것을 인계 문서에서 발견했다).

그래서 **판정된 것과 판정 안 된 것을 가른다.**

  판정된 것    대장에 사유·재검토 조건과 함께 있다 → 조용하다
  판정 안 된 것  아무도 본 적이 없다               → **빨간불**

「통과할 수 없는 검사는 꺼진다」는 반론은 워크플로 주석이 이미 적어 두었고,
그 반론은 **빠져나갈 문이 있으면 성립하지 않는다** — 대장에 사유를 적으면
통과한다. 막는 것은 취약점이 아니라 **아무도 안 본 취약점**이다.
`KNOWN_TARIFF_DEBT`·`KNOWN_ESCALATION_IGNORED_IN_REPLACEMENT` 와 같은 래칫이며
**줄어도 말한다** — 상류가 고쳐 사라진 항목은 대장에서 빼라고 알린다.

무엇을 못 막는가
----------------
`pip-audit` 가 **찾지 못한** 취약점은 여기서도 안 보인다. 이 검사는 스캐너의
출력 대 대장의 대조이지 스캐너의 성능 판정이 아니다. 그리고 **출력에 ID 가
드러나지 않은 건**은 셀 수 없다 — 「2건」이라 적히고 ID 는 하나만 나오는
경우가 실제로 있었다. 그래서 건수를 세지 않고 **ID 를 대조한다**(셀 수 없는
것을 세면 그 수가 거짓이 된다).

종료 코드
---------
  0  찾은 권고가 전부 대장에 있다 (또는 0건)
  1  대장에 없는 권고가 있다 · 대장 항목의 부기가 빠졌다
  2  스캔 결과를 읽지 못했다 (파일 없음·빈 파일·형식 오류) — **검사 미수행**
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML이 필요합니다 — pip install pyyaml", file=sys.stderr)
    raise SystemExit(2) from None


#: 권고 ID 문면 — `pip-audit` 가 내는 세 체계. 종전 CI 가
#: `grep -qiE "GHSA-|PYSEC-|CVE-"` 로 보던 것과 **같은 셋**이며 그 셋을 여기 한
#: 곳으로 모았다 — 두 곳에 두면 한쪽만 늘어 「경고는 떴는데 대조는 안 한」 ID 가
#: 생긴다.
ADVISORY = re.compile(
    r"\b(?:"
    r"PYSEC-\d{4}-\d+"
    r"|GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}"
    r"|CVE-\d{4}-\d+"
    r")\b"
)

#: 판정 하나가 갖춰야 하는 부기. `assumptions.yaml` 의 `replace_when` 과 같은
#: 이유로 `revisit_when` 을 필수로 둔다 — 「무엇이 오면 바뀌나」가 없는 판정은
#: 영구 판정이며, 그것은 판정이 아니라 체념이다.
REQUIRED_FIELDS = ("id", "package", "decision", "reason", "revisit_when")

DECISIONS = ("올리지 않는다", "올린다(예정)")


def load_ledger(path: Path) -> list[dict]:
    if not path.exists():
        print(f"ERROR: 판정 대장이 없습니다 — {path}", file=sys.stderr)
        raise SystemExit(2)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("accepted") or []
    if not isinstance(items, list):
        print(f"ERROR: {path.name} 의 `accepted` 가 목록이 아닙니다", file=sys.stderr)
        raise SystemExit(2)
    return items


def found_advisories(path: Path) -> list[str]:
    """스캔 출력에서 권고 ID 를 뽑는다. **파일이 비면 미수행이다.**

    `pip-audit` 는 취약점이 0건이어도 「No known vulnerabilities found」를
    낸다 — 즉 **빈 파일은 「깨끗하다」가 아니라 「안 돌았다」** 이며, 그 둘을
    같게 읽으면 도구가 없어도 초록불이 된다(CI 2.7 에서 닫은 구멍과 같다).
    """
    if not path.exists():
        print(f"ERROR: 스캔 결과가 없습니다 — {path} (pip-audit 이 돌지 않았습니다)",
              file=sys.stderr)
        raise SystemExit(2)
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print(f"ERROR: {path.name} 이 비었습니다 — 스캔이 돌지 않았습니다", file=sys.stderr)
        raise SystemExit(2)
    return sorted(set(ADVISORY.findall(text)))


def check(found: list[str], items: list[dict]) -> list[str]:
    defects: list[str] = []

    accepted: set[str] = set()
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            defects.append(f"{i}번 항목이 사전이 아닙니다")
            continue
        missing = [f for f in REQUIRED_FIELDS if not str(item.get(f, "")).strip()]
        if missing:
            defects.append(f"{item.get('id', f'{i}번 항목')}: 부기 누락 — {', '.join(missing)}")
        decision = str(item.get("decision", "")).strip()
        if decision and decision not in DECISIONS:
            defects.append(
                f"{item.get('id')}: `decision` 은 {' / '.join(DECISIONS)} 중 하나입니다 "
                f"(받은 값 「{decision}」)"
            )
        if item.get("id"):
            accepted.add(str(item["id"]).strip())

    for advisory in found:
        if advisory not in accepted:
            defects.append(
                f"{advisory}: **판정된 적이 없습니다.** `docs/accepted-vulnerabilities.yaml` 에 "
                "올릴지 말지를 사유·재검토 조건과 함께 적으십시오 — 올리기로 했다면 "
                "판본을 올린 뒤 이 ID 가 사라지는 것으로 닫힙니다"
            )

    # **줄어도 말한다** — 상류가 고쳐 사라진 항목을 대장에 남겨 두면, 다음
    # 사람이 「아직 있는 위험」으로 읽고 없는 일을 한다.
    for stale in sorted(accepted - set(found)):
        defects.append(
            f"{stale}: 대장에 있는데 스캔에 **없습니다.** 상류가 고쳤거나 의존이 빠진 "
            "것이므로 대장에서 그 항목을 지우십시오(래칫은 줄어도 빨간불입니다)"
        )

    return defects


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit", type=Path, default=repo / "audit.txt",
                    help="pip-audit 출력 파일 (기본: 저장소 루트의 audit.txt)")
    ap.add_argument("--ledger", type=Path,
                    default=repo / "docs/accepted-vulnerabilities.yaml")
    args = ap.parse_args()

    print(f"의존성 취약점 판정  {args.audit.name}  ↔  {args.ledger.name}")
    print("─" * 78)

    found = found_advisories(args.audit)
    items = load_ledger(args.ledger)

    print(f"스캔이 낸 권고 {len(found)}건 · 대장에 판정된 것 {len(items)}건")
    for advisory in found:
        print(f"    {advisory}")
    print("─" * 78)

    defects = check(found, items)
    if defects:
        print(f"✗ 결함 {len(defects)}건")
        for d in defects:
            print(f"    {d}")
        return 1

    print("통과 — 찾은 권고가 전부 판정돼 있습니다")
    print("\n판정은 판정으로 남아 있을 때만 유효합니다. `revisit_when` 이 참이 되는 "
          "날 다시 여십시오.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
