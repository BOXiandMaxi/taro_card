# Database schema

MySQL with SQLAlchemy models and Alembic migrations. Primary keys use stable integer IDs except reading IDs, which are UUIDs. All timestamps are UTC. Foreign keys and indexes are defined in the migration, never by manual phpMyAdmin edits.

| Table | Purpose and key constraints |
| --- | --- |
| `users` | Unique email; Argon2 password hash; nullable role; created and updated timestamps. |
| `user_id_sequence` | One row that stores the last allocated account ID for transactional registration. |
| `auth_sessions` | SHA-256 session token hash, account FK, UTC expiry and nullable revocation timestamp. |
| `auth_rate_limits` | Pseudonymous client key, fixed window start, and credential-attempt counter. |
| `tarot_cards` | Exactly 78 seeded stable IDs; unique slug; arcana, suit, rank, expected image filename, nullable verified image path. |
| `card_meanings` | One row per card; upright/reversed keywords and descriptions plus category meanings. Unique card FK. |
| `categories` | Five unique category slugs and Thai names. |
| `questions` | Category FK, Thai prompt, display order, optional recommended spread. |
| `tarot_spreads` | Unique slug, card count 3/5/10, Thai name. |
| `spread_positions` | Spread FK, position number, meaning. Unique `(spread_id, position_number)`. |
| `readings` | UUID, nullable owner FK, category/question or validated custom question, spread FK, status, anonymous capability hash, timestamps. |
| `reading_create_keys` | SHA-256 retry-key registry. Entries survive deletion so a retry cannot recreate a reading. |
| `reading_cards` | Reading FK, position FK, card FK, orientation. Unique `(reading_id, position_id)` and `(reading_id, card_id)`. |
| `reading_interpretations` | Reading FK, validated structured result, source, model, timestamps. One completed result per reading. |
| `ai_usage_logs` | Nullable reading FK, nullable account or pseudonymous guest/IP quota scope, provider/model, tokens, cost estimate, status, timestamp. |
| `analytics_page_views` | Random event UUID primary key, indexed Thai report date, page label, daily browser hash, signed-in flag, and UTC timestamp. |

Reading cards and cached interpretations cascade on reading deletion. AI
usage rows detach via `ON DELETE SET NULL` and remain in shared and scoped
daily budgets. Card, spread, question and category reference rows are
restricted while readings reference them. Session rows cascade if their
account is deleted. Readings restrict account deletion pending a production
account-deletion policy.

## Revision 0004 impact

The revision adds three tables, backfills existing non-null creation retry
hashes, alters the AI usage foreign key to retain logs, and adds date and
scope indexes. Existing readings, capabilities, ownership and attached logs
are preserved. Historical AI logs have no new scope and still count under
the shared daily budget. Pause writes while migrating and allow for MySQL
DDL locks on the usage table. Downgrade requires an online check and
refuses to proceed if detached usage logs exist. A successful downgrade
would remove sessions, rate counters and the retry registry, including
retry protection for already-deleted readings.

The initial migration creates the schema only. Seed scripts insert reference data idempotently and assert the 22/56/78 deck invariant. The 78 locally imported WebP files and their recorded provenance are described in `docs/asset-licenses.md`.
