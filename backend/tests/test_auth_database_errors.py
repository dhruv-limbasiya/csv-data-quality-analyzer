from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.database import get_db
from app.main import app


class FailingLoginDatabase:
    def query(self, _model):
        raise OperationalError(
            "SELECT users",
            {},
            RuntimeError("simulated database failure"),
        )


def test_login_returns_safe_service_unavailable_when_database_query_fails():
    app.dependency_overrides[get_db] = FailingLoginDatabase
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/api/auth/login",
            json={
                "username_or_email": "sample-user",
                "password": "not-a-real-password",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Authentication is temporarily unavailable. Please try again later."
    }
    assert "simulated database failure" not in response.text
