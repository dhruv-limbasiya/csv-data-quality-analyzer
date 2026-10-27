# CSV Data Quality Analyzer

Inspect, assess, and clean CSV datasets through a secure web application. Upload a dataset, review quality findings, preview cleaning operations, and download a cleaned copy.

> **Original files are preserved.** Cleaning creates a separate output; it does not overwrite the uploaded CSV.

## Features

- User accounts with password hashing, HTTP-only sessions, server-side revocation, expiry, logout, and CSRF-protected state changes.
- CSV upload, metadata and preview, quality analysis, configurable cleaning, cleaning history, and authorized output downloads.
- Owner checks on datasets and cleaning records. Cleaned CSV exports mitigate spreadsheet formula injection.
- Direct-to-private-object-storage upload and download for the Vercel deployment path; local files are used only in local development or on a host with persistent storage.

## Architecture

| Component | Technology |
| --- | --- |
| Frontend | React, Vite, React Router |
| API | FastAPI, SQLAlchemy, Pydantic, Vercel Python runtime |
| Data processing | Pandas, NumPy |
| Database | PostgreSQL + Alembic |
| Vercel object storage | Cloudflare R2 private bucket, through backend storage abstraction |
| Tests | pytest, HTTPX, Vitest |

```text
Browser ── HTTPS/API + host-only cookies ──> Vercel FastAPI Function
   │                                          │
   ├── short-lived signed PUT/GET ──────────> private R2 bucket
   │                                          │
   │                                          └── pooled PostgreSQL connection ──> Neon
   └── Vercel-hosted React/Vite static build
```

The browser receives a short-lived, object-specific signed URL only after authenticated backend authorization. The API checks ownership, declared and actual object size, object metadata, expiry, and parses the uploaded CSV before making it available to analysis. Signed URLs are bearer capabilities; keep them private. The API's R2 keys and database secrets are backend-only.

Vercel can run this as one Services project using the root `vercel.json`, or as independent frontend and backend projects using their respective root directories. These are alternative routing setups: a separate frontend project must set `VITE_API_BASE_URL`, while the combined project routes `/api` on the same origin. For separate projects, assign frontend and API HTTPS origins under the same custom domain (for example, `app.<your-domain>` and `api.<your-domain>`). Separate default `*.vercel.app` hostnames are cross-site; browsers that block third-party cookies may otherwise prevent session cookies from reaching the API. Configure exact frontend origins and verify login, CSRF, and logout behavior before accepting users. See the deployment guide for routing details and diagnosis of reported production API 500 responses.

Vercel's function payload limit makes proxying uploaded CSV bodies through the API unsuitable. Vercel local function storage is not durable, so dataset and cleaned files are stored in R2. A controlled migration adds upload state to the existing SQLAlchemy schema; do not replace or reset migration history.

## Local development (Windows PowerShell)

Requirements: Python 3.12, Node.js 20.19+ or 22.12+, and a local PostgreSQL database. Backend tests use the configured `DATABASE_URL` and may write or delete fixture rows; run them only against a fresh disposable database migrated to head (SQLite is supported), never a production or valuable development database.

1. Start PostgreSQL and create a disposable local development database.
2. From repository root, set up Python:

   ```powershell
   cd backend
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements-dev.txt
   Copy-Item .env.example .env
   ```

3. Edit `backend\.env` with the local PostgreSQL URL and two different, randomly generated local secrets. Keep `.env` private and never reuse test placeholders in production. Local storage settings and `VITE_DIRECT_UPLOAD=false` avoid requiring R2 in development.
4. Check the target database, back up any valuable data, then apply migrations:

   ```powershell
   python -m alembic upgrade head
   ```

5. Start the API in this terminal:

   ```powershell
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

6. In another terminal from repository root:

   ```powershell
   cd frontend
   npm ci
   npm run dev
   ```

Open the local Vite URL, usually <http://localhost:5173/>. Vite proxies `/api` to `http://localhost:8000`. Health check: <http://127.0.0.1:8000/api/health>.

