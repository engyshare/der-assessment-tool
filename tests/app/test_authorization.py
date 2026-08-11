"""14.3 — 인가 (SC-2, NFR-403-AC1).

**음성(타인 차단)과 양성(정당 접근 통과)을 둘 다 본다** (브리프 14.3).
전부 막는 구현도 음성 검사만으로는 만점을 받는다.
"""
from __future__ import annotations

import pytest

from app.security.authorization import (
    AccessDecision,
    assert_can_access,
    can_access_scenario,
    is_owner,
)


@pytest.mark.req("NFR-403-AC1", "SC-2")
def test_owner_access_allowed() -> None:
    """양성 — 소유자 접근은 허용.

    오라클: 순위 4 (정의 항등식). resource_owner_id == requesting_user_id.
    """
    decision = can_access_scenario(
        resource_owner_id=1, requesting_user_id=1
    )
    assert decision.allowed


@pytest.mark.req("SC-2", "NFR-403-AC1")
def test_non_owner_without_token_denied() -> None:
    """음성 — 타인(유효 토큰 없음)은 거부 (NFR-403-AC1).

    오라클: 순위 4. resource_owner_id != requesting_user_id, share_token 없음.
    """
    decision = can_access_scenario(
        resource_owner_id=1, requesting_user_id=2
    )
    assert not decision.allowed
    assert "권한이 없다" in decision.reason


def test_non_owner_with_valid_share_token_allowed() -> None:
    """양성 — 유효 공유 토큰 보유자는 허용 (SC-2 예외 조항)."""
    decision = can_access_scenario(
        resource_owner_id=1,
        requesting_user_id=2,
        share_token="abc123",
        valid_share_tokens=("abc123",),
    )
    assert decision.allowed


def test_non_owner_with_invalid_share_token_denied() -> None:
    """음성 — 잘못된 토큰은 거부. 임의 토큰 통과 아니다."""
    decision = can_access_scenario(
        resource_owner_id=1,
        requesting_user_id=2,
        share_token="wrong",
        valid_share_tokens=("abc123",),
    )
    assert not decision.allowed


def test_assert_can_access_raises_on_deny() -> None:
    """거부 시 ``PermissionError`` — 엔드포인트에서 한 줄 검사."""
    with pytest.raises(PermissionError, match="권한이 없다"):
        assert_can_access(resource_owner_id=1, requesting_user_id=99)


def test_assert_can_access_passes_for_owner() -> None:
    """소유자는 예외 없이 통과."""
    assert_can_access(resource_owner_id=1, requesting_user_id=1)  # 예외 없음


def test_is_owner_simple_check() -> None:
    """``is_owner`` — 공유 토큰 없이 «내 것인가» 만 본다."""
    assert is_owner(1, 1) is True
    assert is_owner(1, 2) is False


def test_deny_decision_carries_reason() -> None:
    """거부 사유가 있어야 로그가 의미를 갖는다."""
    decision = can_access_scenario(resource_owner_id=1, requesting_user_id=2)
    assert isinstance(decision, AccessDecision)
    assert decision.reason  # 빈 문자열이 아니어야
