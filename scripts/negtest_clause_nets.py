#!/usr/bin/env python3
"""그물 ③-1·③-2 음성 테스트 — **두 그물이 실제로 잡는가.**

## 왜 한 파일에 둘을 담는가

`negtest_*` 는 검사기 하나에 하나가 원칙이나, 이 둘은 **같은 수집기
(`_citations.py`)를 쓰고 같은 합성 픽스처를 먹는다.** 갈라 놓으면 픽스처
빌더가 두 벌이 되고, 그 두 벌이 갈리는 날 「어느 쪽 그물이 무엇을 봤는가」를
말할 수 없다 — 이 저장소가 반복해 적은 *「같은 사실은 한 곳이 소유한다」* 다.
검사기 이름은 갈래 이름에 적어 어느 것을 재는지 드러낸다.

## 실물을 변이시키지 않는다

`negtest_docstring_references.py`·`negtest_marker_substance.py` 는 검사기가
CLI 인자를 받지 않아 **실물 파일을 잠깐 변이**시킨다. 그 방식은 스위트를
중단시키면 `.mutbak` 이 남는다(R44 · WP-10 이 실측했다). 두 그물은 처음부터
`--spec`·`--tests` 를 받도록 지었으므로 **합성 픽스처만으로 전 갈래를 잰다** —
실물 파일을 건드리지 않고, 중단해도 남는 것이 없다.

## 붙드는 것 열넷

| 갈래 | 검사기 | 무엇을 잡는가 |
|---|---|---|
| ① | ③-1 | 양성 기준선 — 실물 저장소 그대로 `rc=0` (실측이 부채 대장과 같다) |
| ② | ③-1 | 구획을 명시한 조항의 인용이 그 구획을 안 만지면 `rc=1` |
| ③ | ③-1 | **문자열 리터럴은 import 가 아니다** — `"core.engine"` 만 담아도 `rc=1` |
| ④ | ③-1 | 실제로 import 하는 인용이 하나라도 있으면 `rc=0` (오탐 방지) |
| ⑤ | ③-1 | 하위 모듈 import(`core.report.case_report`)도 그 구획을 만진 것이다 |
| ⑥ | ③-1 | 사전에 없는 낱말(은유·다른 구획)은 판정 대상이 아니다 → `rc=2` |
| ⑦ | ③-1 | 인용이 0건인 조항은 지목하지 않는다 (미매핑은 다른 게이트 소관) |
| ⑧ | ③-1 | 부채 대장 래칫 — 새 결손과 사라진 항목을 **양쪽 다** 보고하고 `rc=1` |
| ⑨ | ③-2 | 인용 전부가 다른 조항만 적으면 후보로 오른다 |
| ⑩ | ③-2 | **데코레이터의 마커 문자열을 「적었다」로 세지 않는다** |
| ⑪ | ③-2 | 인용 하나라도 자기 조항을 적으면 안 오른다 |
| ⑫ | ③-2 | 전개 부모(`FR-901-AC1` ↔ `FR-901-AC1.PV`)는 「다른 조항」이 아니다 |
| ⑬ | ③-2 | 후보가 있어도 `rc=0` — **차단으로 오르지 않는다** |
| ⑭ | 공통 | 인용 수집이 정본(`gen_traceability.collect_test_markers`)과 일치한다 |

⑩ 이 이 스위트의 핵심이다. `@pytest.mark.req("FR-901-AC1")` 의 인자는
`ast.walk(함수노드)` 에 딸려 오므로, 그것을 문면으로 세면 **모든 인용이 자기
조항을 적은 것이 되어 그물 ③-2 가 통째로 잠든다**(실측: 인용 있는 조항 294건
전부가 「자기 이름을 적음」이 되고 후보가 0건이 된다). ⑩ 이 없으면 그 회귀가
초록불로 지나간다.

사용:
    python scripts/negtest_clause_nets.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PARTITION = REPO / "scripts" / "check_clause_partition.py"
SELFREF = REPO / "scripts" / "audit_clause_selfreference.py"

FAILURES: list[str] = []

#: 합성 spec 의 뼈대. `_specparse.parse_spec` 이 결함 없이 읽으려면 §9 보안 표에
#: SC 행이 **하나 이상** 있어야 한다 — 없으면 그 파서가 「검사를 수행하지 못한
#: 것을 통과로 읽지 않습니다」로 결함을 낸다(§13.0.1 ④). 그 요구를 여기서
#: 우회하지 않고 그대로 만족시킨다.
SPEC_TAIL = """
## 9. Security and Compliance