## API documentation

The API is served by `backend/app/main.py`. Its authentication and dataset routers add `/api/auth` and `/api/datasets`; the analysis and cleaning routers register their full `/api/...` paths directly. All application endpoints below use the `/api` prefix except the backend root endpoint.

### Base URLs

- Local backend: `http://localhost:8000/api`. The Vite development server proxies browser requests from `http://localhost:5173/api` to `http://localhost:8000/api`.
- The provided Vercel deployment: `https://csv-data-quality-analyzer.vercel.app/api`. This follows the root `vercel.json`, which routes `/api` and `/api/...` to FastAPI. If deploying separate frontend and backend projects instead, set `VITE_API_BASE_URL` to the backend origin (without `/api`); the frontend client appends `/api/...` paths itself.
- `GET /` is the backend root response. In the combined Vercel configuration, `/` is routed to the frontend, so use the backend service root directly to reach it.

Protected endpoints accept the HTTP-only session cookie used by the frontend or an `Authorization: Bearer <token>` header. Cookie-authenticated state-changing requests require the CSRF cookie and matching `X-CSRF-Token` header. Registration and login issue the session and CSRF cookies. Routes marked **No** below are public unless otherwise noted. Demo access is available only when `DEMO_MODE=true`; in that mode login and registration return 404 and `POST /api/auth/demo` starts a dedicated demo session.

### Registered endpoints

| Method | Full endpoint path | Purpose | Authentication required | Request body or parameters | Expected response |
|---|---|---|---|---|---|
| GET | `/` | Backend welcome and version information | No | None | `200`: `message`, `version`, `docs_url` |
| GET | `/api/health` | Check API and database connectivity | No | None | `200`: `status`, `app`, `version`, `database`; `503` if the database check fails |
| POST | `/api/auth/register` | Create an account and start a session | No | JSON: `username` (3–50 characters; letters, numbers, `_`, `-`), `email`, `password` (8–128 characters) | `201`: user fields `id`, `username`, `email`, `is_active`, `created_at`, `updated_at`; sets auth cookies. `409` for duplicate username/email. `404` in demo mode |
| POST | `/api/auth/login` | Authenticate by username or email | No | JSON: `username_or_email`, `password` | `200`: user fields above; sets auth cookies. `401` for invalid credentials. `404` in demo mode |
| POST | `/api/auth/demo` | Create a password-inaccessible demo account and session | No; only available in demo mode | None | `200`: user fields above; sets auth cookies. `404` when demo mode is off |
| POST | `/api/auth/logout` | Revoke the current session and clear cookies | Yes | No body; CSRF header and cookie required for cookie auth | `200`: `{"message":"Logged out successfully."}` |
| GET | `/api/auth/me` | Return the current user's profile | Yes | None | `200`: user fields above; `401` without a valid session |
| GET | `/api/auth/csrf` | Issue/refresh a CSRF token | Yes | None | `200`: `csrf_token`, `message`; also sets the CSRF cookie |
| POST | `/api/datasets/upload` | Upload a CSV directly through the API (local-storage flow) | Yes | `multipart/form-data`: `file` | `201`: dataset detail fields plus `preview_rows`. Returns `410` when remote object storage is configured; use authorization/finalization instead |
| POST | `/api/datasets/upload/authorize` | Reserve a dataset and authorize direct object-storage upload | Yes | JSON: `filename`, `size_bytes` | `201`: `dataset_id`, `upload_url`, `expires_in_seconds`, `required_headers` |
| POST | `/api/datasets/{dataset_id}/finalize` | Verify a direct upload and make the dataset available | Yes | Path: `dataset_id`; no body | `200`: dataset detail fields plus `preview_rows` |
| DELETE | `/api/datasets/{dataset_id}/upload` | Cancel a pending upload | Yes | Path: `dataset_id`; no body | `204`: no response body |
| GET | `/api/datasets` | List the current user's ready datasets | Yes | None | `200`: `total`, `items` (dataset response fields) |
| GET | `/api/datasets/{dataset_id}` | Get owned dataset metadata and preview | Yes | Path: `dataset_id` | `200`: dataset response fields plus `preview_rows`; `403` if not owned |
| POST | `/api/datasets/{dataset_id}/analyze` | Run quality analysis on an owned, ready dataset | Yes | Path: `dataset_id`; no body | `201`: `id`, `dataset_id`, `user_id`, `overall_score`, `summary_stats`, `column_scores`, `issues`, `recommendations`, `created_at` |
| GET | `/api/datasets/{dataset_id}/analyses` | List quality analyses for an owned dataset | Yes | Path: `dataset_id`; query `skip` (default `0`), `limit` (default `50`, capped at `100`) | `200`: `total`, `items` (analysis responses) |
| GET | `/api/analyses/{analysis_id}` | Get one owned quality analysis | Yes | Path: `analysis_id` | `200`: analysis response fields |
| POST | `/api/datasets/{dataset_id}/clean/preview` | Preview a cleaning pipeline without saving changes | Yes | Path: `dataset_id`; JSON: `config`, optional `preview_limit` (default `10`, range `1–50`) | `200`: `dataset_id`, `summary`, `original_preview`, `cleaned_preview`, `columns` |
| POST | `/api/datasets/{dataset_id}/clean` | Apply cleaning and save a separate cleaned output | Yes | Path: `dataset_id`; JSON: `config` | `201`: cleaning record fields including `id`, `dataset_id`, `status`, output metadata, `cleaning_summary`, `cleaning_config`, `created_at` |
| GET | `/api/datasets/{dataset_id}/cleanings` | List cleaning history for an owned dataset | Yes | Path: `dataset_id`; query `skip` (default `0`, minimum `0`), `limit` (default `50`, range `1–100`) | `200`: `total`, `items` (cleaning record responses) |
| GET | `/api/cleanings/{cleaning_id}` | Get one owned cleaning record | Yes | Path: `cleaning_id` | `200`: cleaning record fields |
| GET | `/api/cleanings/{cleaning_id}/download` | Download the cleaned CSV with formula-safe export enabled by default | Yes | Path: `cleaning_id`; query `export_safe` (default `true`) | `200`: CSV attachment for local storage; with remote storage, JSON `download_url` and `filename` |

