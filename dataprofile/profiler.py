# -*- coding: utf-8 -*-
"""
profiler.py - All data profiling logic for DataProfiler.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Type detection
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d*\.\d+$")
_BOOL_VALS = {"true", "false", "1", "0", "yes", "no", "y", "n", "t", "f"}
_DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
    "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
    "%Y/%m/%d", "%d-%m-%Y",
]


def _detect_series_type(series: pd.Series) -> str:
    """Return a canonical type string for a pandas Series."""
    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "FLOAT"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "DATETIME"

    # For object columns, sample non-null values and try to infer
    sample = series.dropna().astype(str).head(200)
    if sample.empty:
        return "VARCHAR"

    if sample.str.lower().isin(_BOOL_VALS).all():
        return "BOOLEAN"

    # Try parsing as datetime
    parsed_dates = 0
    for fmt in _DATE_FORMATS:
        try:
            pd.to_datetime(sample, format=fmt, errors="raise")
            parsed_dates = len(sample)
            break
        except Exception:
            pass
    if parsed_dates == 0:
        # Fallback: pandas generic parser on a small sample
        try:
            result = pd.to_datetime(sample, infer_datetime_format=True, errors="coerce")
            parsed_dates = result.notna().sum()
        except Exception:
            pass
    if parsed_dates / max(len(sample), 1) >= 0.85:
        return "DATETIME"

    if sample.str.match(r"^-?\d+$").all():
        return "INTEGER"
    if sample.str.match(r"^-?\d*\.?\d+$").all():
        return "FLOAT"

    return "VARCHAR"


def _coerce_datetime(series: pd.Series) -> pd.Series:
    """Attempt to coerce a series to datetime, returning NaT on failure."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    try:
        return pd.to_datetime(series, infer_datetime_format=True, errors="coerce")
    except Exception:
        return pd.to_datetime(series, errors="coerce")


# ---------------------------------------------------------------------------
# DOB column auto-detection
# ---------------------------------------------------------------------------

_DOB_PATTERNS = re.compile(
    r"(birth|dob|nacimiento|birthdate|fecha_nac|fecha_nacimiento|bdate|dateofbirth)",
    re.IGNORECASE,
)
_DATE_FIELD_PATTERN = re.compile(
    r"(date|fecha|dt|_at|_on|time|datetime)",
    re.IGNORECASE,
)


def auto_detect_dob_columns(df: pd.DataFrame) -> list[str]:
    """Return column names that look like date-of-birth fields."""
    return [c for c in df.columns if _DOB_PATTERNS.search(c)]


def auto_detect_date_columns(df: pd.DataFrame) -> list[str]:
    """Return all columns that look like date fields (including DOB)."""
    candidates = []
    for col in df.columns:
        series = df[col]
        dtype_str = _detect_series_type(series)
        if dtype_str == "DATETIME":
            candidates.append(col)
        elif _DATE_FIELD_PATTERN.search(col):
            coerced = _coerce_datetime(series)
            if coerced.notna().sum() / max(len(series), 1) >= 0.5:
                candidates.append(col)
    return list(dict.fromkeys(candidates))  # deduplicate, preserve order


# ---------------------------------------------------------------------------
# Core profiling
# ---------------------------------------------------------------------------

TODAY = pd.Timestamp(date.today())
HUNDRED_YEARS_AGO = TODAY - pd.DateOffset(years=100)
EIGHTEEN_YEARS_AGO = TODAY - pd.DateOffset(years=18)
TEN_YEARS_AGO = TODAY - pd.DateOffset(years=10)


def profile_dataframe(
    df: pd.DataFrame,
    table_name: str,
    dob_columns: list[str],
) -> dict[str, Any]:
    """
    Profile a DataFrame and return a structured result dict.

    Parameters
    ----------
    df          : The data to profile.
    table_name  : Friendly name for the table/file.
    dob_columns : Columns confirmed as date-of-birth fields.
    """
    total_records = len(df)
    duplicate_count = int(df.duplicated().sum())
    duplicate_pct = round(duplicate_count / max(total_records, 1) * 100, 2)

    # Detect all date columns (excluding confirmed DOB cols, to avoid double-counting)
    all_date_cols = auto_detect_date_columns(df)
    non_dob_date_cols = [c for c in all_date_cols if c not in dob_columns]

    columns_profile: list[dict[str, Any]] = []

    for col in df.columns:
        series = df[col]
        detected_type = _detect_series_type(series)
        null_count = int(series.isna().sum())
        null_pct = round(null_count / max(total_records, 1) * 100, 2)

        col_result: dict[str, Any] = {
            "column": col,
            "detected_type": detected_type,
            "null_count": null_count,
            "null_pct": null_pct,
            "is_dob": col in dob_columns,
            "is_date": col in all_date_cols,
        }

        # DOB-specific checks
        if col in dob_columns:
            dt_series = _coerce_datetime(series)
            non_null = dt_series.dropna()
            n = max(len(non_null), 1)

            over_100_count = int((non_null < HUNDRED_YEARS_AGO).sum())
            under_18_count = int((non_null > EIGHTEEN_YEARS_AGO).sum())

            col_result["dob_over_100_count"] = over_100_count
            col_result["dob_over_100_pct"] = round(over_100_count / max(total_records, 1) * 100, 2)
            col_result["dob_under_18_count"] = under_18_count
            col_result["dob_under_18_pct"] = round(under_18_count / max(total_records, 1) * 100, 2)

        # Non-DOB date field: check for values >= 10 years old
        if col in non_dob_date_cols:
            dt_series = _coerce_datetime(series)
            non_null = dt_series.dropna()
            stale_count = int((non_null <= TEN_YEARS_AGO).sum())
            col_result["date_stale_10y_count"] = stale_count
            col_result["date_stale_10y_pct"] = round(stale_count / max(total_records, 1) * 100, 2)

        columns_profile.append(col_result)

    # Quality gate evaluation
    errors: list[str] = []
    warnings: list[str] = []

    if duplicate_pct > 5:
        errors.append(f"Duplicate records: {duplicate_pct:.2f}% (threshold: >5%)")

    for cp in columns_profile:
        if cp["null_pct"] > 20:
            errors.append(f"Column '{cp['column']}': {cp['null_pct']:.2f}% nulls (threshold: >20%)")
        if cp.get("dob_over_100_pct", 0) > 0:
            errors.append(
                f"Column '{cp['column']}': {cp['dob_over_100_pct']:.2f}% DOB records older than 100 years"
            )
        if cp.get("dob_under_18_pct", 0) > 2:
            warnings.append(
                f"Column '{cp['column']}': {cp['dob_under_18_pct']:.2f}% DOB records younger than 18 (threshold: >2%)"
            )

    gate_status = "PASS" if not errors else "FAIL"

    return {
        "table_name": table_name,
        "total_records": total_records,
        "total_columns": len(df.columns),
        "duplicate_count": duplicate_count,
        "duplicate_pct": duplicate_pct,
        "dob_columns": dob_columns,
        "columns": columns_profile,
        "quality_gate": {
            "status": gate_status,
            "errors": errors,
            "warnings": warnings,
        },
        "profiled_at": datetime.utcnow().isoformat() + "Z",
    }
