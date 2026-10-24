# CSV Data Quality Analyzer

Inspect, assess, and clean CSV datasets through a secure web application. Upload a dataset, review actionable quality findings, preview cleaning operations, and download a safer cleaned copy.

> **Original files are preserved.** Cleaning creates a separate output; it does not silently overwrite the uploaded CSV.

## Features

- **Secure accounts** — Registration and login with HTTP-only session cookies, server-side session revocation, and CSRF protection.
- **CSV inspection** — Upload CSV files, view dataset metadata, and preview rows.
- **Quality analysis** — Identify missing values, duplicate rows, invalid formats, negative values, and constant columns.
- **Data cleaning** — Configure transformations, preview their effects, apply them, and review cleaning history.
- **Safer exports** — Cleaned CSV downloads protect against spreadsheet formula injection by default.
- **Private datasets** — Dataset and download access is restricted to the owning user.

## Architecture

| Component | Implementation |
| --- | --- |
| Frontend | React, Vite, React Router, Axios, Tailwind CSS, Recharts |
| Backend API | Python, FastAPI, SQLAlchemy, Pydantic |
| Data processing | Pandas, NumPy |
| Database | PostgreSQL with Alembic migrations |
| Automated tests | pytest, HTTPX, Vitest |

```text
.
├── backend/
│   ├── alembic/       # Database migrations
│   ├── app/           # API, models, authentication, and processing services
│   ├── tests/         # Backend tests
│   └── requirements.txt
├── frontend/
│   ├── src/           # React pages, components, and API services
│   ├── package.json
│   └── vercel.json    # Current frontend API rewrite configuration
├── render.yaml        # Render backend/database blueprint
└── DEPLOYMENT.md      # Deployment configuration and readiness checklist
```

## Requirements

- Python 3.12 or newer
- Node.js 20.19+ or 22.12+
- PostgreSQL 14 or newer
- Git

## Local development on Windows

The frontend and backend run in separate terminals. Start PostgreSQL first and create or select the database you intend to use.

### 1. Set up the backend

From the repository root, open PowerShell:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend\.env` with the local PostgreSQL `DATABASE_URL` and two different, randomly generated values for `SECRET_KEY` and `CSRF_SECRET`. Keep this file private; it is ignored by Git. Do not use placeholder secrets outside local development.

Before changing an existing database, verify that `DATABASE_URL` points to the intended database and take a backup. Then apply the available migrations:

```powershell
python -m alembic upgrade head
```

Start the API and leave this terminal running:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Set up the frontend

Open a second PowerShell terminal from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite, typically <http://localhost:5173/>. The frontend makes relative `/api` requests, and the Vite development proxy forwards them to FastAPI on port `8000`.

### Verify the local API

Open <http://127.0.0.1:8000/api/health>. A healthy response includes `"status":"ok"` and `"database":"healthy"`. Interactive API documentation is available at <http://127.0.0.1:8000/docs>.

## Troubleshooting

- **Vite reports `ECONNREFUSED` for `/api/...`:** Start the backend in its own terminal and confirm it is listening on port `8000`.
- **Health returns HTTP 503:** Confirm PostgreSQL is running and the backend's `DATABASE_URL` points to the intended database.
- **Registration returns HTTP 500:** Check the backend terminal for the server-side error and verify the database migration revision with `python -m alembic current`. Current session-backed authentication requires `003_add_user_sessions`.
- **A port is already in use:** Stop the process using that port or update the backend port and Vite proxy together.

## Development commands

Run backend commands from `backend` with its virtual environment activated:

```powershell
python -m pytest
python -m alembic current
```

Run frontend commands from `frontend`:

```powershell
npm test
npm run lint
npm run build
```

Use a dedicated, disposable test database for backend tests. Do not point test fixtures at a database containing application data.

## API overview

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Register an account and establish a session |
| `POST` | `/api/auth/login` | Authenticate with a username or email |
| `POST` | `/api/auth/logout` | Revoke the active session |
| `GET` | `/api/auth/me` | Return the authenticated user's profile |
| `GET` | `/api/auth/csrf` | Obtain a CSRF token |
| `POST` | `/api/datasets/upload` | Upload and inspect a CSV dataset |
| `GET` | `/api/datasets` | List the current user's datasets |
| `POST` | `/api/datasets/{dataset_id}/analyze` | Analyze dataset quality |
| `POST` | `/api/datasets/{dataset_id}/clean/preview` | Preview cleaning operations |
| `POST` | `/api/datasets/{dataset_id}/clean` | Apply cleaning and save a separate result |
| `GET` | `/api/cleanings/{cleaning_id}/download` | Download the cleaned CSV |
| `GET` | `/api/health` | Check API and database health |

Authenticated write requests use CSRF protection. Dataset and download routes enforce user ownership.

## Data storage and security

In local development, uploaded originals and cleaned outputs use the directories configured by `UPLOAD_DIR` and `CLEANED_DIR`. Keep user files and generated datasets out of source control.

Production requires PostgreSQL, unique environment-provided secrets, HTTPS, secure cookies, an exact allowed frontend origin, and durable storage for both uploaded and cleaned files. Review [DEPLOYMENT.md](./DEPLOYMENT.md) before provisioning or deploying. The deployment checklist records provider-specific configuration and outstanding readiness checks; the presence of configuration files alone does not mean the application has been deployed or provider settings verified.
