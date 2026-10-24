import math
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

from app.schemas.cleaning import CleaningConfig
from app.services.csv_service import make_json_serializable

# Accepted boolean string mappings
BOOL_TRUE_VALUES = {"true", "yes", "t", "1", "y"}
BOOL_FALSE_VALUES = {"false", "no", "f", "0", "n"}


def count_missing_cells(df: pd.DataFrame) -> int:
    """
    Counts missing cells consistently with analysis engine:
    NaN, None, and empty string/whitespace-only string cells.
    Does NOT treat string '0' or number 0 as missing.
    """
    total = 0
    for col in df.columns:
        series = df[col]
        # isna covers NaN, None
        isna_mask = series.isna()
        # string whitespace/empty mask
        ws_mask = series.apply(lambda x: isinstance(x, str) and x.strip() == "")
        total += int((isna_mask | ws_mask).sum())
    return total


def count_duplicate_rows(df: pd.DataFrame, subset: Optional[List[str]] = None) -> int:
    """Calculates number of duplicated rows (subsequent occurrences)."""
    if len(df) == 0:
        return 0
    if subset:
        return int(df.duplicated(subset=subset).sum())
    return int(df.duplicated().sum())


class CleaningExecutionError(Exception):
    """Raised when cleaning fails due to invalid parameters or unsafe outcomes."""
    pass


