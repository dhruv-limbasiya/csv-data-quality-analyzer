from pydantic import BaseModel, ConfigDict, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class ScoreBreakdown(BaseModel):
    missing_penalty: float
    duplicate_penalty: float
    validity_penalty: float
    consistency_penalty: float
    formula: str
    explanation: str


class QualityIssue(BaseModel):
    severity: str = Field(..., description="Issue severity: info, warning, error")
    category: str = Field(..., description="Category: missing_values, duplicates, invalid_format, negative_values, constant_column")
    column: Optional[str] = None
    count: Optional[int] = None
    description: str
    rule_applied: str


class ColumnStatistics(BaseModel):
    distinct_count: int
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    q25: Optional[float] = None
    q75: Optional[float] = None
    top_frequent_values: Optional[List[Dict[str, Any]]] = None
    most_frequent_percentage: Optional[float] = None


class ColumnQuality(BaseModel):
    name: str
    inferred_type: str
    semantic_type: str
    missing_count: int
    missing_percentage: float
    non_missing_count: int
    duplicate_values_count: int
    type_mismatch_count: int
    invalid_values_count: int
    quality_score: float
    statistics: Optional[Dict[str, Any]] = None


class AnalysisSummaryStats(BaseModel):
    total_rows: int
    total_columns: int
    total_cells: int
    file_size_bytes: int
    fully_empty_rows: int
    duplicate_rows: int
    duplicate_rows_percentage: float
    columns_with_missing: int
    total_missing_cells: int
    total_invalid_values: int
    columns_by_type: Dict[str, int]
    score_breakdown: Dict[str, Any]


class AnalysisResponse(BaseModel):
    id: int
    dataset_id: int
    user_id: int
    overall_score: float
    summary_stats: Dict[str, Any]
    column_scores: Dict[str, float]
    issues: List[Dict[str, Any]]
    recommendations: Optional[List[str]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisListResponse(BaseModel):
    total: int
    items: List[AnalysisResponse]

    model_config = ConfigDict(from_attributes=True)
