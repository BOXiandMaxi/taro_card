import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, create_engine, event, func, inspect, select
from sqlalchemy.orm import Session

from app.api.routes import readings
from app.database.base import Base, utc_now
from app.database.session import get_session
from app.main import create_app
from app.models import AIUsageLog, CardMeaning, Reading, ReadingCard, ReadingCreateKey, SpreadPosition, TarotCard, TarotSpread
from database.seeds.card_meanings import MEANINGS
from database.seeds.reference_data import CARDS, POSITIONS
from database.seeds.seed import seed_reference_data

ROOT = "/api/readings"
PRESET = {"category_id": 1, "question_id": 1, "spread_id": 1}
LEGACY_ID = "00000000-0000-4000-8000-000000000001"
LEGACY_TOKEN = "a" * 64
LEGACY_KEY_HASH = "b" * 64


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    url = os.getenv("READING_TEST_DATABASE_URL")
    prepared = False
    if url:
        engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
        assert engine.dialect.name == "mysql" and engine.url.database == "tarot_reading_test"
    else:
        engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('reading-db') / 'reading.sqlite'}")

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function("char_length", 1, lambda value: len(value) if value is not None else None)

    try:
        assert not inspect(engine).get_table_names(), "Reading tests require an empty disposable database"
        prepared = True
        scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic"))
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection, opts={"target_metadata": Base.metadata})):
                scripts.get_revision("0001_initial_schema").module.upgrade()
                scripts.get_revision("0002_card_image_filename").module.upgrade()
        with Session(engine) as session, session.begin():
            seed_reference_data(session)
        with engine.begin() as connection:
            legacy_readings = Table("readings", MetaData(), autoload_with=connection)
            connection.execute(legacy_readings.insert().values(
                id=LEGACY_ID, **PRESET, created_at=utc_now(), updated_at=utc_now(),
                anonymous_capability_hash=sha256(LEGACY_TOKEN.encode()).hexdigest(),
            ))
            with Operations.context(MigrationContext.configure(connection)):
                scripts.get_revision("0003_reading_engine").module.upgrade()
                readings_v3 = Table("readings", MetaData(), autoload_with=connection)
                connection.execute(readings_v3.update().where(readings_v3.c.id == LEGACY_ID).values(
                    create_key_hash=LEGACY_KEY_HASH,
                ))
                usage_v3 = Table("ai_usage_logs", MetaData(), autoload_with=connection)
                connection.execute(usage_v3.insert().values(
                    reading_id=LEGACY_ID, provider="test", model="test", status="success",
                    created_at=utc_now() - timedelta(days=2),
                ))
                scripts.get_revision("0004_accounts").module.upgrade()
                scripts.get_revision("0005_visitor_analytics").module.upgrade()
                scripts.get_revision("0006_user_id_sequence").module.upgrade()
        yield engine
    finally:
        if url and prepared:
            Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def app(database):
    app = create_app()

    def test_session():
        with Session(database) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    return app


@pytest.fixture
def client(app):
    with TestClient(app, base_url="https://testserver") as client:
        yield client


