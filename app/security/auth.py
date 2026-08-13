"""인증·세션 — 작업 14.2 / SC-1 · FR-901-AC1 · SC-5.

세션 쿠키: **HttpOnly, Secure, SameSite=Lax**. 기본 만료 24시간.

해싱은 ``app.security.hashing`` (Argon2id). 비밀번호 평문은 저장하지 않는다 —
SC-1 의 핵심이 그것이다.

세션 서명 키(SC-5)는 ``resolve_session_secret()`` 이 환경변수에서 읽는다 —
``app.deps.resolve_db_url()`` 과 같은 모양이다.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.security.hashing import verify_password

#: 세션 쿠키 정책 (SC-1). **세 속성 모두 필수** — 하나라도 빠지면 공격 경로가 된다.
COOKIE_HTTPONLY = True
COOKIE_SECURE = True
COOKIE_SAMESITE = "lax"
SESSION_TTL_SECONDS = 24 * 3600  # FR-901-AC1 기본 24시간

#: SC-5 — 세션 서명 키의 환경변수 이름. ``app.deps.DB_URL_ENV`` 와 같은 계열.
SESSION_SECRET_ENV = "DER_SESSION_SECRET"


@dataclass(frozen=True)
class SessionPolicy:
    """세션 쿠키 정책 — FastAPI ``set_cookie()`` 인자로 직접 넘긴다.

    환경마다 다른 값을 쓸 수 있게 객체로 둔다 — 다만 **세 속성 모두 기본이 켜짐**.
    테스트에서 끄는 것은 명시적으로 해야 한다 (설정 해제가 안전한 기본값).
    """

    httponly: bool = COOKIE_HTTPONLY
    secure: bool = COOKIE_SECURE
    samesite: str = COOKIE_SAMESITE
    max_age_seconds: int = SESSION_TTL_SECONDS

    def assert_sc1_compliant(self) -> None:
        """SC-1 위반 검사 — 세 속성 중 하나라도 꺼지면 예외.

        테스트 또는 로컬 개발에서 ``secure=False`` 를 쓸 수 있게 객체는 허용하되,
        **위반 상태로 배포되면 안 된다** — 이 함수가 시작 시점에 검사한다.
        """
        if not (self.httponly and self.secure and self.samesite == "lax"):
            raise ValueError(
                f"세션 쿠키 정책이 SC-1 을 충족하지 않는다: "
                f"httponly={self.httponly}, secure={self.secure}, "
                f"samesite={self.samesite!r}. 세 속성 모두 필수다"
            )


def session_cookie_name() -> str:
    """세션 쿠키 이름 — 고정 리터럴. 클라이언트·서버가 같아야 한다."""
    return "der_session"


def build_session_cookie_kwargs(policy: SessionPolicy) -> dict[str, object]:
    """FastAPI ``Response.set_cookie()`` 에 넘길 키워드 인자."""
    policy.assert_sc1_compliant()
    return {
        "key": session_cookie_name(),
        "httponly": policy.httponly,
        "secure": policy.secure,
        "samesite": policy.samesite,
        "max_age": policy.max_age_seconds,
    }


def session_expires_at(issued_at: datetime | None = None) -> datetime:
    """세션 만료 시각. 발급 시각 + TTL."""
    base = issued_at or datetime.now(UTC)
    return base + timedelta(seconds=SESSION_TTL_SECONDS)


def authenticate(
    *, email: str, password: str, stored_hash: str
) -> bool:
    """이메일·비밀번호 인증 — 저장된 Argon2id 해시와 비교.

    ``stored_hash`` 는 ``hash_password()`` 로 만든 값이다. 인증 실패는 False 를
    반환한다 — 예외로 두면 «존재하는 이메일» vs «틀린 비밀번호» 가 구분돼
    사용자 열거(user enumeration) 공격에 쓰인다.
    """
    return verify_password(password, stored_hash)


def resolve_session_secret() -> str:
    """SC-5 — 세션 서명 키는 환경변수에서 온다. 고정 기본값을 두지 않는다.

    ``resolve_db_url()`` 과 달리 **기본값이 없다.** DB 경로는 없어도 앱이
    동작해야 하지만, 서명 키는 없으면 «모두가 같은 키를 쓰는» 상태가 되고
    그것은 SC-5 가 막으려는 바로 그 상태다. 그래서 없으면 예외를 낸다 —
    세션 발급을 거부하는 쪽이, 조용히 고정 키를 쓰는 쪽보다 안전하다.

    ``resolve_db_url()`` 처럼 순수 함수로 둔다 — 값을 캐시하지 않고 호출마다
    다시 읽는다. 그래야 «읽어서 버리는» 구현은 서명 검증이 실제로 어긋나는
    테스트(다른 키로 서명·검증)로 드러난다.
    """
    secret = os.environ.get(SESSION_SECRET_ENV)
    if not secret:
        raise RuntimeError(
            f"{SESSION_SECRET_ENV} 환경변수가 없다 — 세션 서명 키는 고정 기본값을 "
            "둘 수 없다 (SC-5). 배포 환경에 이 변수를 설정하라"
        )
    return secret


def sign_session_value(
    email: str, secret: str, *, issued_at: datetime | None = None
) -> str:
    """세션 쿠키에 담을 서명된 값 — ``이메일.발급시각.서명`` 형태.

    평문 이메일을 그대로 쿠키에 넣지 않는다 — 서명이 없으면 클라이언트가
    임의 이메일 값으로 쿠키를 위조할 수 있다.

    ★ **발급 시각이 서명 대상에 들어간다 (FR-901-AC1 「세션 만료」).**
    ---------------------------------------------------------------
    R27 까지 서명 대상은 이메일뿐이었다. 그래서 **토큰에 시각이 없었고,
    `verify_session_value` 는 만료를 검사할 수 없었다** — 25시간 뒤든 1년
    뒤든 그대로 유효했다. `SESSION_TTL_SECONDS` 는 쿠키 `max_age` 로만 나갔고
    그것은 **브라우저에 대한 힌트이지 서버의 강제가 아니다**(쿠키를 손으로
    다시 보내면 그만이다). `session_expires_at()` 은 호출자 0곳의 죽은 코드였다.

    시각을 **서명 대상에 넣는 것**이 요점이다. 서명 밖에 두면 클라이언트가
    발급 시각을 미래로 고쳐 만료를 무한히 미룰 수 있다.
    """
    issued = issued_at or datetime.now(UTC)
    issued_ts = str(int(issued.timestamp()))
    payload = f"{email}.{issued_ts}"
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{digest}"


def verify_session_value(
    token: str, secret: str, *, now: datetime | None = None
) -> str | None:
    """서명된 세션 값 검증 — 성공하면 이메일, 실패하면 ``None``.

    잘못된 키로 서명됐거나 값이 변조됐으면 서명이 어긋나 ``None`` 이 된다.
    **발급 후 `SESSION_TTL_SECONDS`(기본 24시간)를 넘겼으면 서명이 맞아도
    거부한다** — 그것이 FR-901-AC1 의 「세션 만료」다.

    시각 형식이 아닌 토큰(R27 이전 형태 포함)은 **거부한다.** 만료를 판정할
    수 없는 토큰을 통과시키면 옛 토큰이 영구 유효해지고, 그러면 이 검사는
    붙드는 것이 없다.
    """
    # ⚠ **오른쪽부터 두 번 자른다.** 이메일에는 점이 들어간다
    # (`user@example.com`) — 왼쪽부터 자르면 `user@example` 이 되어 서명이
    # 어긋나고, 모든 정상 세션이 조용히 거부된다.
    rest, _, digest = token.rpartition(".")
    email, _, issued_ts = rest.rpartition(".")
    if not email or not issued_ts or not digest:
        return None

    payload = f"{email}.{issued_ts}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        return None

    try:
        issued_at = datetime.fromtimestamp(int(issued_ts), UTC)
    except (ValueError, OverflowError, OSError):
        return None

    if (now or datetime.now(UTC)) > session_expires_at(issued_at):
        return None
    return email
