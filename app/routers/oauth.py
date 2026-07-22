"""소셜 로그인(카카오·구글) — Authorization Code 흐름.

인증 쿠키는 HttpOnly라 브라우저 JS가 만들 수 없다. 그래서 provider 리다이렉트를
프론트가 아니라 백엔드가 받고, 여기서 세션 쿠키를 심은 뒤 프론트로 돌려보낸다.

    FE 버튼 → GET /auth/oauth/{provider}/authorize → provider 동의 화면
            → GET /auth/oauth/{provider}/callback  → 쿠키 설정 후 FE로 302
"""

import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    OAUTH_STATE_EXPIRE_SECONDS,
    create_oauth_state_token,
    decode_oauth_state_token,
)
from app.core.session import issue_tokens, set_auth_cookies
from app.domain.auth_policy import (
    OAUTH_PROVIDER_LABELS,
    build_placeholder_email,
    is_supported_oauth_provider,
    resolve_oauth_display_name,
    sanitize_redirect_path,
)
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.schemas.auth import OAuthProviderInfo, OAuthProvidersResponse
from app.services.oauth import (
    OAuthError,
    OAuthProfile,
    build_authorize_url,
    fetch_profile,
    get_provider_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oauth", tags=["Auth"])

STATE_COOKIE = "adopt_oauth_state"


def _redirect_to_frontend(path: str) -> RedirectResponse:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return RedirectResponse(f"{base}{path}", status_code=status.HTTP_302_FOUND)


def _redirect_with_error(message: str) -> RedirectResponse:
    response = _redirect_to_frontend(f"/login?{urlencode({'error': message})}")
    response.delete_cookie(STATE_COOKIE, path="/")
    return response


async def _find_or_create_user(
    db: AsyncSession, profile: OAuthProfile
) -> User:
    """(provider, provider_user_id)가 신원. 같은 이메일의 기존 계정이 있으면 거기에 연결한다."""
    linked = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == profile.provider,
            OAuthAccount.provider_user_id == profile.provider_user_id,
        )
    )
    account = linked.scalar_one_or_none()
    if account is not None:
        existing = await db.execute(select(User).where(User.id == account.user_id))
        user = existing.scalar_one()
        # provider 쪽에서 이메일이 바뀌었을 수 있으니 연결 정보만 최신으로 둔다.
        account.email = profile.email
        return user

    user = None
    if profile.email:
        by_email = await db.execute(select(User).where(User.email == profile.email))
        user = by_email.scalar_one_or_none()

    if user is None:
        user = User(
            email=profile.email
            or build_placeholder_email(profile.provider, profile.provider_user_id),
            name=resolve_oauth_display_name(profile.name, profile.email),
            hashed_password=None,
        )
        db.add(user)
        await db.flush()

    db.add(
        OAuthAccount(
            user_id=user.id,
            provider=profile.provider,
            provider_user_id=profile.provider_user_id,
            email=profile.email,
        )
    )
    return user


@router.get("/providers", response_model=OAuthProvidersResponse, summary="사용 가능한 소셜 로그인")
async def list_providers() -> OAuthProvidersResponse:
    """client id가 설정된 provider만 돌려준다 — FE가 버튼 노출 여부를 여기에 맞춘다."""
    return OAuthProvidersResponse(
        providers=[
            OAuthProviderInfo(
                provider=provider,
                label=OAUTH_PROVIDER_LABELS.get(provider, provider),
                authorize_path=f"/auth/oauth/{provider}/authorize",
            )
            for provider in settings.enabled_oauth_providers
        ]
    )


@router.get("/{provider}/authorize", summary="소셜 로그인 시작")
async def authorize(provider: str, next: str = "/") -> Response:
    if not is_supported_oauth_provider(provider):
        return _redirect_with_error("지원하지 않는 소셜 로그인이에요")
    try:
        nonce = secrets.token_urlsafe(16)
        authorize_url = build_authorize_url(provider, state=nonce)
    except OAuthError as error:
        return _redirect_with_error(str(error))

    response = RedirectResponse(authorize_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        STATE_COOKIE,
        create_oauth_state_token(nonce=nonce, next_path=sanitize_redirect_path(next)),
        max_age=OAUTH_STATE_EXPIRE_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        # provider 도메인에서 우리 콜백으로 top-level 이동해 돌아오므로 lax여야 쿠키가 붙는다.
        samesite="lax",
        path="/",
    )
    return response


@router.get("/{provider}/callback", summary="소셜 로그인 콜백")
async def callback(
    provider: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """provider가 사용자를 돌려보내는 지점. 어떤 실패든 로그인 화면으로 되돌린다."""
    if not is_supported_oauth_provider(provider):
        return _redirect_with_error("지원하지 않는 소셜 로그인이에요")
    if error or not code:
        return _redirect_with_error("소셜 로그인이 취소되었어요")

    state_cookie = request.cookies.get(STATE_COOKIE)
    decoded = decode_oauth_state_token(state_cookie) if state_cookie else None
    if decoded is None or not state or not secrets.compare_digest(decoded[0], state):
        return _redirect_with_error("로그인 요청이 만료되었어요. 다시 시도해 주세요")
    next_path = sanitize_redirect_path(decoded[1])

    try:
        get_provider_config(provider)
        profile = await fetch_profile(provider, code=code)
    except OAuthError as service_error:
        logger.warning("OAuth 콜백 실패 (provider=%s): %s", provider, service_error)
        return _redirect_with_error(str(service_error))

    user = await _find_or_create_user(db, profile)
    access_token, refresh_token = await issue_tokens(user, db)
    await db.commit()

    response = _redirect_to_frontend(next_path)
    set_auth_cookies(response, access_token, refresh_token)
    response.delete_cookie(STATE_COOKIE, path="/")
    return response
