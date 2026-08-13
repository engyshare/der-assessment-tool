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
    SESSION_SECRET_ENV,
    SESSION_TTL_SECONDS,
    SessionPolicy,
    authenticate,
    build_session_cookie_kwargs,
    resolve_session_secret,
    sign_session_value,
    verify_session_value,
)


@pytest.mark.req("SC-1")
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
    """FR-901-AC1 — 기본 세션 만료 24시간.

    ⚠ **이 단언은 상수의 값만 본다.** R27 까지 「세션 만료」를 붙드는 것이
    이것뿐이었고, 그래서 **만료 로직이 통째로 없어도 초록불이었다** — 실제로
    그 상태였다(토큰에 시각이 없어 검증이 만료를 볼 수 없었다). 만료가
    **동작하는지**는 아래 세 테스트가 본다.
    """
    assert SESSION_TTL_SECONDS == 24 * 3600


# ── FR-901-AC1 — 세션 만료가 **강제되는가** (R27) ─────────────────────────


@pytest.mark.req("FR-901-AC1")
def test_session_is_rejected_after_the_ttl() -> None:
    """★★ 24시간 + 1초가 지난 세션은 **서명이 맞아도** 거부된다.

    오라클: 손계산. TTL 이 24×3600초이므로 발급 시각 + 86,401초는 만료 밖이다.
    시계를 앞당기는 대신 **발급 시각을 과거로 주입**한다 — 시스템 시각을
    건드리면 다른 검사가 함께 흔들린다.
    """
    from datetime import UTC, datetime, timedelta

    secret = "expiry-secret"
    issued = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    token = sign_session_value("user@example.com", secret, issued_at=issued)

    fresh = issued + timedelta(seconds=SESSION_TTL_SECONDS - 1)
    assert verify_session_value(token, secret, now=fresh) == "user@example.com", (
        "만료 전인데 거부됐다 — 경계를 잘못 잡았다"
    )

    expired = issued + timedelta(seconds=SESSION_TTL_SECONDS + 1)
    assert verify_session_value(token, secret, now=expired) is None, (
        "24시간이 지난 세션이 그대로 유효하다 — 만료가 강제되지 않는다"
    )


@pytest.mark.req("FR-901-AC1")
def test_issue_time_is_inside_the_signature() -> None:
    """★★ 발급 시각을 **미래로 고쳐도** 통하지 않는다 — 시각이 서명 대상이다.

    시각을 서명 밖에 두면 클라이언트가 그 자리를 고쳐 만료를 무한히 미룰 수
    있다. 만료 검사는 있는데 우회되는 상태이며, 「만료가 있다」는 검사만으로는
    드러나지 않는다.
    """
    from datetime import UTC, datetime, timedelta

    secret = "forge-secret"
    issued = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    token = sign_session_value("user@example.com", secret, issued_at=issued)

    rest, _, digest = token.rpartition(".")
    email, _, issued_ts = rest.rpartition(".")
    forged = f"{email}.{int(issued_ts) + SESSION_TTL_SECONDS * 10}.{digest}"

    expired_moment = issued + timedelta(seconds=SESSION_TTL_SECONDS + 1)
    assert verify_session_value(forged, secret, now=expired_moment) is None, (
        "발급 시각을 미래로 고친 토큰이 통과했다 — 시각이 서명 밖에 있다"
    )


@pytest.mark.req("FR-901-AC1")
def test_a_token_without_an_issue_time_is_refused() -> None:
    """시각이 없는 토큰(R27 이전 형태)은 거부한다.

    만료를 판정할 수 없는 토큰을 통과시키면 **옛 토큰이 영구 유효**해지고,
    그러면 이 검사는 붙드는 것이 없다. 하위호환을 이유로 열어 두면 조항이
    요구한 만료가 사실상 없는 것과 같다.
    """
    import hashlib
    import hmac

    secret = "legacy-secret"
    email = "user@example.com"
    legacy_digest = hmac.new(
        secret.encode(), email.encode(), hashlib.sha256
    ).hexdigest()

    assert verify_session_value(f"{email}.{legacy_digest}", secret) is None


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
def test_signup_and_login_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB 기반 회원가입 및 로그인 흐름 검증 (FR-901-AC1)."""
    monkeypatch.setenv(SESSION_SECRET_ENV, "test-secret-signup-login")
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
    # SC-5 — 쿠키 값은 평문 이메일이 아니라 서명된 값이다.
    # requests 가 특수문자 포함 쿠키 값을 큰따옴표로 감싸 돌려준다 — 벗겨낸다.
    cookie_value = res_login.cookies["der_session"].strip('"')
    assert cookie_value != "user@example.com"
    assert cookie_value != "session:user@example.com"
    assert (
        verify_session_value(cookie_value, "test-secret-signup-login")
        == "user@example.com"
    )

    # 4. 잘못된 비밀번호 로그인 실패
    res_fail = client.post(
        "/auth/login",
        params={"email": "user@example.com", "password": "wrong_password"},
    )
    assert res_fail.status_code == 200
    assert res_fail.json()["status"] == "failure"


# ── SC-5 — 세션 서명 키는 환경변수에서, 고정 기본값 없이 ──────────────


@pytest.mark.req("SC-5")
def test_resolve_session_secret_reads_env_value_not_hardcoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-5 층① — 환경변수를 읽어서 돌려주는가. 값이 바뀌면 결과도 바뀐다."""
    monkeypatch.setenv(SESSION_SECRET_ENV, "secret-a")
    assert resolve_session_secret() == "secret-a"
    monkeypatch.setenv(SESSION_SECRET_ENV, "secret-b")
    assert resolve_session_secret() == "secret-b"


