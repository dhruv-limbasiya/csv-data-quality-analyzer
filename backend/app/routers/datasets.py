from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from pathlib import Path
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.dataset import Dataset
from app.auth import get_current_user
from app.schemas.dataset import (
    DatasetResponse,
    DatasetDetailResponse,
    DatasetListResponse,
    UploadAuthorizationRequest,
)
from app.services.csv_service import (
    save_upload_stream,
    parse_and_extract_metadata,
    remove_file_safely,
    sanitize_filename,
    validate_file_extension,
)
from app.services.storage import (
    R2_REFERENCE_PREFIX,
    create_upload_authorization,
    delete_reference,
    materialize,
    object_info,
    promote_upload,
    is_remote_storage,
)

logger = logging.getLogger("csv_analyzer.datasets")

router = APIRouter(prefix="/api/datasets", tags=["Datasets"])
MAX_PENDING_UPLOADS_PER_USER = 3


@router.post(
    "/upload",
    response_model=DatasetDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and parse a CSV file",
    description="Upload a CSV dataset. Validates format, encoding, headers, extracts metadata, saves to disk, and records metadata in database."
)
async def upload_csv_dataset(
    file: UploadFile = File(..., description="Multipart CSV file to upload"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload, validate, and parse a CSV file.
    Streams upload to disk to avoid excessive memory usage.
    Cleans up any partially saved file if parsing or database insertion fails.
    """
    if is_remote_storage():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Use the short-lived direct object-storage upload flow.",
        )

    dest_path = None
    try:
        # 1. Stream file to disk with size validation and sanitize filename
        original_filename, stored_filename, dest_path, file_size_bytes = await save_upload_stream(file)

        # 2. Parse CSV with Pandas and extract structural metadata
        row_count, column_count, columns_metadata, preview_rows = parse_and_extract_metadata(dest_path)

        # 3. Persist dataset record in database
        dataset = Dataset(
            user_id=current_user.id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=str(dest_path.resolve()),
            file_size_bytes=file_size_bytes,
            upload_status="ready",
            row_count=row_count,
            column_count=column_count,
            columns_metadata=columns_metadata,
            is_cleaned_version=False,
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        logger.info(
            f"Successfully uploaded dataset id={dataset.id} for user_id={current_user.id} "
            f"({row_count} rows, {column_count} cols, {file_size_bytes} bytes)"
        )

        # Return full detail response including preview
        resp = DatasetDetailResponse.model_validate(dataset)
        resp.preview_rows = preview_rows
        return resp

    except HTTPException:
        # Re-raise known HTTP errors after cleaning up disk file
        if dest_path:
            remove_file_safely(dest_path)
        db.rollback()
        raise

    except Exception as exc:
        # Clean up file and rollback transaction on unexpected error
        logger.error("Unexpected error processing CSV upload.")
        if dest_path:
            remove_file_safely(dest_path)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the uploaded file."
        )


@router.post(
    "/upload/authorize",
    status_code=status.HTTP_201_CREATED,
    summary="Authorize a short-lived direct object-storage upload",
)
def authorize_csv_upload(
    payload: UploadAuthorizationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reserve a user-owned pending dataset and issue a short-lived R2 PUT URL."""
    original_filename = sanitize_filename(payload.filename)
    validate_file_extension(original_filename)
    maximum_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if payload.size_bytes <= 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")
    if payload.size_bytes > maximum_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the maximum allowed upload size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    now = datetime.now(timezone.utc)
    expired_uploads = (
        db.query(Dataset)
        .filter(
            Dataset.user_id == current_user.id,
            Dataset.upload_status == "pending",
            Dataset.upload_expires_at <= now,
        )
        .all()
    )
    for stale_upload in expired_uploads:
        try:
            delete_reference(stale_upload.file_path)
        except HTTPException:
            # R2 staging keys have a one-day lifecycle expiry as a second cleanup path.
            pass
        db.delete(stale_upload)
    if expired_uploads:
        db.flush()

    active_uploads = (
        db.query(Dataset)
        .filter(
            Dataset.user_id == current_user.id,
            Dataset.upload_status == "pending",
            Dataset.upload_expires_at > now,
        )
        .count()
    )
    if active_uploads >= MAX_PENDING_UPLOADS_PER_USER:
        raise HTTPException(status_code=429, detail="Too many active uploads. Finish or cancel an existing upload.")

    authorization_ttl = settings.R2_PRESIGNED_URL_TTL_SECONDS
    expires_at = now + timedelta(seconds=authorization_ttl)
    dataset = Dataset(
        user_id=current_user.id,
        original_filename=original_filename,
        stored_filename=f"{uuid_hex()}.csv",
        file_path="pending",
        file_size_bytes=payload.size_bytes,
        upload_status="pending",
        upload_expires_at=expires_at,
        is_cleaned_version=False,
    )
    db.add(dataset)
    try:
        db.flush()
        key, upload_url = create_upload_authorization(current_user.id, dataset.id)
        dataset.file_path = f"{R2_REFERENCE_PREFIX}{key}"
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "dataset_id": dataset.id,
        "upload_url": upload_url,
        "expires_in_seconds": authorization_ttl,
        "required_headers": {"Content-Type": "application/octet-stream"},
    }


@router.post(
    "/{dataset_id}/finalize",
    response_model=DatasetDetailResponse,
    summary="Verify and finalize a direct object-storage upload",
)
def finalize_csv_upload(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset was not found.")
    if dataset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")
    if dataset.upload_status == "ready":
        return _dataset_detail(dataset)
    if dataset.upload_status != "pending":
        raise HTTPException(status_code=409, detail="Upload is not in a finalizable state.")

    expires_at = dataset.upload_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Upload authorization expired. Start the upload again.")

    source_info = object_info(dataset.file_path)
    if source_info is None:
        raise HTTPException(status_code=409, detail="Uploaded object is missing or has not completed.")
    actual_size = source_info["size"]
    source_etag = source_info["etag"]
    if actual_size == 0 or actual_size != dataset.file_size_bytes or not source_etag:
        raise HTTPException(status_code=409, detail="Uploaded object size does not match the authorized size.")

    source_reference = dataset.file_path
    destination_reference = None
    committed = False
    try:
        with materialize(source_reference) as source_path:
            row_count, column_count, columns_metadata, preview_rows = parse_and_extract_metadata(source_path)
        latest_info = object_info(source_reference)
        if not latest_info or latest_info["etag"] != source_etag:
            raise HTTPException(status_code=409, detail="Uploaded object changed during verification. Retry the upload.")
        destination_key = f"datasets/{current_user.id}/{dataset.id}/{uuid_hex()}.csv"
        destination_reference = f"{R2_REFERENCE_PREFIX}{destination_key}"
        promote_upload(source_reference, destination_reference, source_etag)
        dataset.file_path = destination_reference
        dataset.stored_filename = f"{Path(destination_key).name}"
        dataset.row_count = row_count
        dataset.column_count = column_count
        dataset.columns_metadata = columns_metadata
        dataset.upload_status = "ready"
        dataset.upload_expires_at = None
        db.commit()
        committed = True
        db.refresh(dataset)
    except HTTPException:
        db.rollback()
        if destination_reference and not committed:
            try:
                delete_reference(destination_reference)
            except HTTPException:
                pass
        raise
    except Exception as exc:
        db.rollback()
        if destination_reference and not committed:
            try:
                delete_reference(destination_reference)
            except HTTPException:
                pass
        logger.error("Failed to finalize a dataset upload.")
        raise HTTPException(status_code=503, detail="Upload processing is temporarily unavailable.") from exc

    try:
        delete_reference(source_reference)
    except HTTPException:
        # The configured staging-prefix lifecycle rule removes abandoned staging keys.
        pass
    response = DatasetDetailResponse.model_validate(dataset)
    response.preview_rows = preview_rows
    return response


@router.delete(
    "/{dataset_id}/upload",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a pending direct object-storage upload",
)
def cancel_csv_upload(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset was not found.")
    if dataset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")
    if dataset.upload_status != "pending":
        raise HTTPException(status_code=409, detail="Only pending uploads can be cancelled.")
    delete_reference(dataset.file_path)
    db.delete(dataset)
    db.commit()


@router.get(
    "",
    response_model=DatasetListResponse,
    summary="List current user's datasets",
    description="Returns all datasets owned by the currently authenticated user."
)
def list_datasets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all datasets owned by the authenticated caller."""
    datasets = (
        db.query(Dataset)
        .filter(Dataset.user_id == current_user.id, Dataset.upload_status == "ready")
        .order_by(Dataset.created_at.desc())
        .all()
    )
    return DatasetListResponse(total=len(datasets), items=datasets)


@router.get(
    "/{dataset_id}",
    response_model=DatasetDetailResponse,
    summary="Get dataset details",
    description="Retrieve metadata and sample preview rows for a specific dataset owned by the user."
)
def get_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve metadata and preview for a specific dataset owned by the user."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found."
        )

    # Enforce ownership check
    if dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to access this dataset."
        )
    if dataset.upload_status != "ready":
        raise HTTPException(status_code=409, detail="Dataset upload has not been finalized.")

    with materialize(dataset.file_path) as file_path:
        _, _, _, preview_rows = parse_and_extract_metadata(file_path)

    resp = DatasetDetailResponse.model_validate(dataset)
    resp.preview_rows = preview_rows
    return resp


def uuid_hex() -> str:
    return uuid.uuid4().hex


def _dataset_detail(dataset: Dataset) -> DatasetDetailResponse:
    response = DatasetDetailResponse.model_validate(dataset)
    with materialize(dataset.file_path) as file_path:
        _, _, _, response.preview_rows = parse_and_extract_metadata(file_path)
    return response
