#!/usr/bin/env python3
"""check_task_mapping.py 음성 테스트 — **작업 목록 인용 검사가 실제로 잡는가.**

## 이 파일이 생긴 이유

`check_task_mapping.py` 는 **감지 능력이 증명된 적 없고 CI 도 부르지 않는**
유일한 검사기였다. 그래서 `rc=1` 이 로컬에서만 보이고 커밋은 초록불로 지나간다.

실제로 그 상태에서 벌어진 일이 있다. spec v0.13 이 `FR-202` 를 수용기준 단위로
쪼개 `AC1`~`AC3` 를 Phase 1 로 올리고 v0.14 가 `FR-301-AC4` 를 신설했는데,
**작업 목록이 따라오지 않아 미인용 Must-have 가 0 → 4건이 됐다.** 아무 게이트도
그것을 보지 않았고, 08-09 의 `status.md` 는 계속 「미인용 0건」이라 적고 있었다.

## 이 검사가 붙드는 것 넷

| 판정 | 무엇을 잡는가 |
|---|---|
| 범위 초과 | `FR-106-AC1`~`AC9` 인용인데 실제 수용기준이 4건뿐 |
| **실재하지 않는 인용** | 폐기·오타 ID 인용. **조용히 무효**가 되므로 이름을 준다 |
| **미인용 Must-have** | 인용이 엉뚱한 조항으로 가서 **비어 버린 자리** |
| 형식 이탈(경고) | 표준형 밖의 선언 — 집계에서 통째로 빠진다 |

앞의 셋은 `rc=1` 이고 형식 이탈은 경고다. **경고를 `rc` 로 올리지 않는 것까지
검사한다** — 경고가 차단이 되면 정당한 서술이 커밋을 막고, 그러면 사람이
검사를 끈다.

## 픽스처를 합성한다 — 그리고 그 약점을 두 장치로 막는다

① **양성 기준선** — 위반 없는 픽스처는 `rc=0` 이어야 한다. 검사기의 기대가
   바뀌어 픽스처가 무효가 되면 **여기서 먼저 빨간불**이 난다. 없으면
   「항상 빨간불인 검사」도 전건 통과로 보인다.
② **실물 형식 가드** — 픽스처가 흉내내는 표·필드 형식이 실물
   `docs/traceability.md` 와 `rslt/task-*.md` 에 아직 있는지 본다.

사용:
    python scripts/negtest_task_mapping.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKER = REPO / "scripts" / "check_task_mapping.py"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}")
        for line in detail.splitlines()[:14]:
            print(f"       {line}")
        FAILURES.append(name)


def plant(text: str, old: str, new: str) -> str:
    """위반을 **실제로 심었는지 확인하고** 심는다.

    `str.replace` 는 대상이 없으면 아무 일도 하지 않고 원본을 돌려준다.
    그러면 **심지 않은 픽스처를 검사에 넣고 「위반을 못 잡았다」는 결과**를
    받는다 — R9 에 그 형태로 음성 테스트 하나가 죽어 있었다.
    """
    out = text.replace(old, new)
    if out == text:
        print(f"  FAIL 심기 실패 — 픽스처에서 {old!r} 를 찾지 못했다")
        print("       **검사가 고장난 것이 아니라 심기가 고장난 것이다.**")
        FAILURES.append(f"심기 실패: {old!r}")
        return text
    return out


# ── 픽스처 ────────────────────────────────────────────────────────────────
#
# `TR_ROW` 가 읽는 형식:
#   | `FR-106` | Must-have | 1 | `FR-106-AC1` | 본문 | 자동 | test_x.py |
# 요구사항 셀은 첫 행에만 있고 이후 조항이 물려받는다. **Phase 는 행마다** 다시
# 읽는다 — 물려받게 두면 Phase 2 조항이 Phase 1 로 취급돼 미인용 오탐이 된다.

TRACE_CLEAN = """\
# 매핑표 (픽스처)

| 요구사항 | 우선순위 | Phase | 수용기준 | 본문 | 검증 | 위치 |
|---|---|---|---|---|---|---|
| `FR-900` | Must-have | 1 | `FR-900-AC1` | 첫째 조항 | 자동 | test_a.py |
|  |  | 1 | `FR-900-AC2` | 둘째 조항 | 자동 | test_a.py |
|  |  | 2 | `FR-900-AC3` | Phase 2 조항이라 인용하지 않아도 된다 | 미매핑 | — |
| `NFR-900` | Should-have | 1 | `NFR-900-M1` | Must-have 가 아니다 | 자동 | test_b.py |
"""

#: 위반이 하나도 없는 작업 목록.
#:
#: 마지막 블록인용 줄은 **`- 수용기준:` 표준형이 아닌 채 조항을 언급**한다 —
#: 형식 이탈 경고에 걸려야 하지만 **`rc` 를 1 로 올려서는 안 된다.** 그 갈림이
#: 이 픽스처에 들어 있는 이유다.
TASKS_CLEAN = """\
# 작업 목록 (픽스처)

