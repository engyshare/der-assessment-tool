"""14.2 — 세션 쿠키 정책 (SC-1, FR-901-AC1).

세 속성(HttpOnly, Secure, SameSite=Lax) 모두 필수. 하나라도 빠지면 공격 경로.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security.auth import (
    COOKIE_HTTPONLY,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    SESSION_TTL_SECONDS,
    SessionPolicy,
    authenticate,
    build_session_cookie_kwargs,
)


@pytest.mark.req("FR-901-AC1")
def test_session_cookie_has_all_three_security_attributes() -> None:
    """SC-1 — HttpOnly + Secure + SameSite=Lax. 셋 다 필수."""
    policy = SessionPolicy()
    assert policy.httponly is True
    assert policy.secure is True
    assert policy.samesite == "lax"


@pytest.mark.req("SC-1")
def test_policy_violation_detected() -> None:
    """세 속성 중 하나라도 꺼지면 예외 — SC-1 위반."""
    with pytest.raises(ValueError, match="SC-1"):
        SessionPolicy(secure=False).assert_sc1_compliant()
    with pytest.raises(ValueError, match="SC-1"):
        SessionPolicy(httponly=False).assert_sc1_compliant()
    with pytest.raises(ValueError, match="SC-1"):
        SessionPolicy(samesite="none").assert_sc1_compliant()


def test_cookie_kwargs_pass_to_fastapi() -> None:
    """``set_cookie`` 에 넘길 kwargs 가 세 속성을 다닌다."""
    kwargs = build_session_cookie_kwargs(SessionPolicy())
    assert kwargs["httponly"] is True
    assert kwargs["secure"] is True
    assert kwargs["samesite"] == "lax"


def test_default_ttl_is_24h() -> None:
    """FR-901-AC1 — 기본 세션 만료 24시간."""
    assert SESSION_TTL_SECONDS == 24 * 3600


def test_authenticate_with_correct_password() -> None:
    """저장된 해시와 평문 비교 — 성공."""
    from app.security.hashing import hash_password
    h = hash_password("pw")
    assert authenticate(email="x@y", password="pw", stored_hash=h) is True


def test_authenticate_with_wrong_password_returns_false() -> None:
    """실패는 False — 예외로 두면 사용자 열거(user enumeration) 공격에 쓰인다."""
    from app.security.hashing import hash_password
    h = hash_password("pw")
    assert authenticate(email="x@y", password="wrong", stored_hash=h) is False


def test_constants_immutable_intent() -> None:
    """기본 상수가 켜짐 — 회귀 방지. 누군가 기본을 끄는 것을 잡는다."""
    assert COOKIE_HTTPONLY is True
    assert COOKIE_SECURE is True
    assert COOKIE_SAMESITE == "lax"


@pytest.mark.req("FR-901-AC1")
def test_signup_and_login_flow() -> None:
    """DB 기반 회원가입 및 로그인 흐름 검증 (FR-901-AC1)."""
    client = TestClient(create_app())
    # 1. 회원가입 성공
    res_signup = client.post(
        "/auth/signup",
        params={"email": "user@example.com", "password": "secret_password"},
    )
    assert res_signup.status_code == 200
    assert res_signup.json() == {
        "email": "user@example.com",
        "hash_algorithm": "argon2id",
    }

    # 2. 중복 회원가입 실패 (409)
    res_dup = client.post(
        "/auth/signup",
        params={"email": "user@example.com", "password": "secret_password"},
    )
    assert res_dup.status_code == 409

    # 3. 로그인 성공 및 쿠키 발급
    res_login = client.post(
        "/auth/login",
        params={"email": "user@example.com", "password": "secret_password"},
    )
    assert res_login.status_code == 200
    assert res_login.json()["status"] == "ok"
    assert "der_session" in res_login.cookies

    # 4. 잘못된 비밀번호 로그인 실패
    res_fail = client.post(
        "/auth/login",
        params={"email": "user@example.com", "password": "wrong_password"},
    )
    assert res_fail.status_code == 200
    assert res_fail.json()["status"] == "failure"
