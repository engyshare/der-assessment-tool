#!/usr/bin/env python3
"""check_source_rules.py 음성 테스트 — **정본 대조가 실제로 표류를 잡는가.**

## 이 파일이 생긴 이유

`scripts/` 의 검사기 여덟 중 **이것만 음성 테스트가 없었다.** 그래서
`check_source_rules.py` 는 **감지 능력이 증명된 적 없는 게이트**다 — CI 가
매번 「통과」를 찍지만 그 통과가 무엇을 뜻하는지 아무도 확인하지 않았다.

R13 이 이 스크립트에 머리말 재소유 검사를 넣을 때 **손으로 위반을 심어
`rc=1` 을 확인**했다. 그 확인은 파일에 남지 않았고, 이 저장소가 R7 에 배운
문장이 그것을 예고한다 — *「손으로 훑은 것은 다음에 또 잠든다.」*

## 왜 실물 spec 에 심지 않고 픽스처를 합성하는가

다른 음성 테스트들(`negtest_partition_assignment.py` 등)은 실물 spec 에
`str.replace` 로 위반을 심는다. 그 방식은 **대상이 바뀌면 조용히 빈 치환**이
되어 검사를 죽인다(R9 에 실제로 그렇게 죽어 있었다).

이 검사는 대조 대상이 **spec + lock + 정본 파일 셋의 관계**라서 실물에
심으려면 볼트까지 건드려야 한다. 그래서 픽스처를 합성한다. **대신 합성이
실물과 어긋나 조용해지는 것을 두 장치로 막는다.**

  ① **양성 기준선** — 위반 없는 픽스처는 `rc=0` 이어야 한다. 검사기의 기대가
     바뀌어 픽스처가 더 이상 유효하지 않으면 **여기서 먼저 빨간불이 난다.**
     이것이 없으면 「항상 빨간불인 검사」도 전건 통과로 보인다.
  ② **구조 가드** — 픽스처가 흉내내는 모양이 실물 spec·lock 에 아직 있는지
     본다. 실물이 그 모양을 버리면 이 픽스처는 낡은 것을 검사하는 것이다.

사용:
    python scripts/negtest_source_rules.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKER = REPO / "scripts" / "check_source_rules.py"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}")
        if detail:
            for line in detail.splitlines()[:12]:
                print(f"       {line}")
        FAILURES.append(name)


def plant(text: str, old: str, new: str) -> str:
    """위반을 **실제로 심었는지 확인하고** 심는다.

    `str.replace` 는 대상이 없으면 아무 일도 하지 않고 원본을 돌려준다.
    그러면 **심지 않은 픽스처를 검사에 넣고 「위반을 못 잡았다」는 결과**를
    받는다 — 검사가 멀쩡한데 빨간불이 나거나, 더 나쁘게는 통과로 읽힌다.
    R9 에 그 형태로 음성 테스트 하나가 죽어 있었다.
    """
    out = text.replace(old, new)
    if out == text:
        print(f"  FAIL 심기 실패 — 픽스처에서 {old!r} 를 찾지 못했다")
        print("       픽스처를 고친 뒤 이 문자열도 함께 고칠 것.")
        print("       **검사가 고장난 것이 아니라 심기가 고장난 것이다.**")
        FAILURES.append(f"심기 실패: {old!r}")
        return text
    return out


# ── 픽스처 ────────────────────────────────────────────────────────────────
#
# 실물의 모양을 최소한으로 흉내낸다. 아래 «구조 가드» 가 그 모양이 실물에
# 아직 있는지 확인한다.

DOMAIN_SOURCE = """\
# 분산자원 경제성 평가 원칙 (픽스처)

## 2. 편익 계상

원칙 2-3  관점 분리 — 편익의 귀속은 계약구조에 따른다.

## 부록 A. 편익 항목 추가 시 실무 적용 절차

핵심 규칙 세 가지
"""

EVIDENCE_SOURCE = """\
# 근거 표기 기준 (픽스처)

## 0. 핵심 요약

## 2. 축 2 — 입력값 신뢰도

확정 · 추정 · 가정 셋으로 나눈다.
"""

#: 위반이 하나도 없는 spec. **이것이 `rc=0` 이어야 나머지 판정이 뜻을 갖는다.**
#:
#: 마지막 「변경 요약」 절은 일부러 폐지 좌표(`§2.1`)를 인용한다 —
#: §16.5.3 절차 2b 가 그 블록을 제외하므로 **오탐이 나면 안 되는 자리**다.
#: 제외 처리가 깨지면 기준선이 빨간불로 알려 준다.
SPEC_CLEAN = """\
---
title: 테스트용 spec (픽스처)
version: v0.0
---

## 1. 개요