## 9.0 픽스처 상위 작업 — WP-99 / Wave 1

- **9.1** [T] 첫째 조항을 검증한다
  - 수용기준: `FR-900-AC1`
- **9.2** [I] 둘째 조항을 구현한다
  - 수용기준: `FR-900-AC2`
"""

TASKS_STRAY = TASKS_CLEAN + """\
> 위 9.2 는 `FR-900-AC2` 수용기준을 함께 본다 — 이 줄은 **서술**이고 표준형이
> 아니므로 집계에 들어가지 않는다. 경고로만 나와야 한다.
"""


def _write(path: Path, text: str) -> None:
    """개행을 번역하지 않고 쓴다 — 줄 단위 정규식이 대상이기 때문이다."""
    path.write_text(text, encoding="utf-8", newline="")


def run_checker(tmp: Path, trace_text: str, tasks_text: str) -> tuple[int, str]:
    """픽스처로 검사기를 돌리고 `(종료코드, 출력)` 을 돌려준다.

    **파이프를 걸지 않는다.** `cmd | tail; echo rc=$?` 로 파이프의 종료 코드를
    읽어 `rc=1` 을 `rc=0` 으로 볼 뻔한 적이 있다(R9).
    """
    trace = tmp / "traceability.md"
    tasks = tmp / "task-픽스처.md"
    _write(trace, trace_text)
    _write(tasks, tasks_text)
    r = subprocess.run(
        [sys.executable, str(CHECKER), "--traceability", str(trace),
         "--tasks", str(tasks)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def detects(tmp: Path, name: str, trace_text: str, tasks_text: str,
            needle: str) -> None:
    """위반을 심은 픽스처에서 그 문구가 나오고 `rc != 0` 인지 본다.

    **문구만 보지 않는다.** 문구가 나오는데 `rc=0` 이면 그 검사는 게이트가
    아니라 주석이다 — 호출 측이 종료 코드로만 판단하기 때문이다.
    """
    rc, out = run_checker(tmp, trace_text, tasks_text)
    check(name, needle in out and rc != 0, f"rc={rc}\n{out}")


def main() -> int:
    print("check_task_mapping.py 음성 테스트 — 인용 검사가 실제로 잡는가")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ── ① 양성 기준선 ─────────────────────────────────────────────
        print("\n① 양성 기준선 (위반 없는 픽스처)")
        rc, out = run_checker(tmp, TRACE_CLEAN, TASKS_CLEAN)
        check("위반 없는 픽스처는 rc=0 이다", rc == 0, f"rc={rc}\n{out}")
        check("「통과」를 출력한다", "통과" in out, out)
        # Phase 2 조항과 Should-have 조항을 인용 의무로 세면 **영구 오탐**이 된다.
        check("Phase 2 조항을 미인용으로 세지 않는다",
              "FR-900-AC3" not in out, out)
        check("Must-have 아닌 조항을 미인용으로 세지 않는다",
              "NFR-900-M1" not in out, out)

        # ── ② 미인용 Must-have — 이 라운드에 실제로 터진 판정 ──────────
        print("\n② 미인용 Must-have — 인용이 빠져 비어 버린 자리")
        detects(tmp, "Phase 1 Must-have 인용이 빠지면 잡는다",
                TRACE_CLEAN,
                plant(TASKS_CLEAN, "  - 수용기준: `FR-900-AC2`",
                      "  - 수용기준: `FR-900-AC1`"),
                "FR-900-AC2")
        # 옮겨 간 쪽이 아니라 **비워진 쪽**을 세는지 확인한다. 반대로 세면
        # 「인용이 어디로 갔는가」만 보고 「무엇이 비었는가」를 못 본다.
        rc, out = run_checker(
            tmp, TRACE_CLEAN,
            plant(TASKS_CLEAN, "  - 수용기준: `FR-900-AC2`",
                  "  - 수용기준: `FR-900-AC1`"))
        check("미인용 목록에 남아 있는 인용은 넣지 않는다",
              "미인용 Must-have 수용기준 1건" in out, out)

        # ── ③ 실재하지 않는 인용 — 폐기·오타 ID 는 조용히 무효가 된다 ──
        print("\n③ 실재하지 않는 인용 (유령)")
        detects(tmp, "spec 에 없는 조항 인용을 잡는다",
                TRACE_CLEAN,
                plant(TASKS_CLEAN, "  - 수용기준: `FR-900-AC2`",
                      "  - 수용기준: `FR-900-AC2`, `FR-900-AC9`"),
                "실재하지 않는 수용기준 인용")
        detects(tmp, "오타 요구사항 번호도 잡는다",
                TRACE_CLEAN,
                plant(TASKS_CLEAN, "  - 수용기준: `FR-900-AC1`",
                      "  - 수용기준: `FR-901-AC1`"),
                "실재하지 않는 수용기준 인용")

        # ── ④ 범위 초과 인용 ──────────────────────────────────────────
        print("\n④ 범위 초과 인용")
        detects(tmp, "실제 조항 수보다 넓은 범위 인용을 잡는다",
                TRACE_CLEAN,
                plant(TASKS_CLEAN, "  - 수용기준: `FR-900-AC1`",
                      "  - 수용기준: `FR-900-AC1`~`AC9`"),
                "범위 초과 인용")

        # ── ⑤ 형식 이탈은 **경고다** — rc 로 올리지 않는다 ─────────────
        print("\n⑤ 형식 이탈 — 경고이고 rc 를 올리지 않는다")
        rc, out = run_checker(tmp, TRACE_CLEAN, TASKS_STRAY)
        check("형식 이탈을 경고로 보고한다", "형식 이탈 인용 의심" in out, out)
        # **경고가 차단이 되면 정당한 서술이 커밋을 막고, 사람이 검사를 끈다.**
        check("형식 이탈만으로는 rc=0 이다 (경고를 차단으로 올리지 않는다)",
              rc == 0, f"rc={rc}\n{out}")
        # 그리고 형식 이탈 줄의 인용은 **집계에 들어가지 않아야** 한다 —
        # 들어가면 「있는 인용을 지우는」 오류가 반대로 「없는 인용을 만드는」
        # 오류가 된다.
        check("형식 이탈 줄이 인용 집계를 채우지 않는다",
              "미인용 Must-have 수용기준 없음" in out, out)

        # ── ⑥ 설정 오류는 rc=2 — 「위반 없음」과 갈라야 한다 ────────────
        print("\n⑥ 설정 오류 (rc=2) — 「위반 없음」으로 읽지 않는다")
        r = subprocess.run(
            [sys.executable, str(CHECKER),
             "--traceability", str(tmp / "없는매핑표.md"),
             "--tasks", str(tmp / "task-픽스처.md")],
            capture_output=True, text=True, encoding="utf-8", cwd=str(REPO))
        check("매핑표가 없으면 rc=2 다 (통과로 읽지 않는다)",
              r.returncode == 2, f"rc={r.returncode}\n{r.stdout}{r.stderr}")

        # ── ⑦ 실물 형식 가드 ──────────────────────────────────────────
        print("\n⑦ 실물 형식 가드 — 픽스처가 실물의 형식을 아직 흉내내는가")
        trace_real = (REPO / "docs" / "traceability.md").read_text(encoding="utf-8")
        tasks_cands = sorted((REPO / "rslt").glob("task-*.md"))
        check("실물 작업 목록이 하나로 특정된다", len(tasks_cands) == 1,
              f"{[p.name for p in tasks_cands]}")
        tasks_real = tasks_cands[0].read_text(encoding="utf-8") if tasks_cands else ""

        # 픽스처가 쓰는 표 형식이 실물에서도 실제로 파싱되는가 — 검사기 자신의
        # 정규식으로 확인한다. 여기에 정규식을 베껴 두면 원본이 바뀌어도 조용하다.
        src = CHECKER.read_text(encoding="utf-8")
        m = re.search(r"^TR_ROW = re\.compile\((r?\".*\")\)$", src, re.M)
        check("검사기에서 TR_ROW 정규식을 읽어 왔다", m is not None)
        if m:
            # `literal_eval` 로 읽는다 — 원본의 정규식 리터럴을 그대로 쓰되
            # 임의 코드 실행 경로를 만들지 않는다. 여기에 정규식을 베껴 두면
            # 원본이 바뀌어도 이 검사는 계속 초록불이다.
            tr_row = re.compile(ast.literal_eval(m.group(1)))
            real_rows = sum(1 for ln in trace_real.splitlines() if tr_row.match(ln))
            fx_rows = sum(1 for ln in TRACE_CLEAN.splitlines() if tr_row.match(ln))
            check("실물 매핑표가 그 형식으로 파싱된다 (행 > 100)", real_rows > 100,
                  f"실물 {real_rows}행")
            check("픽스처도 같은 형식으로 파싱된다 (4행)", fx_rows == 4,
                  f"픽스처 {fx_rows}행")
        check("실물 작업 목록이 `- 수용기준:` 필드 관례를 쓴다",
              "- 수용기준:" in tasks_real)
        check("실물 작업 목록이 `## N.M ` 상위 작업 형식을 쓴다",
              re.search(r"^## [\d.]+ ", tasks_real, re.M) is not None)

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("전건 통과 — 인용 검사 4종이 실제로 잡고, 경고는 차단으로 올라가지 않는다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
