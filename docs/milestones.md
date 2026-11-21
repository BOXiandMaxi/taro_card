# Development milestones (audit: 2026-11-20)

- [x] Phase 1: FastAPI, React, SQLAlchemy schema and Alembic migrations.
- [x] Phase 2: 78 seeded cards, Thai meanings, 78 local WebP files and recorded provenance.
- [x] Phase 3: Thai reading pages, responsive layout and reduced-motion support in source.
- [x] Phase 4: server-side secure shuffle, 3/5/10-card draws, fixed reveal and persistence.
- [x] Phase 5: validated AI adapter, quotas, usage logs, caching and database fallback.
- [x] Phase 6: account sessions, guest capabilities, authorization, history and deletion.
- [ ] Phase 7: production release. Backend tests and build pass, but browser E2E and accessibility checks, live AI provider testing, hosting/HTTPS setup and operator privacy details remain.

`AI_PROVIDER=disabled` by default. The adapter is implemented, but live AI responses
cannot be claimed until a provider key is configured and exercised. See
[deployment](deployment.md) for the release gates and audit results.
