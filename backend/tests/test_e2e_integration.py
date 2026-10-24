import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from pathlib import Path

from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.dataset import Dataset
from app.models.analysis import Analysis
from app.models.cleaning import CleaningRecord


@pytest.fixture(scope="module")
def db():
    """Provides a database session for test teardown."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module", autouse=True)
def clean_e2e_users(db: Session):
    """Clean up test users and data created during E2E testing."""
    def _cleanup():
        test_pattern = "e2e_test_%"
        users = db.query(User).filter(User.username.like(test_pattern)).all()
        for u in users:
            # Delete cleanings, analyses, datasets
            db.query(CleaningRecord).filter(CleaningRecord.user_id == u.id).delete()
            db.query(Analysis).filter(Analysis.user_id == u.id).delete()
            datasets = db.query(Dataset).filter(Dataset.user_id == u.id).all()
            for d in datasets:
                try:
                    p = Path(d.file_path)
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
            db.query(Dataset).filter(Dataset.user_id == u.id).delete()
            db.delete(u)
        db.commit()

    _cleanup()
    yield
    _cleanup()


def test_complete_e2e_workflow(db: Session):
    """
    Executes the full 14-step integration test workflow as required by Task 10:
    1. Register
    2. Session check / me
    3. Upload CSV
    4. Dataset list
    5. Dataset detail
    6. Run quality analysis
    7. Analysis results & history
    8. Preview cleaning
    9. Apply cleaning
    10. Cleaning history
    11. Download cleaned CSV
    12. Logout
    13. Unauthenticated access blocked
    14. Cross-user data isolation (User B cannot access User A's data)
    """
    client = TestClient(app)

    # 1. Register User A
    user_a_payload = {
        "username": "e2e_test_user_a",
        "email": "e2e_test_a@example.com",
        "password": "SecurePassword123!",
    }
    reg_res = client.post("/api/auth/register", json=user_a_payload)
    assert reg_res.status_code == 201
    user_a_id = reg_res.json()["id"]

    # Verify cookies established
    assert settings.SESSION_COOKIE_NAME in client.cookies
    assert settings.CSRF_COOKIE_NAME in client.cookies
    csrf_token_a = client.cookies[settings.CSRF_COOKIE_NAME]

    # 2. Session check (verify persistence across requests)
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "e2e_test_user_a"

    # 3. Upload a CSV file with an exact duplicate row
    csv_content = (
        "id,name,email,age,score\n"
        "1,Alice,alice@example.com,25,90.5\n"
        "2,Bob,bob@example.com,30,85.0\n"
        "3,Charlie,invalid-email,N/A,92.0\n"
        "1,Alice,alice@example.com,25,90.5\n"  # exact duplicate row
    )
    upload_res = client.post(
        "/api/datasets/upload",
        files={"file": ("test_workflow.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        headers={"X-CSRF-Token": csrf_token_a},
    )
    assert upload_res.status_code == 201
    dataset_data = upload_res.json()
    dataset_id = dataset_data["id"]
    assert dataset_data["original_filename"] == "test_workflow.csv"
    assert dataset_data["row_count"] == 4
    assert dataset_data["column_count"] == 5
    assert len(dataset_data["preview_rows"]) == 4

    # 4. Confirm dataset appears in dataset list
    list_res = client.get("/api/datasets")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert any(d["id"] == dataset_id for d in items)

    # 5. Open dataset details
    detail_res = client.get(f"/api/datasets/{dataset_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == dataset_id
    assert len(detail_res.json()["columns_metadata"]) == 5

    # 6. Run Quality Analysis
    analyze_res = client.post(
        f"/api/datasets/{dataset_id}/analyze",
        headers={"X-CSRF-Token": csrf_token_a},
    )
    assert analyze_res.status_code == 201
    analysis_data = analyze_res.json()
    analysis_id = analysis_data["id"]
    assert 0 <= analysis_data["overall_score"] <= 100
    assert analysis_data["summary_stats"]["total_rows"] == 4
    assert len(analysis_data["issues"]) > 0
    assert len(analysis_data["recommendations"]) > 0

    # 7. View analysis results & history
    history_res = client.get(f"/api/datasets/{dataset_id}/analyses")
    assert history_res.status_code == 200
    assert history_res.json()["total"] >= 1
    assert history_res.json()["items"][0]["id"] == analysis_id

    single_ana_res = client.get(f"/api/analyses/{analysis_id}")
    assert single_ana_res.status_code == 200
    assert single_ana_res.json()["id"] == analysis_id

    # 8. Preview cleaning transformations (zero persistence)
    cleaning_config = {
        "whitespace_cleaning": {"enabled": True, "trim_whitespace": True},
        "duplicate_removal": {"enabled": True, "keep": "first"},
    }
    preview_res = client.post(
        f"/api/datasets/{dataset_id}/clean/preview",
        json={"config": cleaning_config, "preview_limit": 10},
        headers={"X-CSRF-Token": csrf_token_a},
    )
    assert preview_res.status_code == 200
    prev_json = preview_res.json()
    assert prev_json["summary"]["rows"]["before"] == 4
    assert prev_json["summary"]["rows"]["after"] == 3  # Duplicate removed

    # 9. Apply cleaning and persist separate cleaned output
    apply_res = client.post(
        f"/api/datasets/{dataset_id}/clean",
        json={"config": cleaning_config},
        headers={"X-CSRF-Token": csrf_token_a},
    )
    assert apply_res.status_code == 201
    cleaning_data = apply_res.json()
    cleaning_id = cleaning_data["id"]
    assert cleaning_data["status"] == "completed"
    assert cleaning_data["output_row_count"] == 3

    # 10. View cleaning history
    cl_history_res = client.get(f"/api/datasets/{dataset_id}/cleanings")
    assert cl_history_res.status_code == 200
    assert cl_history_res.json()["total"] >= 1
    assert cl_history_res.json()["items"][0]["id"] == cleaning_id

    cl_record_res = client.get(f"/api/cleanings/{cleaning_id}")
    assert cl_record_res.status_code == 200
    assert cl_record_res.json()["id"] == cleaning_id

    # 11. Download the cleaned CSV
    dl_res = client.get(f"/api/cleanings/{cleaning_id}/download")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"].startswith("text/csv")
    assert "attachment" in dl_res.headers.get("content-disposition", "")
    content_lines = dl_res.text.strip().split("\n")
    assert len(content_lines) == 4  # Header + 3 unique rows

    # 14. Cross-user data isolation test:
    # Register User B in a separate client session
    client_b = TestClient(app)
    user_b_payload = {
        "username": "e2e_test_user_b",
        "email": "e2e_test_b@example.com",
        "password": "SecurePassword123!",
    }
    reg_b = client_b.post("/api/auth/register", json=user_b_payload)
    assert reg_b.status_code == 201
    csrf_b = client_b.cookies[settings.CSRF_COOKIE_NAME]

    # User B cannot see User A's dataset in their list
    b_list = client_b.get("/api/datasets").json()
    assert not any(d["id"] == dataset_id for d in b_list["items"])

    # User B cannot access User A's dataset details (403 Forbidden)
    b_get_ds = client_b.get(f"/api/datasets/{dataset_id}")
    assert b_get_ds.status_code == 403

    # User B cannot analyze User A's dataset (403 Forbidden)
    b_analyze = client_b.post(
        f"/api/datasets/{dataset_id}/analyze",
        headers={"X-CSRF-Token": csrf_b},
    )
    assert b_analyze.status_code == 403

    # User B cannot view User A's analysis record (403 Forbidden)
    b_view_ana = client_b.get(f"/api/analyses/{analysis_id}")
    assert b_view_ana.status_code == 403

    # User B cannot clean User A's dataset (403 Forbidden)
    b_clean = client_b.post(
        f"/api/datasets/{dataset_id}/clean",
        json={"config": cleaning_config},
        headers={"X-CSRF-Token": csrf_b},
    )
    assert b_clean.status_code == 403

    # User B cannot access User A's cleaning record (403 Forbidden)
    b_cl_rec = client_b.get(f"/api/cleanings/{cleaning_id}")
    assert b_cl_rec.status_code == 403

    # User B cannot download User A's cleaned file (403 Forbidden)
    b_dl = client_b.get(f"/api/cleanings/{cleaning_id}/download")
    assert b_dl.status_code == 403

    # Test CSRF Protection failure when cookie auth is used but X-CSRF-Token header is missing
    csrf_fail_res = client.post(
        f"/api/datasets/{dataset_id}/analyze",
        # intentionally omit X-CSRF-Token header
    )
    assert csrf_fail_res.status_code == 403
    assert "CSRF" in csrf_fail_res.json()["detail"]

    # 12. Log out User A
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200

    # 13. Verify protected pages / endpoints require authentication after logout
    unauth_me = client.get("/api/auth/me")
    assert unauth_me.status_code == 401

    unauth_ds = client.get("/api/datasets")
    assert unauth_ds.status_code == 401


def test_security_and_failure_modes(db: Session):
    """
    Validates security constraints and error handling:
    - Invalid login credentials rejected
    - Non-CSV files rejected during upload
    - Missing CSRF rejected on mutating routes
    - Missing cleaning record returns 404
    """
    client = TestClient(app)

    # 1. Invalid login attempt
    bad_login = client.post(
        "/api/auth/login",
        json={"username_or_email": "non_existent_user", "password": "WrongPassword123!"},
    )
    assert bad_login.status_code == 401
    assert "Invalid" in bad_login.json()["detail"]

    # 2. Register temporary user
    reg = client.post(
        "/api/auth/register",
        json={
            "username": "e2e_test_fail_user",
            "email": "e2e_fail@example.com",
            "password": "Password123!",
        },
    )
    assert reg.status_code == 201
    csrf = client.cookies[settings.CSRF_COOKIE_NAME]

    # 3. Reject non-CSV upload
    bad_upload = client.post(
        "/api/datasets/upload",
        files={"file": ("malicious.exe", io.BytesIO(b"binary content"), "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert bad_upload.status_code == 400
    assert "CSV" in bad_upload.json()["detail"]

    # 4. Request non-existent cleaning record
    missing_cl = client.get("/api/cleanings/999999")
    assert missing_cl.status_code == 404

    # 5. Download non-existent cleaning file
    missing_dl = client.get("/api/cleanings/999999/download")
    assert missing_dl.status_code == 404
