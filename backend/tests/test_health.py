from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from sqlalchemy.exc import SQLAlchemyError

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "CSV Data Quality Analyzer" in data["message"]
    assert "version" in data


def test_health_check_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "CSV Data Quality Analyzer"
    assert "status" in data
    assert "database" in data


def test_health_check_fails_when_database_is_unavailable():
    class FailingDatabase:
        def execute(self, _statement):
            raise SQLAlchemyError("database unavailable")

    def failing_db():
        yield FailingDatabase()

    app.dependency_overrides[get_db] = failing_db
    try:
        response = client.get("/api/health")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Database health check failed."
