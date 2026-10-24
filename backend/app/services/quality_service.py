import re
import math
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np
import logging

from app.services.csv_service import map_dtype, make_json_serializable

logger = logging.getLogger("csv_analyzer.quality")

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
NON_NEGATIVE_NAME_REGEX = re.compile(
    r"(?:^|_)(age|quantity|count|income|salary|price|amount|revenue|cost|balance|id|total)(?:_|$)",
    re.IGNORECASE,
)
DATE_NAME_REGEX = re.compile(
    r"(?:^|_)(date|time|timestamp|created|updated|joined|join_date|birth|dob)(?:_|$)",
    re.IGNORECASE,
)


def analyze_dataset_quality(file_path: Path, file_size_bytes: int = 0) -> Dict[str, Any]:
    """
    Performs comprehensive data quality analysis on a CSV file.
    Reads the file without modifying it and returns structured metadata,
    overview stats, column metrics, detected issues, recommendations, and quality scores.
    """
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"Dataset file not found at path: {file_path}")

    # Read original CSV with UTF-8 BOM tolerance
    df = pd.read_csv(file_path, encoding="utf-8-sig")

    row_count = len(df)
    col_count = len(df.columns)
    total_cells = row_count * col_count

    # Handle empty dataset edge case safely
    if row_count == 0 or col_count == 0:
        return _generate_empty_dataset_result(row_count, col_count, file_size_bytes)

    # 1. Duplicate rows analysis (subsequent occurrences)
    duplicate_rows_series = df.duplicated()
    duplicate_rows_count = int(duplicate_rows_series.sum())
    duplicate_rows_pct = round((duplicate_rows_count / row_count) * 100.0, 2)

    # 2. Fully empty rows
    # A row is fully empty if all cells are null or whitespace-only
    is_empty_cell = df.map(lambda x: pd.isna(x) or (isinstance(x, str) and x.strip() == ""))
    fully_empty_rows_count = int(is_empty_cell.all(axis=1).sum())

    # 3. Analyze each column
    columns_quality: List[Dict[str, Any]] = []
    column_scores: Dict[str, float] = {}
    issues: List[Dict[str, Any]] = []
    recommendations: List[str] = []

    columns_by_type: Dict[str, int] = {}
    total_missing_cells = 0
    total_invalid_values = 0
    constant_columns_count = 0
    columns_with_missing_count = 0

    if duplicate_rows_count > 0:
        issues.append({
            "severity": "warning",
            "category": "duplicates",
            "column": None,
            "count": duplicate_rows_count,
            "description": f"Found {duplicate_rows_count} fully duplicated rows ({duplicate_rows_pct}% of dataset).",
            "rule_applied": "Exact row comparison across all columns (subsequent occurrences).",
        })
        recommendations.append(f"Remove {duplicate_rows_count} duplicate rows to ensure uniqueness.")

    for col in df.columns:
        col_str = str(col)
        series = df[col]
        inferred_type = map_dtype(series.dtype)
        columns_by_type[inferred_type] = columns_by_type.get(inferred_type, 0) + 1

        # Missing & whitespace values
        whitespace_mask = series.apply(lambda x: isinstance(x, str) and x != "" and x.strip() == "")
        whitespace_count = int(whitespace_mask.sum())

        missing_mask = series.isna() | series.apply(lambda x: isinstance(x, str) and x.strip() == "")
        missing_count = int(missing_mask.sum())
        non_missing_count = row_count - missing_count
        missing_pct = round((missing_count / row_count) * 100.0, 2)

        total_missing_cells += missing_count
        if missing_count > 0:
            columns_with_missing_count += 1

        if whitespace_count > 0:
            issues.append({
                "severity": "warning",
                "category": "whitespace_cells",
                "column": col_str,
                "count": whitespace_count,
                "description": f"Column '{col_str}' contains {whitespace_count} whitespace-only cells.",
                "rule_applied": "String matching regex ^\\s+$",
            })
            total_invalid_values += whitespace_count

        if missing_pct > 25.0:
            issues.append({
                "severity": "warning",
                "category": "missing_values",
                "column": col_str,
                "count": missing_count,
                "description": f"Column '{col_str}' has high missingness ({missing_pct}% missing).",
                "rule_applied": "Missing value ratio threshold (> 25%).",
            })
            recommendations.append(f"Address missing values in column '{col_str}' ({missing_count} rows missing).")

        # Non-null values for downstream checks
        clean_values = series[~missing_mask]

        # Duplicate values in column
        dup_val_count = int(clean_values.duplicated().sum())

        # Determine semantic type & validate specific patterns
        semantic_type = inferred_type
        invalid_count = 0
        type_mismatch_count = 0

        # A. Email validation
        if "email" in col_str.lower() or (len(clean_values) > 0 and clean_values.astype(str).str.contains("@").mean() > 0.5):
            semantic_type = "email"
            invalid_emails = clean_values.apply(lambda v: not bool(EMAIL_REGEX.match(str(v).strip())))
            invalid_email_count = int(invalid_emails.sum())
            if invalid_email_count > 0:
                invalid_count += invalid_email_count
                total_invalid_values += invalid_email_count
                issues.append({
                    "severity": "error",
                    "category": "invalid_format",
                    "column": col_str,
                    "count": invalid_email_count,
                    "description": f"Found {invalid_email_count} invalid email formats in column '{col_str}'.",
                    "rule_applied": "Standard RFC 5322 compliant email regex matching.",
                })
                recommendations.append(f"Correct {invalid_email_count} invalid email addresses in '{col_str}'.")

        # B. Date validation
        elif DATE_NAME_REGEX.search(col_str) or (len(clean_values) > 0 and clean_values.astype(str).str.contains(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}").mean() > 0.4):
            semantic_type = "date"
            parsed_dates = pd.to_datetime(clean_values, errors="coerce")
            invalid_dates_count = int(parsed_dates.isna().sum())
            if invalid_dates_count > 0:
                invalid_count += invalid_dates_count
                type_mismatch_count += invalid_dates_count
                total_invalid_values += invalid_dates_count
                issues.append({
                    "severity": "error",
                    "category": "invalid_date",
                    "column": col_str,
                    "count": invalid_dates_count,
                    "description": f"Found {invalid_dates_count} unparseable date values in column '{col_str}'.",
                    "rule_applied": "Standard ISO 8601 date parsing.",
                })
                recommendations.append(f"Standardize date formats in column '{col_str}' ({invalid_dates_count} unparseable dates).")

        # C. Boolean validation / detection
        elif len(clean_values) > 0 and clean_values.astype(str).str.strip().str.lower().isin(["true", "false", "yes", "no", "t", "f", "1", "0"]).all():
            semantic_type = "boolean"

        # D. Type mismatch check for string columns that are mostly numeric (mixed types)
        elif inferred_type == "string" and len(clean_values) > 0:
            numeric_test = pd.to_numeric(clean_values, errors="coerce")
            numeric_count = int(numeric_test.notna().sum())
            if 0.5 <= (numeric_count / len(clean_values)) < 1.0:
                non_num_count = len(clean_values) - numeric_count
                type_mismatch_count += non_num_count
                invalid_count += non_num_count
                total_invalid_values += non_num_count
                semantic_type = "mixed_numeric"
                issues.append({
                    "severity": "warning",
                    "category": "type_mismatch",
                    "column": col_str,
                    "count": non_num_count,
                    "description": f"Column '{col_str}' has predominantly numeric data but contains {non_num_count} non-numeric values.",
                    "rule_applied": "Mixed data type heuristic (>50% and <100% parseable as numeric).",
                })
                recommendations.append(f"Standardize column '{col_str}' to a uniform numeric or text type.")

        # E. Negative values in columns that should be non-negative
        if inferred_type in ("integer", "float"):
            if NON_NEGATIVE_NAME_REGEX.search(col_str):
                neg_count = int((clean_values.astype(float) < 0).sum())
                if neg_count > 0:
                    invalid_count += neg_count
                    total_invalid_values += neg_count
                    issues.append({
                        "severity": "error",
                        "category": "negative_values",
                        "column": col_str,
                        "count": neg_count,
                        "description": f"Found {neg_count} negative values in non-negative column '{col_str}'.",
                        "rule_applied": "Value < 0 in column with non-negative naming convention.",
                    })
                    recommendations.append(f"Inspect and correct negative values in column '{col_str}'.")

        # F. Constant column check
        distinct_count = int(clean_values.nunique())
        if distinct_count == 1 and non_missing_count > 1:
            constant_columns_count += 1
            issues.append({
                "severity": "info",
                "category": "constant_column",
                "column": col_str,
                "count": non_missing_count,
                "description": f"Column '{col_str}' is constant with only a single distinct non-null value.",
                "rule_applied": "Column uniqueness check (distinct_count == 1).",
            })
            recommendations.append(f"Consider dropping constant column '{col_str}' as it provides zero variance.")

        # G. High uniqueness check (potential primary key or identifier)
        if non_missing_count > 20 and distinct_count == non_missing_count and semantic_type not in ("email", "date"):
            issues.append({
                "severity": "info",
                "category": "high_uniqueness",
                "column": col_str,
                "count": distinct_count,
                "description": f"Column '{col_str}' has 100% distinct values across non-missing rows (potential unique identifier).",
                "rule_applied": "High uniqueness heuristic (distinct_count == non_missing_count and rows > 20).",
            })

        # H. Calculate column statistics
        col_stats: Dict[str, Any] = {"distinct_count": distinct_count}

        if inferred_type in ("integer", "float") and len(clean_values) > 0:
            num_clean = pd.to_numeric(clean_values, errors="coerce").dropna()
            if len(num_clean) > 0:
                col_stats["min"] = make_json_serializable(num_clean.min())
                col_stats["max"] = make_json_serializable(num_clean.max())
                col_stats["mean"] = make_json_serializable(round(float(num_clean.mean()), 2))
                col_stats["median"] = make_json_serializable(float(num_clean.median()))
                col_stats["std"] = make_json_serializable(round(float(num_clean.std()), 2) if len(num_clean) > 1 else 0.0)
                col_stats["q25"] = make_json_serializable(float(num_clean.quantile(0.25)))
                col_stats["q75"] = make_json_serializable(float(num_clean.quantile(0.75)))
        else:
            # Categorical / text statistics: distinct count, top 5 frequent values, and most frequent value percentage
            if len(clean_values) > 0:
                top_counts = clean_values.value_counts().head(5)
                top_items = []
                for val, cnt in top_counts.items():
                    top_items.append({
                        "value": str(val),
                        "count": int(cnt),
                        "percentage": round((int(cnt) / len(clean_values)) * 100.0, 2),
                    })
                col_stats["top_frequent_values"] = top_items
                if top_items:
                    col_stats["most_frequent_percentage"] = top_items[0]["percentage"]
            else:
                col_stats["top_frequent_values"] = []
                col_stats["most_frequent_percentage"] = None

        # Calculate individual column score (0 - 100)
        col_invalid_pct = round((invalid_count / max(1, non_missing_count)) * 100.0, 2)
        col_score = max(0.0, min(100.0, round(100.0 - (missing_pct * 0.5) - (col_invalid_pct * 0.5), 2)))
        column_scores[col_str] = col_score

        columns_quality.append({
            "name": col_str,
            "inferred_type": inferred_type,
            "semantic_type": semantic_type,
            "missing_count": missing_count,
            "missing_percentage": missing_pct,
            "non_missing_count": non_missing_count,
            "duplicate_values_count": dup_val_count,
            "type_mismatch_count": type_mismatch_count,
            "invalid_values_count": invalid_count,
            "quality_score": col_score,
            "statistics": col_stats,
        })

    # 4. Overall Data Quality Score Formula
    # Explicit composite score based on:
    # - Missingness penalty (max 35 points)
    # - Duplication penalty (max 25 points)
    # - Validity penalty (max 30 points)
    # - Consistency penalty (max 10 points)
    missing_ratio = total_missing_cells / total_cells if total_cells > 0 else 0.0
    missing_penalty = round(min(35.0, missing_ratio * 35.0), 2)

    duplicate_ratio = duplicate_rows_count / row_count if row_count > 0 else 0.0
    duplicate_penalty = round(min(25.0, duplicate_ratio * 25.0), 2)

    invalid_ratio = total_invalid_values / total_cells if total_cells > 0 else 0.0
    validity_penalty = round(min(30.0, invalid_ratio * 100.0), 2)

    consistency_penalty = round(min(10.0, constant_columns_count * 2.5), 2)

    total_penalty = missing_penalty + duplicate_penalty + validity_penalty + consistency_penalty
    overall_score = round(max(0.0, min(100.0, 100.0 - total_penalty)), 2)

    score_breakdown = {
        "missing_penalty": missing_penalty,
        "duplicate_penalty": duplicate_penalty,
        "validity_penalty": validity_penalty,
        "consistency_penalty": consistency_penalty,
        "formula": "overall_score = 100 - (missing_penalty + duplicate_penalty + validity_penalty + consistency_penalty)",
        "explanation": "Calculates composite dataset health based on cell completeness (35%), row uniqueness (25%), format & domain validity (30%), and variance consistency (10%).",
    }

    summary_stats = {
        "total_rows": row_count,
        "total_columns": col_count,
        "total_cells": total_cells,
        "file_size_bytes": file_size_bytes,
        "fully_empty_rows": fully_empty_rows_count,
        "duplicate_rows": duplicate_rows_count,
        "duplicate_rows_percentage": duplicate_rows_pct,
        "columns_with_missing": columns_with_missing_count,
        "total_missing_cells": total_missing_cells,
        "total_invalid_values": total_invalid_values,
        "columns_by_type": columns_by_type,
        "columns_quality": columns_quality,
        "score_breakdown": score_breakdown,
    }

    return {
        "overall_score": overall_score,
        "summary_stats": summary_stats,
        "column_scores": column_scores,
        "issues": issues,
        "recommendations": list(dict.fromkeys(recommendations)),  # Deduplicate recommendations
    }


def _generate_empty_dataset_result(row_count: int, col_count: int, file_size_bytes: int) -> Dict[str, Any]:
    """Generate safe, structured result for empty datasets."""
    return {
        "overall_score": 0.0,
        "summary_stats": {
            "total_rows": row_count,
            "total_columns": col_count,
            "total_cells": 0,
            "file_size_bytes": file_size_bytes,
            "fully_empty_rows": 0,
            "duplicate_rows": 0,
            "duplicate_rows_percentage": 0.0,
            "columns_with_missing": 0,
            "total_missing_cells": 0,
            "total_invalid_values": 0,
            "columns_by_type": {},
            "columns_quality": [],
            "score_breakdown": {
                "missing_penalty": 100.0,
                "duplicate_penalty": 0.0,
                "validity_penalty": 0.0,
                "consistency_penalty": 0.0,
                "formula": "overall_score = 0.0 (empty dataset)",
                "explanation": "Dataset contains zero rows or cells.",
            },
        },
        "column_scores": {},
        "issues": [{
            "severity": "error",
            "category": "empty_dataset",
            "column": None,
            "count": 0,
            "description": "Dataset has 0 rows.",
            "rule_applied": "Row count check",
        }],
        "recommendations": ["Upload a non-empty CSV dataset with data rows."],
    }
