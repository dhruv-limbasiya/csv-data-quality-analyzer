"""Private local-development and Cloudflare R2 storage adapters.

Only short-lived signed PUT authorizations reach the browser. Service credentials
remain in the API process; completed object references are opaque R2 keys in SQL.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import tempfile
from typing import Iterator, Optional
import uuid

from fastapi import HTTPException, status

from app.config import settings


R2_REFERENCE_PREFIX = "r2://"
UPLOAD_CONTENT_TYPE = "application/octet-stream"


class ObjectStorageError(Exception):
    """Raised when the object provider cannot complete a storage operation."""


class R2Storage:
    def __init__(self, client=None):
        self._s3 = client

    @property
    def client(self):
        if self._s3 is None:
            import boto3

            self._s3 = boto3.client(
                "s3",
                endpoint_url=settings.r2_endpoint_url,
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                region_name="auto",
            )
        return self._s3

    def authorize_upload(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.R2_BUCKET,
                "Key": key,
                "ContentType": UPLOAD_CONTENT_TYPE,
            },
            ExpiresIn=settings.R2_PRESIGNED_URL_TTL_SECONDS,
        )

    def authorize_download(self, key: str, filename: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.R2_BUCKET,
                "Key": key,
                "ResponseContentType": "text/csv; charset=utf-8",
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=settings.R2_PRESIGNED_URL_TTL_SECONDS,
        )

    def object_info(self, key: str) -> Optional[dict]:
        try:
            result = self.client.head_object(Bucket=settings.R2_BUCKET, Key=key)
            return {
                "size": int(result["ContentLength"]),
                "etag": result.get("ETag"),
            }
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise ObjectStorageError("Object storage verification failed.") from exc

    def promote(self, source_key: str, destination_key: str, source_etag: str) -> None:
        try:
            self.client.copy_object(
                Bucket=settings.R2_BUCKET,
                Key=destination_key,
                CopySource={"Bucket": settings.R2_BUCKET, "Key": source_key},
                CopySourceIfMatch=source_etag,
                MetadataDirective="COPY",
            )
        except Exception as exc:
            raise ObjectStorageError("Object storage could not finalize the upload.") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=settings.R2_BUCKET, Key=key)
        except Exception as exc:
            raise ObjectStorageError("Object storage cleanup failed.") from exc

    def download(self, key: str, destination: Path) -> None:
        try:
            self.client.download_file(settings.R2_BUCKET, key, str(destination))
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError from exc
            raise ObjectStorageError("Object storage download failed.") from exc

    def upload_file(self, source: Path, key: str) -> None:
        try:
            self.client.upload_file(str(source), settings.R2_BUCKET, key)
        except Exception as exc:
            raise ObjectStorageError("Object storage upload failed.") from exc


_r2 = R2Storage()


def is_remote_storage() -> bool:
    return settings.STORAGE_BACKEND.strip().lower() == "r2"


def _local_path(reference: str) -> Path:
    return Path(reference)


def _r2_key(reference: str) -> str:
    if not reference.startswith(R2_REFERENCE_PREFIX):
        raise ValueError("Invalid object storage reference.")
    return reference[len(R2_REFERENCE_PREFIX):]


def create_upload_authorization(user_id: int, dataset_id: int) -> tuple[str, str]:
    """Return a private staging key and narrowly scoped signed PUT URL."""
    if not is_remote_storage():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Direct object uploads are not enabled for this environment.",
        )
    key = f"staging/{user_id}/{dataset_id}/{uuid.uuid4().hex}.csv"
    try:
        return key, _r2.authorize_upload(key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload storage is temporarily unavailable.",
        ) from exc


def object_size(reference: str) -> Optional[int]:
    try:
        if reference.startswith(R2_REFERENCE_PREFIX):
            info = _r2.object_info(_r2_key(reference))
            return info["size"] if info else None
        path = _local_path(reference)
        return path.stat().st_size if path.is_file() else None
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload storage is temporarily unavailable.",
        ) from exc


def object_info(reference: str) -> Optional[dict]:
    try:
        if reference.startswith(R2_REFERENCE_PREFIX):
            return _r2.object_info(_r2_key(reference))
        path = _local_path(reference)
        return {"size": path.stat().st_size, "etag": None} if path.is_file() else None
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload storage is temporarily unavailable.",
        ) from exc


def promote_upload(source_reference: str, destination_reference: str, source_etag: str) -> None:
    try:
        _r2.promote(_r2_key(source_reference), _r2_key(destination_reference), source_etag)
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload storage could not finalize this file.",
        ) from exc


def delete_reference(reference: str) -> None:
    try:
        if reference.startswith(R2_REFERENCE_PREFIX):
            _r2.delete(_r2_key(reference))
        else:
            _local_path(reference).unlink(missing_ok=True)
    except (OSError, ObjectStorageError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage cleanup is temporarily unavailable.",
        ) from exc


@contextmanager
def materialize(reference: str) -> Iterator[Path]:
    """Yield a local path for a single operation; remove temporary downloads."""
    if not reference.startswith(R2_REFERENCE_PREFIX):
        path = _local_path(reference)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Source dataset file was not found on disk.")
        yield path
        return

    fd, name = tempfile.mkstemp(prefix="csv-analyzer-", suffix=".csv")
    os.close(fd)
    path = Path(name)
    try:
        _r2.download(_r2_key(reference), path)
        yield path
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset file is missing from object storage.",
        ) from exc
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dataset storage is temporarily unavailable.",
        ) from exc
    finally:
        path.unlink(missing_ok=True)


def store_cleaned_file(source: Path, key: str) -> str:
    """Persist a completed cleaning output and return an opaque reference."""
    if is_remote_storage():
        try:
            _r2.upload_file(source, key)
            return f"{R2_REFERENCE_PREFIX}{key}"
        except ObjectStorageError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cleaned file storage is temporarily unavailable.",
            ) from exc
    destination = settings.cleaned_path / Path(key).name
    shutil.move(str(source), str(destination))
    return str(destination.resolve())


def authorize_download(reference: str, filename: str) -> str:
    try:
        return _r2.authorize_download(_r2_key(reference), filename)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Cleaned file storage is temporarily unavailable.",
        ) from exc


def materialize_for_response(reference: str) -> tuple[Path, bool]:
    """Return a path valid through response streaming and whether it needs cleanup."""
    if not reference.startswith(R2_REFERENCE_PREFIX):
        path = _local_path(reference)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Cleaned output file is missing from storage.")
        return path, False
    fd, name = tempfile.mkstemp(prefix="csv-download-", suffix=".csv")
    os.close(fd)
    path = Path(name)
    try:
        _r2.download(_r2_key(reference), path)
        return path, True
    except FileNotFoundError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="Cleaned output file is missing from storage.") from exc
    except ObjectStorageError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=503,
            detail="Cleaned file storage is temporarily unavailable.",
        ) from exc


def remove_temp_file(path: Path) -> None:
    """Best-effort cleanup for temporary response files."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
