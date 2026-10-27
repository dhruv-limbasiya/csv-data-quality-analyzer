# Vercel Deployment Guide

**Preparation only. No provider resources were created, account settings changed, migration run against a provider database, deployment performed, or production data tested.** Follow the steps below in a staging environment before opening the application to real users.

## Reported production 500s: diagnosis and recovery

The public, unauthenticated `GET /api/auth/me` and `GET /api/health` were checked on 2026-10-27 and both returned HTTP 500. No Vercel project access, runtime logs, environment values, or database access were available, so the exact production exception and deployment configuration cannot be established here. No authenticated login request was sent. The unauthenticated `/api/auth/me` path should return 401 before querying the database; its 500 therefore points first to a function import/startup failure or a request routed to something other than the expected FastAPI app, rather than to a bad username/password.

Repository-specific checks:

- The root `vercel.json` is a **single Vercel Services project** configuration: `/api` and `/api/...` are routed to its `backend` service, and other paths to `frontend`. This route is valid only when deploying the repository root as the combined project.
- For the two-project setup described below, set the backend project's Root Directory to `backend` and the frontend project's Root Directory to `frontend`. The frontend's own `vercel.json` intentionally does **not** proxy `/api`; its production build must have `VITE_API_BASE_URL` set to the backend HTTPS origin. If this variable is omitted or points to the wrong host, API requests can reach the static frontend and return 404. The root Services config and independent project setup are alternatives; do not combine their assumptions.
- `app.config` constructs `Settings` at import time and requires `DATABASE_URL`, `SECRET_KEY`, and `CSRF_SECRET`. Missing/invalid values prevent the FastAPI module from loading and can surface as 500s for every backend route. A valid import does not prove database connectivity or that migrations are current.
- `GET /api/auth/me` with no session should return 401 without database access. With a session, it reads `user_sessions` and the user record. Login queries the user table and writes a server-side session; if the database is unavailable or the existing Alembic chain is not applied, login can fail during either operation. Login now returns a generic 503 for SQLAlchemy failures rather than an unhandled 500; this does not repair connectivity/schema problems.

To identify the deployed cause, an operator with authorized Vercel access should inspect the **Function Logs** for the backend deployment at the timestamps of the 500 responses and provide only the exception type, failing module/file and line, and sanitized SQLAlchemy error class/message (remove hostnames, usernames, database names, URLs, query parameters, and all values). The decisive signals are: settings/Pydantic validation at import (check required variable *presence*, not values); module/dependency import failure; `OperationalError`/connection or TLS/allowlist failure; or undefined table/column indicating migration drift. Also verify the actual project's Root Directory and deployed commit, and for separate projects confirm that the built frontend's public `VITE_API_BASE_URL` matches the backend origin and the backend `ALLOWED_ORIGINS` matches the exact frontend origin. Do not copy environment values, presigned URLs, cookies, or full connection strings into tickets or chat.

After correcting only the confirmed issue, deploy a Preview with isolated resources first. Check `/api/health` (200, database healthy), unauthenticated `/api/auth/me` (401), and then perform registration, duplicate registration, login, authenticated `/me`, logout/revocation using a disposable account. If the traceback indicates schema drift, inspect Alembic current/history and use the controlled, backed-up migration procedure in section 7; never migrate production automatically or use destructive schema commands. No deployment or production change was made during this investigation.

## 1. Deployment architecture and request/data flow

Create two independent Vercel projects from this repository:

```text
Browser ── frontend origin ──> Vercel static React/Vite project
   │
   ├── credentialed HTTPS API calls + host-only session cookie
   │                               └──> separate Vercel FastAPI Python Function
   │                                       ├── Neon PostgreSQL (pooled URL)
   │                                       └── Cloudflare R2 private bucket
   └── short-lived signed PUT/GET ───────────────> R2 (CSV bytes bypass Functions)
```

