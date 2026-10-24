# CSV Data Quality Analyzer

A full-stack web application for analyzing and improving the quality of CSV datasets. Upload your data, detect quality issues, apply cleaning operations, and download improved datasets — all through an intuitive browser interface.

## Features

- **User Authentication & Sessions** — Secure registration, login, and logout with HTTP-only cookie sessions and CSRF protection (Phase 3 complete)
- **CSV Upload & Inspection** — Stream uploads, detect encodings, sanitize headers, and extract metadata and previews (Phase 2 complete)
- **Data Quality Analysis Engine** — Detect missing values, duplicates, format errors, negative values, and constant columns, generating composite scores (0–100) and actionable cleaning recommendations (Phase 4 complete)
- **Data Cleaning** — Select cleaning operations, preview results before applying, and compare original vs. cleaned data (Phase 5 complete)
- **Interactive Modern Frontend** — Responsive React dashboard, real-time Recharts visualizations, clean typography, and intuitive workflows (Phase 6 complete)
- **End-to-End API Integration** — Seamless live connection between React SPA and FastAPI backend with cookie sessions, automatic CSRF token headers, and real-time streaming downloads (Phase 7 complete)
- **Exports** — Download cleaned CSV files and audit reports
- **Analysis History** — View and revisit all previous analyses and cleaning operations

> The original uploaded dataset is never silently modified.

Deployment configuration and a pre-deployment checklist are in [DEPLOYMENT.md](./DEPLOYMENT.md).

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React, Vite, JavaScript/JSX, Tailwind CSS, React Router, Axios, Recharts, Lucide React |
| **Backend** | Python 3.13, FastAPI, Uvicorn, Pandas, NumPy, SQLAlchemy 2, Alembic, Pydantic, Bcrypt, ItsDangerous |
| **Database** | PostgreSQL 18 |
| **Testing** | pytest, HTTPX, pytest-asyncio |

## Project Structure

```
├── backend/          # FastAPI application
│   ├── alembic/      # Database migrations
│   ├── app/
│   │   ├── models/   # SQLAlchemy models (User, Dataset, Analysis, CleaningRecord)
│   │   ├── routers/  # FastAPI controllers (auth, datasets, analyses, cleanings, health)
│   │   ├── schemas/  # Pydantic validation schemas (auth, dataset, analysis, cleaning)
│   │   ├── services/ # CSV streaming, security & hashing, quality engine, cleaning engine
│   │   ├── auth.py   # User authentication dependencies & CSRF verification
│   │   ├── config.py # Pydantic settings & environment configuration
│   │   ├── database.py # Engine, SessionLocal, Base, get_db dependency
│   │   └── main.py   # Application entrypoint & CORS configuration
│   ├── tests/        # Test suite (health checks, dataset upload/parsing, auth, quality analysis, cleaning)
│   ├── uploads/      # Private uploaded file storage (git-ignored)
│   └── requirements.txt
├── frontend/         # React SPA (Vite + Tailwind CSS)
│   ├── src/
│   │   ├── components/ # Reusable UI cards, gauges, charts, navigation
│   │   ├── context/    # AuthContext with session check & CSRF handling
│   │   ├── pages/      # Dashboard, Datasets, Quality, Cleaning, History, Auth, Settings
│   │   ├── services/   # Axios API client (auth, dataset, analysis, cleaning)
│   │   └── utils/      # Formatters and constants
│   ├── package.json
│   └── vite.config.js
├── sample_data/      # Example CSV files for testing
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 14+
- Git

### Quick Start

Set up the backend once:

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # Windows Command Prompt
# PowerShell: .\venv\Scripts\Activate.ps1
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env      # Windows; then set local DATABASE_URL and secrets in backend/.env
# Linux/macOS: cp .env.example .env
python -m alembic upgrade head
```

Run the backend and frontend in **two separate terminals**. Start PostgreSQL first and ensure `backend/.env` is configured.

