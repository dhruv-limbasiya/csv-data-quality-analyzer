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

For production, assign the frontend and API HTTPS origins under the same custom domain (for example, `app.<your-domain>` and `api.<your-domain>`). Separate default `*.vercel.app` hostnames are cross-site; browsers that block third-party cookies may otherwise prevent session cookies from reaching the API. Configure exact frontend origins and verify login, CSRF, and logout behavior before accepting users. The deployment guide covers Production and Preview domain setup.

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

For the two separate Vercel projects, provider setup, complete environment-variable matrix, migrations, security, retention and deployment verification steps, see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

`render.yaml` remains a separate Render option with its own persistent disk and migration pre-deploy command. Render is not required for the Vercel path.

## Limits and operational notes

- Serverless analysis uses Pandas to materialize and parse the entire CSV; 1–5 MB is a conservative configurable upload cap, not a proven guarantee that every wide or adversarial CSV will fit function memory/time. Benchmark representative workloads before production. Larger or unpredictable workloads need a persistent worker/compute host.
- Pending uploads and temporary formula-safe exports require R2 lifecycle cleanup. Permanent originals and cleaned results need a documented retention/deletion policy and independent backups; database rows do not automatically delete permanent objects.
- Vercel frontend/API preview origins must be configured explicitly to match credentialed CORS and cookies. See the deployment guide before enabling previews.
- No provider account, resource, deployment, backup, migration against a provider, or production workload has been created or verified as part of this repository preparation.