- The frontend API client uses public build-time `VITE_API_BASE_URL`; it is **not** a proxy or a relative `/api` request in production. Vite's local `/api` proxy remains for development.
- API cookies are HTTP-only, `Secure`, `SameSite=None` and host-only on the API origin. The frontend enables credentials and keeps the CSRF response token in memory because JavaScript on the frontend origin cannot read an API-origin cookie. The API accepts one explicitly configured HTTPS frontend origin in production. CSRF remains required on state-changing authenticated requests.
- Use custom HTTPS domains under the same registrable domain for the two projects (for example, `app.<your-domain>` and `api.<your-domain>`). Their origins remain distinct for CORS, but are same-site for cookie policy. Separate default `*.vercel.app` domains are cross-site, and browser third-party-cookie blocking can break session authentication even with `SameSite=None`; do not use those defaults as the production login path. Use corresponding stable Preview domains and isolated Preview resources, or disable Preview.
- Upload authorization reserves a user-owned pending database row and returns a short-lived PUT URL for a unique private staging key. Finalization checks owner, expiry, reported and actual size, object metadata/ETag, parses the CSV, then conditionally promotes the exact verified staging object. It is designed to return the already-finalized dataset on repeated completion. A cancel route is provided. Missing objects, invalid CSVs, provider failures, and expired requests return errors rather than a ready dataset.
- Original CSV and permanent cleaned output objects remain private in R2. The API issues a short-lived download URL only after ownership checks. Where formula-safe output is needed for export, the generated downloadable copy is stored under `exports/`; this is temporary and should be removed by lifecycle rules.
- Local temporary files are used only during a single API operation to let the current Pandas code read/write files; they are removed and are not persistent storage. The existing quality-analysis and cleaning pipeline is retained and original files are not overwritten.

## Temporary presentation demo mode

Demo mode is **off by default**. Enable both flags only when intentionally preparing a presentation:

- Backend: `DEMO_MODE=true`
- Frontend build: `VITE_DEMO_MODE=true`

For local development, set `DEMO_MODE=true` in `backend\.env`, set `VITE_DEMO_MODE=true` in `frontend\.env.local`, then restart FastAPI and Vite. Remove either setting or set it to `false` to disable its side; normal authenticated behavior resumes when the backend flag is false.

For Vercel, set `DEMO_MODE=true` in the backend project's environment and `VITE_DEMO_MODE=true` in the frontend project's environment, then redeploy both projects so the backend runtime and Vite build use matching flags. Disable by setting both to `false` (or removing them) and redeploying both. Do not place secrets in `VITE_*` variables; Vite exposes them to every browser.

The frontend creates a demo session automatically. The API creates a separate random user for each new unauthenticated browser session; the resulting HTTP-only session uses the normal CSRF checks and ownership checks. Datasets are not shared across demo accounts. The backend login and registration endpoints return 404 while demo mode is enabled. No migration or hardcoded credential is required.

**Security warning:** demo mode is a public feature, not an access-control boundary. Visitors can create demo accounts and consume database, function, and object-storage resources. Use only a separate demo database/storage account containing non-sensitive sample data. Do not enable it against production user data unless you explicitly accept the exposure and abuse risks. This change does not enable the flag in any deployment.

## 2. Important limits and workload fit

