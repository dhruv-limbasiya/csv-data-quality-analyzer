from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.auth import get_current_user
from app.models.dataset import Dataset
from app.models.user import User
import app.routers.datasets as dataset_routes
from app.services.security import hash_password


def test_direct_upload_validates_ownership_size_and_finalizes_idempotently(monkeypatch, tmp_path):
    monkeypatch.setattr(dataset_routes.settings, "MAX_UPLOAD_SIZE_MB", 1)
    db = SessionLocal()
    username = "upload_lifecycle_" + datetime.now(timezone.utc).strftime("%H%M%S%f")
    user = User(
        username=username,
        email=f"{username}@example.invalid",
        hashed_password=hash_password("NotAProductionPassword123!"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    csv_path = tmp_path / "valid.csv"
    csv_path.write_text("name,value\nalpha,1\n", encoding="utf-8")
    promoted = []
    monkeypatch.setattr(
        dataset_routes,
        "create_upload_authorization",
        lambda user_id, dataset_id: (f"staging/{user_id}/{dataset_id}/object.csv", "https://storage.invalid/put"),
    )
    monkeypatch.setattr(
        dataset_routes,
        "object_info",
        lambda _reference: {"size": csv_path.stat().st_size, "etag": '"verified-etag"'},
    )

    @contextmanager
    def materialize_for_test(_reference):
        yield csv_path

    monkeypatch.setattr(dataset_routes, "materialize", materialize_for_test)
    monkeypatch.setattr(
        dataset_routes,
        "promote_upload",
        lambda source, destination, etag: promoted.append((source, destination, etag)),
    )
    monkeypatch.setattr(dataset_routes, "delete_reference", lambda _reference: None)
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)

    try:
        too_large = client.post(
            "/api/datasets/upload/authorize",
            json={"filename": "oversized.csv", "size_bytes": 2 * 1024 * 1024},
        )
        assert too_large.status_code == 413

        authorization = client.post(
            "/api/datasets/upload/authorize",
            json={"filename": "../verified.csv", "size_bytes": csv_path.stat().st_size},
        )
        assert authorization.status_code == 201
        payload = authorization.json()
        assert payload["upload_url"] == "https://storage.invalid/put"
        assert payload["required_headers"]["Content-Type"] == "application/octet-stream"

        record = db.query(Dataset).filter(Dataset.id == payload["dataset_id"]).one()
        assert record.original_filename == "verified.csv"
        assert record.upload_status == "pending"

        finalized = client.post(f"/api/datasets/{record.id}/finalize")
        assert finalized.status_code == 200
        assert finalized.json()["row_count"] == 1
        assert finalized.json()["column_count"] == 2
        db.expire_all()
        assert db.query(Dataset).filter(Dataset.id == record.id).one().upload_status == "ready"
        assert len(promoted) == 1
        assert promoted[0][2] == '"verified-etag"'

        repeated = client.post(f"/api/datasets/{record.id}/finalize")
        assert repeated.status_code == 200
        assert repeated.json()["id"] == record.id
        assert len(promoted) == 1

        # A declared upload that does not match the stored object cannot finalize.
        missing = client.post(
            "/api/datasets/upload/authorize",
            json={"filename": "incomplete.csv", "size_bytes": csv_path.stat().st_size + 1},
        )
        assert missing.status_code == 201
        mismatch = client.post(f"/api/datasets/{missing.json()['dataset_id']}/finalize")
        assert mismatch.status_code == 409
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        client.close()
        db.query(Dataset).filter(Dataset.user_id == user.id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
        db.close()


def test_finalization_rejects_expired_authorization(monkeypatch):
    db = SessionLocal()
    username = "upload_expired_" + datetime.now(timezone.utc).strftime("%H%M%S%f")
    user = User(
        username=username,
        email=f"{username}@example.invalid",
        hashed_password=hash_password("NotAProductionPassword123!"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    dataset = Dataset(
        user_id=user.id,
        original_filename="expired.csv",
        stored_filename=f"{username}.csv",
        file_path="r2://staging/expired/object.csv",
        file_size_bytes=10,
        upload_status="pending",
        upload_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db.add(dataset)
    db.commit()
    dataset_id = dataset.id
    monkeypatch.setattr(dataset_routes, "object_info", lambda _reference: pytest.fail("expired object must not be inspected"))
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        response = client.post(f"/api/datasets/{dataset_id}/finalize")
        assert response.status_code == 410
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        client.close()
        db.query(Dataset).filter(Dataset.user_id == user.id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
        db.close()