@pytest.mark.req("SC-5")
def test_resolve_session_secret_missing_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-5 — 세션 서명 키에는 고정 기본값이 없다. 없으면 예외로 거부한다."""
    monkeypatch.delenv(SESSION_SECRET_ENV, raising=False)
    with pytest.raises(RuntimeError, match=SESSION_SECRET_ENV):
        resolve_session_secret()
    monkeypatch.setenv(SESSION_SECRET_ENV, "")
    with pytest.raises(RuntimeError, match=SESSION_SECRET_ENV):
        resolve_session_secret()


@pytest.mark.req("SC-5")
def test_sign_and_verify_session_value_roundtrip() -> None:
    """서명·검증 왕복 — 같은 키면 이메일이 그대로 나온다."""
    token = sign_session_value("user@example.com", "same-secret")
    assert verify_session_value(token, "same-secret") == "user@example.com"


@pytest.mark.req("SC-5")
def test_verify_session_value_fails_with_wrong_secret() -> None:
    """SC-5 층② — 실제로 그 키로 서명이 만들어지는가.

    소스에 ``DER_SESSION_SECRET`` 이라는 글자가 있는지가 아니라, **다른 키로
    서명하면 검증이 실제로 어긋나는지** 를 본다. 고정 키로 바꿔도 서명·검증이
    항상 맞아떨어지는 구현이면 이 테스트가 잡는다.
    """
    token = sign_session_value("user@example.com", "secret-a")
    assert verify_session_value(token, "secret-b") is None


@pytest.mark.req("SC-5")
def test_verify_session_value_fails_with_tampered_token() -> None:
    """서명 없이 이메일만 바꿔치기한 토큰은 거부된다 — 위조 방지."""
    token = sign_session_value("user@example.com", "secret")
    tampered = token.replace("user@example.com", "attacker@example.com")
    assert verify_session_value(tampered, "secret") is None


# ── FR-901-AC1 — 비밀번호 재설정 ──────────────────────────────────────


@pytest.mark.req("FR-901-AC1")
def test_reset_password_old_fails_new_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """재설정 뒤 옛 비밀번호는 실패하고 새 비밀번호는 성공한다 (FR-901-AC1).

    «재설정 함수를 불렀다» 만 보지 않는다 — 로그인을 두 번 실제로 시도해서
    옛 것이 정말 막히고 새 것이 정말 열리는지를 본다.
    """
    monkeypatch.setenv(SESSION_SECRET_ENV, "test-secret-reset")
    client = TestClient(create_app())
    client.post(
        "/auth/signup",
        params={"email": "reset1@example.com", "password": "old_password"},
    )

    res_reset = client.post(
        "/auth/reset-password",
        params={
            "email": "reset1@example.com",
            "old_password": "old_password",
            "new_password": "new_password",
        },
    )
    assert res_reset.status_code == 200
    assert res_reset.json()["status"] == "ok"

    # 옛 비밀번호 — 로그인 실패
    res_old = client.post(
        "/auth/login",
        params={"email": "reset1@example.com", "password": "old_password"},
    )
    assert res_old.json()["status"] == "failure"

    # 새 비밀번호 — 로그인 성공
    res_new = client.post(
        "/auth/login",
        params={"email": "reset1@example.com", "password": "new_password"},
    )
    assert res_new.json()["status"] == "ok"


@pytest.mark.req("FR-901-AC1")
def test_reset_password_wrong_old_password_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """옛 비밀번호가 틀리면 재설정이 거부되고 비밀번호는 바뀌지 않는다."""
    monkeypatch.setenv(SESSION_SECRET_ENV, "test-secret-reset-wrong")
    client = TestClient(create_app())
    client.post(
        "/auth/signup",
        params={"email": "reset2@example.com", "password": "correct_old"},
    )

    res_reset = client.post(
        "/auth/reset-password",
        params={
            "email": "reset2@example.com",
            "old_password": "wrong_old",
            "new_password": "new_password",
        },
    )
    assert res_reset.json()["status"] == "failure"

    # 기존 비밀번호가 여전히 유효 — 바뀌지 않았다
    res_login = client.post(
        "/auth/login",
        params={"email": "reset2@example.com", "password": "correct_old"},
    )
    assert res_login.json()["status"] == "ok"


@pytest.mark.req("FR-901-AC1")
def test_reset_password_nonexistent_email_rejected() -> None:
    """존재하지 않는 이메일의 재설정 요청은 실패한다 — 사용자 열거 방지 형태."""
    client = TestClient(create_app())
    res_reset = client.post(
        "/auth/reset-password",
        params={
            "email": "nobody@example.com",
            "old_password": "whatever",
            "new_password": "new_password",
        },
    )
    assert res_reset.json()["status"] == "failure"


@pytest.mark.req("FR-901-AC1")
def test_reset_password_stores_hash_not_plaintext() -> None:
    """재설정 뒤 저장되는 값은 Argon2id 해시다 — 평문이 아니다."""
    from sqlalchemy import select

    from app.deps import _session_factory
    from infra.orm.identity import User

    client = TestClient(create_app())
    client.post(
        "/auth/signup",
        params={"email": "reset3@example.com", "password": "old_password"},
    )
    client.post(
        "/auth/reset-password",
        params={
            "email": "reset3@example.com",
            "old_password": "old_password",
            "new_password": "brand_new_password",
        },
    )

    db = _session_factory()
    try:
        user = db.scalar(select(User).where(User.email == "reset3@example.com"))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != "brand_new_password"
    finally:
        db.close()
