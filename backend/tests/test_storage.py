from app.config import settings
from app.services.storage import R2Storage, materialize


class FakeS3:
    def __init__(self):
        self.calls = []

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.calls.append((operation, Params, ExpiresIn))
        return "https://storage.example/signed"

    def head_object(self, Bucket, Key):
        return {"ContentLength": 123, "ETag": '"etag-123"'}

    def copy_object(self, **kwargs):
        self.calls.append(("copy", kwargs))


def test_r2_upload_authorization_is_single_object_and_short_lived(monkeypatch):
    monkeypatch.setattr(settings, "R2_BUCKET", "private-test-bucket")
    client = FakeS3()
    storage = R2Storage(client=client)

    url = storage.authorize_upload("staging/12/34/random.csv")

    assert url == "https://storage.example/signed"
    operation, params, ttl = client.calls[0]
    assert operation == "put_object"
    assert params == {
        "Bucket": "private-test-bucket",
        "Key": "staging/12/34/random.csv",
        "ContentType": "application/octet-stream",
    }
    assert 1 <= ttl <= 600


def test_r2_head_returns_size_and_etag():
    assert R2Storage(client=FakeS3()).object_info("datasets/1/2/data.csv") == {
        "size": 123,
        "etag": '"etag-123"',
    }


def test_r2_finalization_copy_is_conditional_on_verified_object_version():
    client = FakeS3()
    R2Storage(client=client).promote("staging/source.csv", "datasets/final.csv", '"etag-123"')
    assert client.calls[0][0] == "copy"
    assert client.calls[0][1]["CopySourceIfMatch"] == '"etag-123"'


def test_local_materialize_rejects_missing_file(tmp_path):
    from fastapi import HTTPException
    import pytest

    missing = tmp_path / "missing.csv"
    with pytest.raises(HTTPException) as exc:
        with materialize(str(missing)):
            pass
    assert exc.value.status_code == 404
