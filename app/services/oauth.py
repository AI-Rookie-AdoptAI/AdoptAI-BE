"""소셜 로그인(구글·카카오) provider 연동.

provider별로 다른 것은 URL 3개와 프로필 응답 모양뿐이므로 그 차이만 여기에 가둔다.
라우터는 `build_authorize_url` / `fetch_profile` 두 함수만 본다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.domain.auth_policy import OAUTH_PROVIDER_LABELS, is_supported_oauth_provider

CALLBACK_PATH_TEMPLATE = "/api/v1/auth/oauth/{provider}/callback"


class OAuthError(RuntimeError):
    """provider 연동이 실패했을 때. 라우터가 로그인 화면 리다이렉트로 변환한다."""


@dataclass(frozen=True)
class OAuthProfile:
    provider: str
    provider_user_id: str
    email: str | None
    name: str | None


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str
    client_id: str
    client_secret: str


def _provider_configs() -> dict[str, ProviderConfig]:
    return {
        "google": ProviderConfig(
            name="google",
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
            scope="openid email profile",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        ),
        "kakao": ProviderConfig(
            name="kakao",
            authorize_url="https://kauth.kakao.com/oauth/authorize",
            token_url="https://kauth.kakao.com/oauth/token",
            userinfo_url="https://kapi.kakao.com/v2/user/me",
            scope="account_email profile_nickname",
            client_id=settings.KAKAO_CLIENT_ID,
            client_secret=settings.KAKAO_CLIENT_SECRET,
        ),
    }


def get_provider_config(provider: str) -> ProviderConfig:
    if not is_supported_oauth_provider(provider):
        raise OAuthError("지원하지 않는 소셜 로그인이에요")
    config = _provider_configs()[provider]
    if not config.client_id:
        label = OAUTH_PROVIDER_LABELS.get(provider, provider)
        raise OAuthError(f"{label} 로그인이 설정되지 않았어요")
    return config


def build_redirect_uri(provider: str) -> str:
    base = settings.OAUTH_CALLBACK_BASE_URL.rstrip("/")
    return f"{base}{CALLBACK_PATH_TEMPLATE.format(provider=provider)}"


def build_authorize_url(provider: str, *, state: str) -> str:
    config = get_provider_config(provider)
    params = {
        "client_id": config.client_id,
        "redirect_uri": build_redirect_uri(provider),
        "response_type": "code",
        "scope": config.scope,
        "state": state,
    }
    return f"{config.authorize_url}?{urlencode(params)}"


async def _exchange_code_for_access_token(
    client: httpx.AsyncClient, config: ProviderConfig, code: str
) -> str:
    data = {
        "grant_type": "authorization_code",
        "client_id": config.client_id,
        "redirect_uri": build_redirect_uri(config.name),
        "code": code,
    }
    if config.client_secret:
        data["client_secret"] = config.client_secret

    response = await client.post(
        config.token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.is_error:
        raise OAuthError("소셜 로그인 인증에 실패했어요")
    access_token = response.json().get("access_token")
    if not access_token:
        raise OAuthError("소셜 로그인 인증에 실패했어요")
    return str(access_token)


def _parse_profile(provider: str, payload: dict[str, Any]) -> OAuthProfile:
    if provider == "google":
        subject = payload.get("sub")
        if not subject:
            raise OAuthError("구글 계정 정보를 읽지 못했어요")
        return OAuthProfile(
            provider=provider,
            provider_user_id=str(subject),
            email=payload.get("email"),
            name=payload.get("name"),
        )

    # kakao: 이메일·닉네임은 동의 항목이라 없을 수 있다.
    subject = payload.get("id")
    if not subject:
        raise OAuthError("카카오 계정 정보를 읽지 못했어요")
    account = payload.get("kakao_account") or {}
    profile = account.get("profile") or {}
    return OAuthProfile(
        provider=provider,
        provider_user_id=str(subject),
        email=account.get("email"),
        name=profile.get("nickname"),
    )


async def fetch_profile(provider: str, *, code: str) -> OAuthProfile:
    """authorization code를 토큰으로 바꾸고 provider 프로필을 가져온다."""
    config = get_provider_config(provider)
    timeout = httpx.Timeout(settings.OAUTH_TIMEOUT_SECONDS, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            access_token = await _exchange_code_for_access_token(client, config, code)
            response = await client.get(
                config.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.is_error:
                raise OAuthError("소셜 계정 정보를 가져오지 못했어요")
            payload = response.json()
    except httpx.HTTPError as error:
        raise OAuthError("소셜 로그인 서버에 연결하지 못했어요") from error

    if not isinstance(payload, dict):
        raise OAuthError("소셜 계정 정보를 가져오지 못했어요")
    return _parse_profile(provider, payload)