def create(client, body=PRESET, headers=None):
    response = client.post(ROOT, json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response


def assert_hidden(cards):
    assert cards
    for card in cards:
        assert card["card"] is None and card["orientation"] is None and not card["revealed"]
        assert card["meaning"] is None
        assert "card_id" not in card


def test_additive_migration_preserves_old_reading(client, database):
    with database.connect() as connection:
        if database.dialect.name == "sqlite":
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        assert connection.scalar(select(ReadingCreateKey.key_hash).where(
            ReadingCreateKey.key_hash == LEGACY_KEY_HASH,
        )) == LEGACY_KEY_HASH
        assert connection.execute(select(AIUsageLog.status, AIUsageLog.quota_scope).where(
            AIUsageLog.reading_id == LEGACY_ID,
        )).one() == ("success", None)
    cookie = {"Cookie": f"__Secure-tarot-reading-{LEGACY_ID}={LEGACY_TOKEN}"}
    path = f"{ROOT}/{LEGACY_ID}"
    legacy = client.get(path, headers=cookie).json()
    assert legacy["status"] == "CREATED" and legacy["requested_card_count"] == 3
    assert client.post(f"{path}/draw", headers=cookie, json={"selected_indices": [0, 1, 2]}).status_code == 409


def test_local_http_cookie_allows_reading_flow(app):
    with TestClient(app, base_url="http://127.0.0.1:8000") as local:
        created = create(local)
        assert "Secure" not in created.headers["Set-Cookie"]
        path = f"{ROOT}/{created.json()['id']}"
        assert local.get(path).status_code == 200
        assert local.post(f"{path}/draw", json={"selected_indices": [0, 1, 2]}).status_code == 200


@pytest.mark.parametrize(("spread_id", "count"), [(1, 3), (2, 5), (3, 10)])
def test_ordered_draw_and_individual_reveals(client, database, monkeypatch, spread_id, count):
    monkeypatch.setattr(readings.get_settings(), "reversed_cards_enabled", False)
    created = create(client, {**PRESET, "spread_id": spread_id}).json()
    path = f"{ROOT}/{created['id']}"
    assert created["status"] == "CREATED" and created["cards"] == []
    assert created["spread"]["card_count"] == count and created["question"]["id"] == 1
    assert "deck_order" not in created and "anonymous_capability_hash" not in created
    with Session(database) as session:
        deck = session.get(Reading, created["id"]).deck_order
    assert sorted(deck) == list(range(1, 79))
    details = client.get(path).json()
    assert {field: details[field] for field in created} == created
    assert details["category"]["id"] == PRESET["category_id"]
    assert details["created_at"].endswith("Z")
    assert client.post(f"{path}/reveal", json={"position_number": 1}).status_code == 409

    indices = [77, 0, *range(9, 9 - (count - 2), -1)]

    def unexpected_randomness(_):
        pytest.fail("Draw must reuse the persisted deck and skip orientation RNG when reversals are off")

    monkeypatch.setattr(readings.secrets, "randbelow", unexpected_randomness)
    drawn = client.post(f"{path}/draw", json={"selected_indices": indices})
    assert drawn.status_code == 200
    assert drawn.json()["status"] == "DRAWN"
    assert [card["position_number"] for card in drawn.json()["cards"]] == list(range(1, count + 1))
    assert_hidden(drawn.json()["cards"])
    assert_hidden(client.get(path).json()["cards"])
    assert client.post(f"{path}/draw", json={"selected_indices": indices[::-1]}).status_code == 409

    seen = []
    for number in range(count, 0, -1):
        reveal = {"position_number": number}
        opened = client.post(f"{path}/reveal", json=reveal)
        assert opened.status_code == 200
        card = opened.json()
        assert card["revealed"] and card["position_number"] == number
        assert card["orientation"] == "upright" and card["position"]["meaning_th"]
        assert card["card"]["id"] == deck[indices[number - 1]]
        if number == count:
            current = client.get(path).json()["cards"]
            assert_hidden(current[:-1])
            assert current[-1] == card
        seen.append(card)
    assert len({card["card"]["id"] for card in seen}) == count
    assert client.get(path).json()["cards"] == seen[::-1]
    assert client.post(f"{path}/reveal", json={"position_number": count}).json() == seen[0]
    assert client.post(f"{path}/draw", json={"selected_indices": indices}).json() == drawn.json()


def test_shuffle_and_reversal_use_expected_random_ranges(client, monkeypatch):
    monkeypatch.setattr(readings.get_settings(), "reversed_cards_enabled", True)
    bounds = []
    random = iter([0] * 77 + [1, 0, 1])

    def randbelow(bound):
        bounds.append(bound)
        return next(random)

    monkeypatch.setattr(readings.secrets, "randbelow", randbelow)
    path = f"{ROOT}/{create(client).json()['id']}"
    selection = {"selected_indices": [0, 1, 2]}
    draw = client.post(f"{path}/draw", json=selection)
    assert draw.status_code == 200
    assert_hidden(draw.json()["cards"])
    assert_hidden(client.get(path).json()["cards"])
    assert bounds == [*range(78, 1, -1), 2, 2, 2]

    revealed = []
    expected_cards = [(2, "reversed"), (3, "upright"), (4, "reversed")]
    for number, (card_id, orientation) in enumerate(expected_cards, start=1):
        response = client.post(f"{path}/reveal", json={"position_number": number})
        assert response.status_code == 200
        card = response.json()
        assert card["card"]["id"] == card_id
        assert card["orientation"] == orientation
        assert card["meaning"] == {
            "keywords": MEANINGS[card_id][f"{orientation}_keywords"],
            "description": MEANINGS[card_id][f"{orientation}_description"],
        }
        revealed.append(card)
        if number == 1:
            monkeypatch.setattr(readings.get_settings(), "reversed_cards_enabled", False)
        refreshed = client.get(path).json()["cards"]
        assert refreshed[:number] == revealed
        if number < len(expected_cards):
            assert_hidden(refreshed[number:])

    assert client.post(f"{path}/reveal", json={"position_number": 1}).json() == revealed[0]
    assert client.post(f"{path}/draw", json=selection).json() == draw.json()
    assert bounds == [*range(78, 1, -1), 2, 2, 2]


def test_revealed_card_without_meaning_returns_null():
    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(engine, tables=[TarotCard.__table__, CardMeaning.__table__])
        with Session(engine) as session, session.begin():
            session.add(TarotCard(**CARDS[0]))
            session.flush()
            position = SpreadPosition(**POSITIONS[0])
            item = ReadingCard(card_id=CARDS[0]["id"], orientation="reversed", revealed_at=utc_now())
            response = readings._card_response(session, position, item, show_reveals=True)
            assert response.revealed and response.card.id == item.card_id
            assert response.orientation == "reversed"
            assert response.meaning is None
    finally:
        engine.dispose()


def test_create_retry_recovers_lost_cookie_and_rejects_conflicts(client, app, database):
    headers = {"Idempotency-Key": str(uuid4())}
    body = {"category_id": 1, "spread_id": 1, "custom_question": "  คำถาม  "}
    first = create(client, body, headers)
    cookie = first.headers["Set-Cookie"]
    path = f"{ROOT}/{first.json()['id']}"
    assert first.json()["question_text"] == "คำถาม" and first.json()["question"] is None
    for attribute in ("Secure", "HttpOnly", "SameSite=lax", f"Path={path}"):
        assert attribute in cookie
    assert client.post(f"{path}/draw", json={"selected_indices": [0, 1, 2]}).status_code == 200
    with TestClient(app, base_url="https://testserver") as retry:
        assert retry.get(path).status_code == 401
        replayed = create(retry, {**body, "custom_question": "คำถาม"}, headers)
        assert replayed.json() == first.json() and replayed.headers["Set-Cookie"] == cookie
        assert retry.get(path).json()["status"] == "DRAWN"
        assert retry.post(ROOT, json={**body, "spread_id": 2}, headers=headers).status_code == 409
    with Session(database) as session:
        stored = session.get(Reading, first.json()["id"])
        assert stored.anonymous_capability_hash == sha256(cookie.split(";", 1)[0].split("=", 1)[1].encode()).hexdigest()
        assert stored.create_key_hash != headers["Idempotency-Key"]


def test_private_routes_require_matching_cookie(client, app):
    first = create(client).json()["id"]
    second = create(client).json()["id"]
    path = f"{ROOT}/{first}"
    assert client.get(path).status_code == 200
    assert client.get(f"{ROOT}/{second}").status_code == 200
    with TestClient(app, base_url="https://testserver") as stranger:
        for method, suffix, params in (
            ("GET", "", {}),
            ("POST", "/draw", {"json": {"selected_indices": [0, 1, 2]}}),
            ("POST", "/reveal", {"json": {"position_number": 1}}),
        ):
            assert stranger.request(method, f"{path}{suffix}", **params).status_code == 401
            other_token = client.cookies.get(f"__Secure-tarot-reading-{second}")
            forged = {"Cookie": f"__Secure-tarot-reading-{first}={other_token}"}
            assert stranger.request(method, f"{path}{suffix}", headers=forged, **params).status_code == 404
    assert client.post(f"{path}/draw", headers={"Origin": "https://foreign.example"}, json={
        "selected_indices": [0, 1, 2],
    }).status_code == 403
    preflight = client.options(ROOT, headers={
        "Origin": readings.get_settings().cors_origins[0], "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "idempotency-key, content-type",
    })
    assert preflight.status_code == 200


def test_invalid_inputs_do_not_draw(client):
    for body in (
        {**PRESET, "category_id": 2}, {**PRESET, "category_id": 9999}, {**PRESET, "question_id": 9999},
        {**PRESET, "spread_id": 9999}, {**PRESET, "question_id": None}, {**PRESET, "custom_question": "Both"},
        {**PRESET, "question_id": None, "custom_question": " "},
        {**PRESET, "question_id": None, "custom_question": "เ" * 1001},
    ):
        assert client.post(ROOT, json=body).status_code == 422
    assert client.post(ROOT, json=PRESET, headers={"Idempotency-Key": "guessable"}).status_code == 422
    path = f"{ROOT}/{create(client).json()['id']}"
    for indices in ([0, 1], [0, 1, 2, 3], [0, 0, 1], [-1, 0, 1], [0, 1, 78], [True, 1, 2], [0, "1", 2]):
        assert client.post(f"{path}/draw", json={"selected_indices": indices}).status_code == 422
    assert client.get(path).json()["status"] == "CREATED"
    assert client.post(f"{path}/draw", json={"selected_indices": [0, 1, 2]}).status_code == 200
    for number in (0, 4, 11, True):
        assert client.post(f"{path}/reveal", json={"position_number": number}).status_code == 422
    assert_hidden(client.get(path).json()["cards"])


def test_incomplete_spread_rejected(client, database):
    with Session(database) as session, session.begin():
        spread = TarotSpread(slug="incomplete-test", name_th="Incomplete", card_count=3)
        session.add(spread)
        session.flush()
        spread_id = spread.id
    assert client.post(ROOT, json={**PRESET, "spread_id": spread_id}).status_code == 503


def test_failed_draw_rolls_back_the_entire_write(app, client, database):
    reading_id = create(client).json()["id"]
    path = f"{ROOT}/{reading_id}"
    selection = {"selected_indices": [0, 1, 2]}

    def fail_after_flush(session, _):
        if any(isinstance(row, ReadingCard) and row.reading_id == reading_id for row in session.new):
            raise RuntimeError("Simulated failure after the draw writes its rows")

    event.listen(Session, "after_flush", fail_after_flush)
    try:
        with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as retry:
            retry.cookies.update(client.cookies)
            assert retry.post(f"{path}/draw", json=selection).status_code == 500
    finally:
        event.remove(Session, "after_flush", fail_after_flush)
    with Session(database) as session:
        reading = session.get(Reading, reading_id)
        assert reading.status == "CREATED" and reading.selected_indices is None and not reading.cards
    assert client.post(f"{path}/draw", json=selection).status_code == 200


def concurrent_requests(app, engine, sql_matches, path, bodies, headers):
    barrier = Barrier(2, timeout=10)

    def overlap(connection, cursor, statement, parameters, context, executemany):
        if sql_matches(statement):
            barrier.wait()

    def post(body):
        with TestClient(app, base_url="https://testserver") as instance:
            return instance.post(path, json=body, headers=headers)

    event.listen(engine, "before_cursor_execute", overlap)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(post, bodies))
    finally:
        event.remove(engine, "before_cursor_execute", overlap)


