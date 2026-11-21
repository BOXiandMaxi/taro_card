import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.session import get_session
from app.main import create_app
from app.models import CardMeaning, Category, Question, SpreadPosition, TarotCard, TarotSpread
from database.seeds.card_meanings import MEANINGS
from database.seeds.reference_data import CARDS


@pytest.fixture(scope="module")
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    try:
        models = (Category, Question, SpreadPosition, TarotSpread, TarotCard, CardMeaning)
        Base.metadata.create_all(engine, tables=[model.__table__ for model in models])
        with Session(engine) as session, session.begin():
            session.add_all([
                Category(id=2, slug="work", name_th="งาน"),
                Category(id=1, slug="love", name_th="ความรัก"),
                TarotSpread(id=1, slug="three-card", name_th="ไพ่สามใบ", card_count=3, positions=[
                    SpreadPosition(id=11, position_number=3, meaning_th="อนาคต"),
                    SpreadPosition(id=12, position_number=2, meaning_th="ปัจจุบัน"),
                    SpreadPosition(id=13, position_number=1, meaning_th="อดีต"),
                ]),
                Question(id=1, category_id=1, prompt_th="คำถามที่สอง", display_order=2),
                Question(id=2, category_id=1, prompt_th="คำถามแรก", display_order=1, recommended_spread_id=1),
                Question(id=3, category_id=2, prompt_th="งานเป็นอย่างไร", display_order=1),
                TarotCard(**CARDS[1]),
                TarotCard(**CARDS[0], meaning=CardMeaning(**MEANINGS[1])),
            ])

        def test_session():
            with Session(engine) as session:
                yield session

        app = create_app()
        app.dependency_overrides[get_session] = test_session
        with TestClient(app) as client:
            yield client
    finally:
        engine.dispose()


def test_categories_read_database_rows(client):
    response = client.get("/api/categories")
    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "slug": "love", "name_th": "ความรัก"},
        {"id": 2, "slug": "work", "name_th": "งาน"},
    ]


def test_questions_filter_and_order(client):
    response = client.get("/api/questions", params={"category_id": 1})
    assert response.status_code == 200
    assert response.json() == [
        {"id": 2, "category_id": 1, "prompt_th": "คำถามแรก", "display_order": 1, "recommended_spread_id": 1},
        {"id": 1, "category_id": 1, "prompt_th": "คำถามที่สอง", "display_order": 2, "recommended_spread_id": None},
    ]
    assert [question["id"] for question in client.get("/api/questions").json()] == [2, 1, 3]
    empty = client.get("/api/questions", params={"category_id": 99})
    assert empty.status_code == 200
    assert empty.json() == []
    assert client.get("/api/questions", params={"category_id": "invalid"}).status_code == 422


def test_spread_positions_use_position_numbers(client):
    response = client.get("/api/spreads")
    assert response.status_code == 200
    assert response.json() == [{
        "id": 1,
        "slug": "three-card",
        "name_th": "ไพ่สามใบ",
        "card_count": 3,
        "positions": [
            {"id": 13, "spread_id": 1, "position_number": 1, "meaning_th": "อดีต"},
            {"id": 12, "spread_id": 1, "position_number": 2, "meaning_th": "ปัจจุบัน"},
            {"id": 11, "spread_id": 1, "position_number": 3, "meaning_th": "อนาคต"},
        ],
    }]


def test_card_list_and_detail(client):
    response = client.get("/api/cards")
    assert response.status_code == 200
    assert response.json() == CARDS[:2]

    detail = client.get("/api/cards/1")
    assert detail.status_code == 200
    assert detail.json() == {**CARDS[0], "meaning": {key: value for key, value in MEANINGS[1].items() if key != "card_id"}}
    assert client.get("/api/cards/2").json() == {**CARDS[1], "meaning": None}


def test_missing_card_returns_404(client):
    response = client.get("/api/cards/78")
    assert response.status_code == 404
    assert response.json() == {"detail": "Card not found"}
