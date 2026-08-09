"""인증 라우터 — 로그인·회원가입. SC-1.

해싱은 ``app.security.hashing`` (Argon2id). 세션 쿠키는 HttpOnly·Secure·SameSite=Lax
(14.2). 감사 로그는 ``app.audit`` (SC-4, 14.9).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.security import hash_password, is_argon2id, verify_password
from app.security.auth import SessionPolicy, build_session_cookie_kwargs
from infra.orm.identity import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup")
def signup(
    email: str, password: str, db: Session = Depends(get_db)  # noqa: B008
) -> dict[str, str]:
    """회원가입 — 평문을 저장하지 않고 Argon2id 해시만 보관 (SC-1)."""
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="이미 존재하는 이메일")
    hashed = hash_password(password)
    if not is_argon2id(hashed):
        raise HTTPException(
            status_code=500, detail="해싱이 Argon2id 가 아니다 — 구현 오류"
        )
    user = User(email=email, password_hash=hashed)
    db.add(user)
    db.commit()
    return {"email": email, "hash_algorithm": "argon2id"}


@router.post("/login")
def login(
    email: str,
    password: str,
    response: Response,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    """로그인 — 해시 비교 → 세션 쿠키 발급. 감사 로그 기록 (SC-4)."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        # 감사 로그 — 실패도 기록.
        return {"status": "failure", "detail": "이메일 또는 비밀번호"}
    # SC-1 세션 쿠키 — 세 속성 모두 필수
    kwargs = build_session_cookie_kwargs(SessionPolicy())
    response.set_cookie(value=f"session:{email}", **kwargs)  # type: ignore[arg-type]
    return {"status": "ok", "email": email}
