from fastapi.testclient import TestClient

from app.main import app


def test_mutating_request_rejects_unconfigured_origin_before_auth_or_database():
    response = TestClient(app).post(
        "/api/auth/login",
        json={"username_or_email": "irrelevant", "password": "not-a-real-password"},
        headers={"Origin": "https://untrusted.example"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Request origin is not allowed."


def test_api_responses_include_security_headers():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
