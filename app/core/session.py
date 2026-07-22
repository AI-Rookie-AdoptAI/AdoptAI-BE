"""로그인 세션(쿠키 + 토큰 발급) 처리.

이메일 로그인과 소셜 로그인이 똑같은 방식으로 세션을 열어야 해서 라우터 밖으로 뺐다.
쿠키 이름은 FE의 `src/proxy.ts`가 보는 값과 반드시 같아야 한다.
"""

from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.models.refresh_token import RefreshToken
from app.models.user import User

ACCESS_COOKIE = "adopt_access_token"
REFRESH_COOKIE = "adopt_refresh_token"


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


async def issue_tokens(user: User, db: AsyncSession) -> tuple[str, str]:
    """access token(JWT) + refresh token(DB UUID) 발급."""
    access_token, _jti, _exp = create_access_token(user.id)
    rt = RefreshToken(
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(rt)
    await db.flush()
    return access_token, rt.id
