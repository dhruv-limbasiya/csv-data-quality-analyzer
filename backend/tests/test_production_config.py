import pytest
from pydantic import ValidationError

from app.config import Settings


def production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgres://user:password@db.example.com:5432/app",
        "SECRET_KEY": "a" * 48,
        "CSRF_SECRET": "b" * 48,
        "ALLOWED_ORIGINS": "https://analyzer.example.com",
        "COOKIE_SAMESITE": "lax",
        "UPLOAD_DIR": "C:\\var\\data\\uploads",
        "CLEANED_DIR": "C:\\var\\data\\cleaned",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_settings_use_postgres_https_exact_origin_and_secure_cookies():
    settings = production_settings()

    assert settings.DATABASE_URL.startswith("postgresql://")
    assert settings.cors_origins == ["https://analyzer.example.com"]
    assert settings.cookie_secure is True
    assert settings.COOKIE_SAMESITE == "lax"
    assert settings.UPLOAD_DIR == "C:\\var\\data\\uploads"
    assert settings.CLEANED_DIR == "C:\\var\\data\\cleaned"


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
        {"UPLOAD_DIR": "uploads"},
        {"CLEANED_DIR": "cleaned"},
        {"COOKIE_SAMESITE": "none"},
    ],
)
def test_production_settings_reject_unsafe_values(override):
    with pytest.raises(ValidationError):
        production_settings(**override)
