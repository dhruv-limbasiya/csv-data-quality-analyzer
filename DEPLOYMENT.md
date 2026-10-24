# Deployment preparation (not deployed)

## Provider configuration

- **Vercel frontend:** set the project root to `frontend`, build command to `npm run build`, and output directory to `dist`. No Vercel environment variables are required: the frontend makes relative `/api` requests. `frontend/vercel.json` proxies those requests to Render so browser cookies remain same-origin.
- **Render backend:** `render.yaml` sets root directory `backend`, build command `pip install -r requirements.txt`, pre-deploy migration command `alembic upgrade head`, start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, and health check `/api/health`.
- The Render blueprint names the service `csv-data-quality-api`, which suggests `https://csv-data-quality-api.onrender.com`; however, that hostname is **not confirmed as an active service URL**. A public check on 2026-10-24 resolved it but returned `404` with `x-render-routing: no-server`. Do not treat DNS resolution or the configured name as proof. After creating/provisioning the Render service, copy its assigned HTTPS URL from the Render dashboard and use that exact host in `frontend/vercel.json`. No Render account/service metadata is available in this repository to establish the final assigned hostname.
- Set Render's `ALLOWED_ORIGINS` to exactly the final Vercel HTTPS origin, without a path. Do this after the Vercel project hostname is known.

## Required Render environment variables

| Variable | Required value |
| --- | --- |
| `DATABASE_URL` | Render PostgreSQL `connectionString`; a `postgres://` URL is normalized to SQLAlchemy's `postgresql://`. |
| `SECRET_KEY` | Unique generated value, at least 32 characters; never commit or print it. |
| `CSRF_SECRET` | Separate unique generated value, at least 32 characters; never commit or print it. |
| `ENVIRONMENT` | `production`. |
| `ALLOWED_ORIGINS` | One exact frontend origin, e.g. `https://<your-project>.vercel.app`. |
| `COOKIE_SAMESITE` | `lax`, for the same-origin Vercel API proxy. |
| `UPLOAD_DIR` | `/var/data/uploads`. |
| `CLEANED_DIR` | `/var/data/cleaned`. |
| `MAX_UPLOAD_SIZE_MB` | `50` unless the upload limit and disk capacity are reviewed together. |

`render.yaml` supplies all of these: it generates the two secrets through Render and injects the PostgreSQL connection string; it does not contain secret literals. Enter only the final Vercel origin for `ALLOWED_ORIGINS`. Render supplies `PORT` to the start command. `SESSION_COOKIE_NAME` and `CSRF_COOKIE_NAME` are optional and default to `session_id` and `csrf_token`; `ACCESS_TOKEN_EXPIRE_MINUTES` is optional and defaults to 1440. Production startup rejects short secrets, identical secrets, non-PostgreSQL URLs, localhost/wildcard/multiple/non-HTTPS CORS origins, non-Lax cookies, and relative upload/cleaned paths. Production cookies are Secure; Vercel and Render must both use HTTPS. Never paste secret values into chat, source control, or deployment documentation.

The frontend always uses relative `/api` requests; it does not read a build-time API URL. Local Vite development proxies `/api` to `http://localhost:8000`, while Vercel uses the checked-in same-origin rewrite.

## Storage and scaling constraints

Uploaded originals and cleaned results are stored as local files. Render's persistent disk is mounted at `/var/data` to preserve both directories across restarts/deploys. This disk is attached to a single service instance: keep the backend single-instance and do not enable multiple instances/autoscaling with this storage implementation. Configure separate backups and retention for important files and the database; this blueprint does not establish a backup policy.

## Database migration

The migration chain is linear: `001_initial_schema` -> `002_add_cleaning_records` -> `003_add_user_sessions`. Fresh databases are migrated by the configured pre-deploy command. The migrations are additive and do not reset or drop application data. Before applying to an existing database, take a provider backup and verify its current revision. Do not use `stamp`, downgrade, or database reset as a substitute for migrations.

## Beginner deployment procedure (not yet performed)

