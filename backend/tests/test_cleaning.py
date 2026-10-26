import tempfile
import hashlib
from pathlib import Path
import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.config import settings
from app.database import SessionLocal
from app.models.user import User
from app.models.dataset import Dataset
from app.models.cleaning import CleaningRecord
from app.services.cleaning_service import apply_cleaning_pipeline, CleaningExecutionError
from app.schemas.cleaning import (
    CleaningConfig,
    WhitespaceCleaningConfig,
    TextNormalizationConfig,
    MissingValuesConfig,
    TypeConversionItem,
    DuplicateRemovalConfig,
    OutlierHandlingConfig,
)


@pytest.fixture(scope="module")
def db():
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def test_setup(db: Session):
    """Create test users and uploaded test datasets."""
    from app.services.security import hash_password

    # Clean existing test users if leftover
    db.query(User).filter(User.username.in_(["clean_user_a", "clean_user_b"])).delete(synchronize_session=False)
    db.commit()

    user_a = User(
        email="clean_user_a@example.com",
        username="clean_user_a",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    user_b = User(
        email="clean_user_b@example.com",
        username="clean_user_b",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(user_a)
    db.add(user_b)
    db.commit()
    db.refresh(user_a)
    db.refresh(user_b)

    client_a = TestClient(app)
    res_login_a = client_a.post("/api/auth/login", json={"username_or_email": "clean_user_a", "password": "Password123!"})
    assert res_login_a.status_code == 200
    csrf_a = res_login_a.cookies.get(settings.CSRF_COOKIE_NAME)
    assert csrf_a is not None

    client_b = TestClient(app)
    res_login_b = client_b.post("/api/auth/login", json={"username_or_email": "clean_user_b", "password": "Password123!"})
    assert res_login_b.status_code == 200
    csrf_b = res_login_b.cookies.get(settings.CSRF_COOKIE_NAME)
    assert csrf_b is not None

    # Upload test dataset for user_a
    csv_raw = (
        "id,name,email,age,join_date,score\n"
        "1, Alice ,alice@example.com,25,2021-01-15,85.5\n"
        "2,Bob   ,bob@example.com,,2020-05-10,90.0\n"
        "3,  Charlie  ,charlie@example.com,30,,78.0\n"
        "4,Dave,dave@example.com,40,2019-11-20,95.0\n"
        "1, Alice ,alice@example.com,25,2021-01-15,85.5\n"  # Exact duplicate of row 1
    ).encode("utf-8")

    upload_res = client_a.post(
        "/api/datasets/upload",
        headers={"X-CSRF-Token": csrf_a},
        files={"file": ("raw_data.csv", csv_raw, "text/csv")},
    )
    assert upload_res.status_code == 201
    dataset_a_id = upload_res.json()["id"]

    yield {
        "user_a": user_a,
        "user_b": user_b,
        "client_a": client_a,
        "csrf_a": csrf_a,
        "client_b": client_b,
        "csrf_b": csrf_b,
        "dataset_a_id": dataset_a_id,
        "csv_raw": csv_raw,
    }

    # Teardown
    db.query(CleaningRecord).filter(CleaningRecord.user_id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
    db.query(Dataset).filter(Dataset.user_id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
    db.commit()


# -------------------------------------------------------------------------
# Unit Tests for Cleaning Transformations
# -------------------------------------------------------------------------

def test_keep_missing_values_unchanged():
    df = pd.DataFrame({"a": [1, np.nan, 3], "b": ["x", "  ", "z"]})
    config = CleaningConfig(missing_values=MissingValuesConfig(enabled=True, strategy="keep"))
    cleaned_df, summary = apply_cleaning_pipeline(df, config)
    assert len(cleaned_df) == 3
    assert cleaned_df["a"].isna().sum() == 1
    assert "keep" in summary["skipped_operations"][0]


def test_drop_rows_with_missing_values():
    df = pd.DataFrame({"a": [1, np.nan, 3, 4], "b": ["x", "y", "  ", "w"]})
    config = CleaningConfig(missing_values=MissingValuesConfig(enabled=True, strategy="drop_rows"))
    cleaned_df, summary = apply_cleaning_pipeline(df, config)
    assert len(cleaned_df) == 2
    assert list(cleaned_df["a"]) == [1.0, 4.0]
    assert summary["rows"]["difference"] == -2


def test_drop_selected_columns_with_missing_values():
    df = pd.DataFrame({"keep_col": [1, 2, 3], "drop_col": [1, np.nan, 3]})
    config = CleaningConfig(missing_values=MissingValuesConfig(enabled=True, strategy="drop_columns", columns=["drop_col"]))
    cleaned_df, summary = apply_cleaning_pipeline(df, config)
    assert "drop_col" not in cleaned_df.columns
    assert "keep_col" in cleaned_df.columns
    assert summary["columns"]["after"] == 1


def test_fill_numeric_using_mean_and_median():
    df = pd.DataFrame({"num_mean": [10, 20, np.nan, 30], "num_median": [10, 20, np.nan, 100]})
    config = CleaningConfig(
        missing_values=MissingValuesConfig(
            enabled=True,
            strategy="fill_mean",
            columns=["num_mean"]
        )
    )
    cleaned_df, _ = apply_cleaning_pipeline(df, config)
    assert cleaned_df["num_mean"].iloc[2] == 20.0  # mean of [10, 20, 30]

    config_median = CleaningConfig(
        missing_values=MissingValuesConfig(
            enabled=True,
            strategy="fill_median",
            columns=["num_median"]
        )
    )
    cleaned_df_med, _ = apply_cleaning_pipeline(df, config_median)
    assert cleaned_df_med["num_median"].iloc[2] == 20.0  # median of [10, 20, 100]


def test_fill_categorical_using_mode():
    df = pd.DataFrame({"category": ["apple", "banana", "apple", np.nan, "   "]})
    config = CleaningConfig(missing_values=MissingValuesConfig(enabled=True, strategy="fill_mode", columns=["category"]))
    cleaned_df, _ = apply_cleaning_pipeline(df, config)
    assert cleaned_df["category"].iloc[3] == "apple"
    assert cleaned_df["category"].iloc[4] == "apple"


def test_fill_constant_value():
    df = pd.DataFrame({"code": ["A", np.nan, "  ", "B"]})
    config = CleaningConfig(
        missing_values=MissingValuesConfig(
            enabled=True,
            strategy="fill_constant",
            columns=["code"],
            fill_value="UNKNOWN"
        )
    )
    cleaned_df, _ = apply_cleaning_pipeline(df, config)
    assert list(cleaned_df["code"]) == ["A", "UNKNOWN", "UNKNOWN", "B"]


def test_handle_completely_empty_column():
    df = pd.DataFrame({"all_missing": [np.nan, None, "  "], "id": [1, 2, 3]})
    config = CleaningConfig(missing_values=MissingValuesConfig(enabled=True, strategy="fill_mean", columns=["all_missing"]))
    cleaned_df, summary = apply_cleaning_pipeline(df, config)
    assert len(summary["warnings"]) > 0
    assert "no valid numerical values" in summary["warnings"][0]


def test_remove_duplicate_rows_first_and_last():
    df = pd.DataFrame({
        "id": [1, 2, 1],
        "val": ["first", "mid", "last"]
    })
    # Keep first
    cfg_first = CleaningConfig(duplicate_removal=DuplicateRemovalConfig(enabled=True, subset_columns=["id"], keep="first"))
    df_first, sum_first = apply_cleaning_pipeline(df, cfg_first)
    assert len(df_first) == 2
    assert df_first.iloc[0]["val"] == "first"

    # Keep last
    cfg_last = CleaningConfig(duplicate_removal=DuplicateRemovalConfig(enabled=True, subset_columns=["id"], keep="last"))
    df_last, sum_last = apply_cleaning_pipeline(df, cfg_last)
    assert len(df_last) == 2
    assert df_last.iloc[1]["val"] == "last"


def test_trim_and_collapse_whitespace():
    df = pd.DataFrame({"text": ["  hello   world  ", "foo     bar", "baz"]})
    config = CleaningConfig(
        whitespace_cleaning=WhitespaceCleaningConfig(
            enabled=True,
            trim_whitespace=True,
            collapse_internal_whitespace=True
        )
    )
    cleaned_df, summary = apply_cleaning_pipeline(df, config)
    assert cleaned_df["text"].iloc[0] == "hello world"
    assert cleaned_df["text"].iloc[1] == "foo bar"
    assert summary["operations_applied"][0]["changes_count"] == 2


def test_lowercase_and_uppercase_normalization():
    df = pd.DataFrame({"names": ["Alice", "BOB", "Charlie"]})
    # Lowercase
    cfg_lower = CleaningConfig(text_normalization=TextNormalizationConfig(enabled=True, case="lowercase", columns=["names"]))
    df_lower, _ = apply_cleaning_pipeline(df, cfg_lower)
    assert list(df_lower["names"]) == ["alice", "bob", "charlie"]

    # Uppercase
    cfg_upper = CleaningConfig(text_normalization=TextNormalizationConfig(enabled=True, case="uppercase", columns=["names"]))
    df_upper, _ = apply_cleaning_pipeline(df, cfg_upper)
    assert list(df_upper["names"]) == ["ALICE", "BOB", "CHARLIE"]


def test_standardize_null_markers():
    df = pd.DataFrame({"status": ["Active", "N/A", "NULL", "Pending", "-"]})
    config = CleaningConfig(
        text_normalization=TextNormalizationConfig(
            enabled=True,
            standardize_null_markers=True,
            columns=["status"]
        )
    )
    cleaned_df, _ = apply_cleaning_pipeline(df, config)
    assert cleaned_df["status"].isna().sum() == 3
    assert cleaned_df["status"].iloc[0] == "Active"


def test_type_conversion_boolean():
    df = pd.DataFrame({"is_active": ["yes", "no", "true", "0", "1"]})
    config = CleaningConfig(
        type_conversions=[
            TypeConversionItem(column="is_active", target_type="boolean", on_error="reject")
        ]
    )
    cleaned_df, _ = apply_cleaning_pipeline(df, config)
    assert list(cleaned_df["is_active"]) == [True, False, True, False, True]


def test_type_conversion_reject_vs_coerce():
    df = pd.DataFrame({"num": ["10", "20", "invalid_num", "40"]})
    # Reject
    cfg_reject = CleaningConfig(
        type_conversions=[TypeConversionItem(column="num", target_type="integer", on_error="reject")]
    )
    with pytest.raises(CleaningExecutionError):
        apply_cleaning_pipeline(df, cfg_reject)

    # Coerce
    cfg_coerce = CleaningConfig(
        type_conversions=[TypeConversionItem(column="num", target_type="integer", on_error="coerce")]
    )
    cleaned_df, summary = apply_cleaning_pipeline(df, cfg_coerce)
    assert pd.isna(cleaned_df["num"].iloc[2])
    assert summary["operations_applied"][0]["details"]["invalid_values_coerced"] == 1


def test_avoid_silent_decimal_truncation():
    df = pd.DataFrame({"fractional": ["10.5", "20.0"]})
    config = CleaningConfig(
        type_conversions=[TypeConversionItem(column="fractional", target_type="integer", on_error="reject")]
    )
    with pytest.raises(CleaningExecutionError) as exc_info:
        apply_cleaning_pipeline(df, config)
    assert "silent decimal truncation" in str(exc_info.value)


def test_outlier_handling_iqr_clipping():
    df = pd.DataFrame({"salary": [50000, 52000, 48000, 51000, 53000, 1000000]})  # 1,000,000 is extreme outlier
    config = CleaningConfig(
        outlier_handling=OutlierHandlingConfig(
            enabled=True,
            columns=["salary"],
            method="iqr",
            iqr_multiplier=1.5,
            treatment="clip"
        )
    )
    cleaned_df, summary = apply_cleaning_pipeline(df, config)
    assert cleaned_df["salary"].max() < 1000000
    assert summary["operations_applied"][0]["changes_count"] == 1


# -------------------------------------------------------------------------
# API Endpoints & Security Integration Tests
# -------------------------------------------------------------------------

def test_preview_cleaning_endpoint_success(test_setup):
    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]
    dataset_id = test_setup["dataset_a_id"]

    req_payload = {
        "config": {
            "whitespace_cleaning": {"enabled": True, "trim_whitespace": True},
            "duplicate_removal": {"enabled": True, "keep": "first"}
        },
        "preview_limit": 5
    }

    res = client_a.post(
        f"/api/datasets/{dataset_id}/clean/preview",
        headers={"X-CSRF-Token": csrf_a},
        json=req_payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["dataset_id"] == dataset_id
    assert "summary" in data
    assert "original_preview" in data
    assert "cleaned_preview" in data
    assert len(data["cleaned_preview"]) <= 5
    assert data["summary"]["duplicate_rows"]["difference"] == -1


def test_preview_does_not_create_file_or_db_record(test_setup, db: Session):
    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]
    dataset_id = test_setup["dataset_a_id"]

    count_before = db.query(CleaningRecord).filter(CleaningRecord.dataset_id == dataset_id).count()

    res = client_a.post(
        f"/api/datasets/{dataset_id}/clean/preview",
        headers={"X-CSRF-Token": csrf_a},
        json={"config": {"whitespace_cleaning": {"enabled": True}}, "preview_limit": 5},
    )
    assert res.status_code == 200

    count_after = db.query(CleaningRecord).filter(CleaningRecord.dataset_id == dataset_id).count()
    assert count_before == count_after  # Strictly no DB mutation


def test_apply_cleaning_endpoint_success_and_persist(test_setup, db: Session):
    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]
    dataset_id = test_setup["dataset_a_id"]

    req_payload = {
        "config": {
            "whitespace_cleaning": {"enabled": True, "trim_whitespace": True},
            "duplicate_removal": {"enabled": True, "keep": "first"}
        }
    }

    res = client_a.post(
        f"/api/datasets/{dataset_id}/clean",
        headers={"X-CSRF-Token": csrf_a},
        json=req_payload,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "completed"
    assert data["output_row_count"] == 4  # 5 rows minus 1 duplicate
    cleaning_id = data["id"]

    # Verify record in DB
    record = db.query(CleaningRecord).filter(CleaningRecord.id == cleaning_id).first()
    assert record is not None
    assert record.output_file_path is not None
    assert Path(record.output_file_path).exists()


def test_apply_cleaning_missing_source_returns_not_found(test_setup, db: Session):
    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]
    dataset_id = test_setup["dataset_a_id"]
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    original_path = dataset.file_path
    dataset.file_path = str(Path(tempfile.gettempdir()) / "missing-csvqa-test-source.csv")
    db.commit()

    try:
        response = client_a.post(
            f"/api/datasets/{dataset_id}/clean",
            headers={"X-CSRF-Token": csrf_a},
            json={"config": {"whitespace_cleaning": {"enabled": True}}},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    finally:
        dataset.file_path = original_path
        db.commit()


def test_get_dataset_cleanings_history(test_setup):
    client_a = test_setup["client_a"]
    dataset_id = test_setup["dataset_a_id"]

    res = client_a.get(f"/api/datasets/{dataset_id}/cleanings?skip=0&limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


def test_get_cleaning_record_by_id(test_setup, db: Session):
    client_a = test_setup["client_a"]
    dataset_id = test_setup["dataset_a_id"]

    record = db.query(CleaningRecord).filter(CleaningRecord.dataset_id == dataset_id).first()
    assert record is not None

    res = client_a.get(f"/api/cleanings/{record.id}")
    assert res.status_code == 200
    assert res.json()["id"] == record.id


def test_download_cleaned_file(test_setup, db: Session):
    client_a = test_setup["client_a"]
    dataset_id = test_setup["dataset_a_id"]

    record = db.query(CleaningRecord).filter(CleaningRecord.dataset_id == dataset_id).first()
    assert record is not None

    res = client_a.get(f"/api/cleanings/{record.id}/download")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    csv_text = res.text
    assert "Alice" in csv_text
    assert "Dave" in csv_text


def test_unauthenticated_requests_rejected(test_setup):
    unauth_client = TestClient(app)
    dataset_id = test_setup["dataset_a_id"]

    res_prev = unauth_client.post(f"/api/datasets/{dataset_id}/clean/preview", json={"config": {"whitespace_cleaning": {"enabled": True}}})
    assert res_prev.status_code == 401

    res_apply = unauth_client.post(f"/api/datasets/{dataset_id}/clean", json={"config": {"whitespace_cleaning": {"enabled": True}}})
    assert res_apply.status_code == 401

    res_hist = unauth_client.get(f"/api/datasets/{dataset_id}/cleanings")
    assert res_hist.status_code == 401


def test_csrf_token_required_for_state_changing_requests(test_setup):
    client_a = test_setup["client_a"]
    dataset_id = test_setup["dataset_a_id"]

    # Request without CSRF header
    res = client_a.post(
        f"/api/datasets/{dataset_id}/clean",
        json={"config": {"whitespace_cleaning": {"enabled": True}}}
    )
    assert res.status_code == 403
    assert "CSRF verification failed" in res.json()["detail"]


def test_cross_user_dataset_and_cleaning_isolation(test_setup, db: Session):
    client_b = test_setup["client_b"]
    csrf_b = test_setup["csrf_b"]
    dataset_a_id = test_setup["dataset_a_id"]

    # User B attempts to preview User A's dataset
    res_prev = client_b.post(
        f"/api/datasets/{dataset_a_id}/clean/preview",
        headers={"X-CSRF-Token": csrf_b},
        json={"config": {"whitespace_cleaning": {"enabled": True}}},
    )
    assert res_prev.status_code == 403

    # User B attempts to clean User A's dataset
    res_apply = client_b.post(
        f"/api/datasets/{dataset_a_id}/clean",
        headers={"X-CSRF-Token": csrf_b},
        json={"config": {"whitespace_cleaning": {"enabled": True}}},
    )
    assert res_apply.status_code == 403

    # User B attempts to view history of User A's dataset
    res_hist = client_b.get(f"/api/datasets/{dataset_a_id}/cleanings")
    assert res_hist.status_code == 403

    # User B attempts to download User A's cleaned file
    record_a = db.query(CleaningRecord).filter(CleaningRecord.dataset_id == dataset_a_id).first()
    if record_a:
        res_dl = client_b.get(f"/api/cleanings/{record_a.id}/download")
        assert res_dl.status_code == 403


def test_original_file_hash_strictly_unchanged(test_setup, db: Session):
    dataset_id = test_setup["dataset_a_id"]
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    file_path = Path(dataset.file_path)

    sha256_before = hashlib.sha256(file_path.read_bytes()).hexdigest()

    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]

    # Apply cleaning
    res = client_a.post(
        f"/api/datasets/{dataset_id}/clean",
        headers={"X-CSRF-Token": csrf_a},
        json={"config": {"whitespace_cleaning": {"enabled": True}}}
    )
    assert res.status_code == 201

    sha256_after = hashlib.sha256(file_path.read_bytes()).hexdigest()
    assert sha256_before == sha256_after


def test_missing_source_file_returns_404(test_setup, db: Session):
    client_a = test_setup["client_a"]
    csrf_a = test_setup["csrf_a"]
    user_a = test_setup["user_a"]

    ghost_dataset = Dataset(
        user_id=user_a.id,
        original_filename="ghost.csv",
        stored_filename="ghost_cleaning_9999.csv",
        file_path="d:/CSV Data Quality Analyzer/CSV Data Quality Analyzer/backend/uploads/ghost_cleaning_9999.csv",
        file_size_bytes=100,
        row_count=10,
        column_count=2,
    )
    db.add(ghost_dataset)
    db.commit()
    db.refresh(ghost_dataset)

    try:
        res = client_a.post(
            f"/api/datasets/{ghost_dataset.id}/clean/preview",
            headers={"X-CSRF-Token": csrf_a},
            json={"config": {"whitespace_cleaning": {"enabled": True}}}
        )
        assert res.status_code == 404
        assert "not found on disk" in res.json()["detail"]
    finally:
        db.delete(ghost_dataset)
        db.commit()


def test_download_missing_cleaned_file_returns_404(test_setup, db: Session):
    client_a = test_setup["client_a"]
    user_a = test_setup["user_a"]
    dataset_id = test_setup["dataset_a_id"]

    # Create dummy cleaning record pointing to deleted file
    ghost_record = CleaningRecord(
        dataset_id=dataset_id,
        user_id=user_a.id,
        status="completed",
        cleaning_config={"whitespace_cleaning": {"enabled": True}},
        cleaning_summary={},
        output_filename="missing_cleaned.csv",
        output_file_path="d:/CSV Data Quality Analyzer/CSV Data Quality Analyzer/backend/cleaned/missing_cleaned.csv",
        output_file_size_bytes=100,
        output_row_count=10,
        output_column_count=2,
    )
    db.add(ghost_record)
    db.commit()
    db.refresh(ghost_record)

    try:
        res = client_a.get(f"/api/cleanings/{ghost_record.id}/download")
        assert res.status_code == 404
        assert "missing from storage" in res.json()["detail"]
    finally:
        db.delete(ghost_record)
        db.commit()
