# DataProfiler

Local data profiling web app for clinic ERP → BC migration QA.

Profiles CSV, Excel, and Amazon Redshift data and generates downloadable JSON and Excel quality reports.

---

## Requirements

- Python 3.11+
- pip

---

## Setup

```bash
# 1. Clone / navigate to the dataprofile folder
cd dataprofile

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Running the app

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501** in your browser.

---

## Redshift credentials

Set these environment variables **before** launching the app.

### Windows (PowerShell — current session only)

```powershell
$env:REDSHIFT_HOST     = "your-cluster.us-east-1.redshift.amazonaws.com"
$env:REDSHIFT_PORT     = "5439"
$env:REDSHIFT_DB       = "your_database"
$env:REDSHIFT_USER     = "your_username"
$env:REDSHIFT_PASSWORD = "your_password"
streamlit run app.py
```

### Windows (persistent — System Environment Variables)

```powershell
[System.Environment]::SetEnvironmentVariable("REDSHIFT_HOST",     "...", "User")
[System.Environment]::SetEnvironmentVariable("REDSHIFT_PORT",     "5439", "User")
[System.Environment]::SetEnvironmentVariable("REDSHIFT_DB",       "...", "User")
[System.Environment]::SetEnvironmentVariable("REDSHIFT_USER",     "...", "User")
[System.Environment]::SetEnvironmentVariable("REDSHIFT_PASSWORD", "...", "User")
```

### macOS / Linux (.env file approach)

Create a `.env` file in the `dataprofile/` folder:

```
REDSHIFT_HOST=your-cluster.us-east-1.redshift.amazonaws.com
REDSHIFT_PORT=5439
REDSHIFT_DB=your_database
REDSHIFT_USER=your_username
REDSHIFT_PASSWORD=your_password
```

Then launch with:

```bash
set -a && source .env && set +a && streamlit run app.py
```

---

## User flow

1. **Choose data source** — upload a CSV/Excel file or connect to Redshift.
2. **Preview data** — see the first 20 rows and detected column types.
3. **Confirm DOB columns** — auto-detected by name patterns; adjust as needed.
4. **Run Profiler** — click the button to execute all checks.
5. **Review results** — quality gate banner, metric summary, colour-coded column table.
6. **Download reports** — JSON and Excel (multi-sheet, colour-coded).

---

## Profiling checks (Alex's requirements)

| # | Check | Detail |
|---|-------|--------|
| 1 | **Data type detection** | INTEGER, FLOAT, DATETIME, VARCHAR, BOOLEAN per column |
| 2 | **Total record count** | Row count of the table / file |
| 3 | **Duplicate records** | Full-row duplicates — count and % |
| 4 | **DOB > 100 years** | % of records where date of birth is older than 100 years |
| 5 | **DOB < 18 years** | % of records where date of birth is younger than 18 years |
| 6 | **Stale date fields** | % of records where non-DOB date fields have values ≥ 10 years old |
| 7 | **Null values** | % of nulls per column |

### Quality gate thresholds

| Severity | Condition |
|----------|-----------|
| ERROR | Nulls > 20% in any column |
| ERROR | Duplicates > 5% |
| ERROR | Any DOB record older than 100 years |
| WARNING | DOB < 18 years > 2% |

---

## Excel report structure

- **Sheet 1 — Summary**: one row per table with record count, duplicate %, column count, and gate status.
- **Sheet per table**: all columns × all checks, colour-coded:
  - 🔴 Red — ERROR (nulls > 20%, DOB > 100y)
  - 🟡 Yellow — WARNING (nulls > 5%, DOB < 18y > 2%)
  - 🟢 Green — OK

---

## DOB auto-detection

Columns whose names contain any of the following (case-insensitive) are pre-selected as DOB:

`birth`, `dob`, `nacimiento`, `birthdate`, `fecha_nac`, `fecha_nacimiento`, `bdate`, `dateofbirth`

You can override the selection in the UI before running the profiler.

---

## Redshift row limit

Default: **10,000 rows**. Adjustable in the UI (100 – 500,000) via the "Row limit" input.
