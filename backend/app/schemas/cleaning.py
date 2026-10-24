from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime


# Supported operations in deterministic order:
# 1. whitespace_cleaning
# 2. text_normalization
# 3. missing_values
# 4. type_conversion
# 5. duplicate_removal
# 6. outlier_handling

class WhitespaceCleaningConfig(BaseModel):
    enabled: bool = False
    columns: Optional[List[str]] = Field(None, description="Columns to clean. If None or empty, applies to all text/string columns.")
    trim_whitespace: bool = True
    collapse_internal_whitespace: bool = False

    model_config = ConfigDict(extra="forbid")


class TextNormalizationConfig(BaseModel):
    enabled: bool = False
    case: Optional[Literal["lowercase", "uppercase"]] = None
    columns: Optional[List[str]] = None
    normalize_spaces: bool = False
    standardize_null_markers: bool = False
    null_markers: Optional[List[str]] = Field(default_factory=lambda: ["N/A", "NULL", "null", "none", "None", "n/a", "NA", "-", "NaN"])

    model_config = ConfigDict(extra="forbid")


class MissingValuesConfig(BaseModel):
    enabled: bool = False
    strategy: Literal[
        "keep",
        "drop_rows",
        "drop_columns",
        "fill_constant",
        "fill_mean",
        "fill_median",
        "fill_mode"
    ] = "keep"
    columns: Optional[List[str]] = Field(None, description="Specific columns to apply strategy on. If empty/None and strategy is drop_rows, drops rows with missing in any column.")
    fill_value: Optional[Any] = Field(None, description="Constant value to fill with when strategy is fill_constant.")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_missing_config(self):
        if self.enabled:
            if self.strategy == "fill_constant" and self.fill_value is None:
                raise ValueError("fill_value must be provided when strategy is 'fill_constant'")
            if self.strategy in ("drop_columns", "fill_mean", "fill_median", "fill_mode") and not self.columns:
                raise ValueError(f"columns list must be provided and non-empty for strategy '{self.strategy}'")
        return self


class TypeConversionItem(BaseModel):
    column: str
    target_type: Literal["string", "integer", "float", "datetime", "boolean"]
    on_error: Literal["reject", "coerce"] = "reject"
    date_format: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class DuplicateRemovalConfig(BaseModel):
    enabled: bool = False
    subset_columns: Optional[List[str]] = Field(None, description="Subset of columns to evaluate for duplicates. If None or empty, evaluates all columns.")
    keep: Literal["first", "last"] = "first"

    model_config = ConfigDict(extra="forbid")


class OutlierHandlingConfig(BaseModel):
    enabled: bool = False
    columns: List[str] = Field(default_factory=list, description="Numerical columns to evaluate for outliers.")
    method: Literal["iqr"] = "iqr"
    iqr_multiplier: float = Field(1.5, ge=1.0, le=5.0)
    treatment: Literal["clip", "set_null"] = "clip"

    model_config = ConfigDict(extra="forbid")


class CleaningConfig(BaseModel):
    whitespace_cleaning: Optional[WhitespaceCleaningConfig] = None
    text_normalization: Optional[TextNormalizationConfig] = None
    missing_values: Optional[MissingValuesConfig] = None
    type_conversions: Optional[List[TypeConversionItem]] = None
    duplicate_removal: Optional[DuplicateRemovalConfig] = None
    outlier_handling: Optional[OutlierHandlingConfig] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_at_least_one_operation(self):
        has_op = any([
            self.whitespace_cleaning and self.whitespace_cleaning.enabled,
            self.text_normalization and self.text_normalization.enabled,
            self.missing_values and self.missing_values.enabled,
            self.type_conversions and len(self.type_conversions) > 0,
            self.duplicate_removal and self.duplicate_removal.enabled,
            self.outlier_handling and self.outlier_handling.enabled,
        ])
        if not has_op:
            raise ValueError("At least one cleaning operation must be configured and enabled.")
        return self


# -------------------------------------------------------------------------
# Response Schemas
# -------------------------------------------------------------------------

class OperationMetric(BaseModel):
    operation: str
    description: str
    changes_count: int
    details: Optional[Dict[str, Any]] = None


class MetricsComparison(BaseModel):
    before: int
    after: int
    difference: int


class CleaningSummary(BaseModel):
    rows: MetricsComparison
    columns: MetricsComparison
    missing_cells: MetricsComparison
    duplicate_rows: MetricsComparison
    operations_applied: List[OperationMetric]
    warnings: List[str]
    skipped_operations: List[str]
    configuration_used: Dict[str, Any]


class CleaningPreviewRequest(BaseModel):
    config: CleaningConfig
    preview_limit: int = Field(10, ge=1, le=50, description="Max rows to return in preview (default 10, max 50).")

    model_config = ConfigDict(extra="forbid")


class CleaningApplyRequest(BaseModel):
    config: CleaningConfig

    model_config = ConfigDict(extra="forbid")


class CleaningPreviewResponse(BaseModel):
    dataset_id: int
    summary: CleaningSummary
    original_preview: List[Dict[str, Any]]
    cleaned_preview: List[Dict[str, Any]]
    columns: List[str]


class CleaningRecordResponse(BaseModel):
    id: int
    dataset_id: int
    user_id: int
    status: str
    output_filename: Optional[str] = None
    output_file_size_bytes: Optional[int] = None
    output_row_count: Optional[int] = None
    output_column_count: Optional[int] = None
    cleaning_summary: Dict[str, Any]
    cleaning_config: Dict[str, Any]
    error_message: Optional[str] = None
    created_at: datetime
    download_available: bool = True

    model_config = ConfigDict(from_attributes=True)


class CleaningListResponse(BaseModel):
    total: int
    items: List[CleaningRecordResponse]