def apply_cleaning_pipeline(
    df_original: pd.DataFrame,
    config: CleaningConfig,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Applies cleaning operations to a copy of df_original in deterministic order:
    1. Whitespace cleaning
    2. Text normalization
    3. Missing-value handling
    4. Data-type conversion
    5. Duplicate-row removal
    6. Outlier handling

    Returns:
        (df_cleaned, cleaning_summary_dict)
    """
    df = df_original.copy()
    existing_cols = list(df.columns)
    existing_cols_set = set(existing_cols)

    # Initial metrics before cleaning
    before_rows = len(df)
    before_cols = len(df.columns)
    before_missing = count_missing_cells(df)
    before_dups = count_duplicate_rows(df)

    operations_applied: List[Dict[str, Any]] = []
    warnings: List[str] = []
    skipped_operations: List[str] = []

    # -------------------------------------------------------------------------
    # 1. Whitespace Cleaning
    # -------------------------------------------------------------------------
    if config.whitespace_cleaning and config.whitespace_cleaning.enabled:
        ws_conf = config.whitespace_cleaning
        target_cols = ws_conf.columns if ws_conf.columns else [
            c for c in df.columns if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])
        ]
        
        # Validate columns
        valid_cols = [c for c in target_cols if c in existing_cols_set]
        invalid_cols = [c for c in target_cols if c not in existing_cols_set]
        for ic in invalid_cols:
            warnings.append(f"Whitespace cleaning skipped column '{ic}' (column does not exist).")

        changed_cells = 0
        for col in valid_cols:
            series = df[col]
            def clean_ws(val):
                nonlocal changed_cells
                if isinstance(val, str):
                    new_val = val
                    if ws_conf.trim_whitespace:
                        new_val = new_val.strip()
                    if ws_conf.collapse_internal_whitespace:
                        new_val = re.sub(r"\s+", " ", new_val)
                    if new_val != val:
                        changed_cells += 1
                    return new_val
                return val

            df[col] = series.apply(clean_ws)

        operations_applied.append({
            "operation": "whitespace_cleaning",
            "description": f"Cleaned whitespace across {len(valid_cols)} columns (trim={ws_conf.trim_whitespace}, collapse={ws_conf.collapse_internal_whitespace}).",
            "changes_count": changed_cells,
            "details": {"columns": valid_cols, "trim": ws_conf.trim_whitespace, "collapse": ws_conf.collapse_internal_whitespace}
        })

    # -------------------------------------------------------------------------
    # 2. Text Normalization
    # -------------------------------------------------------------------------
    if config.text_normalization and config.text_normalization.enabled:
        tn_conf = config.text_normalization
        target_cols = tn_conf.columns if tn_conf.columns else [
            c for c in df.columns if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])
        ]
        valid_cols = [c for c in target_cols if c in existing_cols_set]
        invalid_cols = [c for c in target_cols if c not in existing_cols_set]
        for ic in invalid_cols:
            warnings.append(f"Text normalization skipped column '{ic}' (column does not exist).")

        changed_cells = 0
        null_markers_set = set(tn_conf.null_markers or []) if tn_conf.standardize_null_markers else set()

        for col in valid_cols:
            def norm_text(val):
                nonlocal changed_cells
                if isinstance(val, str):
                    new_val = val
                    # Check null markers
                    if tn_conf.standardize_null_markers and new_val.strip() in null_markers_set:
                        changed_cells += 1
                        return np.nan
                    if tn_conf.normalize_spaces:
                        new_val = re.sub(r"\s+", " ", new_val)
                    if tn_conf.case == "lowercase":
                        new_val = new_val.lower()
                    elif tn_conf.case == "uppercase":
                        new_val = new_val.upper()
                    if new_val != val:
                        changed_cells += 1
                    return new_val
                return val

            df[col] = df[col].apply(norm_text)

        operations_applied.append({
            "operation": "text_normalization",
            "description": f"Normalized text in {len(valid_cols)} columns (case={tn_conf.case}, null_markers={tn_conf.standardize_null_markers}).",
            "changes_count": changed_cells,
            "details": {"columns": valid_cols, "case": tn_conf.case, "null_markers_standardized": tn_conf.standardize_null_markers}
        })

    # -------------------------------------------------------------------------
    # 3. Missing-Value Handling
    # -------------------------------------------------------------------------
    if config.missing_values and config.missing_values.enabled:
        mv_conf = config.missing_values
        strategy = mv_conf.strategy

        if strategy == "keep":
            skipped_operations.append("Missing-value handling configured as 'keep' (no modifications).")
        elif strategy == "drop_rows":
            rows_before_drop = len(df)
            target_cols = mv_conf.columns if mv_conf.columns else list(df.columns)
            valid_cols = [c for c in target_cols if c in df.columns]
            
            # Treat empty/whitespace-only strings as missing for drop_rows
            missing_row_mask = pd.Series(False, index=df.index)
            for col in valid_cols:
                s = df[col]
                m = s.isna() | s.apply(lambda x: isinstance(x, str) and x.strip() == "")
                missing_row_mask = missing_row_mask | m

            dropped_rows = int(missing_row_mask.sum())
            if dropped_rows == len(df) and len(df) > 0:
                raise CleaningExecutionError(
                    "Safety check failed: Dropping rows with missing values would delete 100% of the dataset."
                )
            df = df[~missing_row_mask].reset_index(drop=True)
            operations_applied.append({
                "operation": "missing_values_drop_rows",
                "description": f"Dropped {dropped_rows} rows containing missing values.",
                "changes_count": dropped_rows,
                "details": {"rows_removed": dropped_rows, "columns_evaluated": valid_cols}
            })

        elif strategy == "drop_columns":
            target_cols = mv_conf.columns or []
            valid_cols = [c for c in target_cols if c in df.columns]
            invalid_cols = [c for c in target_cols if c not in df.columns]
            for ic in invalid_cols:
                warnings.append(f"Cannot drop missing column '{ic}': column does not exist.")

            if len(valid_cols) == len(df.columns):
                raise CleaningExecutionError(
                    "Safety check failed: Cannot drop all columns in dataset."
                )

            df = df.drop(columns=valid_cols)
            operations_applied.append({
                "operation": "missing_values_drop_columns",
                "description": f"Dropped {len(valid_cols)} columns: {', '.join(valid_cols)}.",
                "changes_count": len(valid_cols),
                "details": {"dropped_columns": valid_cols}
            })

        elif strategy == "fill_constant":
            target_cols = mv_conf.columns if mv_conf.columns else list(df.columns)
            valid_cols = [c for c in target_cols if c in df.columns]
            fill_val = mv_conf.fill_value
            filled_cells = 0

            for col in valid_cols:
                s = df[col]
                mask = s.isna() | s.apply(lambda x: isinstance(x, str) and x.strip() == "")
                cnt = int(mask.sum())
                if cnt > 0:
                    df.loc[mask, col] = fill_val
                    filled_cells += cnt

            operations_applied.append({
                "operation": "missing_values_fill_constant",
                "description": f"Filled {filled_cells} missing cells across {len(valid_cols)} columns with constant '{fill_val}'.",
                "changes_count": filled_cells,
                "details": {"fill_value": fill_val, "columns": valid_cols}
            })

        elif strategy in ("fill_mean", "fill_median"):
            target_cols = mv_conf.columns or []
            filled_cells = 0
            for col in target_cols:
                if col not in df.columns:
                    warnings.append(f"Cannot calculate {strategy} for column '{col}': column not found.")
                    continue

                # Ensure numerical
                numeric_series = pd.to_numeric(df[col], errors="coerce")
                valid_numeric = numeric_series.dropna()

                if len(valid_numeric) == 0:
                    warnings.append(f"Column '{col}' has no valid numerical values; skipped {strategy}.")
                    continue

                calc_val = round(float(valid_numeric.mean()), 4) if strategy == "fill_mean" else float(valid_numeric.median())
                mask = df[col].isna() | df[col].apply(lambda x: isinstance(x, str) and x.strip() == "")
                cnt = int(mask.sum())
                if cnt > 0:
                    df.loc[mask, col] = calc_val
                    filled_cells += cnt

            operations_applied.append({
                "operation": f"missing_values_{strategy}",
                "description": f"Imputed {filled_cells} missing values using column {strategy.replace('fill_', '')}.",
                "changes_count": filled_cells,
                "details": {"columns": target_cols, "strategy": strategy}
            })

        elif strategy == "fill_mode":
            target_cols = mv_conf.columns or []
            filled_cells = 0
            for col in target_cols:
                if col not in df.columns:
                    warnings.append(f"Cannot calculate mode for column '{col}': column not found.")
                    continue

                s = df[col]
                clean_vals = s[~s.isna() & ~s.apply(lambda x: isinstance(x, str) and x.strip() == "")]
                if len(clean_vals) == 0:
                    warnings.append(f"Column '{col}' is completely empty; cannot compute mode.")
                    continue

                mode_vals = clean_vals.mode()
                if len(mode_vals) == 0:
                    warnings.append(f"No unique mode found for column '{col}'.")
                    continue
                mode_val = mode_vals.iloc[0]

                mask = s.isna() | s.apply(lambda x: isinstance(x, str) and x.strip() == "")
                cnt = int(mask.sum())
                if cnt > 0:
                    df.loc[mask, col] = mode_val
                    filled_cells += cnt

            operations_applied.append({
                "operation": "missing_values_fill_mode",
                "description": f"Imputed {filled_cells} missing values using column mode.",
                "changes_count": filled_cells,
                "details": {"columns": target_cols}
            })

    # -------------------------------------------------------------------------
    # 4. Data-Type Conversion
    # -------------------------------------------------------------------------
    if config.type_conversions and len(config.type_conversions) > 0:
        converted_items_count = 0
        for item in config.type_conversions:
            col = item.column
            target_type = item.target_type
            on_error = item.on_error

            if col not in df.columns:
                warnings.append(f"Type conversion skipped for column '{col}': column does not exist.")
                continue

            series = df[col]
            success_count = 0
            invalid_count = 0

            if target_type == "string":
                df[col] = series.apply(lambda x: "" if pd.isna(x) else str(x))
                success_count = len(series)

            elif target_type in ("integer", "float"):
                # Numeric conversion without silent truncation for integers
                # If target is integer and values have fractional part like 42.7, reject if on_error == 'reject'
                converted_series = []
                for val in series:
                    if pd.isna(val) or (isinstance(val, str) and val.strip() == ""):
                        converted_series.append(np.nan)
                        continue
                    try:
                        f_val = float(val)
                        if target_type == "integer":
                            if not math.isnan(f_val) and not math.isinf(f_val):
                                if f_val.is_integer():
                                    converted_series.append(int(f_val))
                                    success_count += 1
                                else:
                                    if on_error == "reject":
                                        raise CleaningExecutionError(
                                            f"Cannot convert column '{col}' to integer without silent decimal truncation (value: {val})."
                                        )
                                    converted_series.append(np.nan)
                                    invalid_count += 1
                            else:
                                if on_error == "reject":
                                    raise CleaningExecutionError(f"Non-finite float value '{val}' in integer conversion for column '{col}'.")
                                converted_series.append(np.nan)
                                invalid_count += 1
                        else:
                            converted_series.append(f_val)
                            success_count += 1
                    except (ValueError, TypeError):
                        if on_error == "reject":
                            raise CleaningExecutionError(
                                f"Cannot convert value '{val}' in column '{col}' to {target_type} (on_error='reject')."
                            )
                        converted_series.append(np.nan)
                        invalid_count += 1

                df[col] = converted_series

            elif target_type == "datetime":
                converted_dates = []
                for val in series:
                    if pd.isna(val) or (isinstance(val, str) and val.strip() == ""):
                        converted_dates.append(pd.NaT)
                        continue
                    try:
                        if item.date_format:
                            dt = pd.to_datetime(val, format=item.date_format, errors="raise")
                        else:
                            dt = pd.to_datetime(val, errors="raise")
                        converted_dates.append(dt)
                        success_count += 1
                    except Exception:
                        if on_error == "reject":
                            raise CleaningExecutionError(
                                f"Cannot parse date '{val}' in column '{col}' (on_error='reject')."
                            )
                        converted_dates.append(pd.NaT)
                        invalid_count += 1
                df[col] = converted_dates

            elif target_type == "boolean":
                converted_bools = []
                for val in series:
                    if pd.isna(val) or (isinstance(val, str) and val.strip() == ""):
                        converted_bools.append(np.nan)
                        continue
                    s_str = str(val).strip().lower()
                    if s_str in BOOL_TRUE_VALUES:
                        converted_bools.append(True)
                        success_count += 1
                    elif s_str in BOOL_FALSE_VALUES:
                        converted_bools.append(False)
                        success_count += 1
                    else:
                        if on_error == "reject":
                            raise CleaningExecutionError(
                                f"Cannot convert value '{val}' in column '{col}' to boolean. Accepted: {sorted(list(BOOL_TRUE_VALUES | BOOL_FALSE_VALUES))}."
                            )
                        converted_bools.append(np.nan)
                        invalid_count += 1
                df[col] = converted_bools

            converted_items_count += 1
            operations_applied.append({
                "operation": f"type_conversion_{target_type}",
                "description": f"Converted column '{col}' to {target_type} ({success_count} success, {invalid_count} coerced/invalid).",
                "changes_count": success_count,
                "details": {
                    "column": col,
                    "target_type": target_type,
                    "on_error": on_error,
                    "invalid_values_coerced": invalid_count,
                }
            })

    # -------------------------------------------------------------------------
    # 5. Duplicate-Row Removal
    # -------------------------------------------------------------------------
    if config.duplicate_removal and config.duplicate_removal.enabled:
        dup_conf = config.duplicate_removal
        subset = dup_conf.subset_columns
        if subset:
            invalid_sub = [c for c in subset if c not in df.columns]
            if invalid_sub:
                raise CleaningExecutionError(
                    f"Duplicate removal subset contains invalid column(s): {', '.join(invalid_sub)}"
                )
            if len(subset) == 0:
                raise CleaningExecutionError("Duplicate removal subset cannot be empty.")

        rows_before_dedup = len(df)
        df = df.drop_duplicates(subset=subset, keep=dup_conf.keep).reset_index(drop=True)
        removed_rows = rows_before_dedup - len(df)

        operations_applied.append({
            "operation": "duplicate_removal",
            "description": f"Removed {removed_rows} duplicate rows (keep='{dup_conf.keep}', subset={subset or 'all_columns'}).",
            "changes_count": removed_rows,
            "details": {
                "rows_removed": removed_rows,
                "keep": dup_conf.keep,
                "subset_columns": subset or list(df.columns),
            }
        })

    # -------------------------------------------------------------------------
    # 6. Outlier Handling (IQR-based clipping or nulling)
    # -------------------------------------------------------------------------
    if config.outlier_handling and config.outlier_handling.enabled:
        out_conf = config.outlier_handling
        mult = out_conf.iqr_multiplier
        treatment = out_conf.treatment
        affected_values = 0

        for col in out_conf.columns:
            if col not in df.columns:
                warnings.append(f"Outlier handling skipped column '{col}': column not found.")
                continue

            # Ensure numeric
            s_num = pd.to_numeric(df[col], errors="coerce")
            valid_vals = s_num.dropna()
            if len(valid_vals) < 4:
                warnings.append(f"Outlier handling skipped for '{col}': insufficient data points ({len(valid_vals)} < 4).")
                continue

            q25 = float(valid_vals.quantile(0.25))
            q75 = float(valid_vals.quantile(0.75))
            iqr = q75 - q25
            lower_bound = q25 - (mult * iqr)
            upper_bound = q75 + (mult * iqr)

            outlier_mask = (s_num < lower_bound) | (s_num > upper_bound)
            outlier_count = int(outlier_mask.sum())

            if outlier_count > 0:
                affected_values += outlier_count
                if treatment == "clip":
                    df[col] = s_num.clip(lower=lower_bound, upper=upper_bound)
                elif treatment == "set_null":
                    df.loc[outlier_mask, col] = np.nan

        operations_applied.append({
            "operation": "outlier_handling",
            "description": f"Processed {affected_values} outliers across {len(out_conf.columns)} columns (IQR={mult}, treatment={treatment}).",
            "changes_count": affected_values,
            "details": {"columns": out_conf.columns, "treatment": treatment, "multiplier": mult}
        })

    # -------------------------------------------------------------------------
    # Final Metrics Comparison
    # -------------------------------------------------------------------------
    after_rows = len(df)
    after_cols = len(df.columns)
    after_missing = count_missing_cells(df)
    after_dups = count_duplicate_rows(df)

    summary = {
        "rows": {
            "before": before_rows,
            "after": after_rows,
            "difference": after_rows - before_rows,
        },
        "columns": {
            "before": before_cols,
            "after": after_cols,
            "difference": after_cols - before_cols,
        },
        "missing_cells": {
            "before": before_missing,
            "after": after_missing,
            "difference": after_missing - before_missing,
        },
        "duplicate_rows": {
            "before": before_dups,
            "after": after_dups,
            "difference": after_dups - before_dups,
        },
        "operations_applied": operations_applied,
        "warnings": warnings,
        "skipped_operations": skipped_operations,
        "configuration_used": config.model_dump(),
    }

    return df, summary


FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell_for_export(val: Any) -> Any:
    """
    Guards against CSV Formula Injection (CWE-1236).
    Prepends a single quote `'` if value is a string starting with formula triggers
    (=, +, -, @, \\t, \\r), while preserving legitimate signed numerical values (e.g. -42, +3.14).
    """
    if isinstance(val, str) and val.startswith(FORMULA_PREFIXES):
        try:
            float(val)
            return val
        except ValueError:
            return f"'{val}"
    return val


def sanitize_csv_formulas_for_export(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies formula sanitization across all object/string columns of a DataFrame
    for safe spreadsheet export without altering underlying data cleaning semantics.
    """
    sanitized = df.copy()
    for col in sanitized.columns:
        if sanitized[col].dtype == object or pd.api.types.is_string_dtype(sanitized[col]):
            sanitized[col] = sanitized[col].apply(sanitize_csv_cell_for_export)
    return sanitized
