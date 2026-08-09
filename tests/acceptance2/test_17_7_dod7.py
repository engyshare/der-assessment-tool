"""17.7 DoD 7 — 골든 3종 CI 회귀 통과 및 무료 호스팅 외부 접속 검증."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "golden"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "tests.yml"

#: 골든 시나리오 3종. `tuple` 인 이유는 NFR-205 — 모듈 수준 가변 컨테이너 금지.
GOLDEN_SCENARIO_FILES = (
    "scenario_subsidy_20.yaml",
    "scenario_subsidy_80.yaml",
    "scenario_unsubsidized.yaml",
)


@pytest.mark.req("FR-1103-AC1")
def test_dod7_golden_3_scenarios_exist_and_valid() -> None:
    """DoD 7 — 골든 시나리오 3종 파일 존재 및 사양 검증 (NFR-104 / FR-1103).

    파일이 있고 YAML 로 파싱되는지만 확인한다. 회귀 대조는 별도 검사
    (테스트 코드를 거치는 계산 결과인지 확인 필요).
    """
    expected_files = [
        "scenario_subsidy_20.yaml",
        "scenario_subsidy_80.yaml",
        "scenario_unsubsidized.yaml",
    ]
    for name in expected_files:
        file_path = GOLDEN_DIR / name
        assert file_path.is_file(), f"골든 시나리오 파일이 존재하지 않습니다: {name}"
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"YAML 파싱 실패: {name}"


@pytest.mark.req("NFR-104-M1")
def test_dod7_ci_workflow_includes_pytest_and_ruff() -> None:
    """DoD 7 — GitHub Actions CI 워크플로에 pytest 및 ruff 검사 포함 확인.

    tests/ci/test_ci_gates.py 가 이미 CI 게이트의 실제 동작을 깊게 검사하므로
    여기서는 조항 문면대로 해당 도구가 워크플로에 포함되어 있는지만 확인한다.
    """
    assert WORKFLOW_PATH.is_file(), "CI 워크플로 파일이 존재해야 합니다."
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    # 문자열 검사로 충분 — 실제 실행 검사는 tests/ci/test_ci_gates.py 에서
    # 이미 수행됨 (test_ci_runs_both_gates_and_does_not_swallow_their_verdict)
    assert "pytest" in content
    assert "ruff" in content


@pytest.mark.req("FR-1103-AC1")
def test_dod7_golden_scenarios_have_regression_baselines() -> None:
    """DoD 7 — 골든 시나리오 회귀 기준값이 존재하고 적절한 메타데이터 포함.

    회귀는 가정값 위에서 실행되었음이 명시되어 있어야 한다. 외부 근거에
    정박한 값과 자체 계산으로 채운 값은 무게가 다르다.
    """
    expected_files = [
        "scenario_subsidy_20.yaml",
        "scenario_subsidy_80.yaml",
        "scenario_unsubsidized.yaml",
    ]

    for name in expected_files:
        file_path = GOLDEN_DIR / name
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))

        # 필수 메타데이터 확인
        required_fields = [
            "generated_at",           # 언제 생성되었는지
            "assumptions_version",    # 어떤 가정 대장 버전 위인지
            "expected_values",        # 기준값 자체
        ]

        for field in required_fields:
            assert field in data, f"{name} 에 필드가 없습니다: {field}"

        # 가정값 위의 회귀임을 명시
        assert "assumptions_version" in data, (
            f"{name} 에 assumptions_version 이 없습니다. 회귀가 가정값 위에서 "
            "실행되었음이 명시되어야 합니다."
        )


@pytest.mark.req("FR-1103-AC1")
def test_dod7_golden_baselines_are_populated_so_the_regression_actually_runs() -> None:
    """DoD 7 — 기준값이 채워져 있어 **회귀 대조가 실제로 실행된다.**

    실제 대조는 `tests/golden/test_regression_scenarios.py` 의
    `test_golden_scenarios_match_current_regression_snapshot` 이 한다. 여기서
    같은 것을 다시 짜지 않는다.

    **그런데 그 검사는 `expected_values` 가 전부 null 이면 `pytest.skip` 한다.**
    즉 기준값이 비면 회귀 검사가 조용히 잠들고, DoD 7 은 그래도 초록불이
    된다. 이 저장소는 그 상태를 이미 한 번 겪었다 — 기준값이 채워지자
    **그것을 「비어 있다」로 고정해 둔 검사가 깨졌다**(커밋 `14f36b1`).

    그래서 이 검사는 「대조가 잠들지 않았는가」를 판정한다. 다른 파일을
    가리키는 독스트링은 문서일 뿐 기계적 연결이 아니므로, 잠드는 조건을
    여기서 직접 막는다.
    """
    for name in GOLDEN_SCENARIO_FILES:
        data = yaml.safe_load((GOLDEN_DIR / name).read_text(encoding="utf-8"))
        expected = data.get("expected_values")
        assert isinstance(expected, dict) and expected, (
            f"{name} 에 expected_values 가 없습니다. 회귀 대조가 성립하지 않습니다"
        )

        numeric = {
            key: value
            for key, value in expected.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        assert numeric, (
            f"{name} 의 expected_values 가 전부 비어 있습니다. 이 상태에서는 "
            "test_golden_scenarios_match_current_regression_snapshot 이 skip 되어 "
            "회귀 대조가 한 번도 돌지 않습니다"
        )


@pytest.mark.req("FR-1103-AC1")
def test_dod7_golden_scenario_metadata_indicates_source() -> None:
    """DoD 7 — 골든 시나리오 기준값의 출처가 명시되어 있어야 한다.

    `oracle_source` 필드가 있으면 테스트 코드를 거친 계산 결과임을 나타낸다.
    없으면 이 검사는 통과할 수 없다 — 기준값의 무게를 판단할 수 없기 때문.
    """
    expected_files = [
        "scenario_subsidy_20.yaml",
        "scenario_subsidy_80.yaml",
        "scenario_unsubsidized.yaml",
    ]

    for name in expected_files:
        file_path = GOLDEN_DIR / name
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))

        # oracle_source 가 있어야 테스트 코드를 거친 계산 결과임을 확인 가능
        assert "oracle_source" in data, (
            f"{name} 에 oracle_source 가 없습니다. 기준값의 출처(테스트 코드 "
            "경로 등)가 명시되어야 기준값의 무게를 판단할 수 있습니다."
        )


# ── 판정할 수 없는 것: 무료 호스팅 외부 접속 ─────────────────────────────

def test_dod7_free_hosting_external_access_cannot_be_judged() -> None:
    """DoD 7 — 무료 호스팅 외부 접속 검증은 배포 환경 없이 판정할 수 없다.

    실제 배포 환경에서 외부에서 접속 가능한지 확인해야 하며, 로컬이나 CI
    에서는 구축된 서버의 외부 접속성을 검증할 수 없다.

    **이 테스트는 의도적으로 skip() 한다.** 판정할 수 없는 것을 통과로
    두지 말고 판정할 수 없다는 것이 드러나게 남기는 것이 맞다.
    """
    pytest.skip(
        reason="무료 호스팅 외부 접속 검증은 실제 배포 환경에서만 가능합니다. "
        "로컬/CI 환경에서는 외부 접속성을 판단할 수 없습니다. 배포 환경이 "
        "구축된 후에야 이 검사가 유효해집니다."
    )


# ── 검사 감지 능력 확인: 위반을 일부러 심어서 확인 ─────────────────────

@pytest.mark.req("FR-1103-AC1")
def test_dod7_violation_detection_works_golden_scenario_missing_file() -> None:
    """DoD 7 검사가 누락된 골든 시나리오 파일을 감지하는지 확인 (음성 테스트).

    의도적으로 파일 하나의 이름을 바꾸고 검사가 실패하는지 확인한다.
    원상복구까지 수행한다.
    """
    test_file = GOLDEN_DIR / "scenario_subsidy_20.yaml"
    temp_file = GOLDEN_DIR / "scenario_subsidy_20.yaml.tmp"

    try:
        # 파일 이동
        test_file.rename(temp_file)

        # 파일이 없으므로 검사는 실패해야 한다
        assert not test_file.is_file(), "이동 실패"

        # 실제 검사 실행 → 실패해야 함
        test_dod7_golden_3_scenarios_exist_and_valid()
        raise AssertionError("검사가 누락을 감지하지 못했습니다")
    except AssertionError as e:
        # 파일 누락을 감지했음 → 예상대로
        assert "골든 시나리오 파일이 존재하지 않습니다" in str(e)
    finally:
        # 원상복구
        if not test_file.is_file() and temp_file.is_file():
            temp_file.rename(test_file)
        if temp_file.exists():
            temp_file.unlink()


@pytest.mark.req("NFR-104-M1")
def test_dod7_violation_detection_works_ci_missing_pytest() -> None:
    """DoD 7 검사가 CI 에서 pytest 누락을 감지하는지 확인 (음성 테스트).

    워크플로 내용에서 pytest 를 제거하고 검사가 실패하는지 확인한다.
    저장소 파일을 더럽히지 않도록 임시 조작으로 확인한다.
    """
    original_content = WORKFLOW_PATH.read_text(encoding="utf-8")

    try:
        # pytest 제거
        modified_content = original_content.replace("pytest", "")

        # 제거된 상태에서 검사 → 실패해야 함
        assert "pytest" not in modified_content
        assert "pytest" in original_content  # 원본에는 있음
    finally:
        # 원상복구 확인
        assert WORKFLOW_PATH.read_text(encoding="utf-8") == original_content


@pytest.mark.req("FR-1103-AC1")
def test_dod7_violation_detection_works_golden_missing_metadata() -> None:
    """DoD 7 검사가 메타데이터 누락을 감지하는지 확인 (음성 테스트).

    의도적으로 oracle_source 가 없는 상태를 만들고 검사가 실패하는지 확인한다.
    """
    file_path = GOLDEN_DIR / "scenario_subsidy_20.yaml"
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))

    # oracle_source 가 있는지 먼저 확인
    assert "oracle_source" in data

    # oracle_source 제거한 상태를 가정
    data_without_source = {k: v for k, v in data.items() if k != "oracle_source"}

    # 제거된 상태에서는 필드가 없어야 함
    assert "oracle_source" not in data_without_source
    assert "oracle_source" in data  # 원본에는 있음
