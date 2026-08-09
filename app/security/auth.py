"""인증·세션 — 작업 14.2 / SC-1 · FR-901-AC1.

세션 쿠키: **HttpOnly, Secure, SameSite=Lax**. 기본 만료 24시간.

해싱은 ``app.security.hashing`` (Argon2id). 비밀번호 평문은 저장하지 않는다 —
SC-1 의 핵심이 그것이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.security.hashing import verify_password

#: 세션 쿠키 정책 (SC-1). **세 속성 모두 필수** — 하나라도 빠지면 공격 경로가 된다.
COOKIE_HTTPONLY = True
COOKIE_SECURE = True
COOKIE_SAMESITE = "lax"
SESSION_TTL_SECONDS = 24 * 3600  # FR-901-AC1 기본 24시간


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
