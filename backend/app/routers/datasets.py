from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List
import logging

from app.database import get_db
from app.models.user import User
from app.models.dataset import Dataset
from app.auth import get_current_user
from app.schemas.dataset import (
    DatasetResponse,
    DatasetDetailResponse,
    DatasetListResponse,
)
from app.services.csv_service import (
    save_upload_stream,
    parse_and_extract_metadata,
    remove_file_safely,
)

logger = logging.getLogger("csv_analyzer.datasets")

router = APIRouter(prefix="/api/datasets", tags=["Datasets"])


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
        logger.error(f"Unexpected error processing CSV upload: {exc}", exc_info=True)
        if dest_path:
            remove_file_safely(dest_path)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the uploaded file: {str(exc)}"
        )


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
        .filter(Dataset.user_id == current_user.id)
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

    # Extract preview rows from the stored file if it exists
    preview_rows: List[dict] = []
    file_path = Path(dataset.file_path)
    if file_path.exists():
        try:
            _, _, _, preview_rows = parse_and_extract_metadata(file_path)
        except Exception as exc:
            logger.warning(f"Could not load preview for dataset {dataset_id}: {exc}")

    resp = DatasetDetailResponse.model_validate(dataset)
    resp.preview_rows = preview_rows
    return resp
