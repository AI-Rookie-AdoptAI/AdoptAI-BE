from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/adoptai"
    DATABASE_SSL: bool = False  # Supabase 등 외부 DB는 True
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 86400
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    COOKIE_SECURE: bool = False

    LOCAL_UPLOAD_DIR: str = "/tmp/adoptai_uploads"
    MAX_IMAGE_UPLOAD_BYTES: int = 10 * 1024 * 1024
    CORS_ORIGINS: str = "http://localhost:3000"

    # Supabase Storage (S3 호환). 셋이 모두 채워져야 S3 백엔드로 동작하고,
    # 비어 있으면 LOCAL_UPLOAD_DIR + /static 서빙으로 폴백한다.
    S3_ENDPOINT_URL: str = ""  # https://<project-ref>.storage.supabase.co/storage/v1/s3
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET: str = "adoptai-uploads"
    S3_REGION: str = "ap-northeast-2"  # Supabase 프로젝트 리전과 반드시 일치해야 함
    # public 버킷 URL(.../object/public/...) 생성용. 비우면 엔드포인트 기준 URL로 대체.
    SUPABASE_URL: str = ""  # https://<project-ref>.supabase.co
    STT_BASE_URL: str = "http://localhost:8001"
    STT_TIMEOUT_SECONDS: float = 180.0
    STT_INTERNAL_API_KEY: str = ""
    MAX_AUDIO_UPLOAD_BYTES: int = 25 * 1024 * 1024
    MAX_AUDIO_DURATION_SECONDS: float = 300.0

    VISION_BASE_URL: str = "http://localhost:8002"
    VISION_TIMEOUT_SECONDS: float = 180.0

    # 비밀번호 재설정 / 소셜 로그인이 사용자를 돌려보낼 프론트 주소
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # 메일 발송. SMTP_HOST가 비어 있으면 발송 대신 링크를 로그로 남긴다(로컬 개발).
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    SMTP_TIMEOUT_SECONDS: float = 10.0
    MAIL_FROM: str = "AdoptAI <no-reply@adoptai.local>"

    # OAuth. client id/secret이 모두 채워진 provider만 활성화된다.
    # redirect_uri는 <OAUTH_CALLBACK_BASE_URL>/api/v1/auth/oauth/<provider>/callback 로 만들어지고,
    # 각 콘솔에 등록한 값과 한 글자도 다르면 안 된다.
    OAUTH_CALLBACK_BASE_URL: str = "http://localhost:8000"
    OAUTH_TIMEOUT_SECONDS: float = 10.0
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    KAKAO_CLIENT_ID: str = ""
    KAKAO_CLIENT_SECRET: str = ""  # 카카오는 "보안 > Client Secret"을 끄면 빈 값이어도 된다

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin for item in self.CORS_ORIGINS.split(",") if (origin := item.strip())]

    @property
    def storage_backend(self) -> str:
        """자격증명이 모두 설정됐을 때만 S3를 쓴다 (미설정 로컬 개발은 디스크 폴백)."""
        if self.S3_ENDPOINT_URL and self.S3_ACCESS_KEY_ID and self.S3_SECRET_ACCESS_KEY:
            return "s3"
        return "local"

    @property
    def email_backend(self) -> str:
        """SMTP가 설정됐을 때만 실제로 보낸다 (미설정 로컬 개발은 로그 폴백)."""
        return "smtp" if self.SMTP_HOST else "log"

    @property
    def enabled_oauth_providers(self) -> list[str]:
        """client id가 채워진 provider만 로그인 버튼·엔드포인트에 노출된다."""
        enabled = []
        if self.GOOGLE_CLIENT_ID:
            enabled.append("google")
        if self.KAKAO_CLIENT_ID:
            enabled.append("kakao")
        return enabled


settings = Settings()
