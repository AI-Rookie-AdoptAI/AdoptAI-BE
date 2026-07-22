"""Auth policies shared by API handlers and tests.

DB 세션도 request도 받지 않는 순수 함수만 둔다. 비밀번호 재설정 토큰의 유효성,
소셜 로그인 provider 판별, 로그인 후 돌아갈 경로 검증이 여기서 결정된다.
"""

from datetime import UTC, datetime

SUPPORTED_OAUTH_PROVIDERS = ("google", "kakao")

OAUTH_PROVIDER_LABELS = {"google": "구글", "kakao": "카카오"}


def is_supported_oauth_provider(provider: str) -> bool:
    return provider in SUPPORTED_OAUTH_PROVIDERS


def _as_utc(value: datetime) -> datetime:
    """naive datetime(드라이버·DB 설정에 따라 섞여 들어온다)을 UTC로 맞춘다."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_password_reset_token_usable(
    *,
    expires_at: datetime,
    used_at: datetime | None,
    now: datetime,
) -> bool:
    """한 번 쓴 토큰과 만료된 토큰은 다시 쓸 수 없다."""
    if used_at is not None:
        return False
    return _as_utc(expires_at) > _as_utc(now)


def can_login_with_password(hashed_password: str | None) -> bool:
    """소셜 가입 유저는 비밀번호가 없으므로 비밀번호 로그인 대상이 아니다."""
    return bool(hashed_password)


def resolve_oauth_display_name(profile_name: str | None, email: str | None) -> str:
    """provider가 닉네임을 주지 않는 경우(카카오 동의 항목 미체크 등)의 표시 이름."""
    if profile_name and profile_name.strip():
        return profile_name.strip()
    if email and "@" in email:
        return email.split("@")[0]
    return "이름 없음"


def build_placeholder_email(provider: str, provider_user_id: str) -> str:
    """카카오처럼 이메일 동의를 받지 못한 경우에 쓰는 내부 전용 주소.

    users.email은 유니크 키라 비워 둘 수 없다. 실제로 발송 가능한 주소가 아니라는 것이
    도메인만 봐도 드러나야 해서 예약 도메인(.invalid)을 쓴다.
    """
    return f"{provider}_{provider_user_id}@users.adoptai.invalid"


def is_placeholder_email(email: str) -> bool:
    return email.endswith("@users.adoptai.invalid")


def is_safe_redirect_path(path: str | None) -> bool:
    """오픈 리다이렉트 방지 — FE proxy.ts와 같은 규칙(내부 절대 경로만 허용)."""
    if not path:
        return False
    return path.startswith("/") and not path.startswith("//")


def sanitize_redirect_path(path: str | None, *, fallback: str = "/") -> str:
    return path if path and is_safe_redirect_path(path) else fallback


def build_password_reset_link(frontend_base_url: str, token: str) -> str:
    return f"{frontend_base_url.rstrip('/')}/reset-password?token={token}"


def mask_email(email: str) -> str:
    """재설정 화면에 '어느 계정인지'만 알려주기 위한 마스킹 (ex. ab***@example.com)."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    visible = local[:2]
    return f"{visible}{'*' * max(len(local) - len(visible), 1)}@{domain}"