| ID | 항목 | 우선순위 | Phase | 요구사항 |
|---|---|---|---|---|
| SC-1 | 인증 | **Must-have** | 1 | 시험용 행 |
"""


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}")
        for line in detail.splitlines()[:14]:
            print(f"       {line}")
        FAILURES.append(name)


def write_spec(root: Path, criteria: list[tuple[str, str, str]]) -> Path:
    """`(요구사항 ID, 수용기준 키, 문면)` 목록으로 합성 spec 을 짓는다."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for req, key, text in criteria:
        grouped.setdefault(req, []).append((key, text))
    lines = ["# 시험용 spec", "", "## 1. 본문", ""]
    for req, items in grouped.items():
        lines += [
            f"- **{req}** (Phase 1) 시험용 요구사항.",
            "  - Priority: **Must-have** (Phase 1)",
            "  - Acceptance Criteria:",
        ]
        lines += [f"    - **{key}** {text}" for key, text in items]
    spec = root / "spec.md"
    spec.write_text("\n".join(lines) + "\n" + SPEC_TAIL, encoding="utf-8")
    return spec


def write_test(root: Path, name: str, body: str) -> Path:
    tests = root / "tests"
    tests.mkdir(exist_ok=True)
    path = tests / name
    path.write_text(body, encoding="utf-8")
    return path


def run(script: Path, *args: str) -> tuple[int, str]:
    """검사기를 돌리고 `(종료코드, 출력)`. **파이프를 걸지 않는다.**"""
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO),
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def case_engine(imports: str, extra: str = "") -> str:
    return f'''"""시험용 테스트 파일."""
import pytest
{imports}


@pytest.mark.req("FR-901-AC1")
def test_engine_clause() -> None:
    """무엇을 재는지 여기 적는다."""
    {extra}
    assert True
'''


