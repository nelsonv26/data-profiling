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
# Business key column auto-detection
# ---------------------------------------------------------------------------

_BIZ_KEY_PATTERNS = re.compile(
    r"(phone|telefono|tel[eé]fono|email|correo|"
    r"\bid\b|_id$|^id_|number|numero|n[uú]mero|nombre|name)",
    re.IGNORECASE,
)


def auto_detect_biz_key_columns(df: pd.DataFrame) -> list[str]:
    """Return column names that are likely identity/business-key fields."""
    return [c for c in df.columns if _BIZ_KEY_PATTERNS.search(c)]


# ---------------------------------------------------------------------------
# Narrative summary
# ---------------------------------------------------------------------------

_FRIENDLY_NAMES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"email|correo", re.I), "email address"),
    (re.compile(r"phone|tel[eé]?fono|tel", re.I), "phone number"),
    (re.compile(r"home.*phone|phone.*home|tel.*casa|casa.*tel", re.I), "home phone number"),
    (re.compile(r"cell|mobile|m[oó]vil|celular", re.I), "mobile phone number"),
    (re.compile(r"birth|dob|nacimiento|fecha_nac", re.I), "birth date"),
    (re.compile(r"address|direcci[oó]n|domicilio|addr", re.I), "address"),
    (re.compile(r"zip|postal|c[oó]digo_postal", re.I), "postal code"),
    (re.compile(r"nombre|name", re.I), "name"),
    (re.compile(r"gender|sex|g[eé]nero|sexo", re.I), "gender"),
    (re.compile(r"id\b|identifier|identificador", re.I), "identifier"),
]


def _friendly_column_name(col: str) -> str:
    for pattern, label in _FRIENDLY_NAMES:
        if pattern.search(col):
            return label
    return col.replace("_", " ").strip()


def generate_narrative_summary(result: dict[str, Any]) -> str:
    """
    Build a plain-English paragraph summarising key data quality findings.
    Only mentions columns where null% > 5%.
    """
    total = result["total_records"]
    entity = "records"  # generic; callers can override

    lines: list[str] = []
    lines.append(f"This dataset contains {total:,} {entity}.")

    seen_labels: set[str] = set()
    for cp in result["columns"]:
        if cp["null_pct"] <= 5:
            continue
        null_count = cp["null_count"]
        null_pct = cp["null_pct"]
        label = _friendly_column_name(cp["column"])
        if label in seen_labels:
            continue
        seen_labels.add(label)

        pct_str = f"{null_pct:.1f}%"
        # Express as "1 in N" when that reads more naturally (5–30%)
        if 5 < null_pct < 30:
            ratio = round(100 / null_pct)
            fraction = f"1 in {ratio} {entity} ({pct_str})"
            lines.append(
                f"{fraction} {'has' if total == 1 else 'have'} no {label} recorded."
            )
        else:
            lines.append(
                f"{null_count:,} {entity} ({pct_str}) have no {label} recorded."
            )

    # Business-key duplicates
    bk_count = result.get("biz_key_duplicate_count")
    bk_cols = result.get("biz_key_columns", [])
    if bk_count and bk_count > 0 and bk_cols:
        bk_pct = result.get("biz_key_duplicate_pct", 0)
        key_label = " + ".join(_friendly_column_name(c) for c in bk_cols[:2])
        if len(bk_cols) > 2:
            key_label += " …"
        lines.append(
            f"{bk_count:,} {entity} ({bk_pct:.1f}%) share a duplicate business key ({key_label})."
        )

    return " ".join(lines)


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
    biz_key_columns: list[str] | None = None,
) -> dict[str, Any]:
    """
    Profile a DataFrame and return a structured result dict.

    Parameters
    ----------
    df              : The data to profile.
    table_name      : Friendly name for the table/file.
    dob_columns     : Columns confirmed as date-of-birth fields.
    biz_key_columns : Columns used as composite business key for dup detection.
    """
    biz_key_columns = biz_key_columns or []

    total_records = len(df)

    # Full-row duplicates
    duplicate_count = int(df.duplicated().sum())
    duplicate_pct = round(duplicate_count / max(total_records, 1) * 100, 2)

    # Business-key duplicates
    valid_bk_cols = [c for c in biz_key_columns if c in df.columns]
    if valid_bk_cols:
        bk_mask = df.duplicated(subset=valid_bk_cols, keep=False)
        bk_dup_count = int(bk_mask.sum())
    else:
        bk_dup_count = 0
    bk_dup_pct = round(bk_dup_count / max(total_records, 1) * 100, 2)

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

    if valid_bk_cols and bk_dup_pct > 5:
        errors.append(
            f"Business-key duplicates: {bk_dup_pct:.2f}% records share the same "
            f"{' + '.join(valid_bk_cols)} (threshold: >5%)"
        )

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

    result: dict[str, Any] = {
        "table_name": table_name,
        "total_records": total_records,
        "total_columns": len(df.columns),
        "duplicate_count": duplicate_count,
        "duplicate_pct": duplicate_pct,
        "biz_key_columns": valid_bk_cols,
        "biz_key_duplicate_count": bk_dup_count,
        "biz_key_duplicate_pct": bk_dup_pct,
        "dob_columns": dob_columns,
        "columns": columns_profile,
        "quality_gate": {
            "status": gate_status,
            "errors": errors,
            "warnings": warnings,
        },
        "profiled_at": datetime.utcnow().isoformat() + "Z",
    }

    result["narrative"] = generate_narrative_summary(result)
    return result
