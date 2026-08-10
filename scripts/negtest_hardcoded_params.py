"""`check_hardcoded_params.py` 음성·양성 테스트 — 작업 2.9 / §13.0.1 ④.

**이 검사는 지금 「차단 0건」으로 통과한다. 그 통과가 무엇을 뜻하는지 스스로는
말하지 못한다** — 전제값이 복제되지 않았다는 뜻일 수도, 검사가 아무것도 보지
않는다는 뜻일 수도 있다. 특히 위험한 조합이 둘 있다.

    ① 문턱이 너무 높다        `MONEY_FLOOR` 를 올리면 진짜 복제가 경고로
                              내려가고, 경고는 종료 코드 0 이다.
    ② 제외가 너무 넓다        `UBIQUITOUS`·`JUDGE_FLOOR` 를 넓히면 대장 값이
                              통째로 판정 대상에서 빠진다.

둘 다 **초록불로 나타난다.** 그래서 심어 둔 위반을 잡는지와, 정당한 코드를
오판하지 않는지를 함께 본다.

실행: `python scripts/negtest_hardcoded_params.py`
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_hardcoded_params.py"

#: 대장에 실재하는 원 단위 값 하나. 여기에 값을 새로 지어내면 대장이 바뀔 때
#: 이 테스트가 조용히 아무것도 검사하지 않게 된다.
PLANTED_MONEY = 1_600_000        # capex.pv.rooftop
PLANTED_NON_MONEY = 3_600        # load.household.annual (kWh) — 경고 대역
PLANTED_BELOW_FLOOR = 15         # capex.modular_house.premium (%) — 판정 안 함


def _module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("_check_hardcoded", CHECKER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_check_hardcoded"] = mod
    spec.loader.exec_module(mod)
    return mod


def _fixture(body: str, *, ledger: bool = True) -> Path:
    """저장소를 흉내 낸 임시 트리. 대장은 진짜를 복사한다 —
    가짜 대장을 지어내면 검사가 실제 값에 대해 동작하는지 알 수 없다.
    """
    root = Path(tempfile.mkdtemp(prefix="negtest-params-"))
    (root / "core" / "der").mkdir(parents=True)
    (root / "core" / "__init__.py").write_text("", encoding="utf-8")
    (root / "core" / "der" / "__init__.py").write_text("", encoding="utf-8")
    (root / "core" / "der" / "sample.py").write_text(body, encoding="utf-8")
    if ledger:
        (root / "docs").mkdir()
        shutil.copy(REPO_ROOT / "docs" / "assumptions.yaml", root / "docs")
    return root


def _run(root: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    return result.returncode, result.stdout + result.stderr


CASES: list[tuple[str, str, bool, str]] = [
    # (이름, 소스, 차단되어야 하는가, 출력에 있어야 하는 문자열)
    (
        "음성1 설비단가를 소스에 옮겨 적음",
        f"CAPEX_PV_WON_PER_KW = {PLANTED_MONEY}\n",
        True, "capex.pv.rooftop",
    ),
    (
        "음성2 민감도 상한값을 옮겨 적음",
        "CAPEX_PV_HIGH = 1_920_000\n",
        True, "capex.pv.rooftop.high",
    ),
    (
        "음성3 함수 기본값으로 숨김",
        f"def make(*, capex: int = {PLANTED_MONEY}) -> int:\n    return capex\n",
        True, "capex.pv.rooftop",
    ),
    (
        "음성4 주석이 아니라 코드에 있으면 잡는다",
        f"# 단가는 {PLANTED_MONEY} 원이다 — 이 줄은 서술이다\nVALUE = {PLANTED_MONEY}\n",
        True, "capex.pv.rooftop",
    ),
    (
        "음성5 모듈 수준 가변 dict",
        "TABLE = {'a': 1}\n",
        True, "TABLE",
    ),
    (
        "음성6 클래스 수준 가변 list",
        "class C:\n    ITEMS = [1, 2]\n",
        True, "ITEMS",
    ),
    (
        "음성7 dict() 호출도 가변이다",
        "REGISTRY = dict()\n",
        True, "REGISTRY",
    ),
    (
        "양성1 물리·시간 상수는 차단하지 않는다",
        "SECONDS_PER_HOUR = 3600\nHOURS_PER_YEAR = 8760\n",
        False, "",
    ),
    (
        "양성2 불변 컨테이너는 전역 상태가 아니다",
        "WINDOWS = ((1, 2), (3, 4))\nNAMES = frozenset({'a'})\n",
        False, "",
    ),
    (
        "양성3 함수 안의 dict 는 전역이 아니다",
        "def f():\n    cache = {}\n    return cache\n",
        False, "",
    ),
    (
        "양성4 서술에만 나오는 단가는 위반이 아니다",
        f'"""설치단가는 {PLANTED_MONEY} 원/kW 로 가정했다."""\n'
        f"# 민감도 상한 1_920_000 도 서술이다\nVALUE = 1\n",
        False, "",
    ),
    (
        "경고1 비금액 대장값은 차단이 아니라 경고로 나온다",
        f"LOAD_ANNUAL = {PLANTED_NON_MONEY}\n",
        False, "load.household.annual",
    ),
]


def main() -> int:
    print("check_hardcoded_params 음성·양성 테스트 (작업 2.9)")
    print("─" * 74)

    failures = 0
    for name, body, should_block, expect in CASES:
        root = _fixture(body)
        try:
            code, out = _run(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

        blocked = code == 1
        ok = blocked == should_block and (not expect or expect in out)
        failures += not ok
        mark = "통과" if ok else "**실패**"
        print(f"  {mark:6s} {name}  (종료 {code})")
        if not ok:
            print(f"         기대: 차단={should_block} / 포함={expect!r}")
            for line in out.splitlines()[:12]:
                print(f"         | {line}")

    # 검사가 성립하지 않는 경우 — 통과로 읽으면 안 된다
    root = _fixture("VALUE = 1\n", ledger=False)
    try:
        code, _ = _run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    ok = code == 2
    failures += not ok
    print(f"  {'통과' if ok else '**실패**':6s} 경계1 대장이 없으면 종료 코드 2  (종료 {code})")

    empty = Path(tempfile.mkdtemp(prefix="negtest-params-empty-"))
    (empty / "docs").mkdir()
    shutil.copy(REPO_ROOT / "docs" / "assumptions.yaml", empty / "docs")
    try:
        code, _ = _run(empty)
    finally:
        shutil.rmtree(empty, ignore_errors=True)
    ok = code == 2
    failures += not ok
    print(f"  {'통과' if ok else '**실패**':6s} 경계2 대상 파일 0개면 종료 코드 2  (종료 {code})")

    # 문턱이 조용히 넓어지는 것을 막는다. 값을 올리면 진짜 복제가 경고로
    # 내려가고, 경고는 종료 코드 0 이다 — 초록불로 나타나는 후퇴다.
    mod = _module()
    guards = [
        ("MONEY_FLOOR", mod.MONEY_FLOOR, 10_000),
        ("JUDGE_FLOOR", mod.JUDGE_FLOOR, 1_000),
    ]
    for label, actual, expected in guards:
        ok = actual == expected
        failures += not ok
        mark = "통과" if ok else "**실패**"
        print(f"  {mark:6s} 경계3 {label} = {expected:,} 고정  (실제 {actual:,})")
    ok = {0, 1, -1} == mod.UBIQUITOUS
    failures += not ok
    print(f"  {'통과' if ok else '**실패**':6s} 경계4 UBIQUITOUS 면제가 넓어지지 않았다")

    # 문턱 아래 값(`|값| < JUDGE_FLOOR`)이 어떻게 처리되는지 **동작으로**
    # 고정한다. 경계3은 그 상수의 *값*이 바뀌지 않았는지만 보지 *동작*은
    # 보지 않는다 — 문턱이 무력해져도 경계3은 통과한다.
    #
    # **「출력에 아예 없다」가 아니다.** 검사는 이 대역을 「판정하지 않은
    # 대장 수치」로 **이름을 붙여 내놓고**, 그 절에 *"검사가 보지 않은
    # 범위이며, 깨끗하다는 뜻이 아닙니다"* 라고 적는다. 그래서 옳은 판정은
    # 둘이다 — **차단·경고 절에는 없고, 미판정 절에는 있다.**
    # 뒤쪽이 더 값나간다: 그 값을 **보고서 건너뛴 것**임을 고정하기 때문에,
    # 검사가 아예 읽지 못하게 되는 후퇴도 함께 잡는다.
    #
    # (초판은 `f"{PLANTED_BELOW_FLOOR} ←"` 즉 **출력 서식**으로 없음을
    # 확인했다. 그러면 검사가 아니라 서식을 고정하게 되고, 서식이 바뀌는
    # 날 아무것도 검사하지 않으면서 조용히 통과한다.)
    LEDGER_KEY = "capex.modular_house.premium"
    SKIPPED_HEADING = "판정하지 않은 대장 수치"
    root = _fixture(f"VALUE = {PLANTED_BELOW_FLOOR}\n")
    try:
        code, out = _run(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    judged, _, skipped = out.partition(SKIPPED_HEADING)
    ok = (code == 0
          and SKIPPED_HEADING in out          # 절 자체가 사라지지 않았다
          and LEDGER_KEY not in judged        # 차단·경고로는 잡히지 않는다
          and LEDGER_KEY in skipped)          # 그러나 보고서 건너뛴 것이다
    failures += not ok
    print(
        f"  {'통과' if ok else '**실패**':6s} "
        f"경계5 문턱 아래 값은 차단·경고가 아니라 미판정으로 내놓는다  (종료 {code})"
    )

    print("─" * 74)
    total = len(CASES) + 6
    print(f"음성 7 + 경고 1 + 양성 4 + 경계 6 — 통과 {total - failures} / 실패 {failures}")
    if failures:
        print("\n**검사가 기대대로 동작하지 않습니다.** 문턱·제외 범위를 넓히면")
        print("진짜 복제가 경고로 내려가고, 경고는 종료 코드 0 입니다.")
        return 1
    print("전건 기대대로 — 이 검사는 무언가를 검사한다")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
