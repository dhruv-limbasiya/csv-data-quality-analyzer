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

    MAX_UPLOAD_SIZE_MB: int = 5
    UPLOAD_DIR: str = "uploads"
    CLEANED_DIR: str = "cleaned"
    STORAGE_BACKEND: str = "local"
    R2_ACCOUNT_ID: str = ""
    R2_BUCKET: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_PRESIGNED_URL_TTL_SECONDS: int = 300

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

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

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

        if self.STORAGE_BACKEND.lower() == "r2":
            if not all((self.R2_ACCOUNT_ID, self.R2_BUCKET, self.R2_ACCESS_KEY_ID, self.R2_SECRET_ACCESS_KEY)):
                raise ValueError("Production R2 storage configuration is incomplete.")
            if self.COOKIE_SAMESITE.lower() != "none":
                raise ValueError("Production COOKIE_SAMESITE must be 'none' for separate frontend and API origins.")
            if self.MAX_UPLOAD_SIZE_MB < 1 or self.MAX_UPLOAD_SIZE_MB > 5:
                raise ValueError("R2 deployments require MAX_UPLOAD_SIZE_MB between 1 and 5.")
            if self.R2_PRESIGNED_URL_TTL_SECONDS < 60 or self.R2_PRESIGNED_URL_TTL_SECONDS > 600:
                raise ValueError("R2_PRESIGNED_URL_TTL_SECONDS must be between 60 and 600 seconds.")
        elif self.STORAGE_BACKEND.lower() == "local":
            if not Path(self.UPLOAD_DIR).is_absolute() or not Path(self.CLEANED_DIR).is_absolute():
                raise ValueError("Production local storage paths must be absolute persistent-storage paths.")
            if self.COOKIE_SAMESITE.lower() not in {"lax", "none"}:
                raise ValueError("Production COOKIE_SAMESITE must be 'lax' or 'none'.")
        else:
            raise ValueError("STORAGE_BACKEND must be 'r2' or 'local'.")
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