def net_partition(tmp: Path) -> None:
    print("\n③-1 `check_clause_partition.py` — 조항이 지목한 구획을 인용이 만지는가")

    # ② 구획을 명시한 조항인데 아무도 그 구획을 만지지 않는다
    root = tmp / "gap"
    root.mkdir()
    spec = write_spec(root, [("FR-901", "AC1", "코어 엔진 수정 없이 새 자원이 동작한다")])
    write_test(root, "test_a.py", case_engine("from core.der.pv import PV"))
    rc, out = run(PARTITION, "--spec", str(spec), "--tests", str(root / "tests"),
                  "--ledger", "off")
    check("② 만지는 인용이 없으면 rc=1", rc == 1, f"rc={rc}\n{out}")
    check("② 결손 자리를 조항·구획으로 낸다",
          "FR-901-AC1" in out and "core.engine" in out, out)

    # ③ 문자열 리터럴은 import 가 아니다 — R38 이 본 결함의 형태 그대로다
    root = tmp / "literal"
    root.mkdir()
    spec = write_spec(root, [("FR-901", "AC1", "코어 엔진 수정 없이 새 자원이 동작한다")])
    write_test(root, "test_a.py",
               case_engine("from core.der.pv import PV",
                           extra='forbidden = ["core.engine", "core.cba"]'))
    rc, out = run(PARTITION, "--spec", str(spec), "--tests", str(root / "tests"),
                  "--ledger", "off")
    check("③ 문자열로만 담은 구획은 「만졌다」가 아니다 (rc=1)", rc == 1, f"rc={rc}\n{out}")

    # ④ 실제로 import 하면 초록불이다
    root = tmp / "touch"
    root.mkdir()
    spec = write_spec(root, [("FR-901", "AC1", "코어 엔진 수정 없이 새 자원이 동작한다")])
    write_test(root, "test_a.py", case_engine("from core.der.pv import PV"))
    write_test(root, "test_b.py", '''"""시험용."""
import pytest
from core.engine.rule_based import RuleBasedEngine


@pytest.mark.req("FR-901-AC1")
def test_runs_engine() -> None:
    assert RuleBasedEngine is not None
''')
    rc, out = run(PARTITION, "--spec", str(spec), "--tests", str(root / "tests"),
                  "--ledger", "off")
    check("④ 인용 하나라도 그 구획을 import 하면 rc=0", rc == 0, f"rc={rc}\n{out}")

    # ⑤ 하위 모듈도 그 구획이다
    root = tmp / "submodule"
    root.mkdir()
    spec = write_spec(root, [("FR-901", "AC1", "결과를 리포트에 표시한다")])
    write_test(root, "test_a.py", '''"""시험용."""
import pytest
from core.report.case_report import build_case_report


@pytest.mark.req("FR-901-AC1")
def test_report() -> None:
    assert build_case_report is not None
''')
    rc, out = run(PARTITION, "--spec", str(spec), "--tests", str(root / "tests"),
                  "--ledger", "off")
    check("⑤ 구획 하위 모듈 import 도 「만졌다」다 (rc=0)", rc == 0, f"rc={rc}\n{out}")

    # ⑥ 사전에 없는 낱말은 판정 대상이 아니다 — 사전을 좁게 둔 결과다
    root = tmp / "outside"
    root.mkdir()
    spec = write_spec(root, [("FR-901", "AC1", "데이터셋 해상도를 15분으로 고정한다")])
    write_test(root, "test_a.py", case_engine("from core.der.pv import PV"))
    rc, out = run(PARTITION, "--spec", str(spec), "--tests", str(root / "tests"),
                  "--ledger", "off")
    check("⑥ 구획을 명시한 조항이 0건이면 rc=2 (검사 미수행)", rc == 2, f"rc={rc}\n{out}")

    # ⑦ 인용이 0건인 조항은 지목하지 않는다
    root = tmp / "uncited"
    root.mkdir()
    spec = write_spec(root, [
        ("FR-901", "AC1", "코어 엔진 수정 없이 새 자원이 동작한다"),
        ("FR-901", "AC2", "결과를 리포트에 표시한다"),
    ])
    write_test(root, "test_a.py", '''"""시험용."""
import pytest
from core.engine.rule_based import RuleBasedEngine


@pytest.mark.req("FR-901-AC1")
def test_runs_engine() -> None:
    assert RuleBasedEngine is not None
''')
    rc, out = run(PARTITION, "--spec", str(spec), "--tests", str(root / "tests"),
                  "--ledger", "off")
    check("⑦ 인용 0건인 FR-901-AC2 는 결손으로 세지 않는다 (rc=0)",
          rc == 0 and "FR-901-AC2" not in out, f"rc={rc}\n{out}")

    # ⑧ 부채 대장 래칫 — 합성 입력이면 대장 항목이 전부 「실측되지 않음」이 된다
    root = tmp / "ledger"
    root.mkdir()
    spec = write_spec(root, [("FR-901", "AC1", "코어 엔진 수정 없이 새 자원이 동작한다")])
    write_test(root, "test_a.py", case_engine("from core.der.pv import PV"))
    rc, out = run(PARTITION, "--spec", str(spec), "--tests", str(root / "tests"))
    check("⑧ 대장 래칫이 양쪽을 다 보고하고 rc=1",
          rc == 1 and "대장에 없는 결손" in out and "실측되지 않은 항목" in out,
          f"rc={rc}\n{out}")


