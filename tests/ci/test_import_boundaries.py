"""NFR-208 구획 경계 — import-linter 가 **실제로 위반을 잡는지** 확인한다.

**빈 패키지 위의 `4 kept` 는 공허하다.** Wave 0에서 세 위반이 BROKEN 으로 뜨는
것을 실측했지만 **임시 실행이라 기록만 남고 재현되지 않았다.** 게이트를 CI 로
켠 이상(작업 2.8) 게이트 자신이 무언가를 검사한다는 증거가 상주해야 한다
(§13.0.1 ④) — `negtest_traceability.py` 를 저장소에 넣은 것과 같은 이유다.

**왜 별도 스크립트가 아니라 pytest 인가.** 다른 음성 테스트(`negtest_*.py`)는
검사 대상이 파이썬 함수가 아니라 «도구의 판정» 이라 스크립트로 두었다. 여기서는
검사 대상이 **저장소의 import 그래프**이고, 그것을 흔들려면 실제 파일을 심었다
빼야 한다. pytest 의 정리(`finally`)와 임시 자원 관리가 그 일에 맞고, 무엇보다
`@pytest.mark.req` 로 `NFR-208-AC1`~`M1` 이 매핑된다 — 이 조항들은 게이트
자신이므로 `manual-checks.yaml` 등재가 금지되어 있다(NFR-107-AC5 ⓒ).

**심는 모듈 이름을 `_` 로 시작시키는 이유.** `core/der/` 는 레지스트리가 스캔
하는 디렉터리다(NFR-207). 발견기는 `_` 로 시작하는 모듈을 건너뛰므로 심어도
레지스트리가 오염되지 않는 반면, **import-linter 는 그래프를 전부 보므로 잡는다.**
둘의 차이가 없으면 이 검사를 `core/der/` 안에서 할 수 없다.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: `lint-imports` 콘솔 스크립트가 PATH 에 없을 수 있다. 모듈로 부를 때는
#: `python -m importlinter.cli` 를 쓰지 않는다 — 그 모듈에는 `__main__` 가드가
#: 없어 **import만 되고 끝나며 종료 코드 0** 을 낸다. 위반을 심어도 초록불이다.
INVOKE = [
    sys.executable, "-c",
    "from importlinter.cli import lint_imports_command; lint_imports_command()",
    "--no-cache",
]


def _run() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        INVOKE, cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )


@contextmanager
def planted(relative: str, source: str) -> Iterator[Path]:
    """위반 모듈을 잠시 심는다. **반드시 지운다** — 남으면 저장소가 망가진다."""
    path = REPO_ROOT / relative
    assert not path.exists(), f"이미 존재합니다: {relative}"
    path.write_text(source, encoding="utf-8")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


# ── 양성: 지금의 저장소는 정합한다 ──────────────────────────────────

@pytest.mark.req("NFR-208-M1")
def test_repository_keeps_all_four_contracts() -> None:
    """`4 kept, 0 broken`.

    음성만 보면 «전부 위반으로 보고하는» 장치도 만점을 받는다. 양성을 함께
    둔다 — `negtest_traceability.py` 가 음성 6에 양성 2를 붙인 것과 같다.
    """
    result = _run()
    assert result.returncode == 0, (
        f"저장소가 구획 경계를 위반하고 있습니다:\n{result.stdout}\n{result.stderr}"
    )
    assert "4 kept, 0 broken" in result.stdout, (
        f"계약 수가 4가 아닙니다 — .importlinter 를 확인하십시오:\n{result.stdout}"
    )


# ── 음성: 세 수용기준이 각각 BROKEN 을 낸다 ─────────────────────────

@pytest.mark.req("NFR-208-AC1")
def test_reverse_layer_import_is_broken() -> None:
    """`core/der/` → `core/engine/` 은 역방향이다.

    자원이 엔진을 알면 «자원 1종 추가» 가 엔진 코드를 흔든다 — NFR-201 이
    없애려는 구조이고, 병렬 구획에서는 두 사람이 같은 파일을 만진다는 뜻이다.
    """
    with planted("core/der/_negtest_reverse_layer.py",
                 "import core.engine  # noqa: F401\n"):
        result = _run()
    assert result.returncode == 1, (
        "역방향 import 를 심었는데 통과했습니다 — layers 계약이 무엇도 "
        f"검사하지 않고 있습니다:\n{result.stdout}"
    )
    assert "계층 역방향" in result.stdout, (
        f"다른 계약이 대신 걸렸습니다 — AC1 이 검사되지 않았습니다:\n{result.stdout}"
    )


@pytest.mark.req("NFR-208-AC2")
def test_sibling_partition_import_is_broken() -> None:
    """`core/der/` → `core/regulation/` 은 형제 구획 직접 참조다.

    직접 참조를 허용하면 두 구획이 동시에 진행될 때 한쪽의 **미완성 내부
    표현**에 다른 쪽이 묶이고, W-6(독립 완료 판정)이 깨진다.
    """
    with planted("core/der/_negtest_sibling.py",
                 "import core.regulation  # noqa: F401\n"):
        result = _run()
    assert result.returncode == 1, (
        "형제 구획 직접 import 를 심었는데 통과했습니다 — independence 계약이 "
        f"무엇도 검사하지 않고 있습니다:\n{result.stdout}"
    )
    assert "형제 구획" in result.stdout, (
        f"다른 계약이 대신 걸렸습니다 — AC2 가 검사되지 않았습니다:\n{result.stdout}"
    )


@pytest.mark.req("NFR-208-AC3")
def test_contracts_importing_a_partition_is_broken() -> None:
    """`core/contracts/` 가 구획을 참조하면 순환이 생긴다.

    여기가 무너지면 나머지 두 계약이 **형식적으로만** 성립한다 — 모든 구획이
    계약을 경유하는데 계약 자신이 구획을 참조하기 때문이다. 6.7 의 발견기가
    스캔할 패키지를 **인자로 받는** 것도 이 조항 때문이다.
    """
    with planted("core/contracts/_negtest_impure.py",
                 "import core.der  # noqa: F401\n"):
        result = _run()
    assert result.returncode == 1, (
        "계약이 구획을 import하도록 심었는데 통과했습니다 — forbidden 계약이 "
        f"무엇도 검사하지 않고 있습니다:\n{result.stdout}"
    )
    assert "어떤 구획도 import" in result.stdout, (
        f"다른 계약이 대신 걸렸습니다 — AC3 이 검사되지 않았습니다:\n{result.stdout}"
    )


# ── M1: CI 가 이 검사를 실제로 부른다 ───────────────────────────────

@pytest.mark.req("NFR-208-M1")
def test_ci_runs_import_linter_with_the_console_script() -> None:
    """CI 가 `lint-imports` 를 부르고, **`python -m importlinter.cli` 는 쓰지 않는다.**

    후자는 `__main__` 가드가 없어 import만 되고 끝나며 종료 코드 0 을 낸다 —
    위반을 심어도 초록불이다. 실측 확인했고, 이전 판 `status.md` 가 대체 명령
    으로 그것을 적어 두고 있었다.

    검사기가 저장소에 있다는 사실과 CI 가 그것을 부른다는 사실은 다르다.
    """
    import yaml

    workflow = REPO_ROOT / ".github" / "workflows" / "tests.yml"
    spec = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    commands = "\n".join(
        step["run"]
        for job in spec["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    )
    assert "lint-imports" in commands, (
        "CI 가 import-linter 를 부르지 않습니다 (작업 2.8 / NFR-208-M1)"
    )
    assert "-m importlinter.cli" not in commands, (
        "`python -m importlinter.cli` 는 아무것도 검사하지 않고 종료 코드 0 을 "
        "냅니다 — 콘솔 스크립트 `lint-imports` 를 쓰십시오"
    )
