"""§16.3 구획표의 `FR-` 열 판정이 우연에 기대지 않게 붙든다.

`scripts/check_partition_assignment.py:60` 은 한때 `"FR-" in cells[3]` 라는
부분 문자열 검사였다 — `cells[3]` 에 `"NFR-402"` 만 있어도 참이 됐다.
R38 이 코드를 따라가 확인한 바로는 **지금은 결과가 오염되지 않는다**: 그
다음 줄의 `expand_ranges()` 가 `[A-Z]+` 로 탐욕적 매치를 해서 `"NFR-402"` 를
쪼개지 않고 한 토큰으로 통째 집어내고, 이어지는 `fr.startswith("FR-")` 가
그것을 다시 걸러내기 때문이다.

**즉 지금 안전한 이유가 두 성질(탐욕적 매치·`startswith` 재필터)의 우연한
조합이다.** 이 파일은 그 두 성질을 각각 검사로 고정해, 누군가 `[A-Z]+` 를
`[A-Z]+?`(비탐욕)로 바꾸거나 재필터를 지우면 즉시 빨간불이 나게 한다.
(경계 자체는 `scripts/check_partition_assignment.py:60` 에서 `\bFR-` 로
이미 명시했다 — `.orch/R39/result_scan_boundary.md` §1-b.)

이 게이트를 요구하는 spec 조항 ID 는 없다 — `check_partition_assignment.py`
는 §16.3 배정표 서술로만 근거가 있고 `NFR-107` 같은 전담 조항이 없다
(`.orch/R39/result_scan_boundary.md` 확인 못 함 항목 참조). 그래서 이
파일의 테스트에는 `@pytest.mark.req(...)` 를 달지 않는다 — 없는 근거를
지어내 채우지 않는다(공통 §6).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _module():
    """`scripts/` 는 패키지가 아니므로 경로로 불러온다."""
    name = "_gate_check_partition_assignment"
    if name in sys.modules:
        return sys.modules[name]

    scripts = str(REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)

    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / "check_partition_assignment.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── 1. expand_ranges() 가 "NFR-402" 를 한 토큰으로 낸다 ─────────────────
#
# 지금 옳게 도는 이유가 이 성질이다 — 이유를 검사로 고정한다.
# `[A-Z]+` 를 `[A-Z]+?`(비탐욕)로 바꾸면 "N" | "FR-402" 로 쪼개져 이 검사가
# 빨간불이 되어야 한다.


def test_expand_ranges_keeps_nfr_prefix_as_one_token() -> None:
    mod = _module()
    assert mod.expand_ranges("NFR-402") == ["NFR-402"]


def test_expand_ranges_separates_mixed_nfr_and_fr() -> None:
    mod = _module()
    assert mod.expand_ranges("NFR-402, FR-103") == ["NFR-402", "FR-103"]


def test_expand_ranges_still_expands_fr_ranges() -> None:
    mod = _module()
    assert mod.expand_ranges("FR-101~103") == ["FR-101", "FR-102", "FR-103"]


# ── 2. assigned_to 에 NFR- 이 들어가지 않는다 ───────────────────────────
#
# 합성 §16.3 표로 build_assigned_to() 를 직접 돌린다 — `_specparse` 의
# 요구사항·Phase 파싱과 무관하게 이 함수 하나만 뗀다.

_SYNTHETIC_TABLE = [
    "### 16.3 구획별 소유 경로",
    "| 구획 | 소유 경로 | 대응 FR/NFR | 통합 Wave | 비고 |",
    "|---|---|---|---|---|",
    "| **WP-1** 헬퍼 | `core/x/` | NFR-402 | 1 | NFR 단독 행 |",
    "| **WP-2** 헬퍼 | `core/y/` | FR-402 | 1 | FR 단독 행 |",
    "| **WP-3** 헬퍼 | `core/z/` | NFR-402, FR-103 | 1 | 섞인 행 |",
    "| **WP-4** 헬퍼 | `core/w/` | FR-101~103 | 1 | 범위 행 |",
    "## 17. 다음 절",
]


def test_build_assigned_to_excludes_nfr_only_row() -> None:
    mod = _module()
    assigned = mod.build_assigned_to(_SYNTHETIC_TABLE)
    for fr in assigned:
        assert not fr.startswith("NFR-"), (
            f"NFR- 이 assigned_to 에 들어갔다: {fr!r} — cells[3] 부분 문자열 "
            "검사가 NFR-402 를 통과시키고 있다"
        )


# ── 3. FR- 로 시작하는 진짜 요구사항은 여전히 잡힌다 ────────────────────
#
# 좁히다 못 잡게 되는 반대 방향 실패를 막는다.


def test_build_assigned_to_still_catches_plain_fr_row() -> None:
    mod = _module()
    assigned = mod.build_assigned_to(_SYNTHETIC_TABLE)
    assert assigned.get("FR-402") == ["WP-2"]


def test_build_assigned_to_still_catches_fr_in_mixed_row() -> None:
    mod = _module()
    assigned = mod.build_assigned_to(_SYNTHETIC_TABLE)
    assert "WP-3" in assigned.get("FR-103", [])


def test_build_assigned_to_still_expands_fr_ranges() -> None:
    mod = _module()
    assigned = mod.build_assigned_to(_SYNTHETIC_TABLE)
    assert assigned.get("FR-101") == ["WP-4"]
    assert assigned.get("FR-102") == ["WP-4"]
    assert assigned.get("FR-103") == ["WP-3", "WP-4"]
