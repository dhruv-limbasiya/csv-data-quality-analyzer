import io
import hashlib
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

from app.main import app
from app.config import settings
from app.database import SessionLocal, get_db
from app.models.user import User
from app.models.dataset import Dataset
from app.models.cleaning import CleaningRecord
from app.models.session import UserSession
from app.services.security import (
    hash_password,
    create_session_token,
    verify_session_token,
    verify_session_token_claims,
    create_csrf_token,
    verify_csrf_token,
)
from app.services.cleaning_service import (
    sanitize_csv_cell_for_export,
    sanitize_csv_formulas_for_export,
)
from app.services.csv_service import save_upload_stream, parse_and_extract_metadata


@pytest.fixture(scope="module")
def db():
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module", autouse=True)
def clean_phase8_users(db: Session):
    def _cleanup():
        test_pattern = "p8_test_%"
        users = db.query(User).filter(User.username.like(test_pattern)).all()
        for u in users:
            db.query(CleaningRecord).filter(CleaningRecord.user_id == u.id).delete()
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


@pytest.fixture
def test_user_session(db: Session):
    """Creates a temporary authenticated user and client with session and CSRF cookies."""
    username = "p8_test_auth_user"
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(
            username=username,
            email="p8_test_auth@example.com",
            hashed_password="hashed_pw_test",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    client = TestClient(app)
    session_id = uuid.uuid4().hex
    session_token = create_session_token(user.id, session_id)
    db.add(UserSession(
        user_id=user.id,
        session_id=session_id,
        token_hash=hashlib.sha256(session_token.encode("utf-8")).hexdigest(),
        is_revoked=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    ))
    db.commit()
    csrf_token = create_csrf_token(user.id)
    client.cookies.set(settings.SESSION_COOKIE_NAME, session_token)
    client.cookies.set(settings.CSRF_COOKIE_NAME, csrf_token)
    return client, user, session_token, csrf_token


# =========================================================================
# 1. Authentication, Tokens & CSRF Security Tests
# =========================================================================

def test_tampered_and_malformed_session_token():
    client = TestClient(app)
    # 1. Invalid signature
    client.cookies.set(settings.SESSION_COOKIE_NAME, "tampered.token.signature")
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert "expired or is invalid" in res.json()["detail"]

    # 2. Completely malformed token
    client.cookies.set(settings.SESSION_COOKIE_NAME, "not_a_valid_token_at_all!@#$")
    res2 = client.get("/api/auth/me")
    assert res2.status_code == 401


def test_csrf_header_mismatch_and_tampering(test_user_session):
    client, user, _, real_csrf = test_user_session

    # 1. Missing header on state-changing request
    res = client.post("/api/datasets/upload", files={"file": ("test.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")})
    assert res.status_code == 403
    assert "missing X-CSRF-Token" in res.json()["detail"]

    # 2. Header and cookie mismatch
    res2 = client.post(
        "/api/datasets/upload",
        files={"file": ("test.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
        headers={"X-CSRF-Token": "different_csrf_token_value"},
    )
    assert res2.status_code == 403
    assert "token mismatch" in res2.json()["detail"]

    # 3. Tampered CSRF token
    client.cookies.set(settings.CSRF_COOKIE_NAME, "tampered.csrf.token")
    res3 = client.post(
        "/api/datasets/upload",
        files={"file": ("test.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
        headers={"X-CSRF-Token": "tampered.csrf.token"},
    )
    assert res3.status_code == 403


@pytest.fixture
def registered_phase8_user(db: Session):
    username = "p8_test_login_user"
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(
            username=username,
            email="p8_test_login@example.com",
            hashed_password=hash_password("Password123!"),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def test_login_creates_server_side_session(registered_phase8_user, db: Session):
    client = TestClient(app)
    response = client.post("/api/auth/login", json={
        "username_or_email": registered_phase8_user.username,
        "password": "Password123!",
    })
    assert response.status_code == 200
    token = response.cookies.get(settings.SESSION_COOKIE_NAME)
    claims = verify_session_token_claims(token)
    assert claims is not None

    session = db.query(UserSession).filter(
        UserSession.session_id == claims["session_id"]
    ).one()
    assert session.user_id == registered_phase8_user.id
    assert session.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert session.is_revoked is False
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert expires_at > datetime.now(timezone.utc)


def test_session_expiry_fails_closed(test_user_session, db: Session):
    client, _, token, _ = test_user_session
    claims = verify_session_token_claims(token)
    session = db.query(UserSession).filter(
        UserSession.session_id == claims["session_id"]
    ).one()
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_session_revocation_and_isolation(db: Session):
    client_a = TestClient(app)
    client_b = TestClient(app)
    username = "p8_test_revoke_user"
    response_a = client_a.post("/api/auth/register", json={
        "username": username,
        "email": "p8_revoke@example.com",
        "password": "Password123!",
    })
    assert response_a.status_code == 201
    response_b = client_b.post("/api/auth/register", json={
        "username": "p8_test_isolated_user",
        "email": "p8_isolated@example.com",
        "password": "Password123!",
    })
    assert response_b.status_code == 201
    captured_session_cookie = client_a.cookies.get(settings.SESSION_COOKIE_NAME)
    assert client_b.get("/api/auth/me").status_code == 200

    logout_res = client_a.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert settings.SESSION_COOKIE_NAME not in client_a.cookies
    assert settings.CSRF_COOKIE_NAME not in client_a.cookies
    assert client_a.get("/api/auth/me").status_code == 401

    replay_client = TestClient(app)
    replay_client.cookies.set(settings.SESSION_COOKIE_NAME, captured_session_cookie)
    assert replay_client.get("/api/auth/me").status_code == 401
    assert verify_session_token(captured_session_cookie) is not None
    assert client_b.get("/api/auth/me").status_code == 200


def test_database_session_validation_failure_fails_closed(test_user_session):
    client, _, _, _ = test_user_session

    class FailingDatabase:
        def query(self, *_args, **_kwargs):
            raise SQLAlchemyError("simulated database validation failure")

    def failing_db():
        yield FailingDatabase()

    app.dependency_overrides[get_db] = failing_db
    try:
        response = client.get("/api/auth/me")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 503


# =========================================================================
# 2. Dataset & CSV Upload Tests
# =========================================================================

def test_upload_empty_csv(test_user_session):
    client, _, _, csrf = test_user_session
    # Completely empty (0 bytes)
    res = client.post(
        "/api/datasets/upload",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_upload_utf8_bom_csv(test_user_session):
    client, _, _, csrf = test_user_session
    # CSV encoded with UTF-8 BOM (\xef\xbb\xbf)
    bom_content = b"\xef\xbb\xbfid,name,value\n1,Alpha,100\n2,Beta,200\n"
    res = client.post(
        "/api/datasets/upload",
        files={"file": ("bom_data.csv", io.BytesIO(bom_content), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 201
    data = res.json()
    # First column name should NOT have raw BOM characters in it
    assert data["columns_metadata"][0]["name"] == "id"
    assert data["row_count"] == 2


def test_upload_path_traversal_filename(test_user_session):
    client, _, _, csrf = test_user_session
    # Attempt path traversal in filename
    traversal_name = "../../../../etc/passwd.csv"
    res = client.post(
        "/api/datasets/upload",
        files={"file": (traversal_name, io.BytesIO(b"id,col\n1,val\n"), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 201
    data = res.json()
    # original_filename must be sanitized to the base name without path traversal
    assert data["original_filename"] == "passwd.csv"
    assert ".." not in data["original_filename"]
    assert "/" not in data["original_filename"]
    assert "\\" not in data["original_filename"]


def test_upload_unicode_and_complex_quoting(test_user_session):
    client, _, _, csrf = test_user_session
    # Complex multiline cells, quotes, unicode, emojis
    complex_csv = (
        'id,description,tags\n'
        '1,"Line 1\nLine 2 with, commas and ""escaped quotes""",✨Unicode🚀\n'
        '2,"Simple text",standard\n'
    )
    res = client.post(
        "/api/datasets/upload",
        files={"file": ("complex.csv", io.BytesIO(complex_csv.encode("utf-8")), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["row_count"] == 2
    assert data["column_count"] == 3


def test_upload_duplicate_and_blank_column_names(test_user_session):
    client, _, _, csrf = test_user_session
    # Duplicate headers: id, name, name, (empty)
    csv_content = b"id,name,name,\n1,first,second,extra\n2,foo,bar,baz\n"
    res = client.post(
        "/api/datasets/upload",
        files={"file": ("dup_headers.csv", io.BytesIO(csv_content), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    assert res.status_code == 201
    data = res.json()
    col_names = [c["name"] for c in data["columns_metadata"]]
    # Duplicate headers must be uniquely disambiguated
    assert len(col_names) == len(set(col_names)), "All column names must be unique"


# =========================================================================
# 3. Data Quality Analysis Immutability & Boundary Tests
# =========================================================================

def test_analysis_preserves_original_file_hash(test_user_session, db: Session):
    """Verifies that running quality analysis NEVER alters the original file on disk (SHA-256 match)."""
    client, _, _, csrf = test_user_session
    csv_content = b"id,name,score\n1,Alice,85\n2,Bob,90\n3,Charlie,\n"
    upload_res = client.post(
        "/api/datasets/upload",
        files={"file": ("hash_test.csv", io.BytesIO(csv_content), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    file_path = Path(ds.file_path)
    hash_before = hashlib.sha256(file_path.read_bytes()).hexdigest()

    # Run analysis
    ana_res = client.post(f"/api/datasets/{dataset_id}/analyze", headers={"X-CSRF-Token": csrf})
    assert ana_res.status_code == 201

    hash_after = hashlib.sha256(file_path.read_bytes()).hexdigest()
    assert hash_before == hash_after, "Original CSV file was modified during analysis!"


def test_analysis_single_row_dataset(test_user_session):
    client, _, _, csrf = test_user_session
    csv_content = b"id,city,temp\n1,Metropolis,22.5\n"
    upload_res = client.post(
        "/api/datasets/upload",
        files={"file": ("single_row.csv", io.BytesIO(csv_content), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    dataset_id = upload_res.json()["id"]

    ana_res = client.post(f"/api/datasets/{dataset_id}/analyze", headers={"X-CSRF-Token": csrf})
    assert ana_res.status_code == 201
    data = ana_res.json()
    assert data["summary_stats"]["total_rows"] == 1
    assert 0 <= data["overall_score"] <= 100


# =========================================================================
# 4. Cleaning Immutability & Destructive Protection Tests
# =========================================================================

def test_cleaning_preserves_original_file_hash(test_user_session, db: Session):
    """Verifies that running cleaning creates a separate output and leaves the original file unmodified."""
    client, _, _, csrf = test_user_session
    csv_content = b"id,name,status\n1,Alice  ,ACTIVE\n2,  Bob,INACTIVE\n"
    upload_res = client.post(
        "/api/datasets/upload",
        files={"file": ("immut_test.csv", io.BytesIO(csv_content), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    dataset_id = upload_res.json()["id"]
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    orig_path = Path(ds.file_path)
    hash_before = hashlib.sha256(orig_path.read_bytes()).hexdigest()

    # Apply cleaning
    clean_config = {
        "whitespace_cleaning": {"enabled": True, "trim_whitespace": True},
        "text_normalization": {"enabled": True, "case": "lowercase"},
    }
    clean_res = client.post(
        f"/api/datasets/{dataset_id}/clean",
        json={"config": clean_config},
        headers={"X-CSRF-Token": csrf},
    )
    assert clean_res.status_code == 201

    hash_after = hashlib.sha256(orig_path.read_bytes()).hexdigest()
    assert hash_before == hash_after, "Original CSV file was modified during cleaning!"


def test_cleaning_blocks_zero_row_outcome(test_user_session):
    client, _, _, csrf = test_user_session
    # Dataset where every row has missing values
    csv_content = b"id,missing_col\n1,\n2,\n3,\n"
    upload_res = client.post(
        "/api/datasets/upload",
        files={"file": ("all_missing.csv", io.BytesIO(csv_content), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    dataset_id = upload_res.json()["id"]

    # Attempting to drop_rows drops 100% of rows
    clean_config = {
        "missing_values": {"enabled": True, "strategy": "drop_rows"},
    }
    clean_res = client.post(
        f"/api/datasets/{dataset_id}/clean",
        json={"config": clean_config},
        headers={"X-CSRF-Token": csrf},
    )
    assert clean_res.status_code == 400
    assert "Safety check failed" in clean_res.json()["detail"]


def test_cleaning_blocks_zero_column_outcome(test_user_session):
    client, _, _, csrf = test_user_session
    csv_content = b"single_column\nval1\nval2\n"
    upload_res = client.post(
        "/api/datasets/upload",
        files={"file": ("single_col.csv", io.BytesIO(csv_content), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    dataset_id = upload_res.json()["id"]

    # Attempting to drop the only column
    clean_config = {
        "missing_values": {"enabled": True, "strategy": "drop_columns", "columns": ["single_column"]},
    }
    clean_res = client.post(
        f"/api/datasets/{dataset_id}/clean",
        json={"config": clean_config},
        headers={"X-CSRF-Token": csrf},
    )
    assert clean_res.status_code == 400
    assert "Safety check failed" in clean_res.json()["detail"]


# =========================================================================
# 5. CSV Formula Injection Defense Tests
# =========================================================================

def test_csv_formula_injection_sanitization_logic():
    """Unit test for formula sanitization function."""
    # Malicious spreadsheet triggers
    assert sanitize_csv_cell_for_export("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    assert sanitize_csv_cell_for_export("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_cell_for_export("+1+2") == "'+1+2"  # formula arithmetic string
    assert sanitize_csv_cell_for_export("+EXEC(calc)") == "'+EXEC(calc)"
    assert sanitize_csv_cell_for_export("-cmd") == "'-cmd"
    assert sanitize_csv_cell_for_export("\t=1+1") == "'\t=1+1"
    assert sanitize_csv_cell_for_export("\r@SUM(A1:A10)") == "'\r@SUM(A1:A10)"

    # Legitimate numbers must NOT be escaped
    assert sanitize_csv_cell_for_export("-42") == "-42"
    assert sanitize_csv_cell_for_export("+3.14") == "+3.14"
    assert sanitize_csv_cell_for_export(-100) == -100
    assert sanitize_csv_cell_for_export(42.5) == 42.5
    assert sanitize_csv_cell_for_export("Regular Text") == "Regular Text"


def test_csv_formula_injection_download_endpoint(test_user_session, db: Session):
    """Downloads are formula-safe by default without modifying stored CSV files."""
    client, _, _, csrf = test_user_session
    malicious_csv = (
        "id,payload,balance\n"
        "1,=cmd|' /C calc'!A0,-50.25\n"
        "2,@SUM(A1:A10),+100\n"
        "3,-payload_text,NormalText\n"
        '4,"\t=1+1",250\n'
        '5,"\r@SUM(A1:A10)",-42.5\n'
        "6,+3.14,3\n"
    )
    upload_res = client.post(
        "/api/datasets/upload",
        files={"file": ("formula_test.csv", io.BytesIO(malicious_csv.encode("utf-8")), "text/csv")},
        headers={"X-CSRF-Token": csrf},
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["id"]

    # Apply minimal cleaning to create cleaning record
    clean_config = {"duplicate_removal": {"enabled": True, "keep": "first"}}
    clean_res = client.post(
        f"/api/datasets/{dataset_id}/clean",
        json={"config": clean_config},
        headers={"X-CSRF-Token": csrf},
    )
    assert clean_res.status_code == 201
    cleaning_id = clean_res.json()["id"]

    record = db.query(CleaningRecord).filter(CleaningRecord.id == cleaning_id).one()
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).one()
    original_hash = hashlib.sha256(Path(dataset.file_path).read_bytes()).hexdigest()
    cleaned_hash = hashlib.sha256(Path(record.output_file_path).read_bytes()).hexdigest()

    safe_download = client.get(f"/api/cleanings/{cleaning_id}/download")
    assert safe_download.status_code == 200
    safe_text = safe_download.text
    assert "'=cmd" in safe_text, "Formula trigger was not escaped with single quote"
    assert "'@SUM" in safe_text, "@ trigger was not escaped"
    assert "'-payload_text" in safe_text, "Negative text formula trigger was not escaped"
    assert "-50.25" in safe_text, "Legitimate negative number was corrupted"
    assert "+3.14" in safe_text or "3.14" in safe_text
    assert "'\t=1+1" in safe_text
    assert "'\r@SUM" in safe_text

    assert hashlib.sha256(Path(dataset.file_path).read_bytes()).hexdigest() == original_hash
    assert hashlib.sha256(Path(record.output_file_path).read_bytes()).hexdigest() == cleaned_hash
