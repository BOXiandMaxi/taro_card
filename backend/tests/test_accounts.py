import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.routes import readings
from app.cleanup_auth import cleanup_auth
from app.cleanup_guests import cleanup_guests
from app.core.config import Settings
from app.database.base import utc_now
from app.models import AIUsageLog, AuthRateLimit, AuthSession, Reading, ReadingCard, ReadingInterpretation, TarotSpread, User
from app.services import auth, interpretations
from test_interpretations import install_provider, mock_result, provider_response
from test_reading_engine import PRESET, ROOT, app, client, database

ORIGIN = "https://testserver"
PASSWORD = "test-password"
SESSION = "__Host-tarot-session"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch):
    settings = Settings(_env_file=None, auth_attempt_limit=50)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(readings, "get_provider", lambda _: None)
    return settings


def csrf(client):
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def register(client, email=None):
    email = email or f"{uuid4()}@example.test"
    response = client.post("/api/auth/register", headers=csrf(client), json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response


def test_cleanup_auth_only_removes_expired_rows(database, auth_settings):
    now = utc_now()
    with Session(database) as session, session.begin():
        user = User(email=f"{uuid4()}@example.test", password_hash="test-hash")
        session.add(user)
        session.flush()
        session.add_all([
            AuthSession(token_hash="a" * 64, user_id=user.id, expires_at=now - timedelta(seconds=1)),
            AuthSession(token_hash="b" * 64, user_id=user.id, expires_at=now + timedelta(days=1)),
            AuthRateLimit(client_hash="c" * 64, window_started_at=now - timedelta(hours=1), attempts=1),
            AuthRateLimit(client_hash="d" * 64, window_started_at=now, attempts=1),
        ])
    with Session(database) as session:
        assert cleanup_auth(session) == (1, 1)
        assert cleanup_auth(session, apply=True, batch_size=1) == (1, 1)
        assert cleanup_auth(session) == (0, 0)
        assert session.get(AuthSession, "b" * 64) is not None
        assert session.get(AuthRateLimit, "d" * 64) is not None


def create(client, headers=None):
    response = client.post(ROOT, json=PRESET, headers=headers)
    assert response.status_code == 201, response.text
    return response, f"{ROOT}/{response.json()['id']}"


def reveal(client, path, headers=None):
    assert client.post(f"{path}/draw", json={"selected_indices": [0, 1, 2]}, headers=headers).status_code == 200
    for position in range(1, 4):
        assert client.post(f"{path}/reveal", json={"position_number": position}, headers=headers).status_code == 200


def test_register_login_logout_and_credentials(client, app, database):
    assert client.get("/api/auth/me").status_code == 401
    email = f"{uuid4()}@example.test"
    registration = register(client, f"  {email.upper()}  ")
    account = registration.json()
    assert account == {"id": account["id"], "email": email}
    assert all(flag in registration.headers["Set-Cookie"] for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"))
    token = client.cookies.get(SESSION)
    token_hash = sha256(token.encode()).hexdigest()
    with Session(database) as session:
        assert session.get(User, account["id"]).password_hash.startswith("$argon2id$")
        assert session.get(AuthSession, token_hash).user_id == account["id"]
        assert session.get(AuthSession, token) is None

    assert client.get("/api/auth/me").json() == account
    credentials = {"email": email, "password": PASSWORD}
    duplicate = client.post("/api/auth/register", headers=csrf(client), json=credentials)
    assert duplicate.status_code == 409
    for bad in (dict(credentials, password="wrong"), dict(credentials, email="missing@example.test")):
        invalid = client.post("/api/auth/login", headers=csrf(client), json=bad)
        assert invalid.status_code == 401 and invalid.json() == {"detail": "Invalid email or password"}
    redacted = client.post("/api/auth/login", headers=csrf(client), json=dict(credentials, password="p" * 129))
    assert redacted.status_code == 422 and "p" * 129 not in redacted.text

    login = client.post("/api/auth/login", headers=csrf(client), json=credentials)
    assert login.status_code == 200 and login.json() == account
    fresh = client.cookies.get(SESSION)
    assert fresh != token
    with TestClient(app, base_url=ORIGIN, cookies={SESSION: token}) as old:
        assert old.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout", headers=csrf(client)).status_code == 204
    assert client.cookies.get(SESSION) is None
    with TestClient(app, base_url=ORIGIN, cookies={SESSION: fresh}) as revoked:
        assert revoked.get("/api/auth/me").status_code == 401


def test_expiration_and_local_cookie(app, database):
    with TestClient(app, base_url="http://localhost:8000") as local:
        headers = csrf(local)
        headers["Origin"] = "http://localhost:8000"
        response = local.post("/api/auth/register", headers=headers, json={
            "email": "local@example.test", "password": PASSWORD,
        })
        assert response.status_code == 201
        assert "Secure" not in response.headers["Set-Cookie"] and local.cookies.get("tarot-session")
        token_hash = sha256(local.cookies.get("tarot-session").encode()).hexdigest()
        with Session(database) as session, session.begin():
            session.execute(update(AuthSession).where(AuthSession.token_hash == token_hash).values(expires_at=utc_now()))
        assert local.get("/api/auth/me").status_code == 401
        assert local.get("/api/history").status_code == 401


def test_csrf_origin_and_delete_preflight(client):
    credentials = {"email": "csrf@example.test", "password": PASSWORD}
    headers = csrf(client)
    assert client.get("/api/auth/csrf", headers={"Origin": "https://other.invalid"}).status_code == 403
    assert client.post("/api/auth/register", json=credentials, headers={"Origin": ORIGIN}).status_code == 403
    register(client, credentials["email"])
    valid = csrf(client)
    assert valid["X-CSRF-Token"] != headers["X-CSRF-Token"]
    for invalid in (headers, {"Origin": ORIGIN}, {"X-CSRF-Token": valid["X-CSRF-Token"]},
                    dict(valid, Origin="https://other.invalid")):
        assert client.post(ROOT, json=PRESET, headers=invalid).status_code == 403
        assert client.post("/api/auth/logout", headers=invalid).status_code == 403
    allowed_origin = readings.get_settings().cors_origins[0]
    _, path = create(client, dict(valid, Origin=allowed_origin))
    assert client.delete(path, headers={"Origin": ORIGIN}).status_code == 403
    preflight = client.options(path, headers={
        "Origin": allowed_origin, "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "X-CSRF-Token",
    })
    assert preflight.status_code == 200
    assert "DELETE" in preflight.headers["Access-Control-Allow-Methods"]
    assert "X-CSRF-Token" in preflight.headers["Access-Control-Allow-Headers"]
    assert client.delete(path, headers=valid).status_code == 204


def test_auth_rate_limit_persists_across_clients_and_resets(app, database, auth_settings):
    auth_settings.auth_attempt_limit = 2
    credentials = {"email": "limited@example.test", "password": "wrong"}
    with TestClient(app, base_url=ORIGIN, client=("192.0.2.1", 52000)) as first:
        assert first.post("/api/auth/login", headers=csrf(first), json=credentials).status_code == 401
    with TestClient(app, base_url=ORIGIN, client=("192.0.2.1", 52001)) as second:
        headers = csrf(second)
        assert second.post("/api/auth/login", headers=headers, json=credentials).status_code == 401
        response = second.post("/api/auth/register", headers=headers, json=dict(credentials, password=PASSWORD))
        assert response.status_code == 429 and 0 < int(response.headers["Retry-After"]) <= 900
        with Session(database) as session, session.begin():
            session.execute(update(AuthRateLimit).where(AuthRateLimit.attempts == 2).values(
                window_started_at=utc_now() - timedelta(minutes=16),
            ))
        assert second.post("/api/auth/login", headers=headers, json=credentials).status_code == 401


def test_owner_history_and_guest_isolation(client, app, database):
    guest_created, guest_path = create(client)
    assert f"Max-Age={readings.get_settings().guest_reading_retention_days * 86400}" in guest_created.headers["set-cookie"]
    guest_details = client.get(guest_path).json()
    assert guest_details["category"]["id"] == PRESET["category_id"]
    assert guest_details["created_at"].endswith("Z")
    account = register(client).json()
    headers = dict(csrf(client), **{"Idempotency-Key": str(uuid4())})
    created, path = create(client, headers)
    assert "Set-Cookie" not in created.headers
    assert create(client, headers)[1] == path
    assert client.get(guest_path).status_code == 200
    reveal(client, path, headers)
    result = client.post(f"{path}/interpret", headers=headers)
    assert result.status_code == 200
    with TestClient(app, base_url=ORIGIN) as outsider:
        assert outsider.get("/api/history").status_code == 401
        assert outsider.get(path).status_code == 401
        assert outsider.post(ROOT, json=PRESET, headers={"Idempotency-Key": headers["Idempotency-Key"]}).status_code == 409
        register(outsider)
        outside_headers = dict(csrf(outsider), **{"Idempotency-Key": headers["Idempotency-Key"]})
        assert outsider.post(ROOT, json=PRESET, headers=outside_headers).status_code == 409
        assert outsider.get("/api/history").json() == []
        assert outsider.get(guest_path).status_code == 404
        assert outsider.get(path).status_code == 404
        assert outsider.get(f"{path}/interpretation").status_code == 404
        assert outsider.post(f"{path}/draw", headers=outside_headers, json={"selected_indices": [0, 1, 2]}).status_code == 404
        assert outsider.delete(path, headers=outside_headers).status_code == 404
    history = client.get("/api/history").json()
    assert [row["id"] for row in history] == [created.json()["id"]]
    row = history[0]
    assert row["category"]["id"] == 1 and row["question"]["id"] == 1
    assert len(row["cards"]) == 3 and all(card["revealed"] for card in row["cards"])
    assert row["created_at"].endswith("Z")
    assert row["interpretation_summary"] == result.json()["overall_summary"]
    assert client.get(path).json()["interpretation"] == result.json()
    with Session(database) as session:
        reading = session.get(Reading, row["id"])
        assert reading.user_id == account["id"] and reading.anonymous_capability_hash is None

    assert client.delete(path, headers=headers).status_code == 204
    assert client.get("/api/history").json() == []
    assert client.get(path).status_code == 404
    assert client.post(ROOT, json=PRESET, headers=headers).status_code == 409
    with Session(database) as session:
        for model in (ReadingCard, ReadingInterpretation):
            assert session.scalar(select(func.count()).select_from(model).where(model.reading_id == row["id"])) == 0


@pytest.mark.parametrize("sign_in", ["register", "login"])
def test_guest_resumes_same_reading_and_claims_only_after_authorized_post(client, app, database, sign_in):
    email = f"{uuid4()}@example.test"
    if sign_in == "login":
        register(client, email)
        assert client.post("/api/auth/logout", headers=csrf(client)).status_code == 204

    created, path = create(client)
    reading_id = created.json()["id"]
    name = f"__Secure-tarot-reading-{reading_id}"
    capability = client.cookies.get(name)
    reveal(client, path)
    guest_cards = client.get(path).json()["cards"]
    assert all(card["revealed"] and card["meaning"]["description"] for card in guest_cards)
    assert client.post(f"{path}/interpret", headers=csrf(client)).status_code == 401
    assert client.get(f"{path}/interpretation").status_code == 401
    assert client.get("/api/history").status_code == 401

    # A cached result from the previous guest flow must stay private until claimed.
    with Session(database) as session, session.begin():
        reading = session.get(Reading, reading_id)
        assert reading.user_id is None and reading.status == "DRAWN"
        assert reading.interpretation is None and reading.anonymous_capability_hash == sha256(capability.encode()).hexdigest()
        spread = session.get(TarotSpread, reading.spread_id)
        positions = interpretations.revealed_positions(reading, spread)
        payload = interpretations.load_input(session, reading, spread, positions)
        cached = interpretations.database_interpretation(payload)
        interpretations.save_result(session, reading, cached, model=None)

    assert "interpretation" not in client.get(path).json()
    assert client.get(f"{path}/interpretation").status_code == 401
    if sign_in == "register":
        account = register(client, email).json()
    else:
        response = client.post("/api/auth/login", headers=csrf(client), json={"email": email, "password": PASSWORD})
        assert response.status_code == 200
        account = response.json()

    details = client.get(path).json()
    assert details["id"] == reading_id and details["cards"] == guest_cards
    assert "interpretation" not in details and "interpretation_source" not in details
    assert client.get(f"{path}/interpretation").status_code == 404
    assert client.get("/api/history").json() == []
    headers = csrf(client)
    assert client.post(f"{path}/interpret", headers={"Origin": ORIGIN}).status_code == 403
    assert client.post(f"{path}/interpret", headers=dict(headers, Origin="https://other.invalid")).status_code == 403
    with TestClient(app, base_url=ORIGIN) as outsider:
        register(outsider)
        outside_headers = csrf(outsider)
        assert outsider.post(f"{path}/interpret", headers=outside_headers).status_code == 404
        assert outsider.post(
            f"{path}/interpret", headers=dict(outside_headers, Cookie=f"{SESSION}={outsider.cookies.get(SESSION)}; {name}={'a' * 64}"),
        ).status_code == 404
        assert client.get("/api/history").json() == []
        response = client.post(f"{path}/interpret", headers=headers)
        assert response.status_code == 200 and response.json() == cached.model_dump(mode="json")
        cookie = response.headers["Set-Cookie"]
        assert name in cookie and "Max-Age=0" in cookie and f"Path={path}" in cookie and "HttpOnly" in cookie
        assert client.cookies.get(name) is None
        outsider.cookies.set(name, capability, path=path)
        assert outsider.get(path).status_code == 404
        assert outsider.get(f"{path}/interpretation").status_code == 404
        assert outsider.post(f"{path}/interpret", headers=outside_headers).status_code == 404
        assert outsider.get("/api/history").json() == []

    assert client.get(path).json()["cards"] == guest_cards
    assert client.get(f"{path}/interpretation").json() == response.json()
    history = client.get("/api/history").json()
    assert [row["id"] for row in history] == [reading_id]
    assert history[0]["cards"] == guest_cards
    assert history[0]["interpretation_summary"] == response.json()["overall_summary"]
    with Session(database) as session:
        reading = session.get(Reading, reading_id)
        assert reading.user_id == account["id"] and reading.anonymous_capability_hash is None
        assert session.scalar(select(func.count()).select_from(AIUsageLog).where(AIUsageLog.reading_id == reading_id)) == 0

    token = client.cookies.get(SESSION)
    with Session(database) as session, session.begin():
        session.get(AuthSession, sha256(token.encode()).hexdigest()).expires_at = utc_now() - timedelta(seconds=1)
    assert client.post(f"{path}/interpret", headers=headers).status_code == 401
    assert client.get(f"{path}/interpretation").status_code == 401


def test_guest_deletion_and_retention(client, app, database):
    key = {"Idempotency-Key": str(uuid4())}
    _, path = create(client, key)
    with TestClient(app, base_url=ORIGIN) as outsider:
        assert outsider.delete(path).status_code == 401
    assert client.delete(path, headers={"Origin": "https://other.invalid"}).status_code == 403
    assert client.delete(path).status_code == 204
    assert client.post(ROOT, json=PRESET, headers=key).status_code == 409
    key = {"Idempotency-Key": str(uuid4())}
    guest, old_path = create(client, key)
    register(client)
    owner, owner_path = create(client, csrf(client))
    ids = [guest.json()["id"], owner.json()["id"]]
    with Session(database) as session, session.begin():
        session.execute(update(Reading).where(Reading.id.in_(ids)).values(created_at=utc_now() - timedelta(days=31)))
    assert client.get(old_path).status_code == 404
    with TestClient(app, base_url=ORIGIN) as guest_retry:
        assert guest_retry.post(ROOT, json=PRESET, headers=key).status_code == 409
    with Session(database) as session:
        assert cleanup_guests(session) == 1
        assert cleanup_guests(session, apply=True, batch_size=1) == 1
        assert cleanup_guests(session, apply=True) == 0
    assert client.get(owner_path).status_code == 200
    with TestClient(app, base_url=ORIGIN) as guest_retry:
        assert guest_retry.post(ROOT, json=PRESET, headers=key).status_code == 409


def test_scoped_quotas_survive_deletion_and_cache_hits(client, app, database, monkeypatch):
    calls = []

    def handler(request):
        calls.append(json.loads(json.loads(request.content)["input"]))
        return provider_response(mock_result(calls[-1]))

    install_provider(monkeypatch, handler)
    settings = readings.get_settings()
    monkeypatch.setattr(settings, "ai_guest_ip_daily_request_limit", 0)
    monkeypatch.setattr(settings, "ai_account_daily_request_limit", 1)
    with Session(database) as session:
        used = session.scalar(select(func.count()).select_from(AIUsageLog).where(
            AIUsageLog.created_at >= utc_now().replace(hour=0, minute=0, second=0, microsecond=0),
        ))
    _, guest = create(client)
    reveal(client, guest)
    account = register(client).json()
    headers = csrf(client)
    result = client.post(f"{guest}/interpret", headers=headers)
    assert result.status_code == 200 and len(calls) == 1
    assert client.post(f"{guest}/interpret", headers=headers).json() == result.json() and len(calls) == 1
    assert client.delete(guest, headers=headers).status_code == 204

    _, owned = create(client, headers)
    reveal(client, owned, headers)
    assert client.post(f"{owned}/interpret", headers=headers).status_code == 200 and len(calls) == 1
    assert client.get(owned).json()["interpretation_source"] == "database"
    with TestClient(app, base_url=ORIGIN) as other_member:
        register(other_member)
        other_headers = csrf(other_member)
        _, other_owned = create(other_member, other_headers)
        reveal(other_member, other_owned, other_headers)
        assert other_member.post(f"{other_owned}/interpret", headers=other_headers).status_code == 200 and len(calls) == 2
    with Session(database) as session:
        detached = session.scalars(select(AIUsageLog).where(
            AIUsageLog.reading_id.is_(None), AIUsageLog.quota_scope == f"user:{account['id']}",
        )).all()
        assert len(detached) == 1
    monkeypatch.setattr(settings, "ai_daily_request_limit", used + 2)
    with TestClient(app, base_url=ORIGIN) as third_member:
        register(third_member)
        third_headers = csrf(third_member)
        _, third_owned = create(third_member, third_headers)
        reveal(third_member, third_owned, third_headers)
        assert third_member.post(f"{third_owned}/interpret", headers=third_headers).status_code == 200 and len(calls) == 2
        assert third_member.get(third_owned).json()["interpretation_source"] == "database"


def test_delete_during_interpretation_does_not_recreate_reading(client, database, monkeypatch):
    entered, release = Event(), Event()

    def handler(request):
        entered.set()
        assert release.wait(5)
        return provider_response(mock_result(json.loads(json.loads(request.content)["input"])))

    install_provider(monkeypatch, handler)
    key = {"Idempotency-Key": str(uuid4())}
    created, path = create(client, key)
    reveal(client, path)
    register(client)
    headers = csrf(client)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.post, f"{path}/interpret", headers=headers)
        try:
            assert entered.wait(5)
            assert client.delete(path, headers=headers).status_code == 204
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 404
    assert client.post(ROOT, json=PRESET, headers=dict(headers, **key)).status_code == 409
    with Session(database) as session:
        assert session.get(Reading, created.json()["id"]) is None
