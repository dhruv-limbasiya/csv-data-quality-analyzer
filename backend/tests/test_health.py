from fastapi.testclient import TestClient
from app.main import app

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
