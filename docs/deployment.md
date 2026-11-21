# Deployment preparation and release gates

Audit date: 2026-11-20. The application has not been deployed to an external host.
For the selected Render route, follow [the Render deployment guide](render-deployment.md).
Use a dedicated MySQL/MariaDB database and a separate empty `tarot_reading_test`
database for integration tests. Never point test credentials at the main database.

## Free hosting route for the first release

An OCI Always Free Ubuntu VM is the practical single-host option for this
FastAPI + MariaDB application: run MariaDB, Uvicorn and the static Vite build on
one VM, with Nginx in front. Choose an **Always Free-eligible** compute shape in
the account's home region and keep CPU, memory and storage within the displayed
free allowance. OCI account creation can require a phone number and payment card;
free-shape capacity can be unavailable. Do not select a paid shape or upgrade the
account merely to complete this setup. Check the current
[OCI Always Free limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
before provisioning.

A public HTTPS hostname is still required for secure browser cookies. Use a
domain you control or a free subdomain such as [DuckDNS](https://www.duckdns.org/),
pointed at the VM's public IP. Only open ports 80 and 443 to the public; keep
MariaDB and Uvicorn on loopback. Follow the HTTPS and database rollout sections
below after the VM and hostname exist. Store production secrets on the VM, never
in GitHub. The GitHub workflow verifies code and assets but does not deploy or
need production credentials.

## Build and configuration

1. Install Python 3.11+ and Node.js compatible with Vite 6. Install backend
   dependencies from `backend/requirements.txt`, test dependencies from
   `backend/requirements-dev.txt`, and frontend dependencies with `npm ci`.
2. Copy `.env.example` to `backend/.env` for local development. For production,
   provide these values through the host's secret manager or private environment;
   do not copy credentials into the repository or frontend build:

   | Variable | Production value |
   | --- | --- |
   | `DATABASE_URL` | Dedicated `mysql+pymysql://.../tarot_reading?charset=utf8mb4` URL with a least-privilege app account. |
   | `SECRET_KEY` | Stable random string of at least 32 characters, shared by all API workers. |
   | `FRONTEND_ORIGINS` | Exact HTTPS origin, for example `https://tarot.example.com`; no wildcard. |
   | `COOKIE_SECURE` | `true`. |
   | `AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY`, `GEMINI_API_KEY` | `disabled` until an approved provider/model/key are available. Use `openai` with `AI_API_KEY` or `gemini` with `GEMINI_API_KEY`; set a model supported by that provider. |
   | `AI_TIMEOUT_SECONDS`, `AI_MAX_OUTPUT_TOKENS` | Set provider request bounds within application validation limits. |
   | `AI_DAILY_REQUEST_LIMIT`, `AI_ACCOUNT_DAILY_REQUEST_LIMIT`, `AI_GUEST_IP_DAILY_REQUEST_LIMIT` | Choose budgets before enabling paid AI. |
   | `AI_INPUT_USD_PER_MILLION`, `AI_OUTPUT_USD_PER_MILLION` | Set both only if estimated cost tracking is required and pricing has been verified. |
   | `SESSION_TTL_SECONDS`, `AUTH_ATTEMPT_LIMIT`, `AUTH_WINDOW_SECONDS`, `GUEST_READING_RETENTION_DAYS`, `REVERSED_CARDS_ENABLED` | Review policy values; see `.env.example`. |

3. Copy `frontend/.env.example` to `frontend/.env.production` if a frontend
   override is needed. `VITE_API_BASE_URL=/api` is the public, build-time default.
   Keep the frontend and API on one HTTPS origin. Never put secrets in `VITE_*`.
4. From `frontend/`, run `npm run build`; serve `frontend/dist/` as static files.
   Configure the host to send unknown non-API paths to `index.html` so refreshes
   on `/result/:id` and other React routes work.

## Database rollout

Back up the main database and confirm restore procedure. On a fresh installation,
create the empty database using `database/documentation/create_database.sql`.
That SQL also creates the empty test database; omit the test database on a host
where tests are run elsewhere. On an existing installation, do not re-import a
schema dump or reset the database. Pause application writes before migrating.

From `backend/`, review `python -m alembic upgrade head --sql`, then run
`python -m alembic upgrade head`. Confirm `python -m alembic current` reports
`0004_accounts (head)`. From the repository root, run
`python -m database.seeds.seed --check-only`, then
`python -m database.seeds.seed` to add/update reference data. Run
`python -m database.assets.validate` to check all 78 files, provenance and live
database image references. Use a DB account with migration rights for rollout;
the app runtime account needs only the required table operations.

## HTTPS host

Terminate TLS at a trusted reverse proxy. Serve the static frontend at `/` and
proxy `/api/` to Uvicorn on private loopback port 8000 without stripping `/api`.
For example, an Nginx site can use:

```nginx
server {
    listen 443 ssl;
    server_name tarot.example.com;
    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;
    root /srv/tarot/frontend/dist;
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    location / { try_files $uri $uri/ /index.html; }
}
```

Start Uvicorn behind that proxy with
`uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1`.
Trust only the actual proxy address. Add an HTTP-to-HTTPS redirect and configure
DNS, certificate renewal, process supervision, database backups and monitoring
in the chosen infrastructure. `/api/health` is a liveness route, not a database
or AI readiness probe. Test the real HTTPS origin because cookie and origin
checks depend on the forwarded scheme and host.

## Verification and remaining release work

- Run backend tests with `python -m pytest -q backend/tests` from the repository
  root. For MariaDB concurrency coverage, set `READING_TEST_DATABASE_URL` to the
  exact empty `tarot_reading_test` database, then run
  `python -m pytest -q backend/tests/test_reading_engine.py`; the fixture removes
  its tables afterward.
- Run `npm run build` in `frontend/`. There is no frontend unit test or browser
  E2E runner configured. Manually verify mobile and desktop, keyboard selection,
  reduced motion, refresh on nested routes, auth/logout, guest reading recovery,
  all three spreads, history and deletion against the deployed HTTPS origin.
- Verify the configured AI provider with a controlled paid request and its
  fallback, quota, cached history reload and cost records before claiming live
  AI readiness. The default provider is disabled; fallback readings still work.
- Finish the operator details in `docs/privacy.md` and review image distribution
  rights in `docs/asset-licenses.md` for the deployment jurisdiction.
- Schedule `python -m app.cleanup_auth --apply` and
  `python -m app.cleanup_guests --apply` after reviewing their counts and retention
  policy. Document backup retention and restore tests.

No external deployment is performed by these instructions.
