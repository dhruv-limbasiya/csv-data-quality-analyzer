import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.dataset import Dataset
from app.services.security import verify_password, hash_password


@pytest.fixture(scope="module")
def db():
    """Provides a database session for test setup and teardown."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module", autouse=True)
def clean_module_users(db: Session):
    """Clean up any test users created during auth testing (before and after module)."""
    def _cleanup():
        test_pattern = "auth_%"
        users = db.query(User).filter(User.username.like(test_pattern)).all()
        for u in users:
            db.query(Dataset).filter(Dataset.user_id == u.id).delete()
            db.delete(u)
        db.commit()

    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def client():
    """Clean TestClient with cookies enabled."""
    return TestClient(app)


@pytest.fixture
def registered_user(db: Session):
    """Ensures a dedicated registered user exists for login and session tests."""
    username = "auth_login_user"
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(
            username=username,
            email="auth_login_user@example.com",
            hashed_password=hash_password("StrongPassword123!"),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# -------------------------------------------------------------------------
# 1. Registration Tests
# -------------------------------------------------------------------------

def test_successful_registration(client: TestClient, db: Session):
    """Verify user registration sets password hash, returns safe response, and issues cookies."""
    payload = {
        "username": "auth_reg_user",
        "email": "auth_reg@example.com",
        "password": "StrongPassword123!",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["username"] == "auth_reg_user"
    assert data["email"] == "auth_reg@example.com"
    assert data["is_active"] is True
    assert "hashed_password" not in data  # Never leak password hash

    # Verify database record
    user = db.query(User).filter(User.username == "auth_reg_user").first()
    assert user is not None
    assert user.hashed_password != "StrongPassword123!"  # Never store plaintext
    assert user.hashed_password.startswith("$2b$")  # Bcrypt hash prefix
    assert verify_password("StrongPassword123!", user.hashed_password)

    # Verify cookies were set
    assert settings.SESSION_COOKIE_NAME in response.cookies
    assert settings.CSRF_COOKIE_NAME in response.cookies


def test_registration_duplicate_username(client: TestClient, registered_user: User):
    """Verify registering with an existing username returns 409 Conflict."""
    payload = {
        "username": registered_user.username,
        "email": "another_unique_email@example.com",
        "password": "StrongPassword123!",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 409
    assert "username already exists" in response.json()["detail"].lower()


def test_registration_duplicate_email(client: TestClient, registered_user: User):
    """Verify registering with an existing email returns 409 Conflict."""
    payload = {
        "username": "unique_username_999",
        "email": registered_user.email,
        "password": "StrongPassword123!",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 409
    assert "email address already exists" in response.json()["detail"].lower()


def test_registration_rolls_back_user_when_session_creation_fails(db: Session, monkeypatch):
    """A failed session insert must not leave a user account without a session."""
    def fail_session_creation(_response, _session, _user_id):
        raise OperationalError(
            "INSERT INTO user_sessions",
            {},
            RuntimeError("simulated session table failure"),
        )

    monkeypatch.setattr("app.routers.auth.set_auth_cookies", fail_session_creation)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/auth/register",
        json={
            "username": "auth_atomic_user",
            "email": "auth_atomic@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert db.query(User).filter(User.username == "auth_atomic_user").first() is None


def test_registration_input_validation(client: TestClient):
    """Verify invalid usernames, emails, and weak passwords return 422."""
    # Username with invalid special chars
    r1 = client.post("/api/auth/register", json={
        "username": "bad username!",
        "email": "valid@example.com",
        "password": "ValidPassword123"
    })
    assert r1.status_code == 422

    # Invalid email format
    r2 = client.post("/api/auth/register", json={
        "username": "valid_user",
        "email": "not-an-email",
        "password": "ValidPassword123"
    })
    assert r2.status_code == 422

    # Password too short (< 8 chars)
    r3 = client.post("/api/auth/register", json={
        "username": "valid_user",
        "email": "valid@example.com",
        "password": "short"
    })
    assert r3.status_code == 422


# -------------------------------------------------------------------------
# 2. Login, Logout, and Session Tests
# -------------------------------------------------------------------------

def test_login_with_username_and_email(client: TestClient, registered_user: User):
    """Verify login works with either username or email and validates password."""
    # 1. Login with username
    r_user = client.post("/api/auth/login", json={
        "username_or_email": registered_user.username,
        "password": "StrongPassword123!"
    })
    assert r_user.status_code == 200
    assert r_user.json()["username"] == registered_user.username
    assert settings.SESSION_COOKIE_NAME in r_user.cookies

    # 2. Login with email
    r_email = client.post("/api/auth/login", json={
        "username_or_email": registered_user.email,
        "password": "StrongPassword123!"
    })
    assert r_email.status_code == 200
    assert r_email.json()["email"] == registered_user.email


def test_login_failure_invalid_credentials(client: TestClient, registered_user: User):
    """Verify wrong password or nonexistent user returns 401."""
    # Wrong password
    r1 = client.post("/api/auth/login", json={
        "username_or_email": registered_user.username,
        "password": "WrongPassword!"
    })
    assert r1.status_code == 401
    assert "Invalid username/email or password" in r1.json()["detail"]

    # Nonexistent user
    r2 = client.post("/api/auth/login", json={
        "username_or_email": "nonexistent_user_999",
        "password": "AnyPassword123"
    })
    assert r2.status_code == 401


def test_cookie_security_attributes(client: TestClient, registered_user: User):
    """Verify session cookie attributes: HttpOnly, SameSite, path."""
    response = client.post("/api/auth/login", json={
        "username_or_email": registered_user.username,
        "password": "StrongPassword123!"
    })
    assert response.status_code == 200

    # Inspect Set-Cookie header
    cookie_headers = response.headers.get_list("set-cookie") if hasattr(response.headers, "get_list") else [response.headers.get("set-cookie", "")]
    combined_cookies = " ".join(cookie_headers)

    # Session cookie must be HttpOnly
    assert "httponly" in combined_cookies.lower()
    # SameSite must be lax
    assert "samesite=lax" in combined_cookies.lower()
    # Path must be /
    assert "path=/" in combined_cookies.lower()


def test_get_current_user_profile(client: TestClient, registered_user: User):
    """Verify GET /api/auth/me returns current user when authenticated, 401 when not."""
    # 1. Unauthenticated request
    unauth_client = TestClient(app)
    r_unauth = unauth_client.get("/api/auth/me")
    assert r_unauth.status_code == 401

    # 2. Authenticated request using session cookie from client
    client.post("/api/auth/login", json={
        "username_or_email": registered_user.username,
        "password": "StrongPassword123!"
    })
    r_auth = client.get("/api/auth/me")
    assert r_auth.status_code == 200
    assert r_auth.json()["username"] == registered_user.username


def test_tampered_or_invalid_session_rejected(client: TestClient):
    """Verify tampered session cookies return 401 Unauthorized."""
    tampered_client = TestClient(app)
    tampered_client.cookies.set(settings.SESSION_COOKIE_NAME, "tampered.invalid.token.signature")
    response = tampered_client.get("/api/auth/me")
    assert response.status_code == 401
    assert "Session has expired or is invalid" in response.json()["detail"]


def test_logout_clears_session(client: TestClient, registered_user: User):
    """Verify POST /api/auth/logout clears cookies and invalidates session."""
    # Login first
    login_res = client.post("/api/auth/login", json={
        "username_or_email": registered_user.username,
        "password": "StrongPassword123!"
    })
    assert login_res.status_code == 200
    csrf_token = client.cookies.get(settings.CSRF_COOKIE_NAME)
    assert csrf_token is not None
    # Verify logged in
    assert client.get("/api/auth/me").status_code == 200

    missing_csrf_res = client.post("/api/auth/logout")
    assert missing_csrf_res.status_code == 403
    assert client.get("/api/auth/me").status_code == 200

    # Logout
    logout_res = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_res.status_code == 200
    assert "Logged out successfully" in logout_res.json()["message"]

    # Verify session is no longer valid
    subsequent_res = client.get("/api/auth/me")
    assert subsequent_res.status_code == 401


# -------------------------------------------------------------------------
# 3. CSRF Protection Tests
# -------------------------------------------------------------------------

def test_csrf_protection_on_state_changing_requests(client: TestClient, registered_user: User):
    """
    Verify CSRF protection:
    - State-changing requests with session cookie but missing X-CSRF-Token return 403.
    - Requests with invalid X-CSRF-Token return 403.
    - Requests with valid X-CSRF-Token succeed.
    """
    # Login to obtain session and csrf cookies
    login_res = client.post("/api/auth/login", json={
        "username_or_email": registered_user.username,
        "password": "StrongPassword123!"
    })
    assert login_res.status_code == 200
    csrf_token = client.cookies.get(settings.CSRF_COOKIE_NAME)
    assert csrf_token is not None

    csv_data = b"id,val\n1,100"

    # 1. State-changing upload WITHOUT X-CSRF-Token header -> 403 Forbidden
    res_no_csrf = client.post(
        "/api/datasets/upload",
        files={"file": ("auth_test.csv", csv_data, "text/csv")}
    )
    assert res_no_csrf.status_code == 403
    assert "CSRF verification failed" in res_no_csrf.json()["detail"]

    # 2. State-changing upload with MISMATCHED X-CSRF-Token header -> 403 Forbidden
    res_bad_csrf = client.post(
        "/api/datasets/upload",
        headers={"X-CSRF-Token": "bad-csrf-token"},
        files={"file": ("auth_test.csv", csv_data, "text/csv")}
    )
    assert res_bad_csrf.status_code == 403
    assert "CSRF verification failed" in res_bad_csrf.json()["detail"]

    # 3. State-changing upload with VALID matching X-CSRF-Token header -> 201 Created
    res_valid_csrf = client.post(
        "/api/datasets/upload",
        headers={"X-CSRF-Token": csrf_token},
        files={"file": ("auth_test.csv", csv_data, "text/csv")}
    )
    assert res_valid_csrf.status_code == 201
    assert res_valid_csrf.json()["original_filename"] == "auth_test.csv"


# -------------------------------------------------------------------------
# 4. Cross-User Dataset Ownership with Real Sessions
# -------------------------------------------------------------------------

def test_cross_user_dataset_isolation_with_sessions():
    """Verify that User B cannot access User A's dataset using real cookie sessions."""
    client_a = TestClient(app)
    client_b = TestClient(app)

    # Register User A
    reg_a = client_a.post("/api/auth/register", json={
        "username": "auth_user_a_iso",
        "email": "user_a_iso@example.com",
        "password": "Password123!"
    })
    assert reg_a.status_code == 201
    csrf_a = client_a.cookies.get(settings.CSRF_COOKIE_NAME)

    # User A uploads a dataset
    up_res = client_a.post(
        "/api/datasets/upload",
        headers={"X-CSRF-Token": csrf_a},
        files={"file": ("user_a_private.csv", b"col1,col2\n1,2", "text/csv")}
    )
    assert up_res.status_code == 201
    dataset_a_id = up_res.json()["id"]

    # Register User B
    reg_b = client_b.post("/api/auth/register", json={
        "username": "auth_user_b_iso",
        "email": "user_b_iso@example.com",
        "password": "Password123!"
    })
    assert reg_b.status_code == 201

    # User B lists datasets -> must NOT see User A's dataset
    list_b = client_b.get("/api/datasets")
    assert list_b.status_code == 200
    ids_b = [d["id"] for d in list_b.json()["items"]]
    assert dataset_a_id not in ids_b

    # User B attempts to get User A's dataset by ID -> 403 Forbidden
    detail_b = client_b.get(f"/api/datasets/{dataset_a_id}")
    assert detail_b.status_code == 403
    assert "Access denied" in detail_b.json()["detail"]
