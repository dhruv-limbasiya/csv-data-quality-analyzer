import tempfile
import hashlib
from pathlib import Path
import pytest
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.dataset import Dataset
from app.models.analysis import Analysis
from app.services.quality_service import analyze_dataset_quality


@pytest.fixture(scope="module")
def db():
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup_analysis_test_data(db: Session):
    """Clean up test users, datasets, and analyses before and after tests."""
    def _clean():
        users = db.query(User).filter(User.username.like("qa_%")).all()
        for u in users:
            # Cascades to datasets and analyses
            db.delete(u)
        db.commit()

    _clean()
    yield
    _clean()


@pytest.fixture(scope="module")
def test_setup(db: Session):
    """Creates authenticated clients for User A and User B, with an uploaded sample dataset."""
    client_a = TestClient(app)
    client_b = TestClient(app)

    # 1. Register User A
    reg_a = client_a.post("/api/auth/register", json={
        "username": "qa_user_a",
        "email": "qa_user_a@example.com",
        "password": "StrongPassword123!"
    })
    assert reg_a.status_code == 201
    csrf_a = client_a.cookies.get(settings.CSRF_COOKIE_NAME)

    # 2. Register User B
    reg_b = client_b.post("/api/auth/register", json={
        "username": "qa_user_b",
        "email": "qa_user_b@example.com",
        "password": "StrongPassword123!"
    })
    assert reg_b.status_code == 201
    csrf_b = client_b.cookies.get(settings.CSRF_COOKIE_NAME)

    # 3. User A uploads a rich test dataset
    csv_content = (
        "id,name,email,age,join_date,annual_income,status\n"
        "1,Alice,alice@example.com,29,2022-01-15,65000,Active\n"
        "2,Bob,bob@example.com,42,2021-06-20,82000,Active\n"
        "3,Charlie,,35,2023-03-10,54000,Pending\n"
        "4,Diana,diana@example.com,150,2020-11-05,120000,Active\n"
        "5,Evan,not-an-email,28,2022-08-14,48000,Inactive\n"
        "6,Fiona,fiona@example.com,31,2023-05-22,61000,Active\n"
        "2,Bob,bob@example.com,42,2021-06-20,82000,Active\n"  # Duplicate row
        "8,George,george@example.com,-5,2021-12-01,73000,Pending\n"  # Negative age
        "9,Hannah,hannah@example.com,26,not-a-date,59000,Active\n"  # Invalid date
        "10,Ian,ian@example.com,45,2019-07-30,90000,Active\n"
        "11,Julia,julia@example.com,38,2022-04-18,,Active\n"  # Missing income
        "12,Kevin,kevin@example.com,64,2018-09-12,87000,Inactive\n"
    ).encode("utf-8")

    upload_res = client_a.post(
        "/api/datasets/upload",
        headers={"X-CSRF-Token": csrf_a},
        files={"file": ("qa_customers.csv", csv_content, "text/csv")}
    )
    assert upload_res.status_code == 201
    dataset_a_id = upload_res.json()["id"]

    return {
        "client_a": client_a,
        "csrf_a": csrf_a,
        "client_b": client_b,
        "csrf_b": csrf_b,
        "dataset_a_id": dataset_a_id,
        "csv_content": csv_content,
    }


# -------------------------------------------------------------------------
# 1. Quality Service Engine Core Unit Tests
# -------------------------------------------------------------------------

def test_clean_csv_analysis():
    """Verify that a pristine dataset receives a high quality score (> 95)."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("id,name,score\n1,Alice,90\n2,Bob,85\n3,Charlie,95\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        assert results["overall_score"] >= 95.0
        assert results["summary_stats"]["total_rows"] == 3
        assert results["summary_stats"]["total_columns"] == 3
        assert results["summary_stats"]["total_missing_cells"] == 0
        assert results["summary_stats"]["duplicate_rows"] == 0
        assert len(results["issues"]) == 0
    finally:
        f_path.unlink()


def test_missing_values_and_whitespace_detection():
    """Verify missing values and whitespace-only strings are accurately detected."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("col_a,col_b\n1,Alpha\n,   \n3,Charlie\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        summary = results["summary_stats"]
        assert summary["total_missing_cells"] >= 2
        # col_a has 1 missing, col_b has 1 whitespace
        col_b = [c for c in summary["columns_quality"] if c["name"] == "col_b"][0]
        assert col_b["missing_count"] >= 1
    finally:
        f_path.unlink()


