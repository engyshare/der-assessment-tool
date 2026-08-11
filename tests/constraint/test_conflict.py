"""8.8 — 제약 충돌 검출 (FR-403-AC1~AC4).

음성(충돌 심으면 잡힌다) + 양성(정상 제약은 통과)를 함께 본다. **``math.inf``
sentinel** 이 핵심 — 유한 대형 상수를 쓰면 «제약 없음» 이 «매우 큰 제약» 이 된다.
"""
from __future__ import annotations

import math

import pytest

from core.constraint import ConstraintRegistry
from core.contracts.schemas import ConstraintDecl


def _decl(
    source: str, target: str, kind: str, values: list[float]
) -> ConstraintDecl:
    return ConstraintDecl(
        source_tag=source, target=target, kind=kind, values=tuple(values)
    )


# ── FR-403-AC3 — 충돌 검출 (음성: 심으면 잡힌다) ─────────────────────────

@pytest.mark.req("FR-403-AC1", "FR-403-AC2", "FR-403-AC3")
def test_conflict_min_above_max_is_detected() -> None:
    """min 제약이 max 제약을 넘으면 충돌 — 원인 편익과 함께 보고.

    오라클: 순위 4 (§13.0.1 ④). ESS 방전 하한(예비력) 10 kW 와 SOC 상한 5 kW 가
    어긋나면 ConflictAt 를 반환한다.
    """
    reg = ConstraintRegistry()
    reg.register(_decl("DemandResponse", "ess.discharge_kw", "min", [10.0, 10.0]))
    reg.register(_decl("PeakShaving", "ess.discharge_kw", "max", [5.0, 8.0]))
    conflicts = reg.detect_conflicts()
    assert len(conflicts) == 2, f"충돌 2건이어야 한다 (각 시각): {conflicts}"
    # 기여 편익 — min 은 DemandResponse, max 는 PeakShaving
    c0 = conflicts[0]
    assert c0.target == "ess.discharge_kw"
    assert c0.bound_min == 10.0
    assert c0.bound_max == 5.0
    assert "DemandResponse" in c0.min_contributors
    assert "PeakShaving" in c0.max_contributors


def test_conflict_render_is_human_readable() -> None:
    """ConflictAt.render() 는 사람이 읽는 문장 — 원인 편익을 드러낸다."""
    reg = ConstraintRegistry()
    reg.register(_decl("DemandResponse", "x", "min", [10.0]))
    reg.register(_decl("PeakShaving", "x", "max", [5.0]))
    conflicts = reg.detect_conflicts()
    assert len(conflicts) == 1
    rendered = conflicts[0].render()
    assert "하한" in rendered and "상한" in rendered
    assert "DemandResponse" in rendered and "PeakShaving" in rendered


# ── 양성 — 정상 제약은 충돌 없음 ──────────────────────────────────────────

def test_no_conflict_when_min_below_max() -> None:
    """min 5 ≤ max 10 → 충돌 없음.

    오라클: 순위 4. 정상 제약 구성은 통과해야 한다 — 거짓 충돌이 나면
    실제 충돌이 묻힌다.
    """
    reg = ConstraintRegistry()
    reg.register(_decl("A", "x", "min", [5.0, 3.0]))
    reg.register(_decl("B", "x", "max", [10.0, 8.0]))
    assert reg.detect_conflicts() == []


def test_no_conflict_when_only_one_side_present() -> None:
    """한쪽(또는 양쪽) 제약이 없으면 충돌 없음.

    오라클: 순위 4. 제약이 없는 시각은 math.inf 가 채워져 유한 제약과 충돌하지
    않는다 — 이것이 ``math.inf`` sentinel 의 이유다 (FR-403-AC4).
    """
    reg = ConstraintRegistry()
    # min 만 있고 max 없음
    reg.register(_decl("A", "x", "min", [10.0, 20.0]))
    assert reg.detect_conflicts() == []
    # max 만 있고 min 없음
    reg2 = ConstraintRegistry()
    reg2.register(_decl("B", "y", "max", [5.0]))
    assert reg2.detect_conflicts() == []


# ── FR-403-AC4 — math.inf sentinel ────────────────────────────────────────

@pytest.mark.req("FR-403-AC4")
def test_inf_sentinel_in_min_constraint_means_no_lower_bound() -> None:
    """math.inf 를 sentinel 로 쓴다 — 1e30 같은 유한 상수는 안 된다.

    오라클: 순위 4. min 제약 전체가 inf 면 «제약 없음» → 유한 max 와 충돌 안 함.
    1e30 을 썼다면 bound_min=1e30 이 되어 유한 max 와 거짓 충돌이 난다.
    """
    reg = ConstraintRegistry()
    reg.register(_decl("A", "x", "min", [math.inf, math.inf]))
    reg.register(_decl("B", "x", "max", [100.0, 50.0]))
    assert reg.detect_conflicts() == []


