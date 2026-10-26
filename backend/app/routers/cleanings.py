import uuid
import tempfile
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session
import logging

from app.database import get_db
from app.models.user import User
from app.models.dataset import Dataset
from app.models.cleaning import CleaningRecord
from app.auth import get_current_user
from app.schemas.cleaning import (
    CleaningConfig,
    CleaningPreviewRequest,
    CleaningApplyRequest,
    CleaningPreviewResponse,
    CleaningRecordResponse,
    CleaningListResponse,
    CleaningSummary,
)
from app.services.cleaning_service import (
    apply_cleaning_pipeline,
    CleaningExecutionError,
    sanitize_csv_formulas_for_export,
)
from app.services.csv_service import make_json_serializable
from app.services.storage import (
    authorize_download,
    delete_reference,
    materialize,
    materialize_for_response,
    is_remote_storage,
    object_size,
    remove_temp_file,
    store_cleaned_file,
)

logger = logging.getLogger("csv_analyzer.cleanings")

router = APIRouter(tags=["Data Cleaning"])


def _dataframe_to_preview_dicts(df: pd.DataFrame, limit: int) -> List[Dict[str, Any]]:
    """Convert top N rows of DataFrame to JSON-safe dictionary records."""
    preview_df = df.head(limit)
    records = []
    for _, row in preview_df.iterrows():
        record = {}
        for col in df.columns:
            record[str(col)] = make_json_serializable(row[col])
        records.append(record)
    return records


@router.post(
    "/api/datasets/{dataset_id}/clean/preview",
    response_model=CleaningPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview data cleaning operations",
    description="Loads source CSV, validates cleaning config, applies transformations in memory, and returns before/after preview without writing to disk or database.",
)
def preview_cleaning(
    dataset_id: int,
    payload: CleaningPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview proposed cleaning operations without modifying any file or database record."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found."
        )

    if dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this dataset."
        )

    if dataset.upload_status != "ready":
        raise HTTPException(status_code=409, detail="Dataset upload has not been finalized.")

    try:
        with materialize(dataset.file_path) as file_path:
            df_original = pd.read_csv(file_path, encoding="utf-8-sig")
    except HTTPException:
        raise
    except Exception:
        logger.error("Failed to read CSV dataset id=%s.", dataset_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read the original CSV dataset for preview."
        )

    try:
        df_cleaned, summary = apply_cleaning_pipeline(df_original, payload.config)
    except CleaningExecutionError as cee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(cee)
        )
    except Exception:
        logger.error("Unexpected error during cleaning preview.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while evaluating cleaning preview."
        )

    original_preview = _dataframe_to_preview_dicts(df_original, payload.preview_limit)
    cleaned_preview = _dataframe_to_preview_dicts(df_cleaned, payload.preview_limit)

    return CleaningPreviewResponse(
        dataset_id=dataset.id,
        summary=summary,
        original_preview=original_preview,
        cleaned_preview=cleaned_preview,
        columns=[str(c) for c in df_cleaned.columns],
    )


@router.post(
    "/api/datasets/{dataset_id}/clean",
    response_model=CleaningRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply data cleaning and save new cleaned dataset",
    description="Applies configured cleaning operations, writes cleaned output to private storage, and records history in database.",
)
def apply_cleaning(
    dataset_id: int,
    payload: CleaningApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply cleaning, write cleaned CSV to private storage, and record cleaning history."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found."
        )

    if dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this dataset."
        )

    if dataset.upload_status != "ready":
        raise HTTPException(status_code=409, detail="Dataset upload has not been finalized.")

    try:
        with materialize(dataset.file_path) as file_path:
            df_original = pd.read_csv(file_path, encoding="utf-8-sig")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to read CSV dataset id=%s.", dataset_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read the original CSV dataset for cleaning."
        )

    try:
        df_cleaned, summary = apply_cleaning_pipeline(df_original, payload.config)
    except CleaningExecutionError as cee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(cee)
        )
    except Exception:
        logger.error("Unexpected error during cleaning execution.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while executing cleaning operations."
        )

    # Check for empty dataframe outcomes
    if len(df_cleaned.columns) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Safety check failed: Cleaning operation resulted in 0 columns."
        )
    if len(df_cleaned) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Safety check failed: Cleaning operation resulted in 0 rows."
        )

    # Output storage preparation
    output_filename = f"cleaned_{uuid.uuid4().hex}.csv"
    temp_file_path = None
    output_reference = None

    try:
        # 1. Write to temporary file first
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as temp_file:
            temp_file_path = Path(temp_file.name)
            df_cleaned.to_csv(temp_file, index=False, encoding="utf-8")

        output_file_size = temp_file_path.stat().st_size
        object_key = f"cleaned/{current_user.id}/{dataset.id}/{output_filename}"
        output_reference = store_cleaned_file(temp_file_path, object_key)

        # 3. Create database record
        cleaning_record = CleaningRecord(
            dataset_id=dataset.id,
            user_id=current_user.id,
            status="completed",
            cleaning_config=payload.config.model_dump(),
            cleaning_summary=summary,
            output_filename=output_filename,
            output_file_path=output_reference,
            output_file_size_bytes=output_file_size,
            output_row_count=len(df_cleaned),
            output_column_count=len(df_cleaned.columns),
        )
        db.add(cleaning_record)
        db.commit()
        db.refresh(cleaning_record)

        return cleaning_record

    except Exception as exc:
        logger.error("Failed to persist cleaned file or DB record.")
        db.rollback()
        # Clean up files on error
        if temp_file_path and temp_file_path.exists():
            temp_file_path.unlink(missing_ok=True)
        if output_reference:
            try:
                delete_reference(output_reference)
            except HTTPException:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while saving the cleaned dataset output."
        )


