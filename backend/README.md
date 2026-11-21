# Backend handoff

Python 3.11+. Install from the repository root:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
```

Copy the coordinator-owned root `.env.example` to `backend/.env` and configure
`DATABASE_URL` and comma-separated `FRONTEND_ORIGINS`. Secrets stay out of source
control. The URL must use `mysql+pymysql`; percent-encode special characters in
credentials. The database must already exist. MySQL 8.0.16+ enforces the CHECK
constraints used by this schema. The initial migration and reference seed were
also verified on a local MariaDB 10.4.32 server; later application flows still
need integration testing there. Tables use InnoDB and utf8mb4; UTC is set on each
database connection and timestamps are stored as timezone-free UTC DATETIME.

Run these from `backend/` after installing dependencies:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head --sql
# Review the SQL first. This next command changes the configured database:
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
.venv/Scripts/python.exe -m pytest -q
```

The initial migration creates only eleven application tables. No startup hook
creates tables, seeds data, connects to MySQL, or runs migrations. The health
route is `GET /api/health` → `200 {"status":"ok"}`. OpenAPI is at `/docs`.
Tests use isolated in-memory SQLite and offline MySQL SQL compilation, never the
configured database. SQLite tests do not replace MySQL integration validation.
For MariaDB integration tests, create the empty `tarot_reading_test` database
with `database/documentation/create_database.sql` and set
`READING_TEST_DATABASE_URL` to its connection URL. The reading-engine test fixture
requires this exact database name, creates its tables, then removes them after
the test module. Never point this variable at `tarot_reading`.
Run the full suite only after installing dependencies: missing dependencies are
reported as class-level skips for the standard-library runner.

The backend serves reference data, guest and member readings, and account
history. The [API contract](../docs/api.md) describes both cookie flows.

## Accounts and retention

Revision `0004_accounts` adds session and authentication rate-limit tables, a
registry of hashed creation retry keys, and durable AI usage accounting.
Pause backend writes while applying it and deploy the upgraded schema before
starting the new backend. See [migration impact](../docs/database.md).

For deployment, serve the frontend and API over HTTPS on the same site. Set
`COOKIE_SECURE=true`, configure `FRONTEND_ORIGINS` with the allowed HTTPS
origins, and set a stable random `SECRET_KEY` shared by all workers. The key
pseudonymizes IP buckets for limits. Changing it starts new IP buckets.
Behind a reverse proxy, make the original HTTPS scheme and client IP
available through trusted proxy configuration only. The application uses the
ASGI client address and scheme and does not read forwarding headers directly.
Local loopback HTTP can use `COOKIE_SECURE=false`.

Sessions expire after `SESSION_TTL_SECONDS` (seven days by default).
Registration and login share a budget of `AUTH_ATTEMPT_LIMIT` (10) per client
IP within `AUTH_WINDOW_SECONDS` (900).
From `backend/`, run `.venv/Scripts/python.exe -m app.cleanup_auth` to count
expired session and rate-limit rows; add `--apply` to remove them in batches.
Schedule it daily along with guest cleanup.

Guest readings expire `GUEST_READING_RETENTION_DAYS` (30) days after creation.
From `backend/`, count expired readings with
`.venv/Scripts/python.exe -m app.cleanup_guests`. Add `--apply` to delete
eligible guest readings and their cards and interpretations in batches.
Schedule that command daily for the intended database. Member readings
are excluded and AI usage rows are detached. See the
[privacy draft](../docs/privacy.md) for retained metadata.

## Interpretation configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_PROVIDER` | `disabled` | Use `openai` or `gemini` to enable the selected adapter. |
| `AI_MODEL` | `gpt-6.1-terra` | Set `gemini-3.5-flash-lite` when using Gemini Free tier. |
| `AI_API_KEY` | Empty | Server-side OpenAI API key. |
| `GEMINI_API_KEY` | Empty | Server-side Gemini API key. A missing key uses the database fallback. |
| `AI_TIMEOUT_SECONDS` | `15` | Deadline per attempt, up to 30 seconds. |
| `AI_MAX_OUTPUT_TOKENS` | `4000` | Provider output token cap. Increase for long 10-card readings if needed. |
| `AI_DAILY_REQUEST_LIMIT` | `100` | Shared attempt budget per UTC day. Set to zero for database-only interpretation. |
| `AI_ACCOUNT_DAILY_REQUEST_LIMIT` | `20` | Attempt budget per member account per UTC day. |
| `AI_INPUT_USD_PER_MILLION`, `AI_OUTPUT_USD_PER_MILLION` | Unset | Optional price overrides. Set both when configuring a different model. |

Interpretation requires a signed-in account. When a member interprets a fully
revealed guest reading using its browser capability, that reading joins their
account history and any new AI attempt counts toward their account budget.
The provider receives the question text, category, spread, and only the
already-revealed cards with their orientation and stored meanings. OpenAI
Responses storage is disabled. Gemini uses the GenerateContent JSON schema mode.
The application validates the structured
response and compares each card ID, position, and orientation with the draw
before storing it. Fresh AI prose also gets a conservative Thai-language
check and a check for duplicated whole card paragraphs. A quality failure
is logged as `invalid_response` and uses the database fallback, as do
disabled AI, an exhausted budget, and other provider failures. Successful
fallbacks are cached in the same format.
Existing saved results continue to use the original schema and draw checks.

The fallback uses the saved question, reads the orientation-specific meaning
before adding category context, and connects the positions differently for
the 3-, 5-, and 10-card spreads. It gives separate actions the reader can
try. Blank meanings use available orientation keywords or a position-based
reflection. Long source text is excerpted before composing the result.

From `backend/`, run `.venv/Scripts/python.exe -m pytest -q tests/test_interpretations.py`
for the interpretation tests. They exercise the API with a disposable SQLite
fixture and use mock HTTP responses for provider calls. They cover fallback,
quality rejection, cache reuse, and usage accounting. These checks do not
measure live model output or exercise MySQL/InnoDB.

The service makes up to two attempts. It retries a connection failure or an
eligible HTTP 429 or 503 once after 250 ms. Each attempt reserves a budget slot
and writes an `ai_usage_logs` row before calling the selected provider. The row records the
outcome, any reported tokens, and a USD estimate based on standard
GPT-6.1 Terra input and output rates or the configured overrides. Unknown
model rates and unreported usage produce a zero estimate. The database claim prevents concurrent POST requests
from generating for the same reading. After two minutes, an abandoned claim
can be completed by POST using the fallback. A log left at `started` records
an attempt with an unknown outcome and still counts against its UTC-day budget.

To try Gemini, get a key in Google AI Studio, set `AI_PROVIDER=gemini`,
`AI_MODEL=gemini-3.5-flash-lite`, and `GEMINI_API_KEY` in `backend/.env`, then restart
the backend. Keep `AI_API_KEY` for OpenAI only. Free-tier availability and data
handling depend on the Google account and model; review Google's terms before
sending real user questions. Live Gemini behavior still needs verification with
a valid key. See [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)
and [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

Seeds and their limits are documented in `../database/documentation/seeding.md`.
