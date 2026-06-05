# -*- coding: utf-8 -*-
"""
app.py - DataProfiler Streamlit application.
Run with: streamlit run app.py
"""

from __future__ import annotations

import os
import io
from typing import Any

import pandas as pd
import streamlit as st

from profiler import (
    auto_detect_dob_columns,
    auto_detect_date_columns,
    profile_dataframe,
)
from report import build_excel_report, build_json_report

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="DataProfiler",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _init_state():
    defaults = {
        "df": None,
        "table_name": "",
        "dob_cols": [],
        "profile_result": None,
        "source_type": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ---------------------------------------------------------------------------
# Sidebar — data source selection
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🔬 DataProfiler")
    st.caption("ERP → BC Migration QA Tool")
    st.divider()

    source = st.radio(
        "**Data source**",
        options=["Upload file (CSV / Excel)", "Amazon Redshift"],
        index=0,
    )

# ---------------------------------------------------------------------------
# Helper: load uploaded file
# ---------------------------------------------------------------------------

def _load_uploaded_file(uploaded) -> tuple[pd.DataFrame, str]:
    name: str = uploaded.name
    if name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded, low_memory=False)
        return df, name.rsplit(".", 1)[0]

    # Excel
    xls = pd.ExcelFile(uploaded, engine="openpyxl")
    sheets = xls.sheet_names
    if len(sheets) == 1:
        df = xls.parse(sheets[0])
        return df, f"{name.rsplit('.', 1)[0]}_{sheets[0]}"

    selected_sheet = st.selectbox(
        "This Excel file has multiple sheets — select one to profile:",
        options=sheets,
        key="sheet_selector",
    )
    df = xls.parse(selected_sheet)
    return df, f"{name.rsplit('.', 1)[0]}_{selected_sheet}"


# ---------------------------------------------------------------------------
# Helper: Redshift connection
# ---------------------------------------------------------------------------

def _get_redshift_credentials() -> dict[str, str | int]:
    return {
        "host": os.environ.get("REDSHIFT_HOST", ""),
        "port": int(os.environ.get("REDSHIFT_PORT", 5439)),
        "database": os.environ.get("REDSHIFT_DB", ""),
        "user": os.environ.get("REDSHIFT_USER", ""),
        "password": os.environ.get("REDSHIFT_PASSWORD", ""),
    }


@st.cache_resource(show_spinner="Connecting to Redshift…")
def _redshift_engine(host, port, database, user, password):
    try:
        import redshift_connector  # noqa: F401
        from sqlalchemy import create_engine

        url = f"redshift+redshift_connector://{user}:{password}@{host}:{port}/{database}"
        engine = create_engine(url, connect_args={"sslmode": "require"})
        # Test connection
        with engine.connect() as conn:
            conn.execute(_text("SELECT 1"))
        return engine
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _text(q: str):
    from sqlalchemy import text
    return text(q)


@st.cache_data(show_spinner="Fetching schemas…", ttl=300)
def _list_schemas(_engine) -> list[str]:
    from sqlalchemy import text
    with _engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT table_schema FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog','information_schema','pg_internal') "
            "ORDER BY table_schema"
        ))
        return [r[0] for r in rows]


@st.cache_data(show_spinner="Fetching tables…", ttl=300)
def _list_tables(_engine, schema: str) -> list[str]:
    from sqlalchemy import text
    with _engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema ORDER BY table_name"
        ), {"schema": schema})
        return [r[0] for r in rows]


def _load_redshift_table(engine, schema: str, table: str, limit: int) -> pd.DataFrame:
    from sqlalchemy import text
    query = text(f'SELECT * FROM "{schema}"."{table}" LIMIT :lim')
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"lim": limit})


# ---------------------------------------------------------------------------
# Main — source-specific UI
# ---------------------------------------------------------------------------

st.title("🔬 DataProfiler")
st.markdown("*Data quality checks for clinic ERP → BC migrations*")
st.divider()