def net_selfreference(tmp: Path) -> None:
    print("\n③-2 `audit_clause_selfreference.py` — 인용 전부가 다른 조항만 적는가")

    # ⑨⑩ 다른 조항만 적는다. 데코레이터의 마커는 「적었다」가 아니다
    root = tmp / "sr_flag"
    root.mkdir()
    write_test(root, "test_a.py", '''"""시험용."""
import pytest


@pytest.mark.req("FR-901-AC1")
def test_one() -> None:
    """이 검사는 NFR-208-AC1 을 잰다."""
    assert True


@pytest.mark.req("FR-901-AC1")
def test_two() -> None:
    assert True, "NFR-208-AC1 위반"
''')
    rc, out = run(SELFREF, "--tests", str(root / "tests"))
    check("⑨ 인용 전부가 다른 조항만 적으면 후보로 오른다",
          "후보 FR-901-AC1" in out, out)
    check("⑩ 데코레이터의 마커 문자열은 「적었다」로 세지 않는다",
          "후보 FR-901-AC1" in out, out)
    # 왼쪽 경계가 없으면 `NFR-208-AC1` 의 두 번째 글자에서 `FR-208-AC1` 이 한 번
    # 더 걸려 「적힌 조항」이 둘이 된다. 이 저장소가 반복해 밟은 함정이다.
    line = next((ln for ln in out.splitlines() if "후보 FR-901-AC1" in ln), "")
    check("⑩ 왼쪽 경계 — NFR-208-AC1 을 FR-208-AC1 로 흘리지 않는다",
          line.endswith("적힌 조항: NFR-208-AC1"), f"{line!r}")
    check("⑬ 후보가 있어도 rc=0 (차단이 아니다)", rc == 0, f"rc={rc}\n{out}")

    # ⑪ 자기 조항을 적은 인용이 하나라도 있으면 안 오른다
    root = tmp / "sr_self"
    root.mkdir()
    write_test(root, "test_a.py", '''"""시험용."""
import pytest


@pytest.mark.req("FR-901-AC1")
def test_one() -> None:
    """이 검사는 NFR-208-AC1 을 잰다."""
    assert True


@pytest.mark.req("FR-901-AC1")
def test_two() -> None:
    """FR-901-AC1 을 잰다."""
    assert True
''')
    rc, out = run(SELFREF, "--tests", str(root / "tests"))
    check("⑪ 자기 조항을 적은 인용이 있으면 후보가 아니다",
          rc == 0 and "  후보 " not in out, f"rc={rc}\n{out}")

    # ⑫ 전개 부모·자식은 「다른 조항」이 아니다
    root = tmp / "sr_kin"
    root.mkdir()
    write_test(root, "test_a.py", '''"""시험용."""
import pytest


@pytest.mark.req("FR-901-AC1.PV")
def test_one() -> None:
    """표 전개 전 이름은 FR-901-AC1 이다."""
    assert True
''')
    rc, out = run(SELFREF, "--tests", str(root / "tests"))
    check("⑫ 전개 부모를 적은 것은 자기 조항을 적은 것이다",
          rc == 0 and "  후보 " not in out, f"rc={rc}\n{out}")


def shared_collector() -> None:
    print("\n공통 `_citations.py` — 정본과 같은 것을 보는가")
    sys.path.insert(0, str(REPO / "scripts"))
    import _citations  # noqa: PLC0415
    from gen_traceability import collect_test_markers  # noqa: PLC0415

    official, official_defects = collect_test_markers(REPO / "tests")
    mine, my_defects = _citations.collect(REPO / "tests")
    grouped = _citations.by_clause(mine)

    check("⑭ 파싱 결함이 양쪽 다 없다",
          official_defects == my_defects == [],
          f"정본 {official_defects} / 이 모듈 {my_defects}")
    check("⑭ 인용된 조항 집합이 정본과 같다",
          set(grouped) == set(official),
          f"이 모듈만: {sorted(set(grouped) - set(official))}\n"
          f"정본만:   {sorted(set(official) - set(grouped))}")
    mismatched = {
        cid: (len(grouped[cid]), len(official[cid]))
        for cid in grouped
        if len(grouped[cid]) != len(official[cid])
    }
    check("⑭ 조항별 인용 건수가 정본과 같다", not mismatched, str(mismatched))


def main() -> int:
    print("그물 ③-1·③-2 음성 테스트 — 두 그물이 실제로 잡는가")

    print("\n① 양성 기준선 (실물 저장소 그대로)")
    rc, out = run(PARTITION)
    check("① ③-1 이 실물에서 rc=0 이다", rc == 0, f"rc={rc}\n{out}")
    check("① 실측이 부채 대장과 같다고 말한다", "부채 대장과 같다" in out, out)

    tmp = Path(tempfile.mkdtemp(prefix="negtest_clause_"))
    try:
        net_partition(tmp)
        net_selfreference(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    shared_collector()

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전건 통과 — 두 그물이 잡아야 할 것을 잡고 잡으면 안 될 것을 안 잡는다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
