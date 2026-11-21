# Tarot Reading: architecture

## Folder structure

```text
frontend/            React application and local visual assets
backend/app/api/      HTTP routes and request/response schemas
backend/app/core/     Environment configuration and security settings
backend/app/database/ SQLAlchemy engine and session management
backend/app/models/   Persisted entities
backend/app/services/ Tarot, authentication, and AI services by phase
backend/alembic/      Versioned schema migrations
backend/tests/        Backend tests
database/seeds/       Repeatable reference data
docs/                 Contracts, rules, deployment and licensing
```

## Boundaries

- `frontend/`: Thai React application. It displays server state and never selects authoritative cards or holds secrets.
- `backend/app/api/`: validated REST contract and authorization.
- `backend/app/api/routes/readings.py`: spread validation, cryptographic draw, persistence and reveal.
- `backend/app/services/interpretations.py` and `interpretation_provider.py`: deterministic database fallback and optional AI adapter. The adapter receives validated card and position data; it cannot alter a draw.
- `backend/app/database/` and `backend/app/models/`: SQLAlchemy persistence, with Alembic as the only schema change mechanism.
- `database/seeds/`: repeatable seed data for the 78 cards, meanings, categories, questions, and spreads.

## Reading lifecycle

`CREATED → DRAWING → DRAWN → INTERPRETING → COMPLETED`. An interpretation failure moves to `FAILED`; retrying interpretation never redraws cards. A draw commits all positions and cards together. A repeated draw returns the persisted selection. Concurrent draws must lock the reading row. Timestamps are stored in UTC and displayed in the user's locale.

Anonymous readings use a random access capability in an HttpOnly cookie; reading IDs alone never grant access. Registered users own their readings and can review and delete their history.

## Assets and AI

Card faces use 78 locally imported WebP files with recorded provenance. A single local card back is used for every card. Database meanings provide the deterministic fallback. AI is optional, receives a structured payload, returns schema validated Thai text, and is never the source of card selection.

## Deployment boundaries

Use MySQL, environment based secrets, explicit CORS origins, HTTPS and secure cookies in production. Run migrations and seeds as separate deployment steps. Never expose the AI key or database credentials to the frontend.