# ---- FILE UPLOAD ----
if source == "Upload file (CSV / Excel)":
    uploaded = st.file_uploader(
        "Upload a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        help="Supports CSV and Excel (.xlsx / .xls). For Excel, you will be asked to select a sheet if multiple exist.",
    )

    if uploaded:
        with st.spinner("Reading file…"):
            try:
                df, tname = _load_uploaded_file(uploaded)
                st.session_state["df"] = df
                st.session_state["table_name"] = tname
                st.session_state["profile_result"] = None
            except Exception as exc:
                st.error(f"Could not load file: {exc}")
                st.stop()

# ---- REDSHIFT ----
else:
    creds = _get_redshift_credentials()
    missing = [k for k, v in creds.items() if not v and k != "port"]

    if missing:
        st.warning(
            f"Missing Redshift environment variables: **{', '.join(missing.upper() for missing in missing)}**  \n"
            "Set them before launching the app (see README for details)."
        )
    else:
        with st.spinner("Connecting to Redshift…"):
            try:
                engine = _redshift_engine(**creds)
            except Exception as exc:
                st.error(f"Redshift connection failed: {exc}")
                st.stop()

        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            schemas = _list_schemas(engine)
            selected_schema = st.selectbox("Schema", options=schemas, key="rs_schema")

        with col2:
            tables = _list_tables(engine, selected_schema) if selected_schema else []
            selected_table = st.selectbox("Table", options=tables, key="rs_table")

        with col3:
            row_limit = st.number_input(
                "Row limit",
                min_value=100,
                max_value=500_000,
                value=10_000,
                step=1_000,
                help="Number of rows to fetch for profiling (LIMIT clause).",
            )

        if selected_table and st.button("Load table", type="primary"):
            with st.spinner(f"Fetching {selected_schema}.{selected_table}…"):
                try:
                    df = _load_redshift_table(engine, selected_schema, selected_table, row_limit)
                    tname = f"{selected_schema}.{selected_table}"
                    st.session_state["df"] = df
                    st.session_state["table_name"] = tname
                    st.session_state["profile_result"] = None
                    st.success(f"Loaded {len(df):,} rows from {tname}")
                except Exception as exc:
                    st.error(f"Failed to load table: {exc}")


# ---------------------------------------------------------------------------
# Step 2 — Preview + column list
# ---------------------------------------------------------------------------

df: pd.DataFrame | None = st.session_state["df"]