@router.get(
    "/api/datasets/{dataset_id}/cleanings",
    response_model=CleaningListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cleaning history for a dataset",
    description="Returns all cleaning operations performed on the specified dataset with pagination.",
)
def get_dataset_cleanings(
    dataset_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve cleaning records for a dataset owned by the caller."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found."
        )

    if dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this dataset."
        )

    base_query = db.query(CleaningRecord).filter(CleaningRecord.dataset_id == dataset.id)
    total = base_query.count()
    records = (
        base_query
        .order_by(CleaningRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return CleaningListResponse(total=total, items=records)


@router.get(
    "/api/cleanings/{cleaning_id}",
    response_model=CleaningRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cleaning record details",
    description="Returns metadata and summary for an individual cleaning record by ID.",
)
def get_cleaning_record(
    cleaning_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve details of a specific cleaning record with user ownership validation."""
    record = db.query(CleaningRecord).filter(CleaningRecord.id == cleaning_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cleaning record with ID {cleaning_id} was not found."
        )

    if record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this cleaning record."
        )

    return record


@router.get(
    "/api/cleanings/{cleaning_id}/download",
    status_code=status.HTTP_200_OK,
    summary="Download cleaned CSV file",
    description="Downloads the completed cleaned CSV file for an authorized user with formula-injection protection enabled by default.",
)
def download_cleaned_file(
    cleaning_id: int,
    export_safe: bool = Query(True, description="When true, escapes formula triggers in text cells to guard against spreadsheet injection"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Securely download a cleaned CSV file, sanitizing spreadsheet formulas by default."""
    record = db.query(CleaningRecord).filter(CleaningRecord.id == cleaning_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cleaning record with ID {cleaning_id} was not found."
        )

    if record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this cleaning record."
        )

    if record.status != "completed" or not record.output_file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cleaning operation was not completed or has no output file available."
        )

    # Safe download filename derived from original dataset name
    orig_name = record.dataset.original_filename if record.dataset else "dataset.csv"
    stem = Path(orig_name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem).strip("._") or "dataset"
    safe_download_name = f"{safe_stem[:180]}_cleaned.csv"

    if is_remote_storage():
        download_reference = record.output_file_path
        if export_safe:
            temp_export_path = None
            try:
                with materialize(record.output_file_path) as stored_path:
                    df = pd.read_csv(stored_path, encoding="utf-8-sig")
                df_sanitized = sanitize_csv_formulas_for_export(df)
                with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as temp_export:
                    temp_export_path = Path(temp_export.name)
                    df_sanitized.to_csv(temp_export, index=False, encoding="utf-8-sig")
                key = f"exports/{current_user.id}/{cleaning_id}/{uuid.uuid4().hex}.csv"
                download_reference = store_cleaned_file(temp_export_path, key)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_404_NOT_FOUND:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Cleaned output file is missing from storage.",
                    ) from exc
                raise
            except Exception as exc:
                logger.error("Failed to prepare a sanitized CSV download.")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="A safe CSV download could not be prepared.",
                ) from exc
            finally:
                if temp_export_path:
                    remove_temp_file(temp_export_path)

        if object_size(download_reference) is None:
            raise HTTPException(status_code=404, detail="Cleaned output file is missing from storage.")
        return {
            "download_url": authorize_download(download_reference, safe_download_name),
            "filename": safe_download_name,
        }

    if export_safe:
        temp_export_path = None
        try:
            with materialize(record.output_file_path) as file_path:
                df = pd.read_csv(file_path, encoding="utf-8-sig")
            df_sanitized = sanitize_csv_formulas_for_export(df)
            with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as temp_export:
                temp_export_path = Path(temp_export.name)
                df_sanitized.to_csv(temp_export, index=False, encoding="utf-8-sig")
            return FileResponse(
                path=str(temp_export_path),
                media_type="text/csv",
                filename=safe_download_name,
                headers={"Content-Disposition": f'attachment; filename="{safe_download_name}"'},
                background=BackgroundTask(temp_export_path.unlink, missing_ok=True),
            )
        except HTTPException as exc:
            if temp_export_path and temp_export_path.exists():
                temp_export_path.unlink(missing_ok=True)
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Cleaned output file is missing from storage.",
                ) from exc
            raise
        except Exception:
            if temp_export_path and temp_export_path.exists():
                temp_export_path.unlink(missing_ok=True)
            logger.error("Failed to produce a sanitized CSV export.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create a safe CSV export.",
            )

    file_path, should_cleanup = materialize_for_response(record.output_file_path)
    return FileResponse(
        path=str(file_path),
        media_type="text/csv",
        filename=safe_download_name,
        headers={"Content-Disposition": f'attachment; filename="{safe_download_name}"'},
        background=BackgroundTask(remove_temp_file, file_path) if should_cleanup else None,
    )
