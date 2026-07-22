import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def generate_url_token(nbytes: int = 32) -> str:
    """메일 링크·OAuth state에 쓰는 추측 불가능한 URL-safe 토큰."""
    return secrets.token_urlsafe(nbytes)


def hash_url_token(token: str) -> str:
    """랜덤 토큰은 이미 엔트로피가 충분하므로 sha256으로 충분하다(bcrypt는 링크 검증에 과하다)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(subject: str) -> tuple[str, str, datetime]:
    """JWT 발급. (token, jti, expires_at) 반환."""
    jti = str(uuid.uuid4())
    expire = datetime.now(UTC) + timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS)
    token = jwt.encode(
        {"sub": subject, "jti": jti, "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return token, jti, expire


OAUTH_STATE_EXPIRE_SECONDS = 600


def create_oauth_state_token(*, nonce: str, next_path: str) -> str:
    """OAuth state를 담은 단기 JWT. 쿠키에 넣어 CSRF(주입된 code) 방어에 쓴다."""
    expire = datetime.now(UTC) + timedelta(seconds=OAUTH_STATE_EXPIRE_SECONDS)
    return jwt.encode(
        {"nonce": nonce, "next": next_path, "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_oauth_state_token(token: str) -> tuple[str, str] | None:
    """(nonce, next_path) 반환. 위조·만료면 None — 콜백은 401이 아니라 리다이렉트로 처리한다."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    nonce = payload.get("nonce")
    if not nonce:
        return None
    return str(nonce), str(payload.get("next") or "/")


def decode_token(token: str) -> tuple[str, str]:
    """검증 후 (user_id, jti) 반환. 실패 시 401 raise."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub: str | None = payload.get("sub")
        jti: str | None = payload.get("jti")
        if not sub or not jti:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다")
        return sub, jti
    except JWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다"
        ) from error
