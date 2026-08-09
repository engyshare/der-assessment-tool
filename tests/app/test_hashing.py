"""14.1 — 인증 해싱 (SC-1, NFR-401-AC1).

**Argon2id 를 썼는지가 테스트로 드러난다** (요청 사항). 해시 문자열이
``$argon2id$`` 프리픽스로 시작하는지 검사한다. bcrypt 를 썼다면 ``$2b$``.
"""
from __future__ import annotations

import pytest

from app.security.hashing import (
    MIN_MEMORY_COST,
    MIN_TIME_COST,
    hash_password,
    is_argon2id,
    reset_hasher_for_testing,
    verify_password,
)


@pytest.mark.req("SC-1")
def test_hash_is_argon2id() -> None:
    """해시가 Argon2id 알고리즘을 썼는지 — ``$argon2id$`` 프리픽스로 판정.

    오라클: 순위 4 (정의 항등식 — 해시 문자열 포맷).
    """
    hashed = hash_password("secret123!")
    assert is_argon2id(hashed), (
        f"해시가 Argon2id 가 아니다: {hashed[:20]}... — NFR-401-AC1 이 "
        "Argon2id 를 먼저 열거하며 GPU 대량 시도 공격에 더 강하다"
    )
    assert hashed.startswith("$argon2id$")


@pytest.mark.req("NFR-401-AC1")
def test_verify_accepts_correct_password() -> None:
    """올바른 비밀번호는 True. Argon2id verify."""
    hashed = hash_password("correct-password")
    assert verify_password("correct-password", hashed) is True


def test_verify_rejects_wrong_password() -> None:
    """틀린 비밀번호는 False (예외 아님). 사용자 열거 공격 회피."""
    hashed = hash_password("correct-password")
    assert verify_password("wrong-password", hashed) is False


def test_each_hash_has_random_salt() -> None:
    """같은 평문도 매번 다른 해시 — 솔트가 무작위여야 한다."""
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2, "같은 평문이 같은 해시 — 솔트가 없거나 고정이다"
    # 둘 다 Argon2id 여야
    assert is_argon2id(h1) and is_argon2id(h2)


def test_cost_below_floor_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """OWASP 최소(time_cost≥2, memory_cost≥19456) 아래면 거부.

    정책 수치를 소스에 박지 않되 **하한 검사는 코드에 둔다** (브리프 14.1).
    환경변수로 낮은 값을 주면 예외.
    """
    reset_hasher_for_testing()
    monkeypatch.setenv("ARGON2_TIME_COST", "1")  # 하한 2 아래
    from app.security.hashing import get_hasher
    with pytest.raises(ValueError, match="time_cost"):
        get_hasher()
    reset_hasher_for_testing()


def test_memory_cost_below_floor_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """memory_cost 하한 아래 거부."""
    reset_hasher_for_testing()
    monkeypatch.setenv("ARGON2_MEMORY_COST", "1024")  # 하한 19456 아래
    from app.security.hashing import get_hasher
    with pytest.raises(ValueError, match="memory_cost"):
        get_hasher()
    reset_hasher_for_testing()


def test_floors_match_owasp_minimum() -> None:
    """하한 상수가 OWASP 2023 Argon2id 최소 권장인지 — 회귀 방지."""
    assert MIN_TIME_COST >= 2
    assert MIN_MEMORY_COST >= 19456


# 환경 정리 — 다른 테스트가 기본 해셔를 쓸 수 있게
@pytest.fixture(autouse=True)
def _reset_hasher() -> object:
    yield
    reset_hasher_for_testing()
