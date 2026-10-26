import io
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.config import settings
from app.database import get_db, SessionLocal
from app.models.user import User
from app.models.dataset import Dataset
from app.auth import get_current_user


@pytest.fixture(scope="module")
def db_session():
    """Provides a database session for test setup and teardown."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def test_user(db_session: Session):
    """Creates a temporary test user."""
    user = db_session.query(User).filter(User.username == "test_phase2_user").first()
    if not user:
        user = User(
            email="test_phase2@example.com",
            username="test_phase2_user",
            hashed_password="not_a_real_hash_for_testing_only",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    yield user
    # Cleanup test user datasets
    db_session.query(Dataset).filter(Dataset.user_id == user.id).delete()
    db_session.delete(user)
    db_session.commit()


@pytest.fixture(scope="module")
def second_user(db_session: Session):
    """Creates a second temporary test user to test permission boundaries."""
    user = db_session.query(User).filter(User.username == "test_phase2_other_user").first()
    if not user:
        user = User(
            email="test_phase2_other@example.com",
            username="test_phase2_other_user",
            hashed_password="not_a_real_hash_for_testing_only",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    yield user
    # Cleanup
    db_session.query(Dataset).filter(Dataset.user_id == user.id).delete()
    db_session.delete(user)
    db_session.commit()


@pytest.fixture
def auth_client(test_user):
    """TestClient authenticated as test_user via dependency override."""
    app.dependency_overrides[get_current_user] = lambda: test_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauth_client():
    """TestClient without authentication override."""
    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app)


@pytest.fixture
def temp_upload_dir(monkeypatch):
    """Directs file uploads to an isolated temporary directory during testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(settings, "UPLOAD_DIR", tmpdir)
        yield Path(tmpdir)


# -------------------------------------------------------------------------
# 1. Authentication & Permission Tests
# -------------------------------------------------------------------------

def test_unauthenticated_upload_rejected(unauth_client):
    """Verify that unauthenticated upload returns 401 Unauthorized."""
    csv_content = b"id,name\n1,Alice\n2,Bob"
    response = unauth_client.post(
        "/api/datasets/upload",
        files={"file": ("test.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


def test_unauthenticated_list_rejected(unauth_client):
    """Verify listing datasets without auth returns 401."""
    response = unauth_client.get("/api/datasets")
    assert response.status_code == 401


def test_upload_internal_error_does_not_leak_exception(auth_client, monkeypatch):
    def fail_upload(_upload):
        raise RuntimeError("private-storage-path")

    monkeypatch.setattr("app.routers.datasets.save_upload_stream", fail_upload)
    response = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("data.csv", b"id\n1", "text/csv")},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "An error occurred while processing the uploaded file."
    assert "private-storage-path" not in response.text


def test_cross_user_dataset_access_forbidden(auth_client, second_user, db_session, temp_upload_dir):
    """Verify a user cannot retrieve another user's dataset (returns 403)."""
    # Create a dataset directly for second_user
    fake_file = temp_upload_dir / "other_user.csv"
    fake_file.write_text("id,val\n1,100")
    other_dataset = Dataset(
        user_id=second_user.id,
        original_filename="other_user.csv",
        stored_filename="other_user.csv",
        file_path=str(fake_file),
        file_size_bytes=fake_file.stat().st_size,
        row_count=1,
        column_count=2,
        columns_metadata=[],
    )
    db_session.add(other_dataset)
    db_session.commit()
    db_session.refresh(other_dataset)

    # Attempt to access using test_user's client
    response = auth_client.get(f"/api/datasets/{other_dataset.id}")
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]


# -------------------------------------------------------------------------
# 2. File Validation Tests
# -------------------------------------------------------------------------

def test_upload_invalid_extension_rejected(auth_client, temp_upload_dir):
    """Verify files without .csv extension are rejected with HTTP 400."""
    response = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("malicious.exe", b"not a csv file", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Only CSV files (.csv) are allowed" in response.json()["detail"]


def test_upload_empty_file_rejected(auth_client, temp_upload_dir):
    """Verify 0-byte file upload is rejected and no file remains on disk."""
    response = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()
    # Ensure no files left in upload dir
    assert len(list(temp_upload_dir.glob("*.csv"))) == 0


def test_upload_malformed_unsupported_encoding(auth_client, temp_upload_dir):
    """Verify non-UTF-8 bytes are handled with an appropriate error."""
    # Invalid UTF-8 sequence
    bad_bytes = b"id,name\n1,\xff\xfe\x00\x00\x80"
    response = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("bad_encoding.csv", bad_bytes, "text/csv")},
    )
    assert response.status_code in (400, 422)


def test_upload_csv_no_headers(auth_client, temp_upload_dir):
    """Verify CSV with only whitespace or no usable headers returns 400."""
    response = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("no_headers.csv", b",,,\n,,,\n", "text/csv")},
    )
    assert response.status_code == 400
    assert "headers" in response.json()["detail"].lower()


def test_upload_oversized_file(auth_client, monkeypatch, temp_upload_dir):
    """Verify uploads exceeding configured MAX_UPLOAD_SIZE_MB return 413."""
    # Temporarily set max size to 0.001 MB (~1000 bytes)
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 0.001)
    large_content = b"a" * 2000
    response = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("big.csv", large_content, "text/csv")},
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed upload size" in response.json()["detail"]
    # Check that partial file is cleaned up
    assert len(list(temp_upload_dir.glob("*.csv"))) == 0