`dataset_id`, `analysis_id`, and `cleaning_id` are integer path parameters. Dataset response fields include `id`, `user_id`, `original_filename`, file size, row/column counts, column metadata, cleaned-version metadata, and timestamps. The upload authorization flow returns a short-lived URL for a separate `PUT` to object storage; that `PUT` is not a FastAPI route.

The cleaning `config` accepts enabled whitespace cleaning, text normalization, missing-value handling, type conversions, duplicate removal, and outlier handling. At least one operation must be enabled. For example:

```http
POST /api/datasets/12/clean/preview
Content-Type: application/json
```

```json
{
  "config": {
    "whitespace_cleaning": {
      "enabled": true,
      "trim_whitespace": true
    }
  },
  "preview_limit": 10
}
```

The preview response has the following shape (row and summary values depend on the input CSV):

```json
{
  "dataset_id": 12,
  "summary": {
    "rows": {"before": 100, "after": 100, "difference": 0},
    "columns": {"before": 1, "after": 1, "difference": 0},
    "missing_cells": {"before": 0, "after": 0, "difference": 0},
    "duplicate_rows": {"before": 0, "after": 0, "difference": 0},
    "operations_applied": [{
      "operation": "whitespace_cleaning",
      "description": "Cleaned whitespace across 1 columns (trim=True, collapse=False).",
      "changes_count": 1,
      "details": {"columns": ["name"], "trim": true, "collapse": false}
    }],
    "warnings": [],
    "skipped_operations": [],
    "configuration_used": {
      "whitespace_cleaning": {
        "enabled": true,
        "columns": null,
        "trim_whitespace": true,
        "collapse_internal_whitespace": false
      },
      "text_normalization": null,
      "missing_values": null,
      "type_conversions": null,
      "duplicate_removal": null,
      "outlier_handling": null
    }
  },
  "original_preview": [{"name": "  Ada  "}],
  "cleaned_preview": [{"name": "Ada"}],
  "columns": ["name"]
}
```