def test_finite_sentinel_would_cause_false_conflict() -> None:
    """문서화 — 유한 대형 상수(1e30) 를 쓰면 어떤 일이 나는지 보여주는 역유도.

    오라클: 순위 4. 이 테스트는 ``1e30`` 을 직접 쓰지 «않는다» — 그것이
    sentinel 로 쓰일 때의 함정을 문서로 드러내기 위함이다. ``math.inf`` 만이
    «제약 없음» 을 정확히 나타낸다.
    """
    # 올바른 사용: math.inf → 충돌 없음
    reg_ok = ConstraintRegistry()
    reg_ok.register(_decl("A", "x", "min", [math.inf]))
    reg_ok.register(_decl("B", "x", "max", [100.0]))
    assert reg_ok.detect_conflicts() == []

    # 그래도 유한 대형을 쓰면 어떻게 되는지 — same registry, finite value
    reg_bad = ConstraintRegistry()
    reg_bad.register(_decl("A", "x", "min", [1e30]))
    reg_bad.register(_decl("B", "x", "max", [100.0]))
    conflicts = reg_bad.detect_conflicts()
    assert len(conflicts) == 1, (
        "1e30 을 sentinel 으로 쓰면 «제약 없음» 이 «매우 큰 제약» 이 되어 "
        "거짓 충돌이 난다 — 이것이 math.inf 를 써야 하는 이유다 (FR-403-AC4)"
    )


# ── FR-403-AC1 — min/max 합성 규칙 ────────────────────────────────────────

@pytest.mark.req("FR-403-AC1")
def test_multiple_min_constraints_take_max() -> None:
    """min 제약이 여럿이면 각 시각의 max 가 유효 min — 가장 강한 하한.

    FR-403-AC1(편익별 제약을 단일 시계열로 min/max 합성)의 다중소스 케이스
    실검증 — 소스 2개(A, B)의 min 을 합성한다 (§17.17 — 마커만 추가)."""
    reg = ConstraintRegistry()
    reg.register(_decl("A", "x", "min", [5.0, 10.0]))
    reg.register(_decl("B", "x", "min", [8.0, 3.0]))
    composed = reg.compose()["x"]
    assert composed.bound_min == [8.0, 10.0]  # 각 시각의 max


@pytest.mark.req("FR-403-AC1")
def test_multiple_max_constraints_take_min() -> None:
    """max 제약이 여럿이면 각 시각의 min 이 유효 max — 가장 강한 상한.

    FR-403-AC1 다중소스 케이스 실검증 — 소스 2개(A, B)의 max 를 합성한다
    (§17.17 — 마커만 추가)."""
    reg = ConstraintRegistry()
    reg.register(_decl("A", "x", "max", [20.0, 5.0]))
    reg.register(_decl("B", "x", "max", [15.0, 8.0]))
    composed = reg.compose()["x"]
    assert composed.bound_max == [15.0, 5.0]  # 각 시각의 min


def test_tie_records_multiple_contributors() -> None:
    """동점이면 기여자를 모두 기록 — 한 명만 적으면 동점에서 누락이 생긴다 (FR-403-AC2).

    오라클: 순위 4 (§13.0.1 ④). 두 min 제약이 같은 값이면 두 편익 모두 기여자.
    """
    reg = ConstraintRegistry()
    reg.register(_decl("A", "x", "min", [10.0]))
    reg.register(_decl("B", "x", "min", [10.0]))  # 동점
    composed = reg.compose()["x"]
    assert set(composed.min_contributors[0]) == {"A", "B"}


def test_mismatched_step_lengths_rejected() -> None:
    """같은 target 의 제약 시계열 길이가 다르면 거부 — 합성이 어긋난다."""
    reg = ConstraintRegistry()
    reg.register(_decl("A", "x", "min", [1.0, 2.0, 3.0]))
    reg.register(_decl("B", "x", "max", [1.0, 2.0]))  # 길이 다름
    with pytest.raises(ValueError, match="길이가 다릅니다"):
        reg.compose()


def test_decl_rejects_nan() -> None:
    """ConstraintDecl 은 NaN 을 거부 — NaN 과의 비교는 항상 거짓이라 합성이 무력화된다."""
    with pytest.raises(ValueError, match="NaN"):
        ConstraintDecl(
            source_tag="A", target="x", kind="min", values=(float("nan"),)
        )