**Terminal 1 — backend API** (from the repository root):

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend** (from the repository root):

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (usually `http://localhost:5173`). The Vite `/api` proxy expects the backend on port `8000`; `ECONNREFUSED` in the Vite output means the backend is not running or is not reachable there. Check `http://127.0.0.1:8000/api/health` before using the frontend. To build the frontend, run `npm run build` from `frontend`.

> **Full Stack Connected:** The frontend React SPA seamlessly connects to the FastAPI backend API with automated CSRF header injection, HTTP-only session cookies, live dataset ingestion, dynamic quality auditing, and in-memory cleaning transformation previews.

---

## Data Quality Analysis Engine (Phase 4)

### Quality Scoring Formula

The overall data quality score is a transparent composite metric ranging from **0.0 to 100.0**, calculated via explicit penalty deductions:

$$\text{Overall Score} = \max(0.0, \min(100.0, 100.0 - (\text{P}_{\text{missing}} + \text{P}_{\text{duplicate}} + \text{P}_{\text{validity}} + \text{P}_{\text{consistency}})))$$

#### Penalty Deductions:
1. **Missingness Penalty ($\text{P}_{\text{missing}}$)** — Max 35 points:
   $$\text{P}_{\text{missing}} = \min\left(35.0, \frac{\text{Total Missing Cells}}{\text{Total Cells}} \times 35.0\right)$$
   *(Whitespace-only and empty strings are consistently categorized as missing).*
2. **Duplication Penalty ($\text{P}_{\text{duplicate}}$)** — Max 25 points:
   $$\text{P}_{\text{duplicate}} = \min\left(25.0, \frac{\text{Duplicate Rows}}{\text{Total Rows}} \times 25.0\right)$$
   *(Counts subsequent redundant row occurrences across all columns).*
3. **Validity Penalty ($\text{P}_{\text{validity}}$)** — Max 30 points:
   $$\text{P}_{\text{validity}} = \min\left(30.0, \frac{\text{Total Invalid Values}}{\text{Total Cells}} \times 100.0\right)$$
   *(Includes malformed emails, unparseable dates, negative numbers in non-negative columns, and whitespace-only cells).*
4. **Consistency Penalty ($\text{P}_{\text{consistency}}$)** — Max 10 points:
   $$\text{P}_{\text{consistency}} = \min\left(10.0, \text{Constant Columns Count} \times 2.5\right)$$
   *(Deducts for zero-variance columns providing no informational value).*

Individual **Column Quality Scores** are similarly calculated on a 0–100 scale:
$$\text{Column Score} = \max(0.0, \min(100.0, 100.0 - (\text{Missing \%} \times 0.5) - (\text{Invalid \%} \times 0.5)))$$

---

## API Reference

Interactive Swagger UI documentation is available at `http://localhost:8000/docs`.

### Authentication Endpoints
- `POST /api/auth/register` — Register user, set session & CSRF cookies.
- `POST /api/auth/login` — Log in with username/email, set cookies.
- `POST /api/auth/logout` — Revoke the active server-side session and clear session and CSRF cookies.
- `GET /api/auth/me` — Return profile of authenticated user.
- `GET /api/auth/csrf` — Refresh CSRF token.

### Dataset Endpoints
- `POST /api/datasets/upload` — Upload multipart CSV file (validates extension, streams in 64KB chunks up to 50MB, stores under UUID, parses preview).
- `GET /api/datasets` — List datasets owned by the current user.
- `GET /api/datasets/{id}` — Get dataset metadata and preview rows.

### Quality Analysis Endpoints (Phase 4)