Current official Vercel documentation describes a **4.5 MB request and response body limit** for Vercel Functions; the configured Python entrypoint allows up to 300 seconds. The limits page currently lists Hobby memory at 2 GB, Pro/Enterprise at 4 GB, and Python bundle size up to 500 MB uncompressed. Limits and account-specific features can change; confirm the current plan and function configuration before deployment. See [Vercel Function limits](https://vercel.com/docs/functions/limitations), [Python runtime](https://vercel.com/docs/functions/runtimes/python), and [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi).

CSV file bodies and downloads therefore bypass Vercel Functions through direct-to-R2 signed URLs. The current cap is **1–5 MB** (set backend `MAX_UPLOAD_SIZE_MB` and frontend `VITE_MAX_UPLOAD_SIZE_MB` consistently; both safe examples use 5 MB). It is deliberately conservative, not a verified guarantee of serverless execution: Pandas parses a full in-memory DataFrame, wide columns and pathological input can consume disproportionate memory/time, and API JSON previews/results are also function responses. No representative production workload benchmark has been run. Load-test with representative data on the selected Vercel plan. For larger, wider, or long-running processing, use a persistent non-serverless worker/compute host rather than increasing the cap without measurement.

Do not upload datasets through a Vercel API request or persist files on function-local disk. Vercel's supported Python runtime runs the app as Functions; use object storage for durable user files. Vercel configuration excludes development-only files and sets the currently documented Python entrypoint through `backend/pyproject.toml`.

## 3. Provider selection, quotas, and costs

These figures were checked against official provider pages on 2026-10-26. They are published plan allowances/rates, **not a promise of zero-cost production**. Recheck provider pricing, plan terms, quotas, regional availability, and privacy requirements before account creation. Set spending notifications where available; monitor storage, operations, database compute, and function use.

### Cloudflare R2 Standard (private object storage)

Current official [R2 pricing](https://developers.cloudflare.com/r2/pricing/) lists 10 GB-month storage, 1 million Class A operations, 10 million Class B operations, and internet egress free per month for Standard storage. Above the free allowance, listed rates are $0.015/GB-month, $4.50/million Class A operations, and $0.36/million Class B operations. No internet egress fee is listed. Class A includes writes/copies; Class B includes reads/HEAD. Lifecycle and CORS configuration are additional setup steps; lifecycle cleanup itself is provider-managed. The [R2 lifecycle documentation](https://developers.cloudflare.com/r2/buckets/object-lifecycles/) says expiration may take up to about 24 hours and can take longer.

The implementation uses R2's S3-compatible API with the Python AWS SDK and [presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/). R2 documents that a signed URL is a bearer capability and can be reused until expiration. Here the URL is limited to a specific key and `PUT` or `GET`, defaults to five minutes, and cannot enforce the declared byte size before the upload. Finalization rejects an actual size mismatch or size above the configured cap, but an oversized upload may consume temporary storage/operations before rejection. Configure lifecycle expiry on `staging/` and `exports/`; monitor usage and protect authorization/finalization endpoints against abuse. A lifecycle policy is not configured by code and must be added manually.

### Neon PostgreSQL

Neon's current [plans page](https://neon.com/docs/introduction/plans) lists Free at $0 with 100 CU-hours per project, up to 2 CU (8 GB RAM) autoscaling, 1 GB per project (20 GB account total), 5 GB public transfer/project and one manual snapshot. Launch is pay-as-you-go, with listed $0.106/CU-hour, $0.35/GB-month storage, 500 GB public transfer/project included, and spending notifications. Free compute scales to zero after five minutes. Plan caps and billing semantics can change; a production application may need Launch or another paid provider plan. A one-time snapshot and limited history are not a substitute for independent backups.

Use the Neon **pooled** connection string for serverless API invocations; the engine is configured with one connection per warm process and no overflow. Use the **direct** connection string for controlled Alembic migrations. See [Neon connection pooling](https://neon.com/docs/connect/connection-pooling). Choose Neon region near the API region; avoid unnecessary cross-region latency and check region/plan restrictions. No Neon project exists yet.

### Vercel

Vercel currently lists Hobby at $0/month and Pro at $20/month, subject to plan terms and usage charges; see [Vercel pricing](https://vercel.com/pricing). Do not assume Hobby is appropriate for a commercial workload or that usage is free. Check the account's current eligibility and the pricing tables for function, bandwidth, build, and add-on usage before choosing a plan. Separate frontend and backend projects may count toward applicable account/project limits.

## 4. Required account/provider setup (manual)

No service credentials are stored in the repository. Create and configure all resources in the provider dashboards yourself:

1. Create a Neon PostgreSQL project in a region appropriate for the Vercel backend. Create isolated Production and Preview databases/projects (or otherwise prove Preview cannot touch Production). Enable provider backups/retention appropriate to the data, and record the recovery process.
2. Create a private Cloudflare R2 Standard bucket. Create a bucket-scoped API token/key with only required object read/write permissions; never use an account-wide credential if a narrower permission is available. Keep access key and secret solely in backend environment settings.
3. Configure bucket CORS for the exact frontend HTTPS origin(s) that will use direct signed PUT requests. Allow only `PUT` (and any specifically required method), allow the signed request's `Content-Type` header, and expose only response headers actually required. Do not set wildcard origins for credentialed app architecture. Test preflight and upload from a real browser origin before production.
4. Configure R2 lifecycle rules: expire objects with prefix `staging/` after 1 day and prefix `exports/` after 1 day. **Do not** expire `datasets/` or `cleaned/` without a deliberate retention policy and verified recovery. Lifecycle deletion is asynchronous; monitor staging orphans.
5. Choose custom HTTPS domains for the frontend and API under the same registrable domain before configuring production auth (for example, `app.<your-domain>` and `api.<your-domain>`). Add both domains to the corresponding Vercel projects and complete DNS verification. Create distinct stable Preview domains under that same registrable domain if Preview is needed; otherwise disable Preview until its origin/API/CORS mapping is explicit. Arbitrary per-commit Preview domains are not automatically added to backend `ALLOWED_ORIGINS`.
6. Generate two independent high-entropy secrets locally or in your secrets manager, each at least 32 characters. Enter them only in backend project environment settings. Never paste secrets, signed URLs, database URLs, or user data into chat, logs, tickets, or source control.
7. After the code deploy is prepared, run the additive migration against the selected **non-production/staging database first**. Production migration is an explicit reviewed operation, not a request-start action.

## 5. Environment-variable matrix

The `.env.example` files contain safe local placeholders. In Vercel, set backend variables only on the backend project and `VITE_*` variables only on the frontend project. Vite variables are public build-time values and are embedded in browser assets; never put secrets in them. Configure Production, Preview, and Development separately. Production and Preview should use different databases, buckets/keys, secrets and allowed origins. The frontend Development environment uses Vite locally and can leave `VITE_API_BASE_URL` blank.

| Variable | Purpose | Requiredness | Source/value | Secret/exposure safety | Project scope | Safe local placeholder |
| --- | --- | --- | --- | --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection | Required backend | Neon pooled URL for Vercel runtime; direct URL for manual migration session | **Secret**; never log, commit, or expose to frontend | Backend, each environment; migration operator environment separately | `postgresql://user:password@localhost:5432/csv_data_quality_analyzer` |
| `SECRET_KEY` | Signs server-side session tokens | Required backend | Generate unique random value, 32+ chars | **Secret**, distinct per environment | Backend | `local-only-change-this-to-a-random-secret` |
| `CSRF_SECRET` | Signs CSRF tokens | Required backend | Independently generate, 32+ chars and different from `SECRET_KEY` | **Secret**, distinct per environment | Backend | `local-only-use-a-different-random-secret` |
| `ENVIRONMENT` | Mode/secure production validation | Required backend | `production` in Vercel | Not secret | Backend | `development` |
| `ALLOWED_ORIGINS` | Exact browser origin for credentialed CORS and write-origin check | Required backend | Exactly one origin such as `https://app.<your-domain>` in production; no path, wildcard, or comma list | Public URL but security-sensitive | Backend per environment; Preview exact mapped origin | `http://localhost:5173` |
| `STORAGE_BACKEND` | Selects local or R2 storage adapter | Required backend | `r2` on Vercel; `local` only with local/persistent disk | Not secret | Backend | `local` |
| `COOKIE_SAMESITE` | Session cookie cross-origin behavior | Required backend Vercel | `none` with HTTPS; production frontend and API must use sibling custom domains under the same registrable domain | Not secret; `None` requires secure HTTPS cookies | Backend | `lax` |
| `MAX_UPLOAD_SIZE_MB` | API-side maximum CSV size | Required backend | Integer 1–5; align with frontend cap | Not secret | Backend | `5` |
| `R2_ACCOUNT_ID` | Builds R2 S3 endpoint | Required if `STORAGE_BACKEND=r2` | Cloudflare account identifier | Treat as backend-only configuration | Backend only | blank |
| `R2_BUCKET` | R2 bucket name | Required if R2 | Private bucket name for this environment | Backend-only config | Backend only | blank |
| `R2_ACCESS_KEY_ID` | R2 S3 API credential ID | Required if R2 | Bucket-scoped Cloudflare token | **Secret**, backend only | Backend only; separate Preview/Production | blank |
| `R2_SECRET_ACCESS_KEY` | R2 S3 API secret | Required if R2 | Paired bucket-scoped token secret | **Secret**, backend only | Backend only; separate Preview/Production | blank |
| `R2_PRESIGNED_URL_TTL_SECONDS` | Lifetime for scoped signed upload/download URL | Optional; default 300; production range 60–600 | Keep short (default `300`) | Not secret; signed URLs themselves are secret bearer tokens | Backend | `300` |
| `UPLOAD_DIR` | Local storage path only | Optional; not used for Vercel R2 | For Render, `/var/data/uploads` on attached persistent disk | Path only | Backend local/Render | `uploads` |
| `CLEANED_DIR` | Local storage path only | Optional; not used for Vercel R2 | For Render, `/var/data/cleaned` on attached persistent disk | Path only | Backend local/Render | `cleaned` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session expiry duration | Optional, default `1440` | Choose a deliberate duration | Not secret | Backend | `1440` |
| `SESSION_COOKIE_NAME` | Session cookie name | Optional, default `session_id` | Keep default unless coordinated | Not secret | Backend | `session_id` |
| `CSRF_COOKIE_NAME` | CSRF cookie name | Optional, default `csrf_token` | Keep default unless coordinated | Not secret | Backend | `csrf_token` |
| `VITE_API_BASE_URL` | API origin compiled into frontend | Required on Vercel frontend | Exact HTTPS API custom-domain origin under the same registrable domain as the frontend, e.g. `https://api.<your-domain>` | Public; not a credential | Frontend project; set per Preview/Production | blank (local Vite proxy) |
| `VITE_DIRECT_UPLOAD` | Enables R2 signed browser upload path | Required on Vercel frontend | `true` with matching R2-backed API | Public build-time flag | Frontend project per environment | `false` |
| `VITE_MAX_UPLOAD_SIZE_MB` | Frontend file-selection validation | Required/strongly recommended | Same integer cap as backend; 1–5 | Public build-time value | Frontend project per environment | `5` |

Backend additional settings with defaults (`PROJECT_NAME`, `VERSION`) do not require deployment overrides. `.env` files are for local use only and must never be uploaded to Vercel or committed. Do not place backend secrets in frontend variables, frontend source, or Vite `.env` files.

## 6. Vercel project configuration

### Backend API project

1. Import this repository as a new Vercel project.
2. Set **Root Directory** to `backend` (and include files outside the root only if Vercel explicitly requires them; application runtime is under `backend`).
3. Vercel should detect Python from `requirements.txt` and `pyproject.toml`. The root includes `.python-version` set to the documented Python 3.12 runtime, `pyproject.toml` with the pinned runtime dependencies and `tool.vercel.entrypoint = "app.main:app"`, and `vercel.json` with `app/main.py` function `maxDuration: 300`. Python runtime maps ASGI apps to Vercel Functions; this is not a persistent Uvicorn process. See [Python entrypoints and versions](https://vercel.com/docs/functions/runtimes/python) and [supported Python versions](https://vercel.com/docs/functions/runtimes/python/python-version).
4. Leave the **Build Command** at the Python runtime default unless Vercel dashboard requires a project-specific command. Do not run Uvicorn as a production start command. Runtime dependencies are declared in `pyproject.toml` and mirrored in `requirements.txt`; tests, migrations, and Uvicorn are in `requirements-dev.txt` and not installed as runtime requirements.
5. Assign the API project's Production custom domain under the same registrable domain as the frontend domain. Set the backend environment matrix above for Production and Preview. For Production set `ENVIRONMENT=production`, `STORAGE_BACKEND=r2`, `COOKIE_SAMESITE=none`, a 1–5 MB cap, an exact one-origin frontend `ALLOWED_ORIGINS`, pooled Neon `DATABASE_URL`, and backend-only R2 credentials. Use the corresponding isolated Preview resources and preview frontend origin. Do not enable Preview with Production database or storage credentials.
6. Deploy only after staging migration and provider configuration. Check `https://<backend-origin>/api/health`, expected HTTP 200 and a healthy database response. Do not expose `/docs` unnecessarily if it is not needed.

### Frontend project

1. Import the same repository as a second Vercel project.
2. Set **Root Directory** to `frontend`.
3. Build command: `npm run build`. Output directory: `dist`. Install command: default `npm install`/Vercel detection (lockfile-based) or `npm ci` if supported by project settings.
4. Assign the frontend project's Production custom domain under the same registrable domain as the API domain. Set frontend variables: `VITE_API_BASE_URL` to the corresponding API custom-domain HTTPS origin, `VITE_DIRECT_UPLOAD=true`, and `VITE_MAX_UPLOAD_SIZE_MB` equal to the backend cap. Set in the correct environment before building; Vite embeds these values.
5. The committed `frontend/vercel.json` rewrites the current client routes to `index.html` and adds security headers. It does **not** proxy `/api` to a placeholder provider; browser API calls go to `VITE_API_BASE_URL`, so API traffic cannot fall through to the React document.
6. In the backend environment, set `ALLOWED_ORIGINS` to the exact final frontend custom-domain origin, with scheme, no path or trailing route. Add or update it when the final custom domain changes.

### Preview and local deployment

- A credentialed API cookie is host-only to the API domain, not the frontend domain. The client sends credentials, obtains the CSRF JSON token from `/api/auth/csrf`, stores it in memory, and sends `X-CSRF-Token` on state changes. The recommended sibling custom domains are cross-origin but same-site; do not set `Access-Control-Allow-Origin: *`. Login on two unrelated default Vercel domains is not a supported production configuration because third-party-cookie blocking is outside the application's control.
- For Preview, decide a stable Preview frontend/API origin mapping first. Configure the backend's one-origin validation with the exact frontend origin and `VITE_API_BASE_URL` with that matching API. If arbitrary Vercel preview URLs cannot be mapped safely, disable Preview or use a fixed preview domain and isolated resources. Do not broaden origin validation to arbitrary subdomains.
- Local frontend runs with blank `VITE_API_BASE_URL`, `VITE_DIRECT_UPLOAD=false`, `VITE_MAX_UPLOAD_SIZE_MB=5`; local Vite proxies `/api` to FastAPI. The browser uses `http://localhost:5173` and backend development `ALLOWED_ORIGINS` may separately include the local origin. Local development never needs R2 credentials.

## 7. Database and migration procedure

The existing Alembic history is preserved and linear: `001_initial_schema` → `002_add_cleaning_records` → `003_add_user_sessions` → `004_dataset_upload_state`. Revision `004` adds status/expiry fields, uses a default of `ready` for existing rows, and does not reset or drop prior application data. Migration validation here used only a fresh isolated SQLite database. PostgreSQL behavior and provider deployment remain to be checked in staging.

Migrations do **not** run automatically at API import/request time. Runtime `requirements.txt` intentionally does not include Alembic; install `requirements-dev.txt` in a controlled operator environment.

Controlled procedure:

1. Select the exact target database and environment; verify the database identity and current revision using a direct Neon connection. Take a provider backup/snapshot and confirm restore access.
2. Use a private local operator environment or approved secret manager to supply the **direct** PostgreSQL URL (not the Vercel pooled connection URL). Never print it. From `backend`, install dev requirements and inspect history/current revision: `python -m alembic history` and `python -m alembic current`.
3. For staging, run `python -m alembic upgrade head`; verify `python -m alembic current` reports `004_dataset_upload_state`, then test auth, uploads, analysis, cleaning, and download.
4. Schedule and review the same controlled action for Production, after backup and compatibility review. Do not let Vercel run migrations per invocation. The schema adds backward-compatible defaults, but application/database rollback still requires an explicit reviewed plan.
5. Never run `alembic downgrade`, `stamp`, `drop`, reset, or any destructive SQL to work around a mismatch. Restore procedures should restore a consistent database-and-object-store state; a database restore alone can leave missing object references.

## 8. Security, upload, and operations limits

- Never log database URLs, access keys, cookies, CSRF tokens, complete presigned URLs, CSV rows, or raw exception content from storage/database clients. The current code emits generic provider errors and limited identifiers.
- Keep the R2 bucket private and allow browser origins narrowly. Keep API keys only in backend environment. Signed links are temporary bearer links; expiry does not prevent reuse before expiry.
- Signed PUT URLs do not cap the request body at the declared length. Finalization rejects actual size above the limit, but the object may already have been written. Rate limiting is not implemented in the app. Before public use, add rate/abuse controls for authentication and authorization endpoints, monitor provider cost/usage, limit account registration as appropriate, and test oversize-upload/orphan cleanup.
- Per-user pending upload count is limited in the API. Cancellation removes pending metadata/object where possible; expired staging objects should be swept by R2 lifecycle. A provider outage can leave temporary objects until retry/lifecycle. Orphan reconciliation requires an operational process; no scheduled worker currently exists.
- Finalization is designed to be idempotent; storage failure, missing object, invalid/empty/malformed CSV, expired authorization, and mismatched object metadata do not make the row ready. Repeat upload PUT before finalization can replace the staged key until URL expiry; conditional promotion verifies the ETag observed by the server.
- CORS does not replace authentication, authorization, CSRF, or rate limiting. Test credentialed browser requests, preflight, hostile origins, login/logout/expiry/revocation, owner isolation and authorized download using staging accounts.
- Database rows and object lifecycles are separate. There is currently **no user dataset deletion endpoint or complete retention/account-deletion workflow**. Do not promise deletion until object deletion, related records, backups, retention, and audit handling have been implemented and tested.

## 9. Backups, retention, deletion, rollback, and recovery

- Set a written retention period for `datasets/` and `cleaned/`, user-initiated deletion policy, and account deletion before production. The app currently stores these objects until a person/provider policy removes them. Never apply short lifecycle rules to permanent prefixes by accident.
- Configure R2 lifecycle only for `staging/` and `exports/` at one day initially; confirm bucket prefixes and observe a non-production test object expire. Provider lifecycle is asynchronous and may take longer than 24 hours.
- Configure independent PostgreSQL backups and verify restore on an isolated database. Neon Free's current published backup/history options are limited; move to an appropriate paid tier/backup strategy if recovery objectives require more.
- Maintain a separate backup/recovery plan for permanent R2 objects; test a small non-production restore. Database backup and object backup must be coordinated so restored dataset/cleaning records reference available objects.
- To delete orphaned/stale data, first identify keys and owner/database references, obtain approval, export a recovery manifest, then use provider tools in a reviewed, non-production rehearsal. Do not use broad recursive deletion without a reviewed prefix and backup.
- For application rollback, redeploy the previous Vercel code only after checking schema compatibility. Keep migration `004` in place unless a specifically reviewed recovery plan proves downgrade safe; do not delete migration history. For provider outage or data corruption, pause uploads/processing, preserve logs without secrets, restore database and object state from backups, validate owner isolation, and only then re-enable writes.

## 10. Preview and production verification checklist

Run these checks after configuration, first in Preview/staging:

- [ ] Backend and frontend deployments build with the correct independent root directories and no secret value appears in build output or browser assets.
- [ ] Health endpoint works; DB reports healthy; Alembic current revision matches expected head.
- [ ] Production settings reject missing/equal/short secrets, wrong DB type, wildcard/multiple origins, local origins, invalid cookie policy, incomplete R2 credentials, and upload caps outside 1–5.
- [ ] Registration/login, HTTP-only Secure session cookies, CSRF rejection/acceptance, logout revocation, expiry, and a second account's unauthorized dataset/download access behave correctly.
- [ ] R2 browser CORS preflight and signed PUT work only from configured frontend origin. Test cancel, expired signed URL, network/upload failure, zero/malformed CSV, actual oversize object, missing/incomplete object, repeated finalize, repeated analysis, and storage timeout.
- [ ] Test normal and formula-safe downloads; test R2 lifecycle rules using temporary test keys and verify permanent datasets/cleaned objects are not deleted.
- [ ] Test client route refresh and API errors with API origin unavailable; confirm no `/api` path returns `index.html`.
- [ ] Load-test with representative/wide CSVs and concurrency; measure function memory, CPU, duration, DataFrame peak memory, result JSON size, and cost. Use a persistent worker for unmeasured/oversized workloads.
- [ ] Verify backups and restore in isolated resources. Document actual RPO/RTO, retention, data deletion and incident contacts.

No Vercel build/deployment, R2 upload, Neon connection, browser-origin integration, provider backup/restore, or production workload was verified during repository preparation. These are external account-dependent gates.

## 11. Troubleshooting

| Symptom | Check |
| --- | --- |
| Frontend API network/CORS error | `VITE_API_BASE_URL`, API deployment availability, exact backend `ALLOWED_ORIGINS`, HTTPS scheme, credentials, and browser preflight. Never “fix” by using wildcard CORS. |
| Cookie absent or state change fails | Both origins HTTPS; backend `COOKIE_SAMESITE=none`; `Secure` HTTP-only session cookie; `withCredentials`; login/CSRF bootstrap; `X-CSRF-Token`; exact CORS origin. |
| R2 PUT fails in browser | Bucket CORS exact frontend origin, PUT method, signed `Content-Type`, URL not expired, bucket/account/token settings; do not paste signed URL into logs. |
| Upload finalization returns missing/mismatch | Confirm direct PUT completed, object key is unmodified, object size is within cap, signed URL was for that dataset, and R2 is reachable. Cancel/re-authorize after expiry; lifecycle may remove staging files. |
| API 500/503 with storage/database | Check provider status and environment-variable presence without printing values; test pooled runtime URL and direct migration URL separately. Check startup/config validation and generic server logs. |
| Function timeouts/memory failures | Reduce upload cap or processing scope. Current Pandas workflow loads entire CSV; use persistent worker/host for workloads beyond measured function budget. |
| Missing user file after DB restore | Object backup does not match restored DB point. Restore coordinated object data or mark broken references through a reviewed recovery procedure; do not silently treat local filesystem as durable. |
| Migration says no revision / unexpected schema | Stop; verify target DB and Alembic history/current, take backup, investigate. Do not stamp, downgrade, reset, or run against another environment. |

## 12. Separate non-Vercel option: Render

`render.yaml` remains independent and does not form part of the Vercel architecture. It describes a Render backend with Uvicorn, a managed PostgreSQL database, a persistent disk mounted at `/var/data`, a five-megabyte local upload limit, and `alembic upgrade head` as a separate pre-deploy command. Review Render's current plan cost, database and disk limits, backups, and pricing before provisioning; this blueprint does not make the Render service a dependency of Vercel.

For a separate Render + frontend deployment, use the same frontend's `VITE_API_BASE_URL` pointed to the Render HTTPS origin, keep `VITE_DIRECT_UPLOAD=false`, use `STORAGE_BACKEND=local`, and ensure `UPLOAD_DIR` and `CLEANED_DIR` are on the attached persistent disk. The API must use `COOKIE_SAMESITE=none`, `Secure` cookies, and the exact frontend origin. Be aware local disk storage means a single backend instance; scale-out requires shared object storage. Review Render's deployment migration and backup before approving. This option is not covered by the Vercel R2 configuration.

## Official provider references

- Vercel: [FastAPI](https://vercel.com/docs/frameworks/backend/fastapi), [Python runtime/entrypoint and dependencies](https://vercel.com/docs/functions/runtimes/python), [Python version](https://vercel.com/docs/functions/runtimes/python/python-version), [Function limits](https://vercel.com/docs/functions/limitations), [Pricing](https://vercel.com/pricing).
- Cloudflare: [R2 pricing](https://developers.cloudflare.com/r2/pricing/), [S3 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/), [R2 object lifecycles](https://developers.cloudflare.com/r2/buckets/object-lifecycles/), [CORS](https://developers.cloudflare.com/r2/buckets/cors/), [R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/).
- Neon: [Plans and billing](https://neon.com/docs/introduction/plans), [Connection pooling](https://neon.com/docs/connect/connection-pooling), [Backups](https://neon.com/docs/introduction/backup-restore).