편익 귀속은 [[분산자원 경제성 평가 원칙]] 원칙 2-3 을 따른다.
입력값 신뢰도는 [[근거 표기 기준]] 2절 을 따른다.
편익 항목 추가는 부록 A. 편익 항목 추가 시 실무 적용 절차 와
핵심 규칙 세 가지 를 따른다.

## 2. 상세

여기에는 인용이 없다.

## 17. 변경 요약

v0.0 에서 [[분산자원 경제성 평가 원칙]] §2.1 인용을 걷어냈다.
(이 줄은 제외 절이므로 폐지 좌표를 적어도 위반이 아니다)
"""


def _lock_text(domain_sha: str, evidence_sha: str) -> str:
    return f"""\
version: 1
vault_root: ""
locked_at: "2026-01-01T00:00:00+09:00"
locked_against_spec: "픽스처"

sources:
  - path: "원칙.md"
    wikilink: "[[분산자원 경제성 평가 원칙]]"
    mtime: "2026-01-01T00:00:00+09:00"
    size_bytes: 1
    sha256: "{domain_sha}"
    cited_anchors:
      - "원칙 2-3"
    cited_headings:
      - "부록 A. 편익 항목 추가 시 실무 적용 절차"
      - "핵심 규칙 세 가지"

  - path: "근거.md"
    wikilink: "[[근거 표기 기준]]"
    mtime: "2026-01-01T00:00:00+09:00"
    size_bytes: 1
    sha256: "{evidence_sha}"
    cited_anchors:
      - label: "2절"
        match: "## 2. 축 2 — 입력값 신뢰도"