#### 1. Run Analysis on Dataset
- **URL**: `POST /api/datasets/{dataset_id}/analyze`
- **Authentication**: Required (`session_id` cookie or `Authorization: Bearer <token>`).
- **Headers**: `X-CSRF-Token: <token>` (required for cookie-authenticated callers).
- **Response (`201 Created`)**:
```json
{
  "id": 1,
  "dataset_id": 1,
  "user_id": 1,
  "overall_score": 86.5,
  "summary_stats": {
    "total_rows": 12,
    "total_columns": 7,
    "total_cells": 84,
    "file_size_bytes": 821,
    "fully_empty_rows": 0,
    "duplicate_rows": 1,
    "duplicate_rows_percentage": 8.33,
    "columns_with_missing": 2,
    "total_missing_cells": 2,
    "total_invalid_values": 3,
    "columns_by_type": { "integer": 2, "string": 4, "float": 1 },
    "columns_quality": [...],
    "score_breakdown": {
      "missing_penalty": 0.83,
      "duplicate_penalty": 2.08,
      "validity_penalty": 3.57,
      "consistency_penalty": 0.0,
      "formula": "overall_score = 100 - (missing_penalty + duplicate_penalty + validity_penalty + consistency_penalty)",
      "explanation": "Calculates composite dataset health based on cell completeness (35%), row uniqueness (25%), format & domain validity (30%), and variance consistency (10%)."
    }
  },
  "column_scores": {
    "id": 100.0,
    "customer_name": 100.0,
    "email": 91.67,
    "age": 95.83,
    "join_date": 95.83,
    "annual_income": 95.83,
    "status": 100.0
  },
  "issues": [
    {
      "severity": "warning",
      "category": "duplicates",
      "column": null,
      "count": 1,
      "description": "Found 1 fully duplicated rows (8.33% of dataset).",
      "rule_applied": "Exact row comparison across all columns (subsequent occurrences)."
    },
    {
      "severity": "error",
      "category": "invalid_format",
      "column": "email",
      "count": 1,
      "description": "Found 1 invalid email formats in column 'email'.",
      "rule_applied": "Standard RFC 5322 compliant email regex matching."
    }
  ],
  "recommendations": [
    "Remove 1 duplicate rows to ensure uniqueness.",
    "Correct 1 invalid email addresses in 'email'.",
    "Inspect and correct negative values in column 'age'."
  ],
  "created_at": "2026-10-24T17:20:00Z"
}
```

#### 2. Get Analysis History for a Dataset
- **URL**: `GET /api/datasets/{dataset_id}/analyses?skip=0&limit=50`
- **Query Parameters**:
  - `skip` *(optional, int, default: 0)*: Number of records to skip for pagination.
  - `limit` *(optional, int, default: 50, max: 100)*: Maximum number of analyses to return.
- **Authentication**: Required.
- **Response (`200 OK`)**: Returns `{ "total": <int>, "items": [...] }`.

#### 3. Get Analysis by ID
- **Response (`200 OK`)**: Returns the full analysis record.

---

### Data Cleaning & Export Endpoints (Phase 5)

#### 1. Preview Cleaning Transformations
- **URL**: `POST /api/datasets/{dataset_id}/clean/preview`
- **Authentication**: Required (`session_id` cookie or `Authorization: Bearer <token>`).
- **Headers**: `X-CSRF-Token: <token>`.
- **Description**: Loads source CSV, validates cleaning config, applies transformations in memory, and returns before/after preview (up to `preview_limit` rows, max 50). Does NOT persist files or database records.
- **Request Body**:
```json
{
  "config": {
    "whitespace_cleaning": {
      "enabled": true,
      "trim_whitespace": true,
      "collapse_internal_whitespace": false
    },
    "text_normalization": {
      "enabled": true,
      "case": "lowercase",
      "columns": ["name"],
      "standardize_null_markers": true
    },
    "missing_values": {
      "enabled": true,
      "strategy": "fill_mean",
      "columns": ["age"]
    },
    "type_conversions": [
      {
        "column": "join_date",
        "target_type": "datetime",
        "on_error": "reject"
      }
    ],
    "duplicate_removal": {
      "enabled": true,
      "keep": "first",
      "subset_columns": ["id"]
    },
    "outlier_handling": {
      "enabled": true,
      "columns": ["score"],
      "method": "iqr",
      "iqr_multiplier": 1.5,
      "treatment": "clip"
    }
  },
  "preview_limit": 10
}
```
- **Response (`200 OK`)**:
```json
{
  "dataset_id": 1,
  "summary": {
    "rows": { "before": 100, "after": 95, "difference": -5 },
    "columns": { "before": 6, "after": 6, "difference": 0 },
    "missing_cells": { "before": 12, "after": 2, "difference": -10 },
    "duplicate_rows": { "before": 5, "after": 0, "difference": -5 },
    "operations_applied": [ ... ],
    "warnings": [ ... ],
    "skipped_operations": [ ... ],
    "configuration_used": { ... }
  },
  "original_preview": [ ... ],
  "cleaned_preview": [ ... ],
  "columns": ["id", "name", "email", "age", "join_date", "score"]
}
```

