"""NFR-105 CI 게이트 검증 — 작업 2.5·2.6.

**왜 게이트에 테스트가 붙는가.** 게이트는 그것이 실제로 무언가를 막을 때만
게이트다. 스크립트가 저장소에 있다는 사실과 CI 가 그것을 부른다는 사실은 다르고,
CI 가 부른다는 사실과 그것이 결함을 잡는다는 사실도 다르다. 이 저장소는 그 간극을
세 번 만났다 —

    · CODEOWNERS 에 없는 팀명을 적어 그 줄이 **조용히 무시**되던 상태
    · 매핑 게이트가 `|| true` 로 종료 코드를 버려 **결함 시 초록불**이던 상태
    · 파일 규모 검사가 **자기 파일 두 개만** 보고 있던 상태

그래서 여기서는 셋을 각각 검사한다 — ⓐ 판정 논리가 위반을 잡는가 ⓑ 정당한
변경을 오판하지 않는가 ⓒ **CI 가 실제로 그 게이트를 실행하는가.**

`NFR-105-AC1` 을 자동 매핑으로 다는 이유: 이 조항은 게이트 자신이므로
`docs/manual-checks.yaml` 에 등재하는 것이 **금지**되어 있다 (NFR-107-AC5 ⓒ).
수동 예외 경로를 정당화하는 조항이 그 경로로 "검증됨" 처리되면 아무것도 검증되지
않은 채 초록불이 뜬다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"
CHECKER = REPO_ROOT / "scripts" / "check_test_accompaniment.py"

DIFF_COVER_MIN = 95  # NFR-105 Measurement 1
TOTAL_COVER_MIN = 85  # NFR-203 (작업 2.10)


def _script(stem: str):
    """`scripts/` 는 패키지가 아니므로 경로로 불러온다.

    `sys.path` 에 `scripts/` 를 넣는 이유: 두 게이트가 기준 ref 해석을
    `_gitdiff` 로 공유하며, 스크립트로 실행할 때는 스크립트 디렉터리가 자동으로
    `sys.path` 에 들어가지만 여기서는 그렇지 않다.

    `sys.modules` 에 먼저 등록하는 것도 필수다 — `@dataclass` 는 애노테이션을
    해석할 때 `sys.modules[cls.__module__]` 를 찾고, 등록하지 않으면 그 조회가
    `None` 이 되어 클래스 정의 자체가 실패한다.
    """
    import importlib.util

    scripts = str(REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    name = f"_gate_{stem}"
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / f"{stem}.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _judge(files: dict[str, str], *, statuses: dict[str, str] | None = None):
    """`{경로: 소스}` 를 diff 로 보고 판정한다.

    실제 커밋을 만들지 않는다 — 판정 논리와 git 연결부를 가르는 것이 요점이다.
    git 연결부는 아래 `test_missing_base_ref_...` 가 따로 본다.
    """
    mod = _script("check_test_accompaniment")
    statuses = statuses or {}
    changes = [
        mod.Change(path=p, status=statuses.get(p, "M")) for p in files
    ]
    return mod.check(changes, lambda p: files[p])


# ── ⓐ 위반을 잡는다 ─────────────────────────────────────────────────

@pytest.mark.req("NFR-105-AC1")
def test_implementation_change_without_any_test_change_is_a_violation() -> None:
    violations, accompanied = _judge({
        "core/der/pv.py": "class PV:\n    tag = 'PV'\n",
    })
    assert [v.module for v in violations] == ["core.der.pv"]
    assert not accompanied


@pytest.mark.req("NFR-105-AC1")
def test_an_unrelated_test_change_does_not_count() -> None:
    """**이것이 이 게이트의 실질이다.**

    「아무 테스트나 바뀌면 통과」로 구현하면 core 파일 여섯 개를 고치고 관계없는
    테스트 한 줄을 고친 PR 이 통과한다. 게이트가 있는데 아무것도 막지 않고,
    초록불이므로 그 사실이 드러나지 않는다.
    """
    violations, accompanied = _judge({
        "core/der/pv.py": "class PV:\n    tag = 'PV'\n",
        "tests/asset/test_common_asset.py":
            "from core.asset.common_asset import CEMS\n\n\ndef test_x():\n    assert CEMS\n",
    })
    assert [v.module for v in violations] == ["core.der.pv"]
    assert not accompanied


@pytest.mark.req("NFR-105-AC1")
def test_only_one_of_several_implementation_changes_being_accompanied_fails() -> None:
    """한 건이 동반되었다고 나머지가 면제되지 않는다."""
    violations, accompanied = _judge({
        "core/der/pv.py": "class PV:\n    tag = 'PV'\n",
        "core/der/ess.py": "class ESS:\n    tag = 'ESS'\n",
        "tests/der/test_pv.py":
            "from core.der.pv import PV\n\n\ndef test_x():\n    assert PV\n",
    })
    assert [v.module for v in violations] == ["core.der.ess"]
    assert [a.module for a in accompanied] == ["core.der.pv"]


@pytest.mark.req("NFR-105-AC1")
def test_a_mention_in_a_comment_or_docstring_is_not_a_corresponding_test() -> None:
    """서술은 선언이 아니다 — `ast` 를 쓰는 이유.

    문자열 포함으로 검사하면 *"`core.der.pv` 를 예로 들면"* 이라고 적은 주석이
    대응 테스트로 세어진다. 이 저장소가 여섯 번 걸린 유형의 **반대 방향**이며
    결과가 더 나쁘다: 서술이 선언으로 세어지면 게이트가 조용히 초록불이 된다.
    """
    violations, _ = _judge({
        "core/der/pv.py": "class PV:\n    tag = 'PV'\n",
        "tests/der/test_other.py":
            '"""core.der.pv 를 예로 들어 설명하는 문서다."""\n'
            "# import core.der.pv 도 주석이면 import 가 아니다\n"
            "def test_x():\n    assert True\n",
    })
    assert [v.module for v in violations] == ["core.der.pv"], (
        "주석·독스트링의 언급을 대응 테스트로 세고 있습니다 — 게이트가 조용히 "
        "초록불이 되는 방향의 오판입니다"
    )


@pytest.mark.req("NFR-105-AC1")
def test_deleting_a_test_does_not_count_as_accompaniment() -> None:
    """테스트를 지워서 게이트를 통과하는 경로를 막는다."""
    violations, _ = _judge(
        {
            "core/der/pv.py": "class PV:\n    tag = 'PV'\n",
            "tests/der/test_pv.py": "",
        },
        statuses={"tests/der/test_pv.py": "D"},
    )
    assert [v.module for v in violations] == ["core.der.pv"]


@pytest.mark.req("NFR-105-AC1")
def test_importing_core_itself_does_not_cover_everything() -> None:
    """`import core` 한 줄로 저장소 전체가 포섭되면 게이트가 사라진다."""
    violations, _ = _judge({
        "core/der/pv.py": "class PV:\n    tag = 'PV'\n",
        "tests/der/test_other.py":
            "import core\n\n\ndef test_x():\n    assert core\n",
    })
    assert [v.module for v in violations] == ["core.der.pv"]


# ── ⓑ 정당한 변경을 오판하지 않는다 ─────────────────────────────────

@pytest.mark.req("NFR-105-AC1")
def test_direct_import_counts() -> None:
    violations, accompanied = _judge({
        "core/der/pv.py": "class PV:\n    tag = 'PV'\n",
        "tests/der/test_pv.py":
            "from core.der.pv import PV\n\n\ndef test_x():\n    assert PV\n",
    })
    assert not violations
    assert accompanied[0].how == "import core.der.pv"


@pytest.mark.req("NFR-105-AC1")
def test_naming_convention_counts_even_without_an_import() -> None:
    """규약만 인정하면 계약 변경이 막히고, 규약을 버리면 이 경로가 사라진다.

    `tests/der/test_pv.py` 가 픽스처를 거쳐 간접적으로만 자원을 쓰는 경우가
    실제로 있다. 두 경로를 모두 인정하는 이유다.
    """
    violations, accompanied = _judge({
        "core/der/pv.py": "class PV:\n    tag = 'PV'\n",
        "tests/der/test_pv.py": "def test_x():\n    assert True\n",
    })
    assert not violations
    assert "파일명 규약" in accompanied[0].how


@pytest.mark.req("NFR-105-AC1")
def test_package_import_covers_its_modules_and_says_so() -> None:
    """레지스트리 순회 테스트(NFR-106)는 `core.der` 만 import한다.

    의도된 느슨함이므로 **보고에 그 사실을 적는다** — 느슨함이 보이지 않으면
    그것에 기대는 PR 이 늘어난다.
    """
    violations, accompanied = _judge({
        "core/der/pv.py": "class PV:\n    tag = 'PV'\n",
        "tests/contract/test_registry.py":
            "import core.der\n\n\ndef test_x():\n    assert core.der\n",
    })
    assert not violations
    assert "상위 패키지" in accompanied[0].how


@pytest.mark.req("NFR-105-AC1")
def test_a_docstring_only_package_marker_needs_no_test() -> None:
    """조항의 주어는 *"모든 **계산 코드**"* 다.

    패키지 표식의 독스트링을 고쳤다고 테스트를 요구하면 그 요구가 정당하지
    않고, 정당하지 않은 요구는 게이트를 꺼지게 만든다. 그리고 코드가 없는
    파일에는 고칠 계산이 없다.
    """
    violations, accompanied = _judge({
        "core/der/__init__.py": '"""자원 구획 — WP-1 소유."""\n',
    })
    assert not violations
    assert not accompanied


@pytest.mark.req("NFR-105-AC1")
def test_code_in_a_package_marker_is_still_implementation() -> None:
    """반대 방향도 고정한다 — `__init__.py` 라는 이름이 면제 사유가 아니다."""
    violations, _ = _judge({
        "core/der/__init__.py": '"""자원 구획."""\n\nREGISTRY = {"PV": None}\n',
    })
    assert [v.module for v in violations] == ["core.der"]


@pytest.mark.req("NFR-105-AC1")
def test_deleting_an_implementation_file_needs_no_test() -> None:
    violations, accompanied = _judge(
        {"core/der/pv.py": ""},
        statuses={"core/der/pv.py": "D"},
    )
    assert not violations
    assert not accompanied


@pytest.mark.req("NFR-105-AC1")
def test_changes_outside_core_are_not_the_clause_subject() -> None:
    """조항 문면이 지정한 대상은 `core/` 다.

    검사가 조항보다 강하면 「조항에 없는 이유로 막혔다」는 반발이 게이트를 끈다.
    넓히려면 spec 개정(§16.5)이다.
    """
    violations, accompanied = _judge({
        "app/routers/scenario.py": "def get():\n    return 1\n",
        "scripts/check_file_size.py": "def main():\n    return 0\n",
    })
    assert not violations
    assert not accompanied


# ── ⓒ 검사를 수행하지 못한 것을 통과로 읽지 않는다 ──────────────────

@pytest.mark.req("NFR-105-AC1")
def test_missing_base_ref_exits_2_not_0(tmp_path: Path) -> None:
    """**이 검사가 게이트의 가장 조용한 구멍을 막는다.**

    얕은 클론(`fetch-depth: 1`)에서는 대상 브랜치가 로컬에 없다. 그때 기준 ref
    를 확인하지 않으면 `git diff` 가 빈 목록을 내고, 빈 목록은 「위반 없음」과
    구별되지 않는다 — 게이트가 아무것도 검사하지 않은 채 초록불이 된다.

    08-08 오전에 매핑 게이트에서 만난 것과 같은 유형이다(`|| true` 로 종료 코드를
    버리자 결함 시 파일이 안 바뀌어 diff 가 통과했다).
    """
    _init_repo(tmp_path)
    code = _run_checker(tmp_path, "origin/does-not-exist")
    assert code == 2, (
        f"기준 ref 가 없는데 종료 코드 {code} 입니다. 0 이면 게이트가 조용히 "
        "무력화되고, 1 이면 정당한 PR 이 위반으로 보고됩니다"
    )


@pytest.mark.req("NFR-105-AC1")
def test_empty_diff_exits_2_not_0(tmp_path: Path) -> None:
    """PR 에서 변경 파일 0건은 일어나지 않는다 — 기준 ref 오류의 증상이다."""
    _init_repo(tmp_path)
    assert _run_checker(tmp_path, "HEAD") == 2
    # 로컬 확인용 탈출구는 있으나 CI 에서 쓰지 않는다
    assert _run_checker(tmp_path, "HEAD", "--allow-empty") == 0


def _init_repo(root: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "init")


def _run_checker(root: Path, base: str, *extra: str) -> int:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--base", base, "--root", str(root), *extra],
        capture_output=True, text=True, check=False,
    ).returncode


# ── ⓒ CI 가 실제로 게이트를 실행한다 ────────────────────────────────

@pytest.mark.req("NFR-105-AC1")
def test_ci_runs_both_gates_and_does_not_swallow_their_verdict() -> None:
    """워크플로가 게이트 2종을 부르고, 그 판정을 버리지 않는다.

    yaml 을 문자열로 훑지 않고 **파싱해서** 본다. 문자열 검사로는 주석에 적힌
    명령과 실제 `run:` 이 구분되지 않는다 — 게이트를 주석 처리하고도 이 테스트가
    통과하면 검사가 아무 의미가 없다.

    `continue-on-error` 를 함께 보는 이유: 2.7 이 그 한 줄을 지우는 것으로
    「경고 → 차단」이 되었다. 반대로 누군가 다시 넣으면 잡 이름과 명령은 그대로
    남고 판정만 사라지며, 초록불이므로 드러나지 않는다.
    """
    assert WORKFLOW.is_file(), f"워크플로가 없습니다: {WORKFLOW}"
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    runs: dict[str, list[str]] = {}
    for name, job in spec["jobs"].items():
        assert job.get("continue-on-error") is not True, (
            f"잡 {name!r} 이 continue-on-error 입니다 — 게이트가 경고로 내려가면 "
            "명령은 그대로 남고 판정만 사라집니다"
        )
        runs[name] = [
            step["run"] for step in job.get("steps", []) if isinstance(step.get("run"), str)
        ]

    everything = "\n".join(cmd for cmds in runs.values() for cmd in cmds)

    assert "check_test_accompaniment.py" in everything, (
        "게이트 ②(테스트 동반)를 CI 가 부르지 않습니다 — 스크립트가 저장소에 "
        "있다는 것과 CI 가 그것을 실행한다는 것은 다릅니다 (작업 2.6)"
    )
    assert "diff-cover" in everything, (
        "게이트 ①(변경분 커버리지)를 CI 가 부르지 않습니다 (작업 2.5)"
    )
    assert f"--fail-under={DIFF_COVER_MIN}" in everything, (
        f"diff-cover 의 기준이 {DIFF_COVER_MIN}% 로 고정되어 있지 않습니다. "
        "NFR-105 Measurement 1 은 변경분 커버리지 95% 이며, 이 숫자를 낮추는 "
        "것은 spec 개정입니다 (§16.5)"
    )


@pytest.mark.req("NFR-105-AC1")
def test_ci_checkout_has_full_history_where_the_gates_need_it() -> None:
    """게이트 2종은 기준 브랜치와의 **병합 기점**을 본다.

    얕은 클론이면 그 ref 나 공통 조상이 로컬에 없고, 그러면 판정이 성립하지
    않는다. 그래서 체크아웃 단계에서 고정한다.
    """
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for name, job in spec["jobs"].items():
        commands = "\n".join(
            step["run"] for step in job.get("steps", []) if isinstance(step.get("run"), str)
        )
        if "diff-cover" not in commands and "check_test_accompaniment.py" not in commands:
            continue
        checkouts = [
            step for step in job["steps"]
            if isinstance(step.get("uses"), str) and step["uses"].startswith("actions/checkout")
        ]
        assert checkouts, f"잡 {name!r} 에 checkout 단계가 없습니다"
        assert any(
            str(step.get("with", {}).get("fetch-depth")) == "0" for step in checkouts
        ), (
            f"잡 {name!r} 이 얕은 클론입니다 — 기준 브랜치나 공통 조상이 로컬에 "
            "없으면 게이트가 판정할 수 없습니다"
        )


@pytest.mark.req("NFR-105-AC1")
def test_ci_validates_coverage_inputs_before_judging_them() -> None:
    """입력 검증이 diff-cover **앞에** 있다.

    diff-cover 는 판정할 수 없을 때 통과한다 — `coverage.xml` 의 경로가 저장소
    상대 경로와 어긋나면 *"No lines with coverage information in this diff"* 를
    출력하고 **종료 코드 0** 을 낸다(diff-cover 10.4.2 실측). 문서만 고친 PR
    에서는 그것이 옳고 `core/` 를 고친 PR 에서는 정반대의 뜻인데, 출력과 종료
    코드가 같아 로그로도 구별되지 않는다.

    순서를 검사하는 이유: 뒤에 두면 diff-cover 가 먼저 초록불을 내고 나서
    입력이 틀렸다는 사실이 보고된다. 그 순서로는 게이트가 이미 통과해 있다.
    """
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for name, job in spec["jobs"].items():
        commands = [
            step["run"] for step in job.get("steps", []) if isinstance(step.get("run"), str)
        ]
        joined = "\n".join(commands)
        if "diff-cover" not in joined:
            continue
        guard = next(
            (i for i, c in enumerate(commands) if "check_coverage_inputs.py" in c), None
        )
        judge = next(i for i, c in enumerate(commands) if "diff-cover" in c)
        assert guard is not None, (
            f"잡 {name!r} 이 게이트 ① 입력 검증(check_coverage_inputs.py)을 "
            "부르지 않습니다 — 경로가 어긋난 산출물에서 diff-cover 는 종료 코드 "
            "0 을 냅니다"
        )
        assert guard < judge, (
            f"잡 {name!r} 에서 입력 검증이 diff-cover 뒤에 있습니다 — 그 순서로는 "
            "게이트가 이미 통과한 뒤에 입력이 틀렸다는 사실이 보고됩니다"
        )


@pytest.mark.req("NFR-204-M1")
def test_ci_runs_mypy_strict() -> None:
    """mypy strict 가 CI 에서 강제된다 (작업 2.4).

    `pyproject.toml` 의 `strict = true` 는 08-08 이전부터 있었지만 **아무도
    돌리지 않아 5건이 쌓여 있었다.** 설정 파일에 규칙이 적혀 있다는 것과 그
    규칙이 강제된다는 것은 다르다 — CODEOWNERS(없는 팀명은 조용히 무시)와
    import-linter(CI 에 없었다)에서 이미 두 번 만난 간극이다.

    `strict` 설정 자체도 함께 본다. CI 가 `mypy` 를 부르더라도 설정이 느슨해지면
    같은 명령이 아무것도 잡지 않는다.
    """
    import tomllib

    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    commands = "\n".join(
        step["run"]
        for job in spec["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    )
    assert "mypy" in commands, "CI 가 mypy 를 부르지 않습니다 (NFR-204-M1 / 작업 2.4)"

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["mypy"]["strict"] is True, (
        "mypy 가 strict 가 아닙니다 — NFR-204-M1 의 문면은 `mypy strict 통과` 이며, "
        "느슨하게 바꾸는 것은 spec 개정입니다 (§16.5)"
    )


@pytest.mark.req("NFR-203-M1")
def test_ci_enforces_the_total_coverage_floor() -> None:
    """전체 커버리지 하한 85% (작업 2.10).

    **게이트 ①(변경분 95%)이 이것을 대신하지 못한다.** ①은 그 PR 이 추가·수정한
    라인만 본다. 기존 코드에서 테스트를 지우거나, 커버되던 분기를 커버되지 않는
    형태로 옮기면 변경분은 깨끗한데 전체는 내려간다 — 그 하락을 보는 눈이
    없으면 아무도 알아채지 못한다. 하나는 들어오는 것을, 하나는 이미 있는
    것을 지킨다.
    """
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    commands = "\n".join(
        step["run"]
        for job in spec["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    )
    assert f"--cov-fail-under={TOTAL_COVER_MIN}" in commands, (
        f"전체 커버리지 하한 {TOTAL_COVER_MIN}% 가 CI 에 없습니다 — NFR-203-M1 은 "
        "`pytest-cov CI 게이트` 이며, 값을 낮추는 것은 spec 개정입니다 (§16.5)"
    )


# ── 게이트 ① 입력 검증 자신의 감지 능력 ─────────────────────────────

@pytest.mark.req("NFR-105-AC1")
def test_coverage_inputs_detect_a_path_mismatch() -> None:
    """경로가 어긋난 산출물을 잡는다 — 이것이 게이트 ①의 조용한 구멍이다."""
    mod = _script("check_coverage_inputs")
    measured = {"wrong/place/pv.py"}
    assert mod.missing(["core/der/pv.py"], measured) == ["core/der/pv.py"]


@pytest.mark.req("NFR-105-AC1")
def test_coverage_inputs_accept_matching_and_absolute_paths(tmp_path: Path) -> None:
    """정당한 산출물을 오판하지 않는다 — 오판은 게이트를 꺼지게 만든다.

    `<sources>` 루트와 `filename` 의 조합 방식이 도구마다 다르므로 두 조합과
    꼬리 일치를 모두 인정한다. 한쪽만 보면 경로가 맞는데도 불일치로 보고한다.
    """
    mod = _script("check_coverage_inputs")
    assert mod.missing(["core/der/pv.py"], {"core/der/pv.py"}) == []
    # 절대 경로 예시에 홈 디렉터리 형태를 쓰지 않는다 — 2.3 검사가 그것을
    # 「사용자 이름 노출」로 잡는다(SC-3). 규칙을 느슨하게 하는 대신 예시를
    # 바꾼다: 오탐을 없애려고 검사를 무르게 하면 진짜 유출도 함께 통과한다.
    assert mod.missing(["core/der/pv.py"], {"/build/ci/x/core/der/pv.py"}) == []

    xml = tmp_path / "coverage.xml"
    xml.write_text(
        '<?xml version="1.0" ?>\n'
        "<coverage><sources><source>/build/core</source></sources><packages>"
        '<package><classes><class filename="der/pv.py"/></classes></package>'
        "</packages></coverage>\n",
        encoding="utf-8",
    )
    assert mod.missing(["core/der/pv.py"], mod.measured_files(xml)) == []


@pytest.mark.req("NFR-105-AC1")
def test_coverage_inputs_exit_2_when_the_artifact_is_absent(tmp_path: Path) -> None:
    """산출물이 없는 것을 통과로 읽지 않는다 (§13.0.1 ④)."""
    _init_repo(tmp_path)
    code = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_coverage_inputs.py"),
         "--base", "HEAD", "--root", str(tmp_path)],
        capture_output=True, text=True, check=False,
    ).returncode
    assert code == 2


# ── NFR-202 · NFR-205 (작업 2.9) ─────────────────────────────────────

@pytest.mark.req("NFR-202-M1")
@pytest.mark.req("NFR-205-M1")
def test_ci_runs_the_parameter_and_global_state_scan() -> None:
    """CI 가 파라미터 하드코딩·전역 가변 상태 검사와 **그 음성 테스트**를 부른다.

    음성 테스트를 함께 요구하는 이유: 이 검사는 「차단 0건」으로 통과하고, 그
    통과가 «복제가 없다» 는 뜻인지 «문턱이 너무 높아 아무것도 보지 않는다» 는
    뜻인지 결과만 보고는 구분되지 않는다. 문턱을 올리면 진짜 복제가 경고로
    내려가고 **경고는 종료 코드 0** 이다 — 후퇴가 초록불로 나타난다.
    """
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    commands = "\n".join(
        step["run"]
        for job in spec["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    )
    assert "check_hardcoded_params.py" in commands, (
        "CI 가 NFR-202·NFR-205 검사를 부르지 않습니다 (작업 2.9)"
    )
    assert "negtest_hardcoded_params.py" in commands, (
        "검사의 감지 능력을 확인하지 않습니다 — 게이트를 켠 이상 게이트 자신이 "
        "무언가를 검사한다는 증거가 CI 에 상주해야 합니다 (§13.0.1 ④)"
    )


@pytest.mark.req("NFR-205-M1")
def test_no_module_or_class_level_mutable_containers() -> None:
    """`core/`·`app/`·`infra/` 에 모듈·클래스 수준 가변 컨테이너가 없다.

    조항의 근거는 DER-VET `Params.py` 의 클래스 변수 전역 상태이며, 그것이
    **케이스 그리드 병렬 실행(FR-805)과 구획별 테스트 격리(§16 W-5)를 동시에**
    불가능하게 만들었다.

    **읽기 전용으로 쓰고 있어도 위반이다.** 실제로 `core/der/ess.py` 의
    `_MODE_WINDOWS` 가 평범한 `dict` 였고 아무도 고치지 않았지만, 병렬 실행에서
    한 번의 변형은 다른 케이스의 결과를 조용히 바꾼다 — `MappingProxyType` 으로
    바꾸면 그 가능성 자체가 사라진다.
    """
    mod = _script("check_hardcoded_params")
    root = REPO_ROOT
    findings = mod.check_global_mutable(mod.source_files(root), root)
    assert not findings, "전역 가변 상태: " + ", ".join(
        f"{f.path}:{f.lineno} {f.detail}" for f in findings
    )


# ── SC-3 · SC-5 · SC-8 비공개 유입 차단 (작업 2.3) ───────────────────

PRECOMMIT = REPO_ROOT / ".pre-commit-config.yaml"


@pytest.mark.req("FR-1101-AC5")
@pytest.mark.req("SC-5")
def test_private_data_scan_runs_in_both_pre_commit_and_ci() -> None:
    """조항 문면이 **`pre-commit·CI에 둔다`** 이므로 둘 다 본다.

    한쪽만으로는 성립하지 않는다. 훅은 로컬에서 `--no-verify` 한 줄로 우회되고,
    CI 는 **이미 커밋된 뒤에** 본다. 비공개 데이터는 커밋되는 순간 이력에
    남으므로 「나중에 지우면 된다」가 성립하지 않는다 — 지우려면 저장소 이력을
    다시 써야 하고, 공개된 뒤라면 그것으로도 늦다.
    """
    assert PRECOMMIT.is_file(), f"pre-commit 설정이 없습니다: {PRECOMMIT}"
    hooks = yaml.safe_load(PRECOMMIT.read_text(encoding="utf-8"))
    ids = {
        h.get("id")
        for repo in hooks["repos"]
        for h in repo.get("hooks", [])
    }
    assert "gitleaks" in ids, "pre-commit 에 gitleaks 가 없습니다 (SC-5)"
    assert "check-disclosure" in ids, (
        "pre-commit 에 비공개 유입 검사가 없습니다 (SC-3·SC-8)"
    )

    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    commands = "\n".join(
        step["run"]
        for job in spec["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    )
    assert "gitleaks" in commands, "CI 에 gitleaks 잡이 없습니다 (SC-5)"
    assert "check_disclosure.py" in commands, "CI 에 비공개 유입 검사가 없습니다"
    assert "negtest_disclosure.py" in commands, (
        "검사의 감지 능력을 확인하지 않습니다 — 비밀 스캔은 규칙이 조용히 "
        "무력해져도 **매일 초록불**이고, 알아차리는 시점은 이미 공개된 뒤입니다"
    )


@pytest.mark.req("FR-1101-AC5")
@pytest.mark.req("SC-5")
def test_secret_scan_uses_full_history() -> None:
    """비밀 스캔은 **이력 전체**를 본다.

    얕은 클론이면 과거 커밋에 남은 비밀을 보지 못한 채 초록불이 된다.
    **비밀은 지워도 이력에 남는 것이 문제**이므로, 최근 커밋만 보는 스캔은
    정확히 그 문제를 놓친다.
    """
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for name, job in spec["jobs"].items():
        commands = "\n".join(
            step["run"] for step in job.get("steps", []) if isinstance(step.get("run"), str)
        )
        if "gitleaks" not in commands:
            continue
        checkouts = [
            step for step in job["steps"]
            if isinstance(step.get("uses"), str) and step["uses"].startswith("actions/checkout")
        ]
        assert any(
            str(step.get("with", {}).get("fetch-depth")) == "0" for step in checkouts
        ), f"잡 {name!r} 이 얕은 클론입니다 — 과거 커밋의 비밀을 보지 못합니다"


@pytest.mark.req("FR-1101-AC5")
@pytest.mark.req("SC-8")
def test_every_ledger_value_declares_its_disclosure_grade() -> None:
    """값을 가진 대장 항목은 **명시적으로** 공개 등급을 선언한다.

    SC-8 은 **등급 미지정을 「비공개」로 간주**한다(안전한 기본값). 이 저장소는
    공개 저장소이므로(FR-1101-AC1) 등급을 적지 않은 값은 «커밋될 수 없는 것이
    커밋된 상태»다.

    **08-08 이전에는 이 필드가 아예 없었다.** 실제 내용은 전부 공개 가능한
    값이었지만 그 사실이 어디에도 적혀 있지 않았고, 그 상태로는 **다음에 진짜
    업계 견적이 들어와도 아무것도 달라지지 않는다.**
    """
    ledger = yaml.safe_load(
        (REPO_ROOT / "docs" / "assumptions.yaml").read_text(encoding="utf-8")
    )
    # `SC-8` 마커는 08-08에 §9 표를 추적표에 넣으면서 유효해졌다. 그전에는
    # 이 마커를 달면 생성기가 «실재하지 않는 인용» 으로 잡았고 — 검사기는
    # 옳았다 — 그때 **보안 조항 8건이 통째로 감시 밖**이라는 것이 드러났다.
    ungraded = [
        item["key"] for item in ledger["assumptions"]
        if item.get("value") is not None and item.get("disclosure") != "공개 가능"
    ]
    assert not ungraded, (
        f"등급이 없거나 «공개 가능»이 아닌 값 항목: {ungraded}. 등급 미지정은 "
        "«비공개»로 간주되며 공개 저장소에 커밋될 수 없습니다 (SC-8)"
    )


@pytest.mark.req("SC-3")
def test_personal_identifier_patterns_are_detected(tmp_path: Path) -> None:
    """개별 식별정보 형태를 잡는다 — 그리고 **찾은 값을 보고서에 싣지 않는다.**

    SC-3 은 *"실증 참여 가구의 개별 식별정보 미저장"* 을 요구한다. Q-3 부하
    시계열은 실제 가구 데이터이고, 익명화 전 원본이 저장소에 들어오는 사고를
    막을 수 있는 시점은 **커밋 전 한 번뿐**이다.

    가리는 것도 함께 검사하는 이유: CI 로그와 작업 요약은 저장소보다 넓게
    읽힌다. **보고서가 새 유출 경로가 되면 검사가 문제를 옮길 뿐이다.** 실제로
    한 줄에 셋이 있을 때 각 발견이 나머지 둘을 그대로 실었고, 세 줄을 나란히
    읽으면 원문이 복원됐다 — 이 검사가 그것을 잡았다.

    **픽스처를 리터럴로 적지 않고 조립한다.** 적으면 이 파일이 검사 대상이므로
    스스로 위반이 된다 —「검사 도구를 설명하는 문장이 그 검사에 걸린다」의
    여덟 번째다. 해법은 앞선 일곱과 같다: **면제를 넓히지 않고 대상을 바꾼다.**
    `tests/` 를 통째로 면제하면 진짜 유출이 테스트 픽스처에 섞여 들어와도
    보이지 않는다.
    """
    mod = _script("check_disclosure")

    rrn = "900101" + "-" + "1234567"
    phone = "010" + "-1234-" + "5678"
    email = "hong" + "@" + "somewhere.co.kr"
    benign = "someone" + "@" + "example.com"

    sample = tmp_path / "x.md"
    sample.write_text(
        f"참여자 {rrn} / 담당 {phone} / {email}\n예시는 {benign} 을 쓴다\n",
        encoding="utf-8",
    )
    findings = mod.check_contents(["x.md"], tmp_path)
    rules = {f.rule for f in findings}
    assert "주민등록번호 형태" in rules
    assert "전화번호 형태" in rules
    assert "이메일 주소" in rules

    blob = "\n".join(f.excerpt for f in findings)
    for secret in (rrn, phone, email):
        assert secret not in blob, (
            "찾은 값이 보고서에 그대로 실렸습니다 — 검사가 유출을 막는 대신 "
            "옮기고 있습니다. 한 줄에 여럿이면 각 발견이 나머지를 싣습니다"
        )
    assert benign not in blob, (
        "`example.com` 예시를 개인정보로 오판합니다 — 오탐은 규칙을 넓히는 "
        "압력을 만들고, 넓어진 규칙은 진짜 유출도 통과시킵니다"
    )
