from pathlib import Path
from typing import List
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "CSV Data Quality Analyzer"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str

    SECRET_KEY: str
    CSRF_SECRET: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    SESSION_COOKIE_NAME: str = "session_id"
    CSRF_COOKIE_NAME: str = "csrf_token"
    COOKIE_SAMESITE: str = "lax"

    MAX_UPLOAD_SIZE_MB: int = 50
    UPLOAD_DIR: str = "uploads"
    CLEANED_DIR: str = "cleaned"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if isinstance(value, str) and value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql://", 1)
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in ("production", "prod")

    @property
    def cookie_secure(self) -> bool:
        """Enable Secure cookies in production, where HTTPS is required."""
        return self.is_production

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_production_settings(self):
        if not self.is_production:
            return self

        for key in ("SECRET_KEY", "CSRF_SECRET"):
            if len(getattr(self, key)) < 32:
                raise ValueError(f"{key} must be set to a unique secret of at least 32 characters.")
        if self.SECRET_KEY == self.CSRF_SECRET:
            raise ValueError("SECRET_KEY and CSRF_SECRET must be different values.")

        if not self.DATABASE_URL.startswith("postgresql://"):
            raise ValueError("Production DATABASE_URL must point to PostgreSQL.")

        origins = self.cors_origins
        if len(origins) != 1:
            raise ValueError("Production ALLOWED_ORIGINS must contain exactly one HTTPS frontend origin.")
        origin = urlsplit(origins[0])
        if (
            origin.scheme != "https"
            or not origin.netloc
            or origin.username is not None
            or origin.password is not None
            or origin.hostname is None
            or origin.hostname.lower() == "localhost"
            or origin.hostname.lower().endswith(".localhost")
            or origin.hostname in ("127.0.0.1", "::1")
            or origin.path not in ("", "/")
            or origin.query
            or origin.fragment
            or "*" in origin.netloc
        ):
            raise ValueError("Production ALLOWED_ORIGINS must be one exact HTTPS origin without a path.")

        if self.COOKIE_SAMESITE.lower() != "lax":
            raise ValueError("Production COOKIE_SAMESITE must be 'lax' when frontend API calls use the same-origin proxy.")

        if not Path(self.UPLOAD_DIR).is_absolute() or not Path(self.CLEANED_DIR).is_absolute():
            raise ValueError("Production UPLOAD_DIR and CLEANED_DIR must be absolute persistent-storage paths.")
        return self

    @property
    def upload_path(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / self.UPLOAD_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cleaned_path(self) -> Path:
        path = Path(self.CLEANED_DIR)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / self.CLEANED_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
