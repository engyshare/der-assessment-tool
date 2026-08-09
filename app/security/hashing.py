"""비밀번호 해싱 — 작업 14.1 / SC-1 · NFR-401-AC1.

**Argon2id** (argon2-cffi). 조항이 «Argon2id 또는 bcrypt(cost≥12)» 를 허용하지만
Argon2id 가 먼저 열거되어 있고, 메모리 다량 사용 방식이라 GPU 대량 시도 공격에
더 강하다. **어느 쪽을 썼는지가 테스트로 드러난다** — 해시 문자열이
``$argon2id$`` 로 시작한다.

파라미터는 정책 수치라 소스에 박지 않는다 (브리프 14.1). 환경변수
``ARGON2_TIME_COST`` · ``ARGON2_MEMORY_COST`` 로 덮어쓴다. **하한 검사는 코드에
둔다** — OWASP Argon2id 최소 권장(time_cost≥2, memory_cost≥19456).
"""
from __future__ import annotations

import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

#: OWASP Argon2id 최소 권장 — 이 하한 아래로는 거부 (NFR-401-AC1 정신).
#: bcrypt 의 cost≥12 와 직접 대응하지는 않지만, Argon2id 자체가 bcrypt 보다
#: 메모리 경로를 쓰므로 «같은 공격 비용» 을 유지하려면 OWASP 최소가 합리적.
MIN_TIME_COST = 2
MIN_MEMORY_COST = 19456  # 19 MiB — OWASP 2023 최소


def _build_hasher() -> PasswordHasher:
    """환경변수 → PasswordHasher. **하한 검사는 여기서 한다.**

    정책 수치를 소스에 박으면 환경마다 다른 값을 쓸 때 이 파일을 고쳐야 한다.
    환경변수로 두면 배포마다 다른 강도를 쓰면서 코드는 그대로다.
    """
    time_cost = int(os.environ.get("ARGON2_TIME_COST", "3"))
    memory_cost = int(os.environ.get("ARGON2_MEMORY_COST", "65536"))
    # 하한 검사 — 정책 수치지만 조항이 «충분한 강도» 를 요구
    if time_cost < MIN_TIME_COST:
        raise ValueError(
            f"Argon2id time_cost 가 하한 아래입니다: {time_cost} < {MIN_TIME_COST}. "
            "OWASP 최소 권장 아래면 GPU 대량 시도 공격에 약하다 (NFR-401-AC1)"
        )
    if memory_cost < MIN_MEMORY_COST:
        raise ValueError(
            f"Argon2id memory_cost 가 하한 아래입니다: {memory_cost} < {MIN_MEMORY_COST}. "
            "OWASP 최소(19 MiB) 아래면 Argon2id 의 메모리 경로 이점이 사라진다"
        )
    return PasswordHasher(time_cost=time_cost, memory_cost=memory_cost)


#: 모듈 수준에서 한 번만 만든다 — 매 요청마다 만들면 파라미터 매칭이 의미 없다.
_HASHER: PasswordHasher | None = None


def get_hasher() -> PasswordHasher:
    """현재 PasswordHasher 인스턴스. **지연 초기화** — import 시 환경변수를
    읽지 않아 테스트가 환경변수를 먼저 설정할 수 있다."""
    global _HASHER  # noqa: PLW0603 — 지연 초기화는 global 이 자연스럽다
    if _HASHER is None:
        _HASHER = _build_hasher()
    return _HASHER


def reset_hasher_for_testing() -> None:
    """테스트용 — 환경변수 바꾼 뒤 재초기화 유도. 프로덕션에서는 쓰지 않는다."""
    global _HASHER  # noqa: PLW0603 — 테스트 전용 재초기화
    _HASHER = None


def hash_password(plain: str) -> str:
    """평문 → Argon2id 해시 문자열. ``$argon2id$`` 프리픽스로 알고리즘이 드러난다."""
    return get_hasher().hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """평문 ↔ 해시 비교. 일치하면 True, 불일치면 False (예외 아님)."""
    try:
        get_hasher().verify(hashed, plain)
        return True
    except VerifyMismatchError:
        return False


def is_argon2id(hashed: str) -> bool:
    """해시가 Argon2id 인가 — ``$argon2id$`` 프리픽스로 판정.

    **어느 알고리즘을 썼는지가 테스트로 드러나게 하는 통로** (요청 사항).
    bcrypt 를 썼다면 ``$2b$`` 프리픽스가 나온다.
    """
    return hashed.startswith("$argon2id$")
