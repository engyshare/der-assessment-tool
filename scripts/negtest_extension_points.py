"""확장점 음성 검사 — R16 이 세운 방어를 되돌려 빨간불을 확인한다.

**「확장점이 있다」와 「그 확장점을 검사가 붙들고 있다」는 다르다.**
이 저장소가 일곱 번 만난 형태이고(R8 복사 · R9 재구현 · R10 요약줄 · R13
도달 불가 · R14 배선 · R15 느슨한 패턴), 매번 *「검사는 있었다」* 로 끝났다.

그래서 각 방어를 **실제로 되돌려** 정확히 그 계약 테스트가 빨간불이 되는지
본다. 되돌려도 초록불이면 그 검사는 아무것도 붙들지 않는 것이다.

    python scripts/negtest_extension_points.py      rc=0 이면 전건 확인

**원복은 자동이다.** 실패해도 원본이 돌아온다 (`finally`).

CI 는 이것을 **차단**으로 부른다 — 검사기 자신의 감지 능력 확인이므로
경고로 두면 확장점이 조용히 무너져도 아무 일이 없다.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: (이름, 파일, 되돌릴 것, 그 자리에 넣을 것, 빨간불이어야 하는 테스트)
#:
#: 되돌리는 방식은 **조건을 죽이는 것**이다 — 방어를 지우는 것과 같은 효과이면서
#: 파일 구조를 건드리지 않아 원복이 확실하다.
CASES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "3요소를 생성 조건이 아니라 없는 것으로 (NFR-303)",
        "core/contracts/validation.py",
        "        if missing:",
        "        if False:  # NEGCHECK",
        "tests/contract/test_validation_contract.py::"
        "test_three_parts_are_a_construction_condition_not_a_check",
    ),
    (
        "빈 산출물을 차트로 허용 (FR-1004-AC1)",
        "core/contracts/chart.py",
        "        if not self.payload:",
        "        if False:  # NEGCHECK",
        "tests/contract/test_chart_contract.py::test_empty_artifact_cannot_exist",
    ),
    (
        "없는 차트를 조용히 건너뜀 (FR-1004-AC1)",
        "core/report/charts/__init__.py",
        "    if unknown:",
        "    if False:  # NEGCHECK",
        "tests/contract/test_chart_contract.py::test_unknown_tag_is_refused_not_skipped",
    ),
    (
        "구조별 지불 주체 선언을 무시하고 payer 를 직접 읽음 (FR-205)",
        "core/contracts/valuestream.py",
        "        if self.structure is not None:",
        "        if False:  # NEGCHECK",
        "tests/contract/test_payer_structure_contract.py::"
        "test_same_benefit_different_structure_different_payer",
    ),
    (
        "구조 이름 오타를 기동 시점에 안 잡음 (FR-205-AC1)",
        "core/contracts/valuestream.py",
        "        if unknown:",
        "        if False:  # NEGCHECK",
        "tests/contract/test_payer_structure_contract.py::"
        "test_unknown_structure_in_the_table_fails_at_class_definition",
    ),
    (
        "유형 A 위반을 거부하지 않고 표시만 — R15 이전 상태 (FR-402-AC2.A)",
        "core/valuestream/exclusion_table.py",
        "    if not violations:\n        return",
        "    if True:  # NEGCHECK\n        return",
        "tests/contract/test_exclusion_rules_contract.py::"
        "test_type_a_violation_is_refused_not_merely_labelled",
    ),
    (
        "★ 반대 방향 — 유형 B~D 까지 거부해 오탐 0 을 깨뜨림 (FR-402-AC1)",
        "core/valuestream/exclusion_table.py",
        "        if kind is ExclusionType.A",
        "        if kind is not None  # NEGCHECK",
        "tests/contract/test_exclusion_rules_contract.py::test_types_b_to_d_are_not_refused",
    ),
    (
        "빈 규칙표를 「배타 없음」으로 통과 (FR-402-AC4)",
        "core/valuestream/exclusion_loader.py",
        "    if not isinstance(raw_rules, list) or not raw_rules:",
        "    if False:  # NEGCHECK",
        "tests/contract/test_exclusion_rules_contract.py::"
        "test_an_empty_table_is_an_error_not_a_pass",
    ),
    (
        "기준선 없는 실행을 허용 — 자동 포함이 깨진다 (FR-607-AC1)",
        "core/contracts/casevariant.py",
        "    if not baselines:",
        "    if False:  # NEGCHECK",
        "tests/contract/test_casevariant_contract.py::"
        "test_missing_or_duplicated_baseline_is_refused",
    ),
    (
        "기준선이 맨 위가 아니어도 통과 — 결과 상단 표시가 깨진다 (FR-607-AC1)",
        "core/contracts/casevariant.py",
        "    if not ordered[0].baseline:",
        "    if False:  # NEGCHECK",
        "tests/contract/test_casevariant_contract.py::test_baseline_not_on_top_is_refused",
    ),
)


def run_case(case: tuple[str, str, str, str, str]) -> bool:
    """방어 하나를 되돌리고 해당 테스트가 빨간불인지 본다."""
    name, rel, needle, replacement, test = case
    target = ROOT / rel

    original = target.read_text(encoding="utf-8")
    if needle not in original:
        print(f"  [설정오류] 되돌릴 자리를 찾지 못했다: {rel}")
        print(f"            찾은 것: {needle!r}")
        print("            방어가 이미 없거나 코드가 바뀌었다 — 둘 다 확인이 필요하다")
        return False

    holding = Path(tempfile.mkdtemp())
    backup = holding / target.name
    shutil.copy2(target, backup)
    try:
        target.write_text(original.replace(needle, replacement, 1), encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", test,
                "-x", "--no-header", "-p", "no:cacheprovider",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        went_red = proc.returncode != 0
        mark = "빨간불" if went_red else "★ 초록불"
        print(f"  {mark:<10} {name}")
        if not went_red:
            print("             ↑ 방어를 되돌렸는데 통과했다 — 이 검사는 "
                  "아무것도 붙들지 않는다")
        return went_red
    finally:
        shutil.copy2(backup, target)
        shutil.rmtree(holding, ignore_errors=True)


def main() -> int:
    print(f"확장점 음성 검사 — {len(CASES)}종\n")
    passed = sum(run_case(case) for case in CASES)
    print(f"\n음성 테스트 {len(CASES)}종 — 통과 {passed} / 실패 {len(CASES) - passed}")
    if passed != len(CASES):
        print("\n초록불이 난 항목은 확장점이 아니라 그냥 코드다")
        return 1
    print("전건 통과 — R16 확장점 다섯이 실제로 붙들려 있다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
