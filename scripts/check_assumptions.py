#!/usr/bin/env python3
"""잠정 가정 대장 검사 — docs/assumptions.yaml ↔ spec §15.1

무엇을 막는가
-------------
외부 입력을 기다리지 않고 가정값으로 개발을 진행하기로 했다. 그 결정 자체는
합리적이지만, 가정은 **세 가지 방식으로 조용히 굳는다.**

  ① 부기가 비어 굳는다
     "왜 그 값인가"를 적지 않은 가정은 나중에 아무도 검증하지 못한다.
     6개월 뒤에는 그것이 실측이었는지 짐작이었는지 구분이 안 된다.

  ② 교체 경로 없이 굳는다
     `replace_when` 이 없는 가정은 영구 가정이다. 회신이 와도 무엇을
     바꿔야 하는지 아무도 모른다.

  ③ **검증의 정박점을 가정으로 채워 굳는다 — 이것이 가장 위험하다**
     Q-4(선행 실증 원 계산 가정)와 Q-5(현행 엑셀)는 우리 계산을 재는
     자다. 자를 우리가 만들면 무엇을 재도 맞는다. 이 상태는 초록불로
     남기 때문에 스스로 드러나지 않는다 — 틀린 값보다 나쁘다.
     틀린 값은 회신이 오면 드러나지만, 자기충족 검증은 드러나지 않는다.

     spec §13.0.2가 금지한 자기충족 테스트와 같은 구조이며,
     `NFR-105~107`을 수동 대장에 등재하지 못하게 한 것과도 같은 이유다.
     게이트를 정당화하는 것이 그 게이트로 자기를 통과시키면 안 된다.

검사 7종
--------
  1. 부기 7종 전건 존재      근거 표기 기준 5절 = spec FR-601-AC5.*
  2. 신뢰도 어휘             확정 / 추정 / 가정 만 허용 (축 2)
  3. `확정` 주장의 근거      confidence 가 `확정`인데 source·verified_at 이 비면 결함
  4. **blocked 칸의 값**     track: blocked 에 value·sensitivity 가 있으면 결함
  5. 교체 경로               replace_when 이 없으면 결함
  6. 민감도 정합             assume 은 sensitivity 필수, low ≤ base ≤ high, base == value
  7. Q 목록 대조             spec §15.1 표와 양방향 — 누락 Q / 유령 Q

왜 검사기를 만드는가
--------------------
규칙을 문서에만 적으면 지켜지지 않는다. 이 저장소는 그것을 네 번 확인했다.
검사에 걸리지 않는 규칙은 규칙이 아니라 권고다.

종료 코드
---------
  0  통과
  1  결함 있음
  2  파일·형식 오류 (검사를 수행하지 못함)
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


# 근거 표기 기준 5절이 정한 경제성 입력값 필수 부기 항목 7종.
# spec FR-601-AC5.* 와 같은 이름을 쓴다 — 이름이 갈리면 대조가 불가능해진다.
ANNOTATION_FIELDS = [
    "value_unit",
    "base_year",
    "applicable_scope",
    "derivation_method",
    "source",
    "verified_at",
    "confidence",
]

# 근거 표기 기준 2절 축 2. `미확인`은 축 1 전용이므로 여기서 거부한다 —
# 같은 토큰을 두 축에 쓰면 어느 뜻인지 판정할 수 없다 (spec v0.5 어휘 정정).
CONFIDENCE = {"확정", "추정", "가정"}

TRACKS = {"assume", "default0", "blocked"}

# spec §15.1 표에서 Q 번호를 뽑는다. 표 첫 칸에만 있으므로 행 머리로 한정한다 —
# 본문 서술의 언급까지 세면 폐기된 Q가 살아 있는 것으로 잡힌다.
SPEC_Q_ROW = re.compile(r"^\|\s*\*{0,2}(Q-\d+[a-z]?)\*{0,2}\s*\|")
SPEC_SECTION = re.compile(r"^### 15\.1\s")
SPEC_SECTION_END = re.compile(r"^#{2,3} ")


def load_ledger(path: Path):
    if not path.exists():
        print(f"ERROR: 대장이 없습니다 — {path}", file=sys.stderr)
        raise SystemExit(2)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("assumptions")
    if not isinstance(items, list):
        print(f"ERROR: `assumptions:` 목록을 찾을 수 없습니다 — {path}", file=sys.stderr)
        raise SystemExit(2)
    return items


def spec_questions(path: Path) -> set[str]:
    """spec §15.1 표의 Q 번호 집합."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, ln in enumerate(lines) if SPEC_SECTION.match(ln)), None)
    if start is None:
        print("ERROR: spec에서 §15.1 절을 찾을 수 없습니다", file=sys.stderr)
        raise SystemExit(2)

    found: set[str] = set()
    for ln in lines[start + 1:]:
        if SPEC_SECTION_END.match(ln):
            break
        m = SPEC_Q_ROW.match(ln)
        if m:
            found.add(m.group(1))
    return found