if df is not None:
    st.subheader(f"📋 Preview — {st.session_state['table_name']}")
    st.markdown(f"**{len(df):,} rows × {len(df.columns)} columns**")
    st.dataframe(df.head(20), use_container_width=True)

    with st.expander("Column list with detected types", expanded=False):
        type_rows = []
        for col in df.columns:
            from profiler import _detect_series_type
            type_rows.append({
                "Column": col,
                "Detected Type": _detect_series_type(df[col]),
                "Non-null Count": int(df[col].notna().sum()),
                "Null %": round(df[col].isna().mean() * 100, 2),
            })
        st.dataframe(pd.DataFrame(type_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ---------------------------------------------------------------------------
    # Step 3 — DOB column confirmation
    # ---------------------------------------------------------------------------

    st.subheader("🎂 Date-of-Birth column selection")
    st.markdown(
        "Columns whose names contain *birth*, *dob*, *nacimiento*, *birthdate*, etc. "
        "are pre-selected. **Adjust as needed.**"
    )

    auto_dobs = auto_detect_dob_columns(df)
    confirmed_dobs = st.multiselect(
        "DOB columns",
        options=list(df.columns),
        default=auto_dobs,
        help="These columns will be checked for age < 18 years and age > 100 years.",
    )

    st.divider()

    # ---------------------------------------------------------------------------
    # Step 4 — Run profiler
    # ---------------------------------------------------------------------------

    if st.button("▶ Run Profiler", type="primary", use_container_width=True):
        with st.spinner("Profiling data…"):
            result = profile_dataframe(
                df=df,
                table_name=st.session_state["table_name"],
                dob_columns=confirmed_dobs,
            )
            st.session_state["profile_result"] = result

# ---------------------------------------------------------------------------
# Step 5 — Results
# ---------------------------------------------------------------------------

result: dict[str, Any] | None = st.session_state["profile_result"]

if result is not None:
    st.subheader("📊 Profiling Results")

    gate = result["quality_gate"]

    # Quality gate banner
    if gate["status"] == "PASS":
        st.success("✅ Quality Gate: **PASS** — No critical errors detected.")
    else:
        st.error(f"❌ Quality Gate: **FAIL** — {len(gate['errors'])} error(s) found.")

    if gate["errors"]:
        with st.expander("🔴 Errors", expanded=True):
            for err in gate["errors"]:
                st.markdown(f"- {err}")

    if gate["warnings"]:
        with st.expander("🟡 Warnings", expanded=True):
            for warn in gate["warnings"]:
                st.markdown(f"- {warn}")

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Records", f"{result['total_records']:,}")
    col2.metric("Total Columns", result["total_columns"])
    col3.metric("Duplicate Records", f"{result['duplicate_count']:,}")
    col4.metric("Duplicate %", f"{result['duplicate_pct']:.2f}%")

    st.divider()

    # Detailed column table
    st.subheader("Column-level checks")

    col_rows = []
    for cp in result["columns"]:
        row = {
            "Column": cp["column"],
            "Type": cp["detected_type"],
            "DOB": "✓" if cp["is_dob"] else "",
            "Date Field": "✓" if cp["is_date"] else "",
            "Null Count": cp["null_count"],
            "Null %": cp["null_pct"],
        }
        if cp.get("is_dob"):
            row["DOB >100y Count"] = cp.get("dob_over_100_count", "")
            row["DOB >100y %"] = cp.get("dob_over_100_pct", "")
            row["DOB <18y Count"] = cp.get("dob_under_18_count", "")
            row["DOB <18y %"] = cp.get("dob_under_18_pct", "")
        else:
            row["DOB >100y Count"] = ""
            row["DOB >100y %"] = ""
            row["DOB <18y Count"] = ""
            row["DOB <18y %"] = ""

        if cp.get("date_stale_10y_count") is not None:
            row["Stale Date (≥10y) Count"] = cp["date_stale_10y_count"]
            row["Stale Date (≥10y) %"] = cp["date_stale_10y_pct"]
        else:
            row["Stale Date (≥10y) Count"] = ""
            row["Stale Date (≥10y) %"] = ""

        col_rows.append(row)

    results_df = pd.DataFrame(col_rows)

    def _highlight_cell(val, col_name: str):
        if col_name == "Null %" and isinstance(val, (int, float)):
            if val > 20:
                return "background-color: #FF4C4C; color: white"
            if val > 5:
                return "background-color: #FFD966"
            return "background-color: #92D050"
        if col_name == "DOB >100y %" and isinstance(val, (int, float)):
            return "background-color: #FF4C4C; color: white" if val > 0 else "background-color: #92D050"
        if col_name == "DOB <18y %" and isinstance(val, (int, float)):
            if val > 2:
                return "background-color: #FFD966"
            return ""
        return ""

    def _style_df(df_to_style: pd.DataFrame):
        styled = df_to_style.style
        for col_name in ["Null %", "DOB >100y %", "DOB <18y %"]:
            if col_name in df_to_style.columns:
                styled = styled.applymap(
                    lambda v, cn=col_name: _highlight_cell(v, cn),
                    subset=[col_name],
                )
        return styled

    st.dataframe(_style_df(results_df), use_container_width=True, hide_index=True)

    # ---------------------------------------------------------------------------
    # Step 6 — Downloads
    # ---------------------------------------------------------------------------

    st.divider()
    st.subheader("⬇ Download Reports")

    col_dl1, col_dl2 = st.columns(2)

    with col_dl1:
        json_bytes = build_json_report([result]).encode("utf-8")
        st.download_button(
            label="📄 Download JSON Report",
            data=json_bytes,
            file_name=f"dataprofiler_{result['table_name'].replace('/', '_')}.json",
            mime="application/json",
            use_container_width=True,
        )

    with col_dl2:
        with st.spinner("Generating Excel report…"):
            excel_bytes = build_excel_report([result])
        st.download_button(
            label="📊 Download Excel Report",
            data=excel_bytes,
            file_name=f"dataprofiler_{result['table_name'].replace('/', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
