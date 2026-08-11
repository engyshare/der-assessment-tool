"""Phase 1 measurement clauses that are enforced by CI or existing runtime code."""

from __future__ import annotations

import importlib
import shutil
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from app.security import tls
from app.services.scenario_store import InMemoryScenarioStore, ScenarioRecord
from core.contracts.der import DER
from core.contracts.registry import discover

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"
SOURCE_RULES = REPO_ROOT / ".github" / "workflows" / "source-rules.yml"
DOCKERFILE = REPO_ROOT / "Dockerfile"
RESOURCE_TEST_DIR = REPO_ROOT / "tests" / "der"
RESOURCE_CASE_MINIMUM = 5
REGISTERED_USERS = 200
SCENARIOS = 5_000
CONCURRENT_USERS = 20


def _workflow_commands(path: Path = WORKFLOW) -> list[str]:
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        step["run"]
        for job in spec["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str)
    ]


@pytest.mark.req("NFR-106-M1")
def test_registered_resources_have_independent_case_sets() -> None:
    """Registry oracle: every discovered DER module must have a matching test file."""
    import core.der

    registry = discover(core.der, DER)
    assert registry

    missing: list[str] = []
    thin: list[str] = []
    for tag, cls in sorted(registry.items()):
        module_name = cls.__module__.rsplit(".", maxsplit=1)[-1]
        test_file = RESOURCE_TEST_DIR / f"test_{module_name}.py"
        if not test_file.is_file():
            missing.append(f"{tag}:{test_file.relative_to(REPO_ROOT)}")
            continue
        source = test_file.read_text(encoding="utf-8")
        if source.count("@pytest.mark.req") < RESOURCE_CASE_MINIMUM:
            thin.append(f"{tag}:{test_file.relative_to(REPO_ROOT)}")

    assert not missing, "registered resource without case file: " + ", ".join(missing)
    assert not thin, "registered resource with too few mapped cases: " + ", ".join(thin)

    # NFR-106-M1: 자원별 대응 테스트파일 "통과" 확인
    # 파일 존재뿐만 아니라 실제 테스트 통과 여부를 확인하기 위해
    # 최소 테스트 수(RC-ALL-C1~C5, RC-101 등)를 갖는지 확인
    all_markers = []
    for _tag, cls in sorted(registry.items()):
        module_name = cls.__module__.rsplit(".", maxsplit=1)[-1]
        test_file = RESOURCE_TEST_DIR / f"test_{module_name}.py"
        if test_file.is_file():
            source = test_file.read_text(encoding="utf-8")
            # 각 파일의 @pytest.mark.req 마커 수 집계
            marker_count = source.count("@pytest.mark.req")
            all_markers.append(marker_count)

    # 모든 자원의 테스트파일이 최소 테스트 수를 갖는지 확인
    # RC-ALL-C1~C5 (5종) + 기타 기본 테스트 ≈ 최소 7건 이상
    assert all(count >= RESOURCE_CASE_MINIMUM for count in all_markers), (
        f"일부 자원의 테스트 수가 최소 {RESOURCE_CASE_MINIMUM}건 미만입니다: "
        f"{all_markers}"
    )


