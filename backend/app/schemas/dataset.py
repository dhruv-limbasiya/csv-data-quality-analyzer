from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any, Dict
from datetime import datetime


class ColumnMetadata(BaseModel):
    name: str
    original_name: Optional[str] = None
    data_type: str
    sample_values: List[Any] = []
    has_duplicates: bool = False

    model_config = ConfigDict(from_attributes=True)


class DatasetResponse(BaseModel):
    id: int
    user_id: int
    original_filename: str
    file_size_bytes: int
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    columns_metadata: Optional[List[Dict[str, Any]]] = None
    is_cleaned_version: bool = False
    original_dataset_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetDetailResponse(DatasetResponse):
    preview_rows: List[Dict[str, Any]] = []


class DatasetListResponse(BaseModel):
    total: int
    items: List[DatasetResponse]

    model_config = ConfigDict(from_attributes=True)


class UploadAuthorizationRequest(BaseModel):
    filename: str
    size_bytes: int