Account creation uses this request and returns the user response described above:

```http
POST /api/auth/register
Content-Type: application/json
```

```json
{"username":"ada","email":"ada@example.com","password":"example-password"}
```

```json
{
  "id": 1,
  "username": "ada",
  "email": "ada@example.com",
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

For direct-to-object-storage deployments, reserve the dataset first:

```http
POST /api/datasets/upload/authorize
Content-Type: application/json
```

```json
{"filename":"customers.csv","size_bytes":2048}
```

```json
{
  "dataset_id": 12,
  "upload_url": "<short-lived signed PUT URL>",
  "expires_in_seconds": 300,
  "required_headers": {"Content-Type": "application/octet-stream"}
}
```

`300` is the configured default TTL and may be changed by backend configuration. Send the CSV bytes with `PUT` to `upload_url` using `required_headers`, then call `POST /api/datasets/12/finalize` with the authenticated session to validate and publish it.

The OpenAPI UI and schema are FastAPI-generated at `/docs`, `/redoc`, and `/openapi.json` on the backend origin (also `/docs/oauth2-redirect` for the docs UI). The combined root Vercel rewrite sends non-`/api` paths to the frontend, so these URLs may not be reachable through the combined frontend hostname. There is no settings API route registered; the Settings page uses the authenticated profile and frontend display data.

### Temporary presentation demo

Demo mode is disabled by default. To enable it locally, set `DEMO_MODE=true` in the backend `.env` and `VITE_DEMO_MODE=true` in the frontend environment before starting/rebuilding the apps. The first unauthenticated visit creates a separate, random demo account and an ordinary HTTP-only session; API authentication, CSRF, and per-user ownership checks remain active. Each new browser without a valid session gets its own isolated account. Login and registration endpoints are unavailable while backend demo mode is enabled.

To disable the feature, set both flags to `false` (or remove them) and restart the backend/rebuild the frontend. On Vercel, configure `DEMO_MODE=true` only for the backend and `VITE_DEMO_MODE=true` for the frontend, then redeploy both projects; turn both off and redeploy to disable it. Vite flags are public build-time settings, not secrets.

**Security warning:** enabled demo mode grants public visitors access to create demo accounts and use the application's data-processing features. Use isolated demo database/storage resources and non-sensitive sample data. Do not enable this on a production deployment containing real user data without explicitly accepting the exposure and abuse risks.

### Tests and local checks

Backend commands run from `backend` with its virtual environment:

```powershell
python -m pytest
python -m alembic history
python -m alembic current
```

Use a fresh disposable database migrated to head for the full backend suite. Do not run fixture-mutating tests against production data. Frontend commands from `frontend`:

```powershell
npm test -- --run
npm run lint
npm run build
```

## Deployment

For Vercel project setup, provider configuration, the complete environment-variable matrix, migrations, security, retention and deployment verification steps, see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

`render.yaml` remains a separate Render option with its own persistent disk and migration pre-deploy command. Render is not required for the Vercel path.

## Limits and operational notes

- Serverless analysis uses Pandas to materialize and parse the entire CSV; 1–5 MB is a conservative configurable upload cap, not a proven guarantee that every wide or adversarial CSV will fit function memory/time. Benchmark representative workloads before production. Larger or unpredictable workloads need a persistent worker/compute host.
- Pending uploads and temporary formula-safe exports require R2 lifecycle cleanup. Permanent originals and cleaned results need a documented retention/deletion policy and independent backups; database rows do not automatically delete permanent objects.
- Vercel frontend/API preview origins must be configured explicitly to match credentialed CORS and cookies. See the deployment guide before enabling previews.
- No provider account, resource, deployment, backup, migration against a provider, or production workload has been created or verified as part of this repository preparation.
