# REST API contract

Responses use JSON, with an empty body for `204`. Request validation uses FastAPI's `422` error structure, with submitted values omitted on authentication routes. Private reading routes authorize the member who owns the reading or the matching capability for a guest reading. They return `401` when credentials are absent and `404` when presented credentials fail to authorize the reading. A disallowed origin or failed CSRF check returns `403`. A conflicting retry or lifecycle transition returns `409`.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness; no database query. |
| GET | `/api/categories`, `/api/questions`, `/api/cards`, `/api/cards/{id}`, `/api/spreads` | Seeded reference data. Questions can be filtered by `category_id`. |
| POST | `/api/readings` | Validate category, question/custom question, spread; create `CREATED` reading. |
| GET | `/api/readings/{id}` | Return the current reading and its ordered positions, with card details for revealed positions. |
| POST | `/api/readings/{id}/draw` | Persist the selected indices and assign cards to positions in selection order. |
| POST | `/api/readings/{id}/reveal` | Reveal a single position and return its persisted card, orientation, and matching meaning. |
| POST | `/api/readings/{id}/interpret` | Generate or return the cached interpretation after all cards are revealed. |
| GET | `/api/readings/{id}/interpretation` | Return the cached interpretation. |
| DELETE | `/api/readings/{id}` | Delete an authorized reading, its cards and interpretation. Returns `204`. |
| GET | `/api/auth/csrf` | Fetch a CSRF token for the current browser or session. |
| POST | `/api/auth/register`, `/api/auth/login`, `/api/auth/logout` | Cookie based account session. |
| GET | `/api/auth/me`, `/api/history` | Current user and owned reading history. |

Implemented request/response schemas live in backend Pydantic models and FastAPI OpenAPI output. Never put anonymous capabilities in a URL. The browser sends cookies using `withCredentials`; CORS allows explicit configured origins only.

## Accounts and history

- Fetch `GET /api/auth/csrf` with credentials included to receive `{"csrf_token":"..."}`. Send that value in `X-CSRF-Token` with registration, login, logout and all reading writes made with an active session, including calls on guest readings. Those requests require a same-origin or explicitly allowed `Origin`. Browser requests supply this header automatically. Refresh the CSRF token after registration, login or logout because the browser's session changes.
- Register or log in with `{"email":"reader@example.com","password":"..."}`. Emails are trimmed and lowercased. Registration requires a password of 8–128 characters. Registration returns `201` and login returns `200`, both with `{"id":1,"email":"reader@example.com"}` and a session cookie. Duplicate registration returns `409`. Login with an incorrect email or password returns `401`. Rate-limited requests return `429` with `Retry-After` in seconds.
- `GET /api/auth/me` returns the same account object or `401`. `POST /api/auth/logout` revokes the session, clears the cookie and returns `204`. No route redirects. The session cookie is HttpOnly and SameSite=Lax, with Secure on HTTPS. Keep the CSRF token in memory and let the browser store the session cookie.
- `GET /api/history` returns `401` without a valid session. With a session it returns a JSON array of owned readings, most recent first. Each row includes the regular reading fields plus `category`, `created_at` (UTC ISO 8601) and nullable `interpretation_summary`. Fetch `GET /api/readings/{id}` for the full reading and any cached interpretation. Guest readings stay accessible through their original capabilities and do not appear in account history.

## Reference responses

- Categories, spreads, and cards return JSON arrays ordered by `id`. Each spread includes `positions` ordered by `position_number`.
- Questions are ordered by `category_id` and `display_order`. Omit `category_id` to load all questions. A positive category ID with no matching questions returns `[]`.
- The card list includes card metadata, including nullable `image_filename` and `image_path`. Card detail adds the nullable `meaning` object. A missing card returns `404`.

## Reading engine

- Send `category_id`, `spread_id`, and exactly one of `question_id` or `custom_question` to create a reading. The preset question must belong to the category. A custom question is trimmed and can be 1–1,000 characters. Creation returns `201` and persists the shuffled deck.
- To retry creation, send an `Idempotency-Key` generated with a cryptographic UUIDv4 generator such as `crypto.randomUUID()`. Reuse it for retries in the same account or guest context. A valid replay returns the original reading ID. Guest replays also reissue the original capability cookie. A key reused after deletion or expiry, by a different account or auth context, or with different parameters returns `409`. Treat guest keys as private because they can recover the cookie.
- Create, draw, and GET return `id`, `status`, `category_id`, `requested_card_count`, `question`, `question_text`, `spread`, and `cards`. Use `question.prompt_th` for presets and `question_text` for custom questions. A valid session creates a member-owned reading. Guest readings use an HttpOnly, SameSite=Lax capability cookie scoped to the reading path. On HTTPS it uses Secure. Local HTTP uses a separate cookie name.
- Draw with `{"selected_indices": [77, 0, 12]}` for a three-card spread. Send exactly 3, 5, or 10 distinct integers from 0 through 77, according to the spread. Selection order maps to positions 1 through the spread count. An identical retry returns the same `DRAWN` response. A different ordered selection returns `409` after the first draw commits.
- Draw and draw retries return each position with `position_number`, `position`, `revealed: false`, `card: null`, `orientation: null`, and `meaning: null`. GET uses the same fields and nulls for positions that are still hidden.
- Send `{"position_number": 1}` to reveal position 1. Reveal and subsequent GET requests return that position with `revealed: true`, `card` metadata, and its persisted `orientation` (`upright` or `reversed`). The position's `meaning` contains `keywords` (an array of strings) and `description` (a string) for that orientation, or `null` if the card has no meaning record. Repeating the reveal uses the same card and orientation, including after a reversal setting change.

## Interpretation

- Send POST with an empty body, an active session, and its CSRF token. After all positions are revealed, a member can interpret their own reading or claim a guest reading by sending its matching, unexpired HttpOnly capability cookie. The POST assigns the existing reading and fixed cards to the account, clears guest access, and adds the reading to account history. Signing in alone leaves the guest reading unchanged.
- Both interpretation endpoints return `401` for guests. GET requires ownership, returns `409` before all reveals, and returns `404` if there is no cached interpretation. A member without ownership or a valid claim capability receives `404` on POST. POST returns `409` before all reveals.
- A successful POST returns `200` and moves the reading to `COMPLETED`. Subsequent POST and GET requests return the same result. While a POST is generating, another POST returns `409` with `Retry-After: 2`. A later POST can recover an abandoned generation using database meanings.
- The result contains `reading_id`, `language: "th"`, `overall_summary`, ordered `card_interpretations`, `card_connections`, `practical_guidance`, and `closing_message`. Each card entry contains `position` (1-based integer), `position_name`, `card_id`, `orientation` (`upright` or `reversed`), and `interpretation`. The saved draw determines every identity, position, and orientation.
- Fresh AI output with obviously non-Thai prose or repeated whole card paragraphs uses the database fallback. The fallback uses the saved question, orientation-specific meanings, and the positions of the selected spread, with separate practical steps. Previously saved interpretations continue to be returned from the cache.
- GET `/api/readings/{id}` includes the same shape under `interpretation` for the signed-in owner once available. Guests and signed-in readers with a guest capability can still see revealed cards and their stored individual meanings.

- Paid attempts are subject to shared and account budgets that reset at midnight UTC, including attempts for guest readings claimed during POST. Exhaustion uses the database fallback. Cached results consume no attempt. Deleting a reading preserves the attempt count.
