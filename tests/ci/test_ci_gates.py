"""CI 게이트 및 코드 품질·보안 검증."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"

TOTAL_COVER_MIN = 85  # NFR-203 (작업 2.10)


def _script(stem: str):
    """`scripts/` 는 패키지가 아니므로 경로로 불러온다.

    `sys.path` 에 `scripts/` 를 넣는 이유: 스크립트로 실행할 때는 스크립트
    디렉터리가 자동으로 `sys.path` 에 들어가지만 여기서는 그렇지 않다.

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



# ── CI 정적검사 및 전체 커버리지 ───────────────────────────────────

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


# ── COINCIDENTAL_LITERALS 면제 기제 (R51/WP-2-fix) ───────────────────
#
# 입력을 캐릭터가 정하고 출력을 잰다 — 검사 대상이 스스로 답을 정하는 동어반복을
# 피하려고 `check_hardcoded_params.COINCIDENTAL_LITERALS`(실물)를 그대로 쓰지
# 않고, `monkeypatch` 로 시험용 목록·시험용 저장소 트리를 각자 만든다
# (`test_missing_sensitivity_is_refused_not_filled` 와 같은 형태).


def _bare_ledger(tmp_path: Path, *, value: int) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "assumptions.yaml").write_text(
        'price_basis: "명목"\nassumptions:\n'
        '  - key: "capex.pv.rooftop"\n'
        f'    value: {value}\n'
        f'    sensitivity: {{low: 1, base: {value}, high: {value}}}\n'
        '    value_unit: "원/kW"\n'
        '    base_year: "2026"\n'
        '    applicable_scope: "s"\n'
        '    derivation_method: "d"\n'
        '    source: null\n'
        '    verified_at: null\n'
        '    confidence: "가정"\n'
        '    replace_when: "r"\n',
        encoding="utf-8",
    )


def _bare_source(tmp_path: Path, *, body: str) -> None:
    (tmp_path / "core" / "der").mkdir(parents=True)
    (tmp_path / "core" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "core" / "der" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "core" / "der" / "sample.py").write_text(body, encoding="utf-8")


@pytest.mark.req("NFR-202-M1")
def test_blank_exemption_reason_is_refused() -> None:
    """★ 사유가 비면 **면제가 아니다** — 목록 자체를 거부한다.

    `check_hardcoded_params.COINCIDENTAL_LITERALS`(실물)를 건드리지 않는다 —
    `_blank_exemption_keys` 는 받은 사전만 본다.
    """
    mod = _script("check_hardcoded_params")
    mapping = {("core/x.py", 1.0): "   ", ("core/y.py", 2.0): "정당한 사유"}
    assert mod._blank_exemption_keys(mapping) == [("core/x.py", 1.0)]


@pytest.mark.req("NFR-202-M1")
def test_check_hardcoded_params_rejects_blank_exemption_at_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """`main()` 이 사유 없는 면제를 만나면 **본 스캔을 시작하기 전에** rc=2 로 멈춘다."""
    mod = _script("check_hardcoded_params")
    monkeypatch.setattr(mod, "COINCIDENTAL_LITERALS", {("core/x.py", 1.0): ""})
    code = mod.main(["--root", str(tmp_path)])
    assert code == 2


@pytest.mark.req("NFR-202-M1")
def test_stale_exemption_is_reported_only_when_its_path_was_scanned() -> None:
    """★ 「낡았다」는 **스캔된 경로인데 안 걸렸다**일 때만 성립한다.

    스캔에 없는 경로(예: `negtest_hardcoded_params.py` 의 임시 트리처럼 그
    파일 자체가 없는 실행)까지 낡았다고 하면, 이 검사기의 음성 시험이 돌 때마다
    거짓 rc=1 이 난다 — 그것을 막는 것이 이 시험의 요점이다.
    """
    mod = _script("check_hardcoded_params")
    mapping = {("core/x.py", 5.0): "사유"}
    assert mod._stale_exemptions(mapping, used=set(), scanned_paths={"core/x.py"}) == [
        ("core/x.py", 5.0)
    ]
    assert mod._stale_exemptions(mapping, used=set(), scanned_paths=set()) == []
    assert mod._stale_exemptions(
        mapping, used={("core/x.py", 5.0)}, scanned_paths={"core/x.py"}
    ) == []


@pytest.mark.req("NFR-202-M1")
def test_check_hardcoded_params_reports_stale_exemption_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """면제 목록에 있는데 소스에 그 리터럴이 없으면 `main()` 이 rc=1 로 말한다."""
    mod = _script("check_hardcoded_params")
    _bare_ledger(tmp_path, value=999_999)
    _bare_source(tmp_path, body="VALUE = 1\n")  # 999_999 는 여기 없다 — 낡았다
    monkeypatch.setattr(
        mod, "COINCIDENTAL_LITERALS", {("core/der/sample.py", 999_999.0): "더 이상 없음"}
    )
    code = mod.main(["--root", str(tmp_path)])
    assert code == 1


@pytest.mark.req("NFR-202-M1")
def test_check_hardcoded_params_demotes_an_exempted_match_to_a_labelled_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """★ **감추지 않는다** — 면제된 충돌은 사라지지 않고 사유와 함께 경고로 남는다."""
    mod = _script("check_hardcoded_params")
    _bare_ledger(tmp_path, value=424_242)
    _bare_source(tmp_path, body="LIMIT = 424_242\n")
    monkeypatch.setattr(
        mod, "COINCIDENTAL_LITERALS",
        {("core/der/sample.py", 424_242.0): "무관한 예시 상한"},
    )
    code = mod.main(["--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "✗ core/der/sample.py" not in out, "면제됐는데 여전히 차단으로 인쇄된다"
    assert "면제: 무관한 예시 상한" in out, "사유가 인쇄되지 않는다 — 감춘 것과 같다"


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

    # SC-3 최소화 수집 검증: 시스템이 개인정보 수집을 최소화함을 확인
    # 검사가 민감 정보 감지와 보고 최소화를 수행함을 확인
    assert len(findings) == 3, f"3종 민감 정보 감지됨: {[f.rule for f in findings]}"
    # 검사가 민감 정보를 감지했음을 확인
    assert len(rules) >= 3