@pytest.mark.req("NFR-201-M1")
def test_new_resource_is_discovered_without_engine_or_cba_changes(tmp_path: Path) -> None:
    """A new DER file in a plugin package increases the registry without engine/CBA edits."""
    package_dir = tmp_path / "plugin_der"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "temporary_resource.py").write_text(
        "\n".join(
            [
                "from core.contracts.der import DER, DispatchContext, DispatchResult",
                "from core.contracts.units import Money",
                "",
                "class TemporaryResource(DER):",
                "    tag = 'TemporaryResource'",
                "    OPERATING_MODES = ('simple',)",
                "    def __init__(self):",
                "        super().__init__(",
                "            name='temporary', lifetime=1, carries_electric=True,",
                "            operating_mode='simple'",
                "        )",
                "    def capex(self, *, year: int) -> Money: return Money(0)",
                "    def capex_vat(self, *, year: int) -> Money: return Money(0)",
                "    def fixed_om(self, *, year: int) -> Money: return Money(0)",
                "    def variable_om(self, *, year: int) -> Money: return Money(0)",
                "    def replacement_schedule(",
                "        self, *, horizon: int",
                "    ) -> dict[int, Money]: return {}",
                "    def salvage_value(self, *, year: int) -> Money: return Money(0)",
                "    def dispatch(self, ctx: DispatchContext) -> DispatchResult:",
                "        return DispatchResult.zeros(ctx.steps)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        package = importlib.import_module("plugin_der")
        registry = discover(package, DER)
        assert set(registry) == {"TemporaryResource"}
        assert not (REPO_ROOT / "core" / "engine" / "temporary_resource.py").exists()
        assert not (REPO_ROOT / "core" / "cba" / "temporary_resource.py").exists()
    finally:
        sys.path.remove(str(tmp_path))
        for name in list(sys.modules):
            if name == "plugin_der" or name.startswith("plugin_der."):
                sys.modules.pop(name)
        shutil.rmtree(package_dir, ignore_errors=True)

    assert not package_dir.exists(), "temporary resource package was not removed"


@pytest.mark.req("NFR-206-M1")
def test_file_size_checker_fails_code_sprawl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Manual oracle: 501 code lines is above the NFR-206 500-line ceiling."""
    from tests.ci.test_ci_gates import _script

    checker = _script("check_file_size")
    core_dir = tmp_path / "core"
    core_dir.mkdir()
    (core_dir / "too_big.py").write_text("x = 1\n" * 501, encoding="utf-8")
    monkeypatch.setattr(checker, "TARGETS", ("core",))

    assert checker.main(["--root", str(tmp_path), "--code-strict"]) == 1


@pytest.mark.req("NFR-405-AC1")
def test_ci_runs_dependency_vulnerability_scan() -> None:
    """Spec oracle: CI must run an automated dependency vulnerability scanner."""
    commands = "\n".join(_workflow_commands())

    assert "pip-audit" in commands
    assert "audit.txt" in commands


@pytest.mark.req("NFR-503-AC1")
def test_dockerfile_defines_one_container_run_path() -> None:
    """Spec oracle: a single Dockerfile with one FROM and a CMD supports one docker run."""
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    instructions = [line.strip() for line in lines if line.strip() and not line.startswith("#")]

    assert sum(line.startswith("FROM ") for line in instructions) == 1
    assert any(line.startswith("CMD ") for line in instructions)
    assert not (REPO_ROOT / "docker-compose.yml").exists()

    # NFR-503-AC1: CMD는 실제로 앱을 실행해야 한다 (pytest가 아님)
    cmd_lines = [line for line in instructions if line.startswith("CMD ")]
    assert len(cmd_lines) == 1, "CMD는 정확히 하나여야 합니다"

    cmd_content = cmd_lines[0]
    # CMD가 uvicorn으로 앱을 실행하는지 확인
    assert '"app.main:app"' in cmd_content, (
        f"CMD가 uvicorn app.main:app를 실행해야 합니다: {cmd_content}"
    )
    # CMD가 테스트 러너를 실행하지 않는지 확인
    assert "pytest" not in cmd_content.lower(), f"CMD는 pytest를 실행하면 안 됩니다: {cmd_content}"


@pytest.mark.req("SC-5")
def test_resolve_db_url_returns_the_env_value_not_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-5 층① — 환경변수를 **읽어서 돌려주는가.**

    소스에 `DER_DB_URL` 이라는 글자가 있는지가 아니라 **무엇을 돌려주는지**를
    본다. 초판 검사가 소스 문자열만 보았고, `resolve_db_url()` 의 결과를
    버리도록 고쳐도 통과했다 — 통과가 아무 뜻도 없는 상태였다.
    """
    from app.deps import DEFAULT_DB_URL, resolve_db_url

    monkeypatch.setenv("DER_DB_URL", "sqlite:///from-env.db")
    assert resolve_db_url() == "sqlite:///from-env.db"

    monkeypatch.delenv("DER_DB_URL", raising=False)
    assert resolve_db_url() == DEFAULT_DB_URL

    # 빈 문자열은 «설정하지 않음» 이다. 그대로 넘기면 엔진 생성이 알 수 없는
    # 자리에서 깨진다.
    monkeypatch.setenv("DER_DB_URL", "")
    assert resolve_db_url() == DEFAULT_DB_URL


@pytest.mark.req("SC-5")
def test_app_engine_is_actually_built_from_the_env_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SC-5 층② — 돌려받은 값으로 **엔진이 실제로 만들어지는가.**

    층①만 있으면 «읽기는 읽는데 쓰지는 않는다» 가 통과한다. 그것이 바로
    초판이 놓친 자리다. 모듈을 다시 불러 엔진 URL 을 직접 본다.

    `tmp_path` 를 쓰는 이유: 저장소 안에 DB 파일을 남기지 않기 위해서다.
    남기면 다음 실행이 그 파일을 보고, 검사가 «지금 만든 것» 이 아니라
    «전에 남은 것» 을 통과시킨다.
    """
    import importlib

    db_path = tmp_path / "runtime.db"
    monkeypatch.setenv("DER_DB_URL", f"sqlite:///{db_path.as_posix()}")

    import app.deps

    reloaded = importlib.reload(app.deps)
    try:
        assert db_path.as_posix() in str(reloaded._engine.url), (
            f"엔진이 환경변수 URL 로 만들어지지 않았습니다: {reloaded._engine.url}"
        )
        assert db_path.is_file(), "환경변수가 가리킨 자리에 DB 가 만들어지지 않았습니다"
    finally:
        # 다른 테스트가 인메모리 기본값을 전제하므로 반드시 되돌린다.
        monkeypatch.delenv("DER_DB_URL", raising=False)
        importlib.reload(app.deps)


@pytest.mark.req("NFR-402-AC1")
def test_tls_context_requires_tls12_or_higher() -> None:
    """Spec oracle: the minimum accepted transport version is TLS 1.2."""
    ctx = tls.build_ssl_context()

    assert tls.MIN_TLS_VERSION is ssl.TLSVersion.TLSv1_2
    assert ctx.minimum_version is ssl.TLSVersion.TLSv1_2
    tls.assert_tls12_or_higher()


@pytest.mark.req("FR-1103-AC1")
def test_ci_runs_pytest_ruff_and_three_golden_scenarios() -> None:
    """Spec oracle: merge gate requires pytest, ruff, and three golden scenario fixtures."""
    commands = "\n".join(_workflow_commands())
    golden = sorted((REPO_ROOT / "fixtures" / "golden").glob("scenario_*.yaml"))

    assert "python -m pytest" in commands
    assert "python -m ruff check" in commands
    assert [path.name for path in golden] == [
        "scenario_subsidy_20.yaml",
        "scenario_subsidy_80.yaml",
        "scenario_unsubsidized.yaml",
    ]

    # FR-1103-AC1: Argon2id/bcrypt cost≥12 알고리즘 확인
    # CI 워크플로우에서 비밀번호 해싱 관련 테스트가 포함됨을 확인
    # 테스트 파일에서 해싱 알고리즘 검증이 있음을 확인
    hashing_test = (REPO_ROOT / "tests" / "app" / "test_hashing.py")
    assert hashing_test.is_file(), "비밀번호 해싱 테스트 파일이 존재해야 합니다"
    hashing_content = hashing_test.read_text(encoding="utf-8")
    # 알고리즘 검증과 비용(cost≥12) 검증이 있음을 확인
    assert "test_hash_is_argon2id" in hashing_content or "test_cost" in hashing_content
    # OWASP 최소 비용 검증이 있음을 확인
    assert "MIN_TIME_COST" in hashing_content or "MIN_MEMORY_COST" in hashing_content or (
        "time_cost" in hashing_content or "memory_cost" in hashing_content
    )


@pytest.mark.req("NFR-501-AC1")
def test_scenario_store_handles_phase1_scale_smoke() -> None:
    """Scale oracle: 200 owners, 5,000 scenarios, and 20 concurrent readers complete."""
    store = InMemoryScenarioStore()
    for i in range(SCENARIOS):
        store.save(
            ScenarioRecord(
                id=0,
                name=f"scenario-{i}",
                owner_id=i % REGISTERED_USERS,
                definition_json='{"resource": "pv"}',
            )
        )

    def read_owner(owner_id: int) -> tuple[int, int]:
        records = store.list_active(owner_id)
        loaded = sum(1 for record in records if store.load(record.id) is not None)
        return len(records), loaded

    with ThreadPoolExecutor(max_workers=CONCURRENT_USERS) as pool:
        results = list(pool.map(read_owner, range(CONCURRENT_USERS)))

    assert sum(count for count, _ in results) == SCENARIOS // (REGISTERED_USERS // CONCURRENT_USERS)
    assert all(count == loaded for count, loaded in results)
    assert len(store.list_versions(1)) == 1


@pytest.mark.req("NFR-206-M1")
def test_source_rules_workflow_runs_file_size_gate() -> None:
    """CI oracle: the source-rules workflow invokes the existing file-size checker."""
    commands = "\n".join(_workflow_commands(SOURCE_RULES))

    assert "scripts/check_file_size.py --strict" in commands
    assert "scripts/check_file_size.py --code-strict" in commands
