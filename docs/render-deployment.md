# Deploy on Render (free web service)

This repository contains a `render.yaml` Blueprint and a multistage `Dockerfile`.
The Docker image builds React and serves it with FastAPI on one HTTPS origin.
The service needs an **external persistent MySQL-compatible database**. Render's
free Postgres does not match the current MySQL application schema and expires
after 30 days; the free web service filesystem is temporary.

## 1. Prepare a database

One free option is a **MySQL-compatible TiDB Cloud Starter** instance. Create it
at [TiDB Cloud](https://tidbcloud.com/), preferably in a region near Render's
Singapore service. Choose MySQL compatibility and keep the monthly spending
limit at zero if you want to stay within its free quota. In the TiDB SQL editor,
create the application database:

```sql
CREATE DATABASE IF NOT EXISTS `tarot_reading`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Use **Connect** in TiDB Cloud to get the host, port, username, and password.
Construct a SQLAlchemy URL with a URL-encoded password:

```text
mysql+pymysql://USER:PASSWORD@HOST:PORT/tarot_reading?charset=utf8mb4&ssl_verify_cert=true&ssl_verify_identity=true
```

TiDB Cloud Starter requires TLS for its public endpoint. This project has not
yet been tested against an actual TiDB instance; run the migrations and a
reading end to end before treating the database choice as verified. Use a
dedicated production database and never run test fixtures against it.

## 2. Create the tables and card data from this computer

Install the backend dependencies locally as described in [the backend guide](../backend/README.md).
In PowerShell from the repository root, enter the URL when prompted (the URL
is not placed in the command line or stored in Git; keep the terminal private):

```powershell
$env:DATABASE_URL = Read-Host 'TiDB SQLAlchemy DATABASE_URL'
Push-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
Pop-Location
backend\.venv\Scripts\python.exe -m database.seeds.seed --check-only
backend\.venv\Scripts\python.exe -m database.seeds.seed
backend\.venv\Scripts\python.exe -m database.assets.validate
```

`alembic current` should report `0005_visitor_analytics (head)`. The seed should report
78 cards and 78 meanings. Existing local MariaDB accounts and reading history
are **not** copied by the seed; a separate data migration would be needed if
you want to retain them. Remove the terminal variable when finished:

```powershell
Remove-Item Env:DATABASE_URL
```

### Add or remove an analytics administrator

For an existing TiDB or local MariaDB database, run `alembic upgrade head`
using that database's migration credentials before deploying the app update.
Revision `0005_visitor_analytics` adds a nullable `users.role` column and an
`analytics_page_views` table. It preserves all existing users and readings.
Use Alembic to apply the schema revision instead of duplicating the DDL in the
SQL editor. The runtime account needs its usual read/write access on both
tables.

Register your account on the site you intend to administer. In the TiDB SQL
editor or local database client, select the app database and look up the exact
email. Replace the example email and numeric ID below with your own values.

```sql
USE tarot_reading;
SELECT id, email, role FROM users WHERE email = 'owner@example.com';

UPDATE users SET role = 'admin'
WHERE id = 123 AND email = 'owner@example.com';

SELECT id, email, role FROM users
WHERE id = 123 AND email = 'owner@example.com';
```

Refresh the signed-in site and open **Account → สถิติเข้าชม** or
`/admin/analytics`. Every report request checks the current role in the
database. To remove access, repeat the same exact update with `SET role = NULL`.

The app prunes events outside the latest 30 Thai calendar days in bounded
batches as visits arrive. For maintenance when the app is idle, use this from
`backend/` with the intended database URL:

```powershell
./.venv/Scripts/python.exe -m app.cleanup_analytics
# Review the count before removing the expired analytics rows.
./.venv/Scripts/python.exe -m app.cleanup_analytics --apply
```

## 3. Create the Render service

1. Sign in at [Render Dashboard](https://dashboard.render.com/) and choose
   **New → Blueprint**.
2. Connect GitHub and select `BOXiandMaxi/taro_card` on branch `main`.
3. Render reads `render.yaml`. Confirm the single `taro-card` **Free** web
   service in Singapore. When prompted for `DATABASE_URL`, paste the value of
   the `DATABASE_URL` line in the private `backend/.env.render.local` file if
   the runtime account has been prepared; otherwise use a dedicated TiDB
   account with read/write access to `tarot_reading`. The Blueprint generates
   a stable `SECRET_KEY` and enables secure
   cookies. Keep the database URL and generated secret only in Render's
   environment settings.
4. Click **Deploy Blueprint** and wait for the Docker build and deploy. Open the assigned
   `https://...onrender.com` URL, then check `/api/health` at the same host.

The frontend uses `/api` on this same host; no frontend URL or CORS setting is
needed for the default Render domain. For a custom domain, set
`FRONTEND_ORIGINS` in Render to its exact HTTPS origin and redeploy. If both the
Render domain and custom domain must work, list both origins separated by a
comma. The server's host allowlist follows these origins.

For an existing Blueprint, set `AI_PROVIDER=gemini`, `AI_MODEL` to a model
available to your Gemini API project, and `GEMINI_API_KEY` in **Render →
taro-card → Environment**. Set `AI_TIMEOUT_SECONDS=30` and
`AI_MAX_OUTPUT_TOKENS=6000` if older values are already present there. The
Blueprint marks the AI settings as `sync: false` so later syncs do not reset
them; Render does not prompt for new `sync: false` variables when updating an
existing Blueprint. Keep the key out of GitHub and frontend variables. If the
provider is disabled, has no key, or fails, the app serves a clearly labeled
preliminary database reading. Test a new reading and verify that it is sourced
from AI, then reopen history to verify the result is reused without another
provider request.

## 4. Verify and operate

Test registration, login, a three-card reading, interpretation, history, and
logout on the public HTTPS URL. Then test five and ten cards and mobile layout.
Check Render logs if a request fails. The `/api/health` endpoint checks only
that the app responds; it does not prove database or AI connectivity.

Render's free web service sleeps after 15 minutes without traffic and can take
about a minute to wake. Its local files disappear on restart or redeploy; the
database keeps accounts and history. Back up the external database and arrange
the guest/session cleanup commands in [the general deployment guide](deployment.md). The Docker image
build has not been run locally unless Docker is available; the frontend build
and backend tests are the local checks.

References: [Render Blueprint](https://render.com/docs/blueprint-spec),
[Render free tier](https://render.com/docs/free),
[TiDB Cloud Starter limits](https://docs.pingcap.com/tidbcloud/serverless-limitations/),
[TiDB TLS connection](https://docs.pingcap.com/ai/connect/).
