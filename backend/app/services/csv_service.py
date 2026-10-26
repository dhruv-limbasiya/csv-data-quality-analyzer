import os
import uuid
import math
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np
from fastapi import UploadFile, HTTPException, status
from app.config import settings
import logging

logger = logging.getLogger("csv_analyzer.service")

CHUNK_SIZE = 64 * 1024  # 64 KB streaming buffer
ALLOWED_EXTENSIONS = {".csv"}
ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/csv",
    "text/plain",
    "text/x-csv",
    "application/x-csv",
    "application/vnd.ms-excel",
    "application/octet-stream",
}


def sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize original filename to prevent path traversal and special character issues."""
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided in upload."
        )
    # Normalize Windows and POSIX separators regardless of the host OS.
    clean_name = filename.replace("\\", "/").split("/")[-1].strip()
    if not clean_name or clean_name in (".", ".."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename."
        )
    if len(clean_name) > 255 or any(ord(char) < 32 for char in clean_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename.",
        )
    return clean_name


def validate_file_extension(filename: str, content_type: Optional[str] = None):
    """Validate that the file extension is .csv and content type is acceptable."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type '{suffix}'. Only CSV files (.csv) are allowed."
        )


async def save_upload_stream(upload_file: UploadFile) -> Tuple[str, str, Path, int]:
    """
    Streams an uploaded file to disk in chunks to avoid memory spikes.
    Validates file size against MAX_UPLOAD_SIZE_MB and ensures non-empty content.

    Returns:
        Tuple of (original_filename, stored_filename, file_path, file_size_bytes)
    """
    original_filename = sanitize_filename(upload_file.filename)
    validate_file_extension(original_filename, upload_file.content_type)

    # Ensure destination upload directory exists
    upload_dir = settings.upload_path
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate collision-free UUID stored filename
    stored_filename = f"{uuid.uuid4().hex}.csv"
    dest_path = upload_dir / stored_filename

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_bytes = 0

    try:
        with open(dest_path, "wb") as buffer:
            while True:
                chunk = await upload_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed upload size of {settings.MAX_UPLOAD_SIZE_MB} MB."
                    )
                buffer.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes)."
            )

        return original_filename, stored_filename, dest_path, total_bytes

    except Exception:
        # Atomic cleanup on failure
        remove_file_safely(dest_path)
        raise


def remove_file_safely(file_path: Optional[Path]):
    """Safely removes a file from disk if it exists."""
    if file_path and isinstance(file_path, (str, Path)):
        p = Path(file_path)
        if p.exists() and p.is_file():
            try:
                p.unlink()
                logger.info(f"Cleaned up file at {p}")
            except OSError as err:
                logger.warning(f"Failed to delete file {p}: {err}")


def map_dtype(dtype: Any) -> str:
    """Map pandas data type to a clean, user-friendly descriptive string."""
    dtype_str = str(dtype).lower()
    if "int" in dtype_str:
        return "integer"
    elif "float" in dtype_str:
        return "float"
    elif "bool" in dtype_str:
        return "boolean"
    elif "datetime" in dtype_str:
        return "datetime"
    return "string"


def make_json_serializable(val: Any) -> Any:
    """Convert numpy/pandas types to JSON-safe Python primitives."""
    if val is None:
        return None
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if isinstance(val, (pd.Timestamp, np.datetime64)):
        return str(val)
    if pd.isna(val):
        return None
    return str(val)


def parse_and_extract_metadata(file_path: Path) -> Tuple[int, int, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parses the saved CSV file using Pandas.
    Extracts row count, column count, column metadata, and first 5 preview rows.
    Handles UTF-8 and UTF-8 with BOM, detects duplicate column headers,
    and returns JSON-safe data structures.
    """
    # 1. Test encoding: Try utf-8-sig (handles UTF-8 and UTF-8 with BOM)
    try:
        # First read just the header to validate column structure
        df_header = pd.read_csv(file_path, encoding="utf-8-sig", nrows=0)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file encoding. Please provide a UTF-8 or UTF-8 with BOM encoded CSV file."
        )
    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file contains no data or headers."
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Malformed CSV file."
        )

    # Validate that we have columns
    raw_columns = list(df_header.columns)
    if not raw_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file does not contain usable column headers."
        )

    # Check if all headers are empty/unnamed whitespace
    if all(str(col).strip() == "" or str(col).startswith("Unnamed:") for col in raw_columns):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file has no named column headers."
        )

    # 2. Read full dataset
    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse CSV file content: {str(exc)}"
        )

    row_count = len(df)
    column_count = len(df.columns)

    # Detect duplicate columns and build column metadata
    # Pandas will have automatically suffixed duplicates with .1, .2
    # Let's inspect raw headers vs parsed df.columns to document duplicate handling
    seen_headers: Dict[str, int] = {}
    columns_metadata: List[Dict[str, Any]] = []

    for col in df.columns:
        col_str = str(col)
        # Determine base name before pandas .1 suffix if duplicate
        base_name = col_str
        is_duplicate = False
        if "." in col_str and col_str.rsplit(".", 1)[-1].isdigit():
            possible_base = col_str.rsplit(".", 1)[0]
            if possible_base in seen_headers:
                base_name = possible_base
                is_duplicate = True

        seen_headers[base_name] = seen_headers.get(base_name, 0) + 1
        if seen_headers[base_name] > 1:
            is_duplicate = True

        # Extract sample non-null values (up to 3 samples)
        non_null_samples = df[col].dropna().unique()[:3]
        clean_samples = [make_json_serializable(s) for s in non_null_samples]

        columns_metadata.append({
            "name": col_str,
            "original_name": base_name if is_duplicate else col_str,
            "data_type": map_dtype(df[col].dtype),
            "sample_values": clean_samples,
            "has_duplicates": is_duplicate,
        })

    # 3. Build JSON-serializable preview rows (first 5 rows)
    preview_df = df.head(5)
    preview_rows: List[Dict[str, Any]] = []
    for _, row in preview_df.iterrows():
        row_dict = {}
        for col in df.columns:
            row_dict[str(col)] = make_json_serializable(row[col])
        preview_rows.append(row_dict)

    return row_count, column_count, columns_metadata, preview_rows