def test_duplicate_rows_detection():
    """Verify duplicate row counting (subsequent occurrences)."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("a,b\n1,X\n2,Y\n1,X\n1,X\n")  # 4 rows, 2 duplicates
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        assert results["summary_stats"]["duplicate_rows"] == 2
        assert results["summary_stats"]["duplicate_rows_percentage"] == 50.0
    finally:
        f_path.unlink()


def test_numerical_and_categorical_statistics():
    """Verify statistical metrics for numeric and categorical columns."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("num,category\n10,Apple\n20,Apple\n30,Banana\n40,Apple\n50,Orange\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        cols = {c["name"]: c for c in results["summary_stats"]["columns_quality"]}

        # Numerical statistics
        num_stats = cols["num"]["statistics"]
        assert num_stats["min"] == 10
        assert num_stats["max"] == 50
        assert num_stats["mean"] == 30.0
        assert num_stats["median"] == 30.0

        # Categorical statistics
        cat_stats = cols["category"]["statistics"]
        assert cat_stats["distinct_count"] == 3
        top_val = cat_stats["top_frequent_values"][0]
        assert top_val["value"] == "Apple"
        assert top_val["count"] == 3
    finally:
        f_path.unlink()


def test_invalid_email_and_dates_detection():
    """Verify heuristic detection of bad email addresses and unparseable dates."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("user_email,signup_date\nvalid@test.com,2023-01-01\nbad-email,not-a-date\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        issues = results["issues"]
        categories = [i["category"] for i in issues]
        assert "invalid_format" in categories
        assert "invalid_date" in categories
    finally:
        f_path.unlink()


def test_constant_columns_detection():
    """Verify columns with a single distinct value are flagged."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("id,status\n1,Active\n2,Active\n3,Active\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        issues = results["issues"]
        assert any(i["category"] == "constant_column" and i["column"] == "status" for i in issues)
    finally:
        f_path.unlink()


def test_empty_dataset_edge_case():
    """Verify header-only or zero-row CSV returns safe 0.0 score without crashing."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("col1,col2,col3\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        assert results["overall_score"] == 0.0
        assert results["summary_stats"]["total_rows"] == 0
        assert any(i["category"] == "empty_dataset" for i in results["issues"])
    finally:
        f_path.unlink()


def test_empty_column_handling():
    """Verify columns with 100% missing values are handled gracefully."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("id,empty_col,name\n1,,Alice\n2,,Bob\n3,,Charlie\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        cols = {c["name"]: c for c in results["summary_stats"]["columns_quality"]}
        assert cols["empty_col"]["missing_count"] == 3
        assert cols["empty_col"]["missing_percentage"] == 100.0
        assert cols["empty_col"]["non_missing_count"] == 0
        assert cols["empty_col"]["statistics"]["distinct_count"] == 0
        assert cols["empty_col"]["statistics"]["top_frequent_values"] == []
    finally:
        f_path.unlink()


def test_mixed_and_ambiguous_types():
    """Verify detection of mixed numeric and text values in string columns."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("code,mixed_val\nA1,100\nB2,200\nC3,not_a_number\nD4,400\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        cols = {c["name"]: c for c in results["summary_stats"]["columns_quality"]}
        assert cols["mixed_val"]["semantic_type"] == "mixed_numeric"
        assert cols["mixed_val"]["type_mismatch_count"] == 1
        assert any(i["category"] == "type_mismatch" for i in results["issues"])
    finally:
        f_path.unlink()


def test_boolean_semantic_detection():
    """Verify boolean semantic classification from yes/no and true/false values."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("id,is_active\n1,true\n2,false\n3,true\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        cols = {c["name"]: c for c in results["summary_stats"]["columns_quality"]}
        assert cols["is_active"]["semantic_type"] == "boolean"
    finally:
        f_path.unlink()


