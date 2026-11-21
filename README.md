# Tarot Reading

Thai language tarot reading application. The workspace is being built in phases; see [milestones](docs/milestones.md) for the current implementation status. The product treats tarot as entertainment and reflection, not certain prediction or professional advice.

## Structure

- `frontend/`: React, Vite, Tailwind and UI.
- `backend/`: FastAPI, SQLAlchemy models, Alembic and tests.
- `database/seeds/`: repeatable reference data.
- `database/assets/`: card manifest, provenance, importer and validator.
- `frontend/public/assets/cards/`: 78 local WebP faces and a shared SVG back.
- `docs/`: architecture, API, schema, tarot rules, licensing and deployment.

## Local setup

Prerequisites: Python 3.11+, Node.js compatible with Vite 6, and MySQL 8 or the locally verified MariaDB 10.4.32. Use `utf8mb4`. No real credentials belong in the repository. To create the empty main and test databases, run [database/documentation/create_database.sql](database/documentation/create_database.sql) with an account that has `CREATE DATABASE` permission; then use Alembic and the seed command below for the tables and reference data.

1. Copy `.env.example` to `backend/.env` and set `DATABASE_URL` and a random `SECRET_KEY`. The example credentials are placeholders.
2. In `backend/`, create a virtual environment and install `requirements.txt`.
3. From `backend/`, review the SQL with `.venv/Scripts/python.exe -m alembic upgrade head --sql`, then apply the migration with `.venv/Scripts/python.exe -m alembic upgrade head` to the configured database.
4. From the project root, run `backend/.venv/Scripts/python.exe -m database.seeds.seed --check-only`, then `backend/.venv/Scripts/python.exe -m database.seeds.seed` to insert reference metadata. The write command requires a configured MySQL database.
5. From `backend/`, start the API with `.venv/Scripts/python.exe -m uvicorn app.main:app --reload`. FastAPI documentation is at `/docs` and liveness at `/api/health`.
6. In `frontend/`, run `npm ci` and `npm run dev`. The public API path defaults to `/api`; see [frontend/.env.example](frontend/.env.example). On Windows PowerShell with script execution disabled, use `npm.cmd`.

See [API contract](docs/api.md), [database design](docs/database.md), [tarot rules](docs/tarot-rules.md), and [Render deployment steps](docs/render-deployment.md). AI interpretation has a validated provider adapter but is disabled by default until provider credentials are configured; database meanings provide the fallback.

## Tests

Run `backend/.venv/Scripts/python.exe -m pytest -q backend/tests` from the repository root, `backend/.venv/Scripts/python.exe -m database.assets.validate`, and `npm run build` in `frontend/`. MariaDB concurrency tests require the dedicated empty `tarot_reading_test` database; see the [deployment guide](docs/deployment.md). Frontend unit and browser E2E test runners are not yet configured. The [milestone checklist](docs/milestones.md) distinguishes implemented features from release gates.