#### 2. Apply Cleaning & Persist New Version
- **URL**: `POST /api/datasets/{dataset_id}/clean`
- **Authentication**: Required (`session_id` cookie or `Authorization: Bearer <token>`).
- **Headers**: `X-CSRF-Token: <token>`.
- **Description**: Applies configured cleaning transformations in deterministic order, writes output atomically to private storage (`cleaned/cleaned_<uuid>.csv`), records cleaning history in PostgreSQL (`cleaning_records`), and returns the metadata. Source CSV is never modified.
- **Response (`201 Created`)**:
```json
{
  "id": 1,
  "dataset_id": 1,
  "user_id": 1,
  "status": "completed",
  "output_filename": "cleaned_a1b2c3d4e5f6.csv",
  "output_file_size_bytes": 1045,
  "output_row_count": 95,
  "output_column_count": 6,
  "cleaning_summary": { ... },
  "cleaning_config": { ... },
  "created_at": "2026-10-24T18:15:00Z",
  "download_available": true
}
```

#### 3. Get Cleaning History for a Dataset
- **URL**: `GET /api/datasets/{dataset_id}/cleanings?skip=0&limit=50`
- **Authentication**: Required.
- **Response (`200 OK`)**: Returns `{ "total": <int>, "items": [...] }`.

#### 4. Get Cleaning Record Details
- **URL**: `GET /api/cleanings/{cleaning_id}`
- **Authentication**: Required. Verifies ownership through the associated dataset.
- **Response (`200 OK`)**: Returns the full cleaning record.

#### 5. Download Cleaned CSV File
- **URL**: `GET /api/cleanings/{cleaning_id}/download`
- **Authentication**: Required.
- **Description**: Securely streams the cleaned CSV as an attachment with sanitized download filename (e.g., `customers_cleaned.csv`). Storage paths are not exposed.

---

## Database Migrations

Apply database schema changes with Alembic:

```bash
cd backend
python -m alembic upgrade head
```

- `001_initial_schema`: `users`, `datasets`, and `analyses` tables.
- `002_add_cleaning_records`: `cleaning_records` table with foreign keys to `datasets` and `users`.
- `003_add_user_sessions`: `user_sessions` table for revocable, expiring server-side sessions.

---

## Testing & Quality Assurance (Phase 8)

### Running Backend Tests

Run the full automated pytest suite in the backend virtual environment:

```bash
cd backend
python -m pytest -v tests
```

