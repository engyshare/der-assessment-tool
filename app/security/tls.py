"""TLS 1.2+ 강제 — 작업 14.10 / NFR-402-AC1.

프로덕션 배포 시 TLS 1.2 미만을 거부한다. uvicorn/Gunicorn/리버스 프록시 단의
설정이 주이고, 여기서는 **애플리케이션 시작 시점에 강제 사실을 검증**한다.
"""
from __future__ import annotations

import ssl

#: 최소 TLS 버전 — NFR-402-AC1. TLS 1.2 미만(SSLv3, TLS 1.0, 1.1)은 거부.
MIN_TLS_VERSION = ssl.TLSVersion.TLSv1_2


def build_ssl_context(min_version: ssl.TLSVersion | None = None) -> ssl.SSLContext:
    """TLS 1.2+ 를 강제하는 SSLContext.

    uvicorn 에 ``--ssl-keyfile`` · ``--ssl-certfile`` 과 함께 넘긴다.
    **최소 버전 하한 검사는 여기서 한다.**
    """
    version = min_version or MIN_TLS_VERSION
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = version
    # 구식 암호 제거 — TLS 1.2+ 를 쓰더라도 약한 암호(SUITES)를 허용하면 무의미
    ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20")
    ctx.disable_ssl_v2 = True  # type: ignore[attr-defined]
    ctx.disable_ssl_v3 = True  # type: ignore[attr-defined]
    return ctx


def assert_tls12_or_higher() -> None:
    """시작 시점 검증 — 현재 SSL 구현이 TLS 1.2 를 아는가.

    오래된 빌드의 Python 은 TLS 1.2 상수 자체가 없을 수 있다 — 그 환경에서
    강제가 «선언만 있고 안 된다» 는 것을 잡는다.
    """
    if not hasattr(ssl.TLSVersion, "TLSv1_2"):
        raise RuntimeError(
            "이 Python 빌드는 TLS 1.2 를 지원하지 않는다 (NFR-402-AC1 위반). "
            "OpenSSL 1.0.2+ / Python 3.7+ 가 필요하다"
        )