1. **Create the PostgreSQL database and backend on Render.** Sign in to Render, create a Blueprint instance from this repository, and review the database (`csv-data-quality-db`) and web service (`csv-data-quality-api`) resources before approving creation. Keep the database private and use the blueprint's `DATABASE_URL` database connection reference; do not copy it into source files or chat.
2. **Review Render settings before provisioning.** Confirm the backend root/build/pre-deploy/start/health commands above. Confirm the persistent disk mount is `/var/data`, `UPLOAD_DIR=/var/data/uploads`, and `CLEANED_DIR=/var/data/cleaned`; both data directories are under that mount. Keep one backend instance because uploaded and cleaned files are local to its disk.
3. **Set the Render environment.** The blueprint provides `ENVIRONMENT`, generated `SECRET_KEY` and `CSRF_SECRET`, `DATABASE_URL`, `COOKIE_SAMESITE`, storage paths, and upload limit. After Vercel has a final hostname, set `ALLOWED_ORIGINS` to exactly `https://<your-project>.vercel.app` (or the exact custom HTTPS origin). Check in Render's dashboard that the two generated secrets are distinct; do not reveal or copy them.
4. **Provision and verify the backend.** After approving the Render resources, copy the service's assigned HTTPS URL from its dashboard. Check `/api/health` returns 200 with PostgreSQL available. Confirm the deployment migration reaches `003_add_user_sessions`. For an existing database, take a backup and check its current Alembic revision first; the pre-deploy command must not be run against an unreviewed database.
5. **Set up Vercel.** Import the same repository, set project root to `frontend`, build command to `npm run build`, and output directory to `dist`. No Vercel environment variables are needed for the current relative `/api` frontend.
6. **Match the Vercel rewrite to Render.** Compare the Render dashboard's exact HTTPS service URL with the destination in `frontend/vercel.json`. If they differ, update the rewrite to use the dashboard hostname and keep the `/api/$1` suffix. Do not guess a hostname from the Render service name.
7. **Deploy Vercel and align CORS.** Once the Vercel URL is final, set Render `ALLOWED_ORIGINS` to that exact HTTPS origin without a trailing path, then deploy/redeploy the frontend and backend as needed. Use the same origin users will actually open, including a custom domain if applicable.
8. **Run the approval checks before real use.** Through the Vercel `/api` path, test health, login, CSRF-protected writes, logout and token replay, and cross-user download denial. Confirm browser cookies are Secure and the session cookie is HttpOnly. Upload a test CSV and confirm its original and cleaned output persist after a backend restart. Verify backups, retention, service plans, costs, and one-instance storage constraints.

## Current npm audit finding

`npm audit --json` was run on 2026-10-24 in `frontend`. It reports **3 moderate package findings, with no high or critical findings**: `postcss-nested@6.2.0`, `postcss-selector-parser@6.1.5`, and `tailwindcss@3.4.19`. The underlying advisory is [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf), a potential CPU-exhaustion issue from quadratic parsing of flat selectors. The parser is included through the PostCSS/Tailwind dependency tree; npm reports Tailwind CSS 4.3.3 as the available remediation, which is a major upgrade. No forced upgrade was applied. Reassess compatibility and the current advisory status before production release.

## Approval checklist

- [ ] Copy the actual Render dashboard service URL and make `frontend/vercel.json` match it; the currently configured hostname has not been confirmed active.
- [ ] Set `ALLOWED_ORIGINS` to the final, exact Vercel HTTPS origin.
- [ ] Confirm the two provider-generated secrets are distinct and not exposed in logs.
- [ ] Confirm the backend uses the injected Render PostgreSQL URL.
- [ ] Confirm persistent storage is mounted and writable at `/var/data`; keep one backend instance.
- [ ] Confirm migrations reach `003_add_user_sessions`; back up any existing database first.
- [ ] Confirm `/api/health` returns HTTP 200 with a healthy DB and HTTP 503 when the DB is unavailable.
- [ ] Test login, CSRF-protected mutations, logout, captured-token replay, and cross-user authorization through the Vercel `/api` path.
- [ ] Confirm upload originals and cleaned outputs remain accessible after a backend restart.
- [ ] Verify production cookie attributes (`Secure`, session `HttpOnly`) in an HTTPS browser session.
- [ ] Review Vercel/Render plans, storage capacity, costs, backup, and retention settings.

No deployment, provider-resource creation, secret provisioning, or application-database migration was performed.