def test_high_uniqueness_detection():
    """Verify high uniqueness heuristic triggers for unique key columns (> 20 rows)."""
    rows = ["uuid_key,val"] + [f"ID_{i},{i*10}" for i in range(25)]
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("\n".join(rows) + "\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        assert any(i["category"] == "high_uniqueness" and i["column"] == "uuid_key" for i in results["issues"])
    finally:
        f_path.unlink()


# -------------------------------------------------------------------------
# 2. API Endpoints & Ownership Tests
# -------------------------------------------------------------------------

def test_run_analysis_endpoint_success(test_setup):
    """Verify POST /api/datasets/{dataset_id}/analyze runs, persists, and returns analysis."""
    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]
    dataset_id = test_setup["dataset_a_id"]

    res = client_a.post(
        f"/api/datasets/{dataset_id}/analyze",
        headers={"X-CSRF-Token": csrf_a}
    )
    assert res.status_code == 201
    data = res.json()

    assert data["dataset_id"] == dataset_id
    assert 0.0 <= data["overall_score"] <= 100.0
    assert len(data["column_scores"]) == 7
    assert len(data["issues"]) > 0
    assert len(data["recommendations"]) > 0

    analysis_id = data["id"]

    # Verify retrieval by analysis ID
    get_res = client_a.get(f"/api/analyses/{analysis_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == analysis_id

    # Verify retrieval in dataset analysis history
    history_res = client_a.get(f"/api/datasets/{dataset_id}/analyses")
    assert history_res.status_code == 200
    assert history_res.json()["total"] >= 1
    assert any(item["id"] == analysis_id for item in history_res.json()["items"])


def test_unauthenticated_analysis_rejected(test_setup):
    """Verify unauthenticated calls to analyze or get analyses return 401."""
    dataset_id = test_setup["dataset_a_id"]
    unauth_client = TestClient(app)

    r1 = unauth_client.post(f"/api/datasets/{dataset_id}/analyze")
    assert r1.status_code == 401

    r2 = unauth_client.get(f"/api/datasets/{dataset_id}/analyses")
    assert r2.status_code == 401

    r3 = unauth_client.get("/api/analyses/1")
    assert r3.status_code == 401


def test_csrf_required_for_analyze(test_setup):
    """Verify POST /api/datasets/{id}/analyze without CSRF token returns 403."""
    client_a = test_setup["client_a"]
    dataset_id = test_setup["dataset_a_id"]

    # Call without X-CSRF-Token header
    res = client_a.post(f"/api/datasets/{dataset_id}/analyze")
    assert res.status_code == 403
    assert "CSRF verification failed" in res.json()["detail"]


def test_cross_user_analysis_forbidden(test_setup):
    """Verify User B cannot analyze or view User A's dataset analyses."""
    client_b = test_setup["client_b"]
    csrf_b = test_setup["csrf_b"]
    dataset_a_id = test_setup["dataset_a_id"]

    # User B attempts to analyze User A's dataset -> 403 Forbidden
    res = client_b.post(
        f"/api/datasets/{dataset_a_id}/analyze",
        headers={"X-CSRF-Token": csrf_b}
    )
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

    # User B attempts to view User A's analysis history -> 403 Forbidden
    history_res = client_b.get(f"/api/datasets/{dataset_a_id}/analyses")
    assert history_res.status_code == 403


def test_analyze_nonexistent_dataset(test_setup):
    """Verify analyzing nonexistent dataset returns 404."""
    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]

    res = client_a.post(
        "/api/datasets/999999/analyze",
        headers={"X-CSRF-Token": csrf_a}
    )
    assert res.status_code == 404


def test_original_csv_preserved_unchanged(test_setup, db: Session):
    """Verify original CSV file on disk is strictly unchanged after analysis."""
    dataset_id = test_setup["dataset_a_id"]
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    assert dataset is not None

    file_path = Path(dataset.file_path)
    sha256_before = hashlib.sha256(file_path.read_bytes()).hexdigest()

    # Run analysis
    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]
    res = client_a.post(
        f"/api/datasets/{dataset_id}/analyze",
        headers={"X-CSRF-Token": csrf_a}
    )
    assert res.status_code == 201

    sha256_after = hashlib.sha256(file_path.read_bytes()).hexdigest()
    assert sha256_before == sha256_after  # File is strictly immutable


def test_analyze_missing_source_file(test_setup, db: Session):
    """Verify 404 returned when dataset record exists in DB but source CSV was deleted from disk."""
    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]

    # Query User A to get valid user_id
    user_a = db.query(User).filter(User.username == "qa_user_a").first()
    assert user_a is not None

    # Create dummy dataset record pointing to missing file
    ghost_dataset = Dataset(
        user_id=user_a.id,
        original_filename="ghost.csv",
        stored_filename="ghost_stored_99999.csv",
        file_path="d:/CSV Data Quality Analyzer/CSV Data Quality Analyzer/backend/uploads/ghost_stored_99999.csv",
        file_size_bytes=100,
        row_count=10,
        column_count=2,
    )
    db.add(ghost_dataset)
    db.commit()
    db.refresh(ghost_dataset)

    try:
        res = client_a.post(
            f"/api/datasets/{ghost_dataset.id}/analyze",
            headers={"X-CSRF-Token": csrf_a}
        )
        assert res.status_code == 404
        assert "not found on disk" in res.json()["detail"]
    finally:
        db.delete(ghost_dataset)
        db.commit()


def test_json_serialization_safety_with_nan_inf():
    """Verify make_json_serializable handles NaN, Infinity, and numpy datatypes safely."""
    from app.services.csv_service import make_json_serializable
    import json

    assert make_json_serializable(float("nan")) is None
    assert make_json_serializable(float("inf")) is None
    assert make_json_serializable(float("-inf")) is None
    assert make_json_serializable(np.int64(42)) == 42
    assert make_json_serializable(np.float64(3.14)) == 3.14
    assert make_json_serializable(np.bool_(True)) is True

    # Test serialization of complete analysis payload
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("a,b\n1,NaN\n2,Infinity\n3,4\n")
        f_path = Path(f.name)

    try:
        results = analyze_dataset_quality(f_path, f_path.stat().st_size)
        dumped = json.dumps(results)
        assert dumped is not None
        assert "NaN" not in dumped or '"NaN"' in dumped  # No bare NaN tokens in JSON
    finally:
        f_path.unlink()


def test_analyses_pagination(test_setup):
    """Verify skip and limit query parameters on GET /api/datasets/{id}/analyses."""
    client_a = test_setup["client_a"]
    dataset_id = test_setup["dataset_a_id"]

    # Fetch page with limit=1
    res = client_a.get(f"/api/datasets/{dataset_id}/analyses?skip=0&limit=1")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert len(data["items"]) <= 1
