from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.dependencies import get_current_user
from app.models.refresh_token import RefreshToken
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenRefreshResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

_bearer_optional = HTTPBearer(auto_error=False)


def _user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, name=user.name, created_at=user.created_at)


async def _issue_tokens(user: User, db: AsyncSession) -> tuple[str, str]:
    """access token(JWT) + refresh token(DB UUID) 발급."""
    access_token, _jti, _exp = create_access_token(user.id)
    rt = RefreshToken(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(rt)
    await db.flush()
    return access_token, rt.id


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, summary="회원가입")
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일이에요")

    user = User(email=body.email, name=body.name, hashed_password=hash_password(body.password))
    db.add(user)
    await db.flush()

    access_token, refresh_token = await _issue_tokens(user, db)
    await db.commit()
    await db.refresh(user)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        user=_user_response(user),
    )


@router.post("/login", response_model=AuthResponse, summary="로그인")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않아요",
        )

    access_token, refresh_token = await _issue_tokens(user, db)
    await db.commit()

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        user=_user_response(user),
    )


@router.post("/refresh", response_model=TokenRefreshResponse, summary="액세스 토큰 갱신")
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenRefreshResponse:
    result = await db.execute(select(RefreshToken).where(RefreshToken.id == body.refresh_token))
    rt = result.scalar_one_or_none()

    if not rt or rt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        if rt:
            await db.delete(rt)
            await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않거나 만료된 refresh token이에요")

    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one()

    # 토큰 로테이션: 기존 삭제 후 새로 발급
    await db.delete(rt)
    access_token, new_refresh_token = await _issue_tokens(user, db)
    await db.commit()

    return TokenRefreshResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
    )


@router.get("/me", response_model=UserResponse, summary="내 정보 조회")
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="로그아웃")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_optional),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    access token의 jti를 블랙리스트에 등록하고, 연결된 refresh token도 삭제합니다.
    토큰이 없거나 이미 무효화된 경우에도 204를 반환합니다 (프론트가 항상 쿠키 삭제).
    """
    if not credentials:
        return

    try:
        user_id, jti = decode_token(credentials.credentials)
    except HTTPException:
        return

    # access token 블랙리스트 등록 (이미 있으면 skip)
    existing = await db.execute(select(TokenBlacklist).where(TokenBlacklist.jti == jti))
    if not existing.scalar_one_or_none():
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS)
        db.add(TokenBlacklist(jti=jti, expires_at=expires_at))

    # 해당 유저의 refresh token 전체 삭제
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await db.commit()
