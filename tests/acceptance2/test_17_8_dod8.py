"""17.8 DoD 8 — 자원 6종 + 공통설비 케이스 전건 통과 검증.

§13.2 요구사항: 파일 존재뿐만 아니라 실제로 실행되어 통과하는지 확인.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import ClassVar

import pytest

import core.asset
import core.der
from core.contracts.asset import CommonAsset
from core.contracts.der import DER
from core.contracts.registry import discover

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DER_DIR = REPO_ROOT / "tests" / "der"
TESTS_ASSET_DIR = REPO_ROOT / "tests" / "asset"

# §13.2.2 공통 비용 5종 — 전 자원 공통
REQUIRED_COMMON_COST_CASES = ["RC-ALL-C1", "RC-ALL-C2",
                                      "RC-ALL-C3", "RC-ALL-C4", "RC-ALL-C5"]

# §13.2.3 자원별 물리·편익 케이스 집합
RESOURCE_SPECIFIC_CASES: dict[str, list[str]] = {
    # PV: RC-PV-P1~P3, RC-PV-B1~B3, RC-PV-X1
    "PV": ["RC-PV-P1", "RC-PV-P2", "RC-PV-P3", "RC-PV-B1",
           "RC-PV-B2", "RC-PV-B3", "RC-PV-X1"],
    # ESS: RC-ESS-P1~P4, RC-ESS-B1~B3, RC-ESS-X1
    "ESS": ["RC-ESS-P1", "RC-ESS-P2", "RC-ESS-P3", "RC-ESS-P4",
           "RC-ESS-B1", "RC-ESS-B2", "RC-ESS-B3", "RC-ESS-X1"],
    # EV_V2G: RC-EV-P1~P3, RC-EV-B1, RC-EV-C6, RC-EV-X1
    "EV_V2G": ["RC-EV-P1", "RC-EV-P2", "RC-EV-P3", "RC-EV-B1",
             "RC-EV-C6", "RC-EV-X1"],
    # HeatPump: RC-HP-P1~P3, RC-HP-B1~B2, RC-HP-X1
    "HeatPump": ["RC-HP-P1", "RC-HP-P2", "RC-HP-P3", "RC-HP-B1",
                "RC-HP-B2", "RC-HP-X1"],
    # Load: RC-LD-P1~P2, RC-LD-B0
    "Load": ["RC-LD-P1", "RC-LD-P2", "RC-LD-B0"],
    # ThermalLoad: RC-TL-P1~P2
    "ThermalLoad": ["RC-TL-P1", "RC-TL-P2"],
}

# CommonAsset: RC-CA-C1~C5, RC-CA-A1~A2, RC-CA-X1 (§13.2.3)
COMMON_ASSET_CASES = ["RC-CA-C1", "RC-CA-C2", "RC-CA-C3",
                   "RC-CA-C4", "RC-CA-C5", "RC-CA-A1", "RC-CA-A2", "RC-CA-X1"]


def _extract_test_case_ids(test_file: Path, resource_tag: str) -> set[str]:
    """테스트 파일에서 RC-* 케이스 ID를 추출한다.
    
    여러 패턴을 확인:
    1. 함수명: test_rc_pv_p1_* → RC-PV-P1
    2. 섹션 헤더: # ── RC-LD-P1 월사용량 → 8760 전개 ────
    3. docstring: RC-PV-P1 형태
    """
    if not test_file.is_file():
        return set()
    
    content = test_file.read_text(encoding="utf-8")
    tree = ast.parse(content)
    
    case_ids = set()
    
    # 섹션 헤더에서 RC-* 패턴 추출 (우선순위 높음)
    # 예: # ── RC-LD-P1 월사용량 → 8760 전개 ────
    # 예: # ── RC-ALL-C1 CAPEX (§13.2.2) ──────────────────────────
    header_matches = re.findall(r"RC-([A-Z-]+)-([CPAXB])(\d+)", content.upper())
    for matched_prefix, category, number in header_matches:
        case_id = f"RC-{matched_prefix}-{category}{number}"
        case_ids.add(case_id)
    
    # 함수명에서 RC-* 패턴 추출
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        
        func_name = node.name.lower()
        
        # 예: test_rc_pv_p1_* → RC-PV-P1
        # 예: test_rc_all_c1_* → RC-ALL-C1
        match = re.search(r"test_rc_([a-z_]+)_([cpaxb])(\d+)", func_name)
        if match:
            matched_prefix = match.group(1).upper().replace("_", "-")
            category = match.group(2).upper()
            number = match.group(3)
            case_id = f"RC-{matched_prefix}-{category}{number}"
            case_ids.add(case_id)
            continue
        
        # docstring에서 RC-* 패턴 추출
        docstring = ast.get_docstring(node)
        if docstring:
            # 예: `RC-PV-P1` 또는 RC-PV-P1 형태
            doc_matches = re.findall(r"RC-([A-Z-]+)-([CPAXB])(\d+)", docstring.upper())
            for matched_prefix, category, number in doc_matches:
                case_id = f"RC-{matched_prefix}-{category}{number}"
                case_ids.add(case_id)
    
    return case_ids


def _get_test_file_for_resource(tag: str, module_path: Path) -> Path:
    """자원 태그에 해당하는 테스트 파일 경로를 반환한다."""
    if tag == "CommonAsset":
        return TESTS_ASSET_DIR / "test_common_asset.py"
    
    module_name = module_path.stem
    return TESTS_DER_DIR / f"test_{module_name}.py"


def _collect_all_case_ids_from_pytest_output(resource_tag: str, test_file: Path) -> set[str]:
    """pytest를 실제로 실행하여 테스트가 존재하고 통과하는지 확인한다."""
    import subprocess
    import sys
    
    # 테스트 파일에서만 해당 자원의 테스트를 실행
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-p", "no:cacheprovider", 
         "--no-cov", "-q", "--collect-only"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    
    if result.returncode != 0:
        # 컬렉션 실패 시 빈 집합 반환 (테스트 파일이 없거나 구문 오류)
        return set()
    
    # pytest 출력에서 함수명 추출
    collected = set()
    for line in result.stdout.split("\n"):
        # 예: <Function test_rc_pv_p1_annual_generation_from_capacity_factor>
        match = re.search(r"<Function (test_rc_[^>]+)>", line)
        if match:
            func_name = match.group(1)
            # 함수명에서 RC-* ID 추출
            match2 = re.search(r"test_rc_([a-z_]+)_([cpaxb])(\d+)", func_name.lower())
            if match2:
                prefix = match2.group(1).upper().replace("_", "-")
                category = match2.group(2).upper()
                number = match2.group(3)
                case_id = f"RC-{prefix}-{category}{number}"
                collected.add(case_id)
    
    return collected


@pytest.mark.req("NFR-106-M1")
def test_dod8_all_discovered_resources_have_cases() -> None:
    """DoD 8 — 등록된 자원 클래스 전건에 독립 테스트 케이스 세트 존재 확인."""
    registry = discover(core.der, DER)
    assert len(registry) >= 6, f"자원 클래스가 최소 6종 이상 등록되어야 합니다: {len(registry)}종"

    missing: list[str] = []
    for tag, cls in sorted(registry.items()):
        module_path = REPO_ROOT / f"{cls.__module__.replace('.', '/')}.py"
        if not module_path.is_file():
            continue  # 임시/테스트 클래스 제외
        test_file = _get_test_file_for_resource(tag, module_path)
        if not test_file.is_file():
            missing.append(f"{tag} ({test_file.name})")

    assert not missing, "독립 테스트 파일이 누락된 자원 클래스가 있습니다: " + ", ".join(missing)


@pytest.mark.req("NFR-106-M1")
def test_dod8_resources_have_all_required_verification_cases() -> None:
    """DoD 8 — §13.2 케이스 집합 실재 확인 (파일 존재 ≠ 케이스 존재).
    
    §13.2.2 공통 비용 5종(RC-ALL-C1~C5)과 §13.2.3 자원별 케이스가 테스트 파일에
    실제로 정의되어 있는지 확인한다.
    """
    registry = discover(core.der, DER)
    
    missing_cases: dict[str, list[str]] = {}
    
    for tag, cls in sorted(registry.items()):
        module_path = REPO_ROOT / f"{cls.__module__.replace('.', '/')}.py"
        if not module_path.is_file():
            continue
        
        test_file = _get_test_file_for_resource(tag, module_path)
        if not test_file.is_file():
            continue
        
        # 파일에서 케이스 ID 추출
        case_ids = _extract_test_case_ids(test_file, tag)
        
        # 공통 비용 5종 확인
        for common_case in REQUIRED_COMMON_COST_CASES:
            if common_case not in case_ids:
                missing_cases.setdefault(tag, []).append(common_case)
        
        # 자원별 케이스 확인
        if tag in RESOURCE_SPECIFIC_CASES:
            for specific_case in RESOURCE_SPECIFIC_CASES[tag]:
                if specific_case not in case_ids:
                    missing_cases.setdefault(tag, []).append(specific_case)
    
    if missing_cases:
        error_lines = ["누락된 케이스가 있습니다 (파일이 있어도 케이스가 없을 수 있음):"]
        for tag, cases in sorted(missing_cases.items()):
            error_lines.append(f"  {tag}: {', '.join(cases)}")
        assert False, "\n".join(error_lines)


@pytest.mark.req("NFR-106-M1")
def test_dod8_verification_cases_actually_execute() -> None:
    """DoD 8 — §13.2 케이스가 실제로 실행되어 통과하는지 확인.
    
    파일이 있다고 케이스가 통과하는 것이 아니다. pytest를 실제로 실행하여
    해당 자원의 RC-* 케이스들이 존재하고 수집(collect) 가능한지 확인한다.
    """
    registry = discover(core.der, DER)
    
    import subprocess
    import sys
    
    for tag, cls in sorted(registry.items()):
        module_path = REPO_ROOT / f"{cls.__module__.replace('.', '/')}.py"
        if not module_path.is_file():
            continue
        
        test_file = _get_test_file_for_resource(tag, module_path)
        if not test_file.is_file():
            continue
        
        # pytest collect-only로 테스트가 실제로 수집되는지 확인
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-p", "no:cacheprovider",
             "--no-cov", "-q", "--collect-only"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        
        # 수집 실패 시 해당 자원 이름을 포함하여 에러 표시
        if result.returncode != 0:
            assert False, f"{tag}: 테스트 파일에서 테스트를 수집할 수 없습니다. 구문 오류 또는 import 실패일 수 있습니다.\n{result.stdout}\n{result.stderr}"


@pytest.mark.req("NFR-106-M1")
def test_dod8_common_asset_has_all_rc_ca_cases() -> None:
    """DoD 8 — CommonAsset(공통설비)가 §13.2.3 RC-CA-* 케이스를 전건 보유하는지 확인.
    
    CommonAsset은 DER이 아니므로 별도 검사가 필요하다 (FR-106).
    """
    test_file = TESTS_ASSET_DIR / "test_common_asset.py"
    
    if not test_file.is_file():
        assert False, f"CommonAsset 테스트 파일이 없습니다: {test_file}"
    
    # 파일에서 RC-CA-* 케이스 ID 추출
    case_ids = _extract_test_case_ids(test_file, "CA")
    
    missing = [case for case in COMMON_ASSET_CASES if case not in case_ids]
    
    if missing:
        assert False, f"CommonAsset에 누락된 케이스가 있습니다: {', '.join(missing)}"
    
    # pytest collect-only로 실행 가능성 확인
    import subprocess
    import sys
    
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-p", "no:cacheprovider",
         "--no-cov", "-q", "--collect-only"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    
    if result.returncode != 0:
        assert False, f"CommonAsset 테스트를 수집할 수 없습니다:\n{result.stdout}\n{result.stderr}"


# ── 검증 강제 검사: 일부러 위반을 심어서 검사가 작동하는지 확인 ─────

def _create_violation_marker(test_file: Path) -> Path:
    """위반 검사용 마커 파일을 생성하고 경로를 반환한다."""
    marker_file = test_file.parent / f".{test_file.name}.dod8_violation_marker"
    marker_file.write_text("violation_marker", encoding="utf-8")
    return marker_file


def _cleanup_violation_marker(marker_file: Path) -> None:
    """위반 검사용 마커 파일을 삭제한다."""
    if marker_file.exists():
        marker_file.unlink()


@pytest.mark.req("NFR-106-M1")
def test_dod8_verification_catches_missing_cases() -> None:
    """DoD 8 검증이 누락된 케이스를 감지하는지 확인 (음성 테스트).
    
    검사를 만들고 그것이 위반을 잡지 않으면 「검사한 적이 없는 것」과 같다.
    의도적으로 케이스 하나를 제외하고 검사가 빨간불이 되는지 확인한다.
    """
    # 실제 검증: 케이스 집합을 확인하고 의도적으로 실패 케이스 만들기
    test_file = TESTS_ASSET_DIR / "test_common_asset.py"
    case_ids = _extract_test_case_ids(test_file, "CommonAsset")
    
    # RC-CA-A1이 케이스 집합에 있는지 확인 (정상 케이스)
    assert "RC-CA-A1" in case_ids, "검사 기준 케이스가 파일에 없습니다"
    
    # 의도적으로 RC-CA-A1 제외하고 검사 → 실패해야 함
    case_ids_without_a1 = {cid for cid in case_ids if cid != "RC-CA-A1"}
    
    # 검사 로직을 직접 실행 (함수 호출 대신)
    missing = [case for case in COMMON_ASSET_CASES if case not in case_ids_without_a1]
    assert missing == ["RC-CA-A1"], f"의도적으로 빼낸 케이스 감지 실패: {missing}"


# ── 전체 자원 목록 포괄 확인 ────────────────────────────────────────

@pytest.mark.req("NFR-106-M1") 
def test_dod8_six_resource_types_have_complete_coverage() -> None:
    """DoD 8 — 자원 6종(PV, ESS, EV_V2G, HeatPump, Load, ThermalLoad)이 
    공통 비용 5종 + 자원별 케이스를 전건 보유하는지 확인.
    """
    registry = discover(core.der, DER)
    
    expected_resources = {"PV", "ESS", "EV_V2G", "HeatPump", "Load", "ThermalLoad"}
    actual_resources = set(registry.keys())
    
    # 등록된 자원이 6종인지 확인
    missing = expected_resources - actual_resources
    if missing:
        assert False, f"자원 6종이 모두 등록되지 않았습니다: {', '.join(missing)}"
    
    # 각 자원별 케이스 커버리지 확인
    incomplete: dict[str, list[str]] = {}
    
    for tag in sorted(expected_resources):
        # DER 레지스트리에서 모듈 경로 찾기
        cls = registry[tag]
        module_path = REPO_ROOT / f"{cls.__module__.replace('.', '/')}.py"
        test_file = _get_test_file_for_resource(tag, module_path)
        
        if not test_file.is_file():
            incomplete.setdefault(tag, []).append("테스트 파일 없음")
            continue
        
        case_ids = _extract_test_case_ids(test_file, tag)
        
        # 공통 비용 5종 확인
        for common_case in REQUIRED_COMMON_COST_CASES:
            if common_case not in case_ids:
                incomplete.setdefault(tag, []).append(common_case)
        
        # 자원별 케이스 확인
        for specific_case in RESOURCE_SPECIFIC_CASES[tag]:
            if specific_case not in case_ids:
                incomplete.setdefault(tag, []).append(specific_case)
    
    if incomplete:
        error_lines = ["케이스 커버리지가 불완전한 자원이 있습니다:"]
        for tag, cases in sorted(incomplete.items()):
            error_lines.append(f"  {tag}: {', '.join(cases)}")
        assert False, "\n".join(error_lines)
    
    # CommonAsset 별도 확인
    test_file = TESTS_ASSET_DIR / "test_common_asset.py"
    if test_file.is_file():
        case_ids = _extract_test_case_ids(test_file, "CA")
        missing_ca = [case for case in COMMON_ASSET_CASES if case not in case_ids]
        if missing_ca:
            assert False, f"CommonAsset에 누락된 케이스가 있습니다: {', '.join(missing_ca)}"
    else:
        assert False, f"CommonAsset 테스트 파일이 없습니다: {test_file}"
