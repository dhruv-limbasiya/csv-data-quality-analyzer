import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, settings
from app.database import Base, get_db
from app.main import app
from app.models.dataset import Dataset
from app.models.user import User
from app.services.security import hash_password


@pytest.fixture
def isolated_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, test_session
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_demo_mode_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    test_settings = Settings(
        _env_file=None,
        DATABASE_URL="sqlite://",
        SECRET_KEY="local-secret",
        CSRF_SECRET="different-local-secret",
    )

    assert test_settings.DEMO_MODE is False


def test_disabled_demo_keeps_registration_and_login_available(isolated_client, monkeypatch):
    client, _ = isolated_client
    monkeypatch.setattr(settings, "DEMO_MODE", False)

    assert client.post("/api/auth/demo").status_code == 404
    assert client.post(
        "/api/auth/register",
        json={
            "username": "normal_demo_test",
            "email": "normal-demo-test@example.com",
            "password": "StrongPassword123!",
        },
    ).status_code == 201

    login = client.post(
        "/api/auth/login",
        json={
            "username_or_email": "normal_demo_test",
            "password": "StrongPassword123!",
        },
    )
    assert login.status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "normal_demo_test"


def test_demo_session_isolated_and_still_requires_csrf(isolated_client, monkeypatch):
    client, session_factory = isolated_client
    monkeypatch.setattr(settings, "DEMO_MODE", True)

    assert client.get("/api/auth/me").status_code == 401
    assert client.post(
        "/api/auth/register",
        json={
            "username": "blocked_register",
            "email": "blocked-register@example.com",
            "password": "StrongPassword123!",
        },
    ).status_code == 404
    assert client.post(
        "/api/auth/login",
        json={"username_or_email": "blocked_register", "password": "StrongPassword123!"},
    ).status_code == 404

    db = session_factory()
    owner = User(
        username="separate_owner",
        email="separate-owner@example.com",
        hashed_password=hash_password("StrongPassword123!"),
    )
    db.add(owner)
    db.flush()
    dataset = Dataset(
        user_id=owner.id,
        original_filename="private.csv",
        stored_filename="private.csv",
        file_path="private.csv",
        file_size_bytes=12,
        upload_status="pending",
    )
    db.add(dataset)
    db.commit()
    dataset_id = dataset.id
    owner_id = owner.id
    db.close()

    demo = client.post("/api/auth/demo")
    assert demo.status_code == 200
    demo_user = demo.json()
    assert demo_user["username"].startswith("demo_")
    assert demo_user["id"] != owner_id
    assert "httponly" in demo.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["id"] == demo_user["id"]
    assert client.get(f"/api/datasets/{dataset_id}").status_code == 403

    csrf_token = client.cookies.get(settings.CSRF_COOKIE_NAME)
    client.cookies.delete(settings.CSRF_COOKIE_NAME)
    assert client.post("/api/auth/logout").status_code == 403

    client.cookies.set(settings.CSRF_COOKIE_NAME, csrf_token)
    assert client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    ).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