def is_blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def check(items: list, spec_qs: set[str]) -> list[str]:
    defects: list[str] = []

    def bad(item, msg: str):
        label = item.get("key") or item.get("q_ref") or "(무명)"
        defects.append(f"{label}: {msg}")

    seen_keys: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            defects.append(f"항목이 매핑이 아닙니다: {item!r:.60}")
            continue

        key = item.get("key")
        if is_blank(key):
            defects.append("`key`가 없는 항목이 있습니다 — "
                           "교체 시 무엇을 고칠지 특정할 수 없습니다")
            continue
        if key in seen_keys:
            bad(item, "`key` 중복 — 같은 항목이 두 값을 갖게 됩니다")
        seen_keys.add(key)

        track = item.get("track")
        if track not in TRACKS:
            bad(item, f"`track`이 {sorted(TRACKS)} 중 하나가 아닙니다: {track!r}")
            continue

        # ── 1. 부기 7종 ──────────────────────────────────────────────
        #
        # blocked 도 예외가 아니다. 값이 없는 것과 왜 없는지를 안 적은 것은
        # 다르다 — derivation_method 에 "가정하면 안 되는 이유"가 들어간다.
        for f in ANNOTATION_FIELDS:
            if f not in item:
                bad(item, f"부기 항목 `{f}` 필드 자체가 없습니다 "
                      "(근거 표기 기준 5절 7종)")

        if is_blank(item.get("derivation_method")):
            bad(item, "`derivation_method`가 비었습니다 — "
                      "근거 없는 가정은 나중에 검증할 수 없습니다")

        # ── 2. 신뢰도 어휘 ───────────────────────────────────────────
        conf = item.get("confidence")
        if conf not in CONFIDENCE:
            bad(item, f"`confidence`는 {sorted(CONFIDENCE)} 중 하나여야 합니다 "
                      f"(축 2): {conf!r}")

        # ── 3. `확정` 주장의 근거 ────────────────────────────────────
        if conf in ("확정", "추정"):
            if is_blank(item.get("source")):
                bad(item, f"`{conf}`을 주장하는데 `source`가 비었습니다 — "
                          "근거 없이 신뢰도를 올릴 수 없습니다")
            if is_blank(item.get("verified_at")):
                bad(item, f"`{conf}`을 주장하는데 `verified_at`이 비었습니다 — "
                          "실제로 열어본 날짜가 필요합니다")

        # ── 4. blocked 칸의 값 — 자기충족 검증 차단 ──────────────────
        #
        # 이 검사가 이 스크립트의 존재 이유다.
        if track == "blocked":
            if item.get("value") is not None:
                bad(item, "**track: blocked 인데 `value`가 채워져 있습니다.** "
                          "검증의 정박점을 가정으로 채우면 우리가 만든 값으로 우리 "
                          "계산을 검증하게 됩니다 (§13.0.2 자기충족 테스트). "
                          "값을 비우고 판정을 유예하십시오")
            if item.get("sensitivity") is not None:
                bad(item, "track: blocked 인데 `sensitivity`가 있습니다 — "
                          "없는 값에 범위를 줄 수 없습니다")
            if not item.get("blocks"):
                bad(item, "track: blocked 인데 `blocks`가 없습니다 — "
                          "무엇이 유예되는지 적지 않으면 그 판정이 조용히 통과로 세어집니다")

        # ── 5. 교체 경로 ─────────────────────────────────────────────
        if is_blank(item.get("replace_when")):
            bad(item, "`replace_when`이 비었습니다 — 교체 조건이 없는 가정은 영구 가정이 됩니다")

        # ── 6. 민감도 정합 ───────────────────────────────────────────
        sens = item.get("sensitivity")
        if track == "assume":
            if not isinstance(sens, dict):
                bad(item, "track: assume 은 `sensitivity`(low/base/high)가 필수입니다 — "
                          "단일 값만 두면 그 값이 맞다는 인상을 줍니다")
            else:
                missing = [k for k in ("low", "base", "high") if k not in sens]
                if missing:
                    bad(item, f"`sensitivity`에 {missing} 가 없습니다")
                else:
                    lo, base, hi = sens["low"], sens["base"], sens["high"]
                    if not all(isinstance(x, (int, float)) for x in (lo, base, hi)):
                        bad(item, "`sensitivity` 값이 수치가 아닙니다")
                    elif not (lo <= base <= hi):
                        bad(item, "`sensitivity` 순서가 어긋납니다: "
                                  f"{lo} ≤ {base} ≤ {hi} 이어야 합니다")
                    elif item.get("value") != base:
                        bad(item, f"`value`({item.get('value')})와 "
                                  f"`sensitivity.base`({base})가 다릅니다 — 같은 사실이 "
                                  "두 값을 가지면 어느 쪽이 정본인지 판정할 수 없습니다")
        elif track == "default0" and item.get("value") != 0:
            bad(item, f"track: default0 인데 `value`가 0이 아닙니다: {item.get('value')!r} — "
                      "제도 미확인 항목의 크기를 추정하면 없는 제도 위에 편익을 쌓게 됩니다")

    # ── 7. Q 목록 대조 ───────────────────────────────────────────────
    ledger_qs = {i.get("q_ref") for i in items if isinstance(i, dict) and i.get("q_ref")}

    for q in sorted(spec_qs - ledger_qs):
        defects.append(f"{q}: spec §15.1에 있으나 대장에 없습니다 — "
                       f"확보 전까지 무엇으로 대신하는지가 정해지지 않았습니다")
    for q in sorted(ledger_qs - spec_qs):
        defects.append(f"{q}: 대장에 있으나 spec §15.1에 없습니다 — "
                       f"폐기된 Q이거나 오타입니다")

    return defects