# -------------------------------------------------------------------------
# 3. Path Traversal & Collision Safety
# -------------------------------------------------------------------------

def test_path_traversal_sanitized(auth_client, temp_upload_dir):
    """Verify filenames with path traversal elements are safely sanitized."""
    csv_content = b"id,name\n1,Alpha"
    response = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("../../../../etc/passwd.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "passwd.csv"
    assert ".." not in data["original_filename"]


def test_filename_collision_safety(auth_client, temp_upload_dir):
    """Verify uploading two files with the identical original filename creates 2 unique files."""
    csv_content = b"id,value\n1,10\n2,20"
    res1 = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("same_name.csv", csv_content, "text/csv")},
    )
    res2 = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("same_name.csv", csv_content, "text/csv")},
    )
    assert res1.status_code == 201
    assert res2.status_code == 201
    assert res1.json()["id"] != res2.json()["id"]
    files = list(temp_upload_dir.glob("*.csv"))
    assert len(files) == 2


# -------------------------------------------------------------------------
# 4. Valid Upload, Parsing & Metadata
# -------------------------------------------------------------------------

def test_valid_csv_upload_and_metadata(auth_client, temp_upload_dir):
    """Test valid CSV upload with UTF-8 BOM, diverse data types, and preview extraction."""
    # Include UTF-8 BOM \xef\xbb\xbf
    bom_csv = (
        "\ufeffid,name,amount,is_active,signup_date\n"
        "1,Alice,123.45,True,2023-01-15\n"
        "2,Bob,99.00,False,2023-02-20\n"
        "3,Charlie,,True,2023-03-25\n"
    ).encode("utf-8")

    response = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("customers.csv", bom_csv, "text/csv")},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["original_filename"] == "customers.csv"
    assert data["row_count"] == 3
    assert data["column_count"] == 5
    assert len(data["columns_metadata"]) == 5
    assert len(data["preview_rows"]) == 3

    # Check that preview rows are JSON serializable and handle missing values
    charlie_row = [r for r in data["preview_rows"] if r["name"] == "Charlie"][0]
    assert charlie_row["amount"] is None or charlie_row["amount"] == "" or str(charlie_row["amount"]) == "None"


def test_duplicate_column_headers_handled(auth_client, temp_upload_dir):
    """Verify CSV with duplicate header names is safely renamed and flagged."""
    dup_csv = b"metric,value,metric,value\n1,10,2,20\n3,30,4,40"
    response = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("duplicates.csv", dup_csv, "text/csv")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["column_count"] == 4
    col_names = [col["name"] for col in data["columns_metadata"]]
    assert len(set(col_names)) == 4  # All resulting names must be unique
    has_dups = any(col["has_duplicates"] for col in data["columns_metadata"])
    assert has_dups is True


# -------------------------------------------------------------------------
# 5. List and Get Dataset Endpoints
# -------------------------------------------------------------------------

def test_list_and_get_dataset(auth_client, temp_upload_dir):
    """Verify GET /api/datasets and GET /api/datasets/{id}."""
    csv_content = b"x,y\n10,20\n30,40"
    upload_res = auth_client.post(
        "/api/datasets/upload",
        files={"file": ("points.csv", csv_content, "text/csv")},
    )
    assert upload_res.status_code == 201
    ds_id = upload_res.json()["id"]

    # List datasets
    list_res = auth_client.get("/api/datasets")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    ids = [item["id"] for item in list_data["items"]]
    assert ds_id in ids

    # Get specific dataset
    get_res = auth_client.get(f"/api/datasets/{ds_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["id"] == ds_id
    assert get_data["original_filename"] == "points.csv"
    assert len(get_data["preview_rows"]) == 2


def test_get_nonexistent_dataset(auth_client):
    """Verify requesting non-existent dataset returns 404."""
    response = auth_client.get("/api/datasets/99999999")
    assert response.status_code == 404


def test_get_dataset_surfaces_missing_storage_file(auth_client, db_session, test_user, temp_upload_dir):
    """A missing stored CSV must not be reported as a successful empty preview."""
    dataset = Dataset(
        user_id=test_user.id,
        original_filename="missing.csv",
        stored_filename=f"missing-{test_user.id}.csv",
        file_path=str(temp_upload_dir / "missing.csv"),
        file_size_bytes=1,
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)

    try:
        response = auth_client.get(f"/api/datasets/{dataset.id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Source dataset file was not found on disk."
    finally:
        db_session.delete(dataset)
        db_session.commit()


def test_database_failure_cleans_up_file(auth_client, temp_upload_dir):
    """Verify that if database persistence fails, the uploaded file is cleaned up."""
    csv_content = b"a,b\n1,2"
    with patch("sqlalchemy.orm.Session.commit", side_effect=Exception("Simulated DB Crash")):
        response = auth_client.post(
            "/api/datasets/upload",
            files={"file": ("fail_cleanup.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "An error occurred while processing the uploaded file."
        assert "Simulated DB Crash" not in response.text

    # Verify no leaked files in upload directory
    remaining_files = list(temp_upload_dir.glob("*.csv"))
    assert len(remaining_files) == 0
