"""게이트 ③(`check_commit_order.py`)의 감지 능력 확인 — 음성 1 + 양성 2 + 경계 2.

**검사기가 통과했다는 사실만으로는 그것이 무언가를 검사한다는 증거가 되지
않는다.** 이 저장소는 그 간극을 여러 번 만났고(파일 규모 검사가 자기 파일 두 개만
보던 상태 · 매핑 게이트가 `|| true` 로 판정을 버리던 상태), 그래서 게이트를 켠
이상 게이트 자신도 검사한다 (§13.0.1 ④).

**이 게이트에서 그 확인이 특히 필요하다.** 게이트 ③은 위반에도 **종료 코드 0** 을
낸다(조항이 *"차단 아님"* 이라고 못 박는다). 종료 코드로는 *"위반을 잡았다"* 와
*"아무것도 못 잡았다"* 가 **구별되지 않으므로**, 여기서는 **출력을 본다.**

**실물 소스를 변이시키지 않는다.** 다른 음성 스위트는 spec 을 치환해 임시 사본을
만들지만, 순서는 **커밋 이력**에만 있다 — 파일 내용으로는 심을 수 없다. 그래서
임시 디렉터리에 **진짜 git 저장소**를 만들고 커밋을 실제 순서대로 쌓는다.

    음성 1  구현 → 테스트 순서로 커밋  → 위반으로 잡아야 한다
    양성 1  테스트 → 구현 순서로 커밋  → 잡으면 안 된다
    양성 2  한 커밋에 구현·테스트 함께  → 잡으면 안 된다 (순서가 없다)
    경계 1  커밋이 하나뿐              → 종료 코드 2 (통과가 아니다)
    경계 2  기준 ref 가 없다           → 종료 코드 2

양성 둘을 함께 두는 이유: 순서 판정은 **뒤집혀도 위반 0건일 때 통과와 구별되지
않는다**(`git log` 의 기본이 최신순이라 실제로 일어날 수 있는 오류다). 음성만
보면 「전부 위반으로 낸다」도 합격하고, 그러면 전부가 경고이므로 아무도 읽지
않는다.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_commit_order.py"

IMPL = "core/der/pv.py"
TEST = "tests/der/test_pv.py"

IMPL_SOURCE = '''"""임시 저장소의 구현 파일."""


class PV:
    tag = "PV"

    def capex(self) -> int:
        return 1
'''

TEST_SOURCE = '''"""임시 저장소의 대응 테스트."""

import core.der.pv


def test_tag() -> None:
    assert core.der.pv.PV.tag == "PV"
'''


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def init_repo(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    git(root, "branch", "base")


def write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def commit(root: Path, message: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


def run(root: Path, base: str = "base") -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--base", base, "--root", str(root)],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def fail(case: str, why: str, out: str) -> None:
    print(f"FAILED [{case}]: {why}")
    print("─" * 60)
    print(out)
    sys.exit(1)


def require_pair_was_judged(case: str, out: str) -> None:
    """짝이 실제로 잡혔는지 먼저 단언한다 — **심기가 고장난 것을 가려내는 자리다.**

    게이트 ②가 짝을 못 찾으면 판정 대상이 0건이 되고, 이 검사는 그때도 종료
    코드 0 을 낸다. 그러면 *"위반을 못 잡았다"* 와 *"잡을 것이 애초에 없었다"*
    가 구별되지 않는다 — 심지 않은 것을 통과로 읽는 형태이며 이 저장소가
    반복해서 세는 결함이다.
    """
    if "구현↔테스트 짝 1건" not in out:
        fail(case, "짝이 1건으로 잡히지 않았다 — 검사기가 아니라 심기가 고장났다", out)


def case_violation_is_detected(root: Path) -> None:
    """음성 1 — 구현을 먼저, 테스트를 나중에 커밋한다."""
    init_repo(root)
    write(root, IMPL, IMPL_SOURCE)
    commit(root, "구현 먼저")
    write(root, TEST, TEST_SOURCE)
    commit(root, "테스트 나중")

    code, out = run(root)
    print("음성 1 — 구현 → 테스트 순서로 심었다")
    require_pair_was_judged("음성 1", out)
    if code != 0:
        fail("음성 1", f"위반은 경고여야 하는데 종료 코드 {code} 다 (조항: 차단 아님)", out)
    if "::warning::" not in out or "나중에 커밋된 짝 1건" not in out:
        fail("음성 1", "구현이 테스트보다 먼저 커밋된 것을 잡지 못했다", out)
    if IMPL not in out:
        fail("음성 1", f"경고에 위반 경로({IMPL})가 없다", out)
    print(f"  잡았다 — 종료 코드 {code}(경고) · 위반 1건 · {IMPL}")


def case_correct_order_is_not_flagged(root: Path) -> None:
    """양성 1 — 테스트를 먼저, 구현을 나중에 커밋한다."""
    init_repo(root)
    write(root, TEST, TEST_SOURCE)
    commit(root, "실패하는 테스트 먼저")
    write(root, IMPL, IMPL_SOURCE)
    commit(root, "구현 나중")

    code, out = run(root)
    print("양성 1 — 테스트 → 구현 순서로 심었다")
    require_pair_was_judged("양성 1", out)
    if code != 0:
        fail("양성 1", f"정상 순서인데 종료 코드 {code} 다", out)
    if "::warning::" in out:
        fail("양성 1", "정상 순서(TDD)를 위반으로 냈다 — 판정이 뒤집혀 있다", out)
    print(f"  오판하지 않았다 — 종료 코드 {code} · 경고 없음")


def case_one_commit_holding_both_is_not_flagged(root: Path) -> None:
    """양성 2 — 한 커밋이 구현과 테스트를 함께 담는다."""
    init_repo(root)
    write(root, IMPL, IMPL_SOURCE)
    write(root, TEST, TEST_SOURCE)
    commit(root, "구현과 테스트를 함께")
    (root / "README.md").write_text("y\n", encoding="utf-8")
    commit(root, "두 번째 커밋 — 범위를 판정 가능하게 만든다")

    code, out = run(root)
    print("양성 2 — 한 커밋에 구현·테스트를 함께 심었다")
    require_pair_was_judged("양성 2", out)
    if code != 0:
        fail("양성 2", f"종료 코드 {code} 다", out)
    if "::warning::" in out:
        fail("양성 2", "한 커밋 안에는 순서가 없는데 위반으로 냈다 — "
                       "이 저장소의 라운드가 실제로 이렇게 커밋한다", out)
    print(f"  오판하지 않았다 — 종료 코드 {code} · 경고 없음")


def case_single_commit_cannot_be_judged(root: Path) -> None:
    """경계 1 — 커밋이 하나뿐이면 미판정이지 통과가 아니다."""
    init_repo(root)
    write(root, IMPL, IMPL_SOURCE)
    write(root, TEST, TEST_SOURCE)
    commit(root, "커밋 하나뿐")

    code, out = run(root)
    print("경계 1 — 범위에 커밋이 하나뿐이다")
    if code != 2:
        fail("경계 1", f"종료 코드 {code} 다 — 0 이면 미판정이 통과로 읽힌다", out)
    if "판정할 수 없습니다" not in out:
        fail("경계 1", "미판정이라고 말하지 않는다", out)
    print(f"  종료 코드 {code} — 미판정을 통과로 읽지 않는다")


def case_missing_base_ref_cannot_be_judged(root: Path) -> None:
    """경계 2 — 기준 ref 가 없으면 미판정이다(얕은 클론에서 실제로 일어난다)."""
    init_repo(root)
    write(root, IMPL, IMPL_SOURCE)
    commit(root, "구현")
    write(root, TEST, TEST_SOURCE)
    commit(root, "테스트")

    code, out = run(root, base="origin/does-not-exist")
    print("경계 2 — 기준 ref 가 없다")
    if code != 2:
        fail("경계 2", f"종료 코드 {code} 다 — 0 이면 게이트가 조용히 무력화된다", out)
    print(f"  종료 코드 {code} — 기준 ref 부재를 통과로 읽지 않는다")


def main() -> None:
    cases = (
        case_violation_is_detected,
        case_correct_order_is_not_flagged,
        case_one_commit_holding_both_is_not_flagged,
        case_single_commit_cannot_be_judged,
        case_missing_base_ref_cannot_be_judged,
    )
    for case in cases:
        with tempfile.TemporaryDirectory() as directory:
            case(Path(directory))

    print()
    print("음성 1 + 양성 2 + 경계 2 통과 — 게이트 ③은 커밋 순서 위반을 실제로 "
          "잡고, 정상 순서와 한 커밋 동봉을 오판하지 않으며, 판정할 수 없는 "
          "형편을 통과로 읽지 않는다")


if __name__ == "__main__":
    main()
