import pytest
from pydantic import ValidationError

from app.config import Settings


def production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql://local-user:placeholder-only@db.example.com:5432/app",
        "SECRET_KEY": "a" * 48,
        "CSRF_SECRET": "b" * 48,
        "ALLOWED_ORIGINS": "https://analyzer.example.com",
        "COOKIE_SAMESITE": "none",
        "STORAGE_BACKEND": "r2",
        # Keep test cases deterministic when the caller has local storage
        # directories configured in its environment.
        "UPLOAD_DIR": "uploads",
        "CLEANED_DIR": "cleaned",
        "R2_ACCOUNT_ID": "example-account",
        "R2_BUCKET": "analyzer-test",
        "R2_ACCESS_KEY_ID": "placeholder-access",
        "R2_SECRET_ACCESS_KEY": "placeholder-secret",
        "MAX_UPLOAD_SIZE_MB": 5,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_requires_postgres_exact_https_origin_and_private_r2():
    settings = production_settings()

    assert settings.DATABASE_URL.startswith("postgresql://")
    assert settings.cors_origins == ["https://analyzer.example.com"]
    assert settings.cookie_secure is True
    assert settings.COOKIE_SAMESITE == "none"
    assert settings.STORAGE_BACKEND == "r2"
    assert settings.MAX_UPLOAD_SIZE_MB == 5


@pytest.mark.parametrize(
    "override",
    [
        {"SECRET_KEY": "short"},
        {"CSRF_SECRET": "a" * 48},
        {"DATABASE_URL": "sqlite:///application.db"},
        {"ALLOWED_ORIGINS": "http://localhost:5173"},
        {"ALLOWED_ORIGINS": "https://one.example,https://two.example"},
        {"ALLOWED_ORIGINS": "https://analyzer.example.com/dashboard"},
        {"ALLOWED_ORIGINS": "https://localhost:5173"},
        {"COOKIE_SAMESITE": "lax"},
        {"STORAGE_BACKEND": "local"},
        {"R2_BUCKET": ""},
        {"MAX_UPLOAD_SIZE_MB": 6},
        {"R2_PRESIGNED_URL_TTL_SECONDS": 30},
    ],
)
def test_production_rejects_unsafe_or_incomplete_settings(override):
    with pytest.raises(ValidationError):
        production_settings(**override)


def test_production_normalizes_legacy_postgres_scheme():
    settings = production_settings(
        DATABASE_URL="postgres://local-user:placeholder-only@db.example.com:5432/app"
    )
    assert settings.DATABASE_URL.startswith("postgresql://")


def test_production_supports_non_vercel_persistent_local_storage(tmp_path):
    settings = production_settings(
        STORAGE_BACKEND="local",
        COOKIE_SAMESITE="none",
        UPLOAD_DIR=str(tmp_path / "uploads"),
        CLEANED_DIR=str(tmp_path / "cleaned"),
    )
    assert settings.UPLOAD_DIR == str(tmp_path / "uploads")