The backend suite contains 108 automated tests across 8 test files:
- **Authentication & Security (`test_auth.py`, `test_phase8_security_and_reliability.py`)**: Registration, password verification, HttpOnly cookie attributes, signed-token validation, server-side session creation, expiry and logout revocation, session isolation, database-failure handling, and CSRF validation.
- **CSV Ingestion & Validation (`test_datasets.py`)**: Multipart streaming, chunked processing, 50MB size threshold, duplicate header deduplication, UTF-8 BOM detection, unicode and multiline quoting, and path traversal prevention.
- **Quality Analysis Engine (`test_quality_analysis.py`)**: Heuristic penalty scoring (0–100), missingness (including whitespace-only cells), duplication, format validity, variance consistency, single-row/empty dataset edge cases, and SHA-256 cryptographic immutability of the source dataset.
- **Data Cleaning Suite (`test_cleaning.py`)**: Deterministic transformation pipeline (whitespace, casing, null markers, imputation, type conversion with decimal safety, deduplication, IQR clipping/nulling), zero-mutation preview isolation, and destructive operation guardrails (blocking 100% row/column elimination).
- **Export Safety & CSV Injection Defense (`test_phase8_security_and_reliability.py`)**: Sanitization of spreadsheet formula trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`) in string export cells while preserving legitimate signed numerical values (`-42.5`, `+3.14`).
- **End-to-End User Workflows & Multi-User Isolation (`test_e2e_integration.py`)**: Complete 14-step integration test from registration to cleaning download, verifying 403 Forbidden cross-user access barriers across datasets, analyses, cleanings, and files.

### Running Frontend Tests

Run the Vitest test suite in the frontend directory:

```bash
cd frontend
npm test               # Runs unit and component test suite via Vitest
npm run lint           # Static code analysis via oxlint
npm run build          # Verifies production distribution and route code-splitting
```

The frontend suite contains 14 tests covering:
- Client-side cookie parsing and safe `X-CSRF-Token` extraction.
- Automatic proactive CSRF token recovery for mutating requests.
- FastAPI validation error mapping and 401 session expiration handling.
- Blob error decoding on failed binary downloads.
- Formula-safe defaults when downloading cleaned CSVs.
- Reusable UI component rendering (`Card`, `Badge`, `PageHeader`, `FormField`, `EmptyState`).
- Route-based code-splitting via `React.lazy` and `Suspense`, maintaining the main bundle under 330 kB.

---

## Security Architecture & Review Findings

### 1. Authentication & Cookie Flags
- Sessions are carried in an `HttpOnly`, `SameSite=Lax` cookie (`session_id`), protecting against client-side script theft (XSS).
- The `secure` flag is automatically configured: enabled in production (`HTTPS`) and disabled for local HTTP development.

### 2. Cross-Site Request Forgery (CSRF) Protection
- State-changing HTTP verbs (`POST`, `PUT`, `DELETE`, `PATCH`) enforce double-submit CSRF verification.
- A cryptographically signed token is issued in a readable `csrf_token` cookie; frontend requests submit this in the `X-CSRF-Token` header.
- The server validates that the header matches the cookie and resolves to the authenticated user ID.

### 3. File System & Path Traversal Prevention
- Uploaded filenames are stripped of directories (`Path(filename).name`) and stored on disk under randomly generated UUIDs (`uploads/<uuid>.csv`).
- Cleaned files are saved under isolated UUIDs (`cleaned/cleaned_<uuid>.csv`).
- Internal server filesystem paths are never returned in client API responses.

### 4. CSV Formula Injection (CWE-1236) Defense
- Exported spreadsheets can inadvertently execute arbitrary code if cell values begin with formula triggers (`=`, `@`, `+`, `-`).
- Downloads are sanitized by default. The `export_safe` query parameter defaults to `true` and prefixes risky text cells with a single quote (`'`), while preserving legitimate signed numbers such as `-50.25` and `+3.14`.

### 5. Server-Side Session Revocation
- Sessions use `itsdangerous.URLSafeTimedSerializer` signed tokens and a `user_sessions` database record with a unique session identifier, token hash, and expiration.
- Each authenticated request validates the token and its active, unexpired database record. `/api/auth/logout` revokes only the current session, so a copied token cannot be replayed and other users' sessions remain valid.
- The session table is introduced by forward migration `003_add_user_sessions`.

---

## Known Limitations & Performance
- **In-Memory Processing**: Cleaning operates in-memory using Pandas, bounded by the 50 MB upload limit (`MAX_UPLOAD_SIZE_MB`). Larger datasets in future iterations can leverage streaming chunks or asynchronous worker queues.
- **Destructive Operation Protection**: Cleaning operations that would drop 100% of rows or all columns are blocked by safety validation to prevent accidental complete data loss.
- **Original File Immutability**: All cleaning actions generate separate output files; the original uploaded file remains untouched (verified via SHA-256 hash assertions).

## License

This project is part of a portfolio submission.
