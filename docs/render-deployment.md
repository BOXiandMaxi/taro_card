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
In PowerShell from the repository root, enter the URL when prompted (the
answer is not printed or stored in Git):

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

`alembic current` should report `0004_accounts (head)`. The seed should report
78 cards and 78 meanings. Existing local MariaDB accounts and reading history
are **not** copied by the seed; a separate data migration would be needed if
you want to retain them. Remove the terminal variable when finished:

```powershell
Remove-Item Env:DATABASE_URL
```

## 3. Create the Render service

1. Sign in at [Render Dashboard](https://dashboard.render.com/) and choose
   **New → Blueprint**.
2. Connect GitHub and select `BOXiandMaxi/taro_card` on branch `main`.
3. Render reads `render.yaml`. Confirm the single `taro-card` **Free** web
   service in Singapore. When prompted for `DATABASE_URL`, paste the same
   TiDB URL. The Blueprint generates a stable `SECRET_KEY` and enables secure
   cookies. Keep the database URL and generated secret only in Render's
   environment settings.
4. Click **Apply** and wait for the Docker build and deploy. Open the assigned
   `https://...onrender.com` URL, then check `/api/health` at the same host.

The frontend uses `/api` on this same host; no frontend URL or CORS setting is
needed for the default Render domain. For a custom domain, set
`FRONTEND_ORIGINS` in Render to its exact HTTPS origin and redeploy. If both the
Render domain and custom domain must work, list both origins separated by a
comma. The server's host allowlist follows these origins.

The Blueprint leaves `AI_PROVIDER=disabled`; database-based fallback readings
remain available. To enable live AI later, configure a supported provider,
model, API key, and request limits in **Render → service → Environment**, never
in GitHub or a `VITE_` variable. Test one reading, its history reload, and the
AI usage limit after enabling it.

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
