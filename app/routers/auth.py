from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    decode_token,
    generate_url_token,
    hash_password,
    hash_url_token,
    verify_password,
)
from app.core.session import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    issue_tokens,
    set_auth_cookies,
)
from app.dependencies import get_current_user
from app.domain.auth_policy import (
    build_password_reset_link,
    can_login_with_password,
    is_password_reset_token_usable,
    mask_email,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    ResetTokenStatusResponse,
    TokenRefreshResponse,
    UserResponse,
)
from app.services.email import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["Auth"])

_bearer_optional = HTTPBearer(auto_error=False)


def _user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, name=user.name, created_at=user.created_at)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, summary="회원가입")
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일이에요")

    user = User(email=body.email, name=body.name, hashed_password=hash_password(body.password))
    db.add(user)
    await db.flush()

    access_token, refresh_token = await issue_tokens(user, db)
    await db.commit()
    await db.refresh(user)
    set_auth_cookies(response, access_token, refresh_token)

    return AuthResponse(
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        user=_user_response(user),
    )


@router.post("/login", response_model=AuthResponse, summary="로그인")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # 소셜 가입 계정(비밀번호 없음)도 같은 문구로 막는다 — 가입 수단이 노출되면 안 된다.
    if (
        not user
        or not can_login_with_password(user.hashed_password)
        or not verify_password(body.password, str(user.hashed_password))
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않아요",
        )

    access_token, refresh_token = await issue_tokens(user, db)
    await db.commit()
    set_auth_cookies(response, access_token, refresh_token)

    return AuthResponse(
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        user=_user_response(user),
    )


@router.post("/refresh", response_model=TokenRefreshResponse, summary="액세스 토큰 갱신")
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> TokenRefreshResponse:
    refresh_token = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token이 없습니다")
    result = await db.execute(select(RefreshToken).where(RefreshToken.id == refresh_token))
    rt = result.scalar_one_or_none()

    if not rt or rt.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        if rt:
            await db.delete(rt)
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않거나 만료된 refresh token이에요"
        )

    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one()

    # 토큰 로테이션: 기존 삭제 후 새로 발급
    await db.delete(rt)
    access_token, new_refresh_token = await issue_tokens(user, db)
    await db.commit()
    set_auth_cookies(response, access_token, new_refresh_token)

    return TokenRefreshResponse(
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
    )


async def _find_reset_token(db: AsyncSession, token: str) -> PasswordResetToken | None:
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_url_token(token))
    )
    return result.scalar_one_or_none()


@router.post(
    "/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
    summary="비밀번호 재설정 메일 요청",
)
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    가입된 이메일이면 재설정 링크를 보냅니다.

    가입 여부와 무관하게 항상 202를 반환합니다 — 응답 차이로 회원 이메일을 알아낼 수 있으면
    안 되기 때문입니다. 메일 발송은 응답 이후 백그라운드에서 처리합니다.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user:
        # 새 링크를 보내면 이전 링크는 죽는다 (유효한 링크는 항상 최대 1개).
        await db.execute(
            delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
        raw_token = generate_url_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_url_token(raw_token),
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            )
        )
        await db.commit()
        background_tasks.add_task(
            send_password_reset_email,
            to_email=user.email,
            reset_link=build_password_reset_link(settings.FRONTEND_BASE_URL, raw_token),
        )

    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get(
    "/password/reset",
    response_model=ResetTokenStatusResponse,
    summary="재설정 링크 유효성 확인",
)
async def check_reset_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> ResetTokenStatusResponse:
    """만료·사용된 링크로 새 비밀번호를 다 입력한 뒤에야 실패하는 일이 없도록 먼저 확인합니다."""
    reset_token = await _find_reset_token(db, token)
    if reset_token is None or not is_password_reset_token_usable(
        expires_at=reset_token.expires_at,
        used_at=reset_token.used_at,
        now=datetime.now(UTC),
    ):
        return ResetTokenStatusResponse(valid=False)

    user_result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return ResetTokenStatusResponse(valid=False)
    return ResetTokenStatusResponse(valid=True, email=mask_email(user.email))


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="새 비밀번호 설정",
)
async def reset_password(
    body: ResetPasswordRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    재설정 토큰으로 비밀번호를 바꿉니다.

    토큰은 1회용이고, 성공하면 해당 유저의 refresh token을 전부 지워 기존 세션을 끊습니다
    (비밀번호를 바꾸는 이유가 계정 탈취일 수 있습니다).
    """
    reset_token = await _find_reset_token(db, body.token)
    if reset_token is None or not is_password_reset_token_usable(
        expires_at=reset_token.expires_at,
        used_at=reset_token.used_at,
        now=datetime.now(UTC),
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="만료되었거나 이미 사용된 링크예요. 재설정을 다시 요청해 주세요",
        )

    user_result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="만료되었거나 이미 사용된 링크예요. 재설정을 다시 요청해 주세요",
        )

    user.hashed_password = hash_password(body.new_password)
    reset_token.used_at = datetime.now(UTC)
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await db.commit()

    # 브라우저에 남은 세션 쿠키도 정리해 로그인 화면부터 다시 시작하게 한다.
    clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse, summary="내 정보 조회")
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="로그아웃")
async def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    access token의 jti를 블랙리스트에 등록하고, 연결된 refresh token도 삭제합니다.
    토큰이 없거나 이미 무효화된 경우에도 204를 반환합니다 (프론트가 항상 쿠키 삭제).
    """
    token = credentials.credentials if credentials else request.cookies.get(ACCESS_COOKIE)
    clear_auth_cookies(response)
    if not token:
        return

    try:
        user_id, jti = decode_token(token)
    except HTTPException:
        return

    # access token 블랙리스트 등록 (이미 있으면 skip)
    existing = await db.execute(select(TokenBlacklist).where(TokenBlacklist.jti == jti))
    if not existing.scalar_one_or_none():
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS)
        db.add(TokenBlacklist(jti=jti, expires_at=expires_at))

    # 해당 유저의 refresh token 전체 삭제
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await db.commit()