"""


def _write(path: Path, text: str) -> None:
    """개행을 번역하지 않고 쓴다 — 해시 대조가 바이트를 보기 때문이다."""
    path.write_text(text, encoding="utf-8", newline="")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_checker(tmp: Path, lock_text: str, spec_text: str,
                *, vault: bool = True) -> tuple[int, str]:
    """픽스처로 검사기를 돌리고 `(종료코드, 출력)` 을 돌려준다.

    **파이프를 걸지 않는다.** `cmd | tail; echo rc=$?` 로 파이프의 종료 코드를
    읽어 `rc=1` 을 `rc=0` 으로 볼 뻔한 적이 있다(R9).
    """
    vault_dir = tmp / "vault"
    vault_dir.mkdir(exist_ok=True)
    # **`newline=""` 가 없으면 Windows 에서 `\n` → `\r\n` 으로 번역된다.**
    # 그러면 파일 바이트가 위 문자열과 달라 `_sha()` 가 계산한 해시와 어긋나고,
    # **위반이 없는 픽스처가 「해시 불일치」로 잡힌다.** 실제로 그렇게 났고
    # 양성 기준선(①)이 그것을 잡았다 — 기준선이 없었다면 판정 문구만 보고
    # 「전건 통과」로 읽었을 것이다.
    _write(vault_dir / "원칙.md", DOMAIN_SOURCE)
    _write(vault_dir / "근거.md", EVIDENCE_SOURCE)

    lock = tmp / "fixture.lock"
    spec = tmp / "spec-픽스처.md"
    _write(lock, lock_text)
    _write(spec, spec_text)

    cmd = [sys.executable, str(CHECKER), "--lock", str(lock), "--spec", str(spec)]
    if vault:
        cmd += ["--vault", str(vault_dir)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       cwd=str(REPO))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def detects(tmp: Path, name: str, lock_text: str, spec_text: str,
            needle: str, *, vault: bool = True) -> None:
    """위반을 심은 픽스처에서 그 문구가 나오고 종료 코드가 0이 아닌지 본다.

    **문구만 보지 않는다.** 문구가 나오는데 `rc=0` 이면 그 검사는 게이트가
    아니라 주석이다 — 호출 측이 종료 코드로만 판단하기 때문이다.
    """
    rc, out = run_checker(tmp, lock_text, spec_text, vault=vault)
    hit = needle in out and rc != 0
    check(name, hit, f"rc={rc}\n{out}")


def main() -> int:
    print("check_source_rules.py 음성 테스트 — 정본 대조가 표류를 잡는가")

    domain_sha = _sha(DOMAIN_SOURCE)
    evidence_sha = _sha(EVIDENCE_SOURCE)
    lock_clean = _lock_text(domain_sha, evidence_sha)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ── ① 양성 기준선 — 이것이 통과해야 아래가 뜻을 갖는다 ─────────────
        print("\n① 양성 기준선 (위반 없는 픽스처)")
        rc, out = run_checker(tmp, lock_clean, SPEC_CLEAN)
        check("위반 없는 픽스처는 rc=0 이다", rc == 0, f"rc={rc}\n{out}")
        check("「통과」를 출력한다", "통과 — 정본과 spec이 정합합니다" in out, out)
        # 제외 절(변경 요약)의 폐지 좌표를 위반으로 세면 **영구 오탐**이 된다.
        check("제외 절의 폐지 좌표는 오탐하지 않는다",
              "폐지된 하위 절 번호 인용" not in out, out)
        check("모호한 인용을 오탐하지 않는다",
              "출처가 모호한 원칙 인용" not in out, out)

        # ── ② 대조 1: 정본 해시 ────────────────────────────────────────────
        print("\n② 정본 해시 — 정본이 lock 기록 이후 바뀌었는가")
        detects(tmp, "정본 해시가 다르면 잡는다",
                plant(lock_clean, domain_sha, "0" * 64), SPEC_CLEAN,
                "해시 불일치")

        # ── ③ 대조 2: 저장소 사본 ──────────────────────────────────────────
        print("\n③ 저장소 사본 — 사본이 없거나 정본과 다른가")
        detects(tmp, "저장소 사본이 없으면 잡는다",
                plant(lock_clean, '    wikilink: "[[분산자원 경제성 평가 원칙]]"',
                      '    wikilink: "[[분산자원 경제성 평가 원칙]]"\n'
                      '    repo_copy: "docs/없는사본-픽스처.md"'),
                SPEC_CLEAN, "저장소 사본 없음")
        # 정본도 사본도 없으면 **판정을 수행하지 못한 것**이다 — 통과로 읽으면
        # §13.0.1 ④ 위반이다.
        detects(tmp, "정본과 사본이 모두 없으면 통과로 읽지 않는다",
                plant(lock_clean, 'path: "원칙.md"', 'path: "없는정본.md"'),
                SPEC_CLEAN, "정본과 저장소 사본 모두 없음")

        # ── ④ 대조 3: 앵커·제목 실재 ───────────────────────────────────────
        print("\n④ 앵커 실재 — spec 이 인용하는 좌표가 정본에 아직 있는가")
        # lock 과 spec 양쪽에 넣어야 **인용 정합 검사가 아니라 앵커 실재
        # 검사가** 걸린다. 한쪽만 넣으면 다른 검사가 먼저 잡아 이 경로를
        # 검사하지 못한다 — R13 의 「앞선 분기가 먼저 걸러 버린」 그 형태다.
        detects(tmp, "정본에서 사라진 원칙 앵커를 잡는다",
                plant(lock_clean, '      - "원칙 2-3"',
                      '      - "원칙 2-3"\n      - "원칙 9-9"'),
                plant(SPEC_CLEAN, "원칙 2-3 을 따른다.",
                      "원칙 2-3 을 따른다. 또한 [[분산자원 경제성 평가 원칙]] "
                      "원칙 9-9 도 따른다."),
                "인용 앵커 소실: 원칙 9-9")
        detects(tmp, "정본에서 사라진 인용 제목을 잡는다",
                plant(lock_clean, '      - "핵심 규칙 세 가지"',
                      '      - "핵심 규칙 세 가지"\n      - "없는 제목 전문"'),
                plant(SPEC_CLEAN, "핵심 규칙 세 가지 를 따른다.",
                      "핵심 규칙 세 가지 와 없는 제목 전문 을 따른다."),
                "인용 제목 소실: 없는 제목 전문")

        # ── ⑤ 대조 4: spec ↔ lock 인용 정합 (양방향) ───────────────────────
        print("\n⑤ 인용 정합 — 본문 인용과 lock 목록이 양방향으로 맞는가")
        detects(tmp, "spec 이 인용하나 lock 에 없으면 잡는다",
                lock_clean,
                plant(SPEC_CLEAN, "## 2. 상세\n\n여기에는 인용이 없다.",
                      "## 2. 상세\n\n"
                      "[[분산자원 경제성 평가 원칙]] 원칙 5-1 도 적용한다."),
                "spec이 인용하나 lock에 없음: 원칙 5-1")
        detects(tmp, "lock 에 있으나 spec 이 인용하지 않으면 잡는다",
                lock_clean,
                plant(SPEC_CLEAN,
                      "편익 귀속은 [[분산자원 경제성 평가 원칙]] 원칙 2-3 을 따른다.",
                      "편익 귀속에 대한 인용을 지웠다."),
                "lock에 있으나 spec이 인용하지 않음: 원칙 2-3")
        detects(tmp, "lock 에 있으나 spec 이 인용하지 않는 제목을 잡는다",
                lock_clean,
                plant(SPEC_CLEAN, "핵심 규칙 세 가지 를 따른다.", "그 절차를 따른다."),
                "lock에 있으나 spec이 인용하지 않는 제목: 핵심 규칙 세 가지")
        # 출처 표지 없는 `원칙 N-M` — 두 규칙 문서가 원칙 번호 19개를 공유하므로
        # 어느 문서인지 판정할 수 없다.
        detects(tmp, "출처 표지 없는 원칙 인용을 잡는다",
                lock_clean,
                plant(SPEC_CLEAN, "여기에는 인용이 없다.", "원칙 4-3 을 적용한다."),
                "출처가 모호한 원칙 인용")

        # ── ⑥ 대조 5: 폐지 좌표 인용 ───────────────────────────────────────
        print("\n⑥ 폐지 좌표 — 정본이 폐기한 하위 절 번호를 쓰고 있는가")
        detects(tmp, "본문의 폐지 좌표 인용을 잡는다",
                lock_clean,
                plant(SPEC_CLEAN, "여기에는 인용이 없다.",
                      "[[분산자원 경제성 평가 원칙]] §2.1 을 참조한다."),
                "폐지된 하위 절 번호 인용")
        # 표지 집합이 갈리면 한쪽만 인정하는 표기가 탐지 사각이 된다 —
        # 스크립트 주석이 실제로 그렇게 빠져나간 전례를 적고 있다
        # (`도메인 원칙 §2.4`).
        detects(tmp, "위키링크가 아닌 「도메인 원칙」 표기도 잡는다",
                lock_clean,
                plant(SPEC_CLEAN, "여기에는 인용이 없다.",
                      "도메인 원칙 §2.4 를 참조한다."),
                "폐지된 하위 절 번호 인용")

        # ── ⑦ 머리말 재소유 (R13 이 손으로만 확인한 자리) ──────────────────
        print("\n⑦ 머리말 재소유 — 판본의 소유가 lock 하나인가")
        detects(tmp, "머리말이 sha256 을 다시 소유하면 잡는다",
                lock_clean,
                plant(SPEC_CLEAN, "version: v0.0",
                      "version: v0.0\nevidence_standard: "
                      f'"[[근거 표기 기준]] sha256: {evidence_sha}"'),
                "머리말이 정본 판본을 재소유합니다")
        # **값이 맞아도 잡아야 한다.** 값을 맞추는 것으로 닫히는 검사라면
        # 다음 개정에 같은 자리가 다시 어긋난다(§16.1 W-4 · 원칙 3-C).
        detects(tmp, "머리말이 mtime 을 다시 소유하면 잡는다",
                lock_clean,
                plant(SPEC_CLEAN, "version: v0.0",
                      "version: v0.0\ndomain_rules: "
                      '"[[분산자원 경제성 평가 원칙]] @ 2026-01-01T00:00:00+09:00"'),
                "머리말이 정본 판본을 재소유합니다")

        # ── ⑧ 픽스처가 실물의 모양을 아직 흉내내는가 (구조 가드) ───────────
        #
        # 합성 픽스처의 약점은 **실물이 모양을 바꿔도 조용하다**는 것이다.
        # 그러면 낡은 것을 검사하면서 초록불을 낸다. 여기서 그것을 막는다.
        print("\n⑧ 구조 가드 — 픽스처가 실물의 모양을 아직 흉내내는가")
        real_lock = (REPO / "docs/source-rules.lock").read_text(encoding="utf-8")
        specs = sorted((REPO / "rslt").glob("spec-*.md"))
        check("실물 spec 이 하나로 특정된다", len(specs) == 1,
              f"{[p.name for p in specs]}")
        real_spec = specs[0].read_text(encoding="utf-8") if specs else ""

        for needle, why in (
            ("cited_anchors", "lock 이 원칙 앵커 목록을 든다"),
            ("cited_headings", "lock 이 제목 앵커 목록을 든다"),
            ("repo_copy", "lock 이 저장소 사본을 가리킨다"),
            ("sha256", "lock 이 판본을 sha256 으로 고정한다"),
        ):
            check(f"실물 lock: {why}", needle in real_lock)
        check("실물 spec 이 도메인 정본 위키링크를 인용한다",
              "[[분산자원 경제성 평가 원칙]]" in real_spec)
        check("실물 spec 본문이 `## 1. ` 로 시작하는 구조다",
              "\n## 1. " in real_spec)
        # **실물 저장소로도 한 번 돌린다.** 픽스처만 검사하면 「검사기는 잡는데
        # 저장소가 실제로 표류 중」인 상태를 이 파일이 못 본다. 머리말 재소유가
        # 되살아나면(R13 이 lock 하나로 줄인 자리) 여기서 걸린다.
        real = subprocess.run(
            [sys.executable, str(CHECKER)], capture_output=True, text=True,
            encoding="utf-8", cwd=str(REPO))
        check("실물 저장소가 이 게이트를 통과한다 (rc=0)", real.returncode == 0,
              f"rc={real.returncode}\n{real.stdout}{real.stderr}")

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("전건 통과 — 정본 대조 5종 + 머리말 재소유 검사가 실제로 잡는다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