@pytest.fixture
def mysql(database):
    if database.dialect.name != "mysql":
        pytest.skip("READING_TEST_DATABASE_URL is required to exercise InnoDB concurrency")
    return database


def test_concurrent_create_retry(app, mysql):
    headers = {"Idempotency-Key": str(uuid4())}
    first, second = concurrent_requests(
        app, mysql, lambda sql: sql.startswith("INSERT INTO reading_create_keys "), ROOT, [PRESET, PRESET], headers,
    )
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.headers["Set-Cookie"] == second.headers["Set-Cookie"]
    with Session(mysql) as session:
        assert session.scalar(select(func.count()).select_from(Reading).where(
            Reading.create_key_hash == sha256(bytes.fromhex(headers["Idempotency-Key"].replace("-", ""))).hexdigest(),
        )) == 1


@pytest.mark.parametrize("same_selection", [True, False])
def test_concurrent_draw_and_reveal(client, app, mysql, same_selection):
    reading_id = create(client).json()["id"]
    path = f"{ROOT}/{reading_id}"
    cookie_name = f"__Secure-tarot-reading-{reading_id}"
    headers = {"Cookie": f"{cookie_name}={client.cookies.get(cookie_name)}"}
    picks = [[0, 1, 2], [0, 1, 2] if same_selection else [2, 1, 0]]

    def row_lock(sql):
        return sql.endswith("FOR UPDATE")

    results = concurrent_requests(app, mysql, row_lock, f"{path}/draw", [
        {"selected_indices": indices} for indices in picks
    ], headers)
    assert sorted(result.status_code for result in results) == [200, 200 if same_selection else 409]
    winner = next(i for i, result in enumerate(results) if result.status_code == 200)
    if same_selection:
        assert results[0].json() == results[1].json()
    first, second = concurrent_requests(app, mysql, row_lock, f"{path}/reveal", [{"position_number": 2}] * 2, headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    with Session(mysql) as session:
        reading = session.get(Reading, reading_id)
        assert reading.selected_indices == picks[winner]
        assert len(reading.cards) == 3 and len({card.card_id for card in reading.cards}) == 3
        opened = [card for card in reading.cards if card.revealed_at is not None]
        assert len(opened) == 1 and opened[0].card_id == first.json()["card"]["id"]
        revealed_at = opened[0].revealed_at
        row_id = opened[0].id
    assert client.post(f"{path}/reveal", json={"position_number": 2}).json() == first.json()
    with Session(mysql) as session:
        assert session.get(ReadingCard, row_id).revealed_at == revealed_at
