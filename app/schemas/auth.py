from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class ResetTokenStatusResponse(BaseModel):
    """재설정 화면이 폼을 그리기 전에 링크가 아직 유효한지 확인한다."""

    valid: bool
    email: str | None = None  # 마스킹된 이메일 (ex. sh*****@example.com)


class OAuthProviderInfo(BaseModel):
    provider: str
    label: str
    authorize_path: str


class OAuthProvidersResponse(BaseModel):
    providers: list[OAuthProviderInfo]


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime


class AuthResponse(BaseModel):
    expires_in: int
    user: UserResponse


class TokenRefreshResponse(BaseModel):
    expires_in: int