def summarize(items: list) -> None:
    by_track = {t: [i for i in items if i.get("track") == t] for t in TRACKS}
    print(f"· 등재 {len(items)}건 — "
          f"가정 진행 {len(by_track['assume'])} / "
          f"기본 비활성 {len(by_track['default0'])} / "
          f"가정 불가 {len(by_track['blocked'])}")

    conf_counts: dict[str, int] = {}
    for i in items:
        c = i.get("confidence")
        conf_counts[c] = conf_counts.get(c, 0) + 1
    parts = " / ".join(f"{k} {v}" for k, v in sorted(conf_counts.items()))
    print(f"· 신뢰도 — {parts}")

    high = [i for i in items if i.get("impact") in ("최상", "높음")]
    if high:
        print(f"· 영향도 최상·높음 {len(high)}건 — 회신을 먼저 받아야 할 항목")
        for i in high:
            print(f"    {i['q_ref']:6} {i.get('key',''):<38.38} {i.get('impact','')}")

    blocked = [i for i in items if i.get("track") == "blocked"]
    if blocked:
        print(f"\n· 유예 중인 판정 — 가정 불가 {len(blocked)}건이 막고 있다")
        for i in blocked:
            for b in i.get("blocks", []):
                print(f"    {b:28} ← {i['q_ref']} {i.get('title','')}")
        print("  **이 판정들은 통과로도 실패로도 세지 않는다.** 미판정으로 남긴다")


def main() -> int:
    repo = Path(__file__).resolve().parent.parent

    ap = argparse.ArgumentParser(description="잠정 가정 대장 검사 (§15.1)")
    ap.add_argument("--ledger", type=Path, default=repo / "docs/assumptions.yaml")
    ap.add_argument("--spec", type=Path, default=None)
    args = ap.parse_args()

    spec_path = args.spec
    if spec_path is None:
        candidates = sorted((repo / "rslt").glob("spec-*.md"))
        if len(candidates) != 1:
            print(f"ERROR: spec을 특정할 수 없습니다 ({len(candidates)}건)", file=sys.stderr)
            return 2
        spec_path = candidates[0]

    print(f"잠정 가정 대장  {args.ledger.name}  ↔  {spec_path.name} §15.1")
    print("─" * 78)

    items = load_ledger(args.ledger)
    spec_qs = spec_questions(spec_path)

    summarize(items)
    print("─" * 78)

    defects = check(items, spec_qs)
    if defects:
        print(f"✗ 결함 {len(defects)}건")
        for d in defects:
            print(f"    {d}")
        print("─" * 78)
        return 1

    print("통과 — 부기 7종·신뢰도·교체 경로·민감도·Q 목록 정합")
    print("\n가정은 가정이라고 표시된 채로만 유효합니다. 회신이 오면 "
          "값과 부기를 갱신하고 이 검사를 다시 돌리십시오.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
