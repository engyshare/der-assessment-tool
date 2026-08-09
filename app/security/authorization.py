"""인가 — 작업 14.3 / SC-2 · NFR-403-AC1.

시나리오 접근은 **소유자 또는 유효 공유 토큰 보유자** 로 제한한다 (SC-2).

**음성과 양성을 둘 다 본다** (브리프 14.3). 전부 막는 구현도 음성 검사만으로는
만점을 받는다 — 정당한 소유자 접근이 통과하는지(양성)와 타인 접근이 차단되는지
(음성)를 같은 무게로 검사한다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessDecision:
    """인가 판정 — 허용 여부와 거부 사유. 거부 사유가 있어야 로그가 의미를 갖는다."""

    allowed: bool
    reason: str = ""

    @classmethod
    def allow(cls, reason: str = "") -> AccessDecision:
        return cls(allowed=True, reason=reason)

    @classmethod
    def deny(cls, reason: str) -> AccessDecision:
        return cls(allowed=False, reason=reason)


def can_access_scenario(
    *,
    resource_owner_id: int,
    requesting_user_id: int,
    share_token: str | None = None,
    valid_share_tokens: tuple[str, ...] = (),
) -> AccessDecision:
    """시나리오 접근 인가 — 소유자이거나 유효 공유 토큰 보유자.

    소유자: ``resource_owner_id == requesting_user_id``.
    공유 토큰: ``share_token`` 이 ``valid_share_tokens`` 안에 있으면 허용 —
    소유자가 발급한 토큰이어야 한다 (임의 토큰 통과 아님).
    """
    if resource_owner_id == requesting_user_id:
        return AccessDecision.allow("소유자")
    if share_token is not None and share_token in valid_share_tokens:
        return AccessDecision.allow("유효 공유 토큰")
    return AccessDecision.deny(
        f"사용자 {requesting_user_id} 은(는) 리소스(소유자 {resource_owner_id}) "
        "에 접근할 권한이 없다 — 소유자가 아니며 유효 공유 토큰도 없다 (SC-2)"
    )


def assert_can_access(
    *,
    resource_owner_id: int,
    requesting_user_id: int,
    share_token: str | None = None,
    valid_share_tokens: tuple[str, ...] = (),
) -> None:
    """인가 판정 — 거부 시 ``PermissionError``.

    엔드포인트에서 ``assert_can_access(...)`` 한 줄로 권한을 검사한다.
    FastAPI 의존성으로 감싸는 것은 14.6 라우터 단에서 한다.
    """
    decision = can_access_scenario(
        resource_owner_id=resource_owner_id,
        requesting_user_id=requesting_user_id,
        share_token=share_token,
        valid_share_tokens=valid_share_tokens,
    )
    if not decision.allowed:
        raise PermissionError(decision.reason)


def is_owner(resource_owner_id: int, requesting_user_id: int) -> bool:
    """단순 소유자 판정 — 공유 토큰 없이 «내 것인가» 만 본다."""
    return resource_owner_id == requesting_user_id
