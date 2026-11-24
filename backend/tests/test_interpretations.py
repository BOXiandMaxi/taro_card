import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Event
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes import readings
from app.core.config import Settings
from app.database.base import utc_now
from app.models import AIUsageLog, CardMeaning, Reading, ReadingInterpretation
from app.services import auth, interpretations
from app.services.interpretation_provider import Attempt, GeminiProvider, OpenAIProvider, get_provider
from database.seeds.card_meanings import MEANINGS
from database.seeds.reference_data import CATEGORIES, QUESTIONS
from test_reading_engine import ROOT, app, client as guest_client, create, database

CATEGORY_FIELDS = ["daily_life_meaning", "finance_meaning", "love_meaning", "career_meaning", "general_guidance_meaning"]
THAI_CARD_PROSE = (
    # The first two share an opening but give different advice and must pass.
    "ลองสังเกตว่าส่วนไหนของสถานการณ์ที่คุณจัดการได้ในตอนนี้",
    "ลองสังเกตว่าเงื่อนไขที่ยังคลุมเครือทำให้คุณต้องชะลอการตัดสินใจหรือเปล่า",
    "เริ่มจากทางเลือกที่เปิดโอกาสให้เปลี่ยนใจได้เมื่อมีข้อมูลเพิ่ม",
    "ความคาดหวังเดิมอาจมีผลกับวิธีที่คุณตั้งคำถามในครั้งนี้",
    "ทบทวนเหตุการณ์ที่เพิ่งผ่านไปก่อนตั้ง deadline ให้ตัวเองอีกครั้ง",
    "ดูว่าความเปลี่ยนแปลงเล็ก ๆ ช่วยให้มีทางเลือกกว้างขึ้นไหม",
    "ลองบอกตัวเองว่าคุณให้ความสำคัญกับอะไรในการตัดสินใจนี้",
    "ถามคนที่เกี่ยวข้องเพื่อให้เข้าใจเงื่อนไขของสถานการณ์มากขึ้น",
    "เขียนสิ่งที่หวังและสิ่งที่กังวลแยกกันเพื่อดูว่าอะไรมีหลักฐานรองรับ",
    "ถ้าเงื่อนไขรอบตัวเปลี่ยน ลองเผื่อทางเลือกอีกทางไว้",
)
GENERIC_THAI_PROSE = (
    "ไพ่{name} ชวนให้คุณทบทวนสถานการณ์ในตอนนี้และเปิดใจรับความเปลี่ยนแปลง "
    "ลองพิจารณาทางเลือกที่มีอยู่แล้วค่อยตัดสินใจในจังหวะที่เหมาะกับคุณ"
)


def authenticate(client, monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(_env_file=None, auth_attempt_limit=100))
    csrf = client.get("/api/auth/csrf").json()["csrf_token"]
    response = client.post("/api/auth/register", headers={
        "Origin": "https://testserver", "X-CSRF-Token": csrf,
    }, json={"email": f"{uuid4()}@example.test", "password": "test-password"})
    assert response.status_code == 201, response.text
    client.headers["Origin"] = "https://testserver"
    client.headers["X-CSRF-Token"] = client.get("/api/auth/csrf").json()["csrf_token"]
    return response.json()["id"]


@pytest.fixture(name="client")
def authenticated_client(guest_client, monkeypatch):
    authenticate(guest_client, monkeypatch)
    return guest_client


def begin_reading(client, category=1, spread=1, *, custom=False):
    question = {"custom_question": "  ฉันควรเริ่มจากตรงไหน  "} if custom else {"question_id": (category - 1) * 6 + 1}
    reading = create(client, {"category_id": category, "spread_id": spread, **question}).json()
    return f"{ROOT}/{reading['id']}", reading["spread"]["card_count"]


def draw_and_reveal(client, path, count, *, leave_hidden=0):
    assert client.post(f"{path}/draw", json={"selected_indices": list(range(count))}).is_success
    cards = []
    for position in range(1, count + 1 - leave_hidden):
        response = client.post(f"{path}/reveal", json={"position_number": position})
        assert response.is_success, response.text
        cards.append(response.json())
    return cards


def provider_response(result):
    return httpx.Response(200, json={
        "status": "completed",
        "usage": {"input_tokens": 1000, "output_tokens": 200},
        "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}],
    })


def mock_result(payload):
    return {
        "reading_id": payload.get("reading_id", "test-reading"),
        "language": "th",
        "overall_summary": "ขอให้ค่อย ๆ ทบทวนสิ่งที่สำคัญ",
        "card_interpretations": [
            {
                "position": card["position"], "position_name": card["position_name"],
                "card_id": card["card_id"], "orientation": card["orientation"],
                "interpretation": prose,
            }
            for card, prose in zip(payload["cards"], THAI_CARD_PROSE)
        ],
        "card_connections": "ไพ่สะท้อนความรู้สึกในแต่ละด้าน",
        "practical_guidance": ["ลองจดสิ่งที่กำลังคิดอยู่"],
        "closing_message": "ให้เวลากับตัวเอง",
    }


def install_provider(monkeypatch, handler, *, timeout=2, limit=100):
    settings = Settings(
        _env_file=None, ai_provider="openai", ai_model="gpt-6.1-terra", ai_api_key="mock-key",
        ai_timeout_seconds=timeout, ai_max_output_tokens=4000,
        ai_input_usd_per_million=None, ai_output_usd_per_million=None,
    )
    monkeypatch.setattr(readings.get_settings(), "ai_daily_request_limit", limit)
    monkeypatch.setattr(readings.get_settings(), "ai_account_daily_request_limit", limit)
    monkeypatch.setattr(readings, "get_provider", lambda _: OpenAIProvider(settings, httpx.MockTransport(handler)))


def saved_rows(database, path):
    reading_id = path.rsplit("/", 1)[-1]
    with Session(database) as session:
        return (
            session.scalar(select(ReadingInterpretation).where(ReadingInterpretation.reading_id == reading_id)),
            session.scalars(
                select(AIUsageLog).where(AIUsageLog.reading_id == reading_id).order_by(AIUsageLog.id)
            ).all(),
        )


def test_openai_settings_and_alternate_model_prices(monkeypatch):
    for key, value in {
        "AI_PROVIDER": "openai",
        "AI_MODEL": "alternate-model",
        "AI_API_KEY": "mock-key",
        "AI_TIMEOUT_SECONDS": "8.5",
        "AI_MAX_OUTPUT_TOKENS": "2048",
        "AI_DAILY_REQUEST_LIMIT": "7",
        "AI_INPUT_USD_PER_MILLION": "1.25",
        "AI_OUTPUT_USD_PER_MILLION": "5",
    }.items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None)
    provider = get_provider(settings)
    assert isinstance(provider, OpenAIProvider)
    assert (provider.model, provider.timeout, provider.max_tokens) == ("alternate-model", 8.5, 2048)
    assert settings.ai_daily_request_limit == 7
    assert provider.estimate_cost(Attempt("success", 1000, 200)) == Decimal("0.00225")
    monkeypatch.setenv("AI_API_KEY", "")
    assert get_provider(Settings(_env_file=None)) is None


def test_gemini_settings_require_own_key():
    settings = Settings(
        _env_file=None, ai_provider="gemini", ai_model="gemini-2.5-flash",
        ai_api_key="openai-key", gemini_api_key="",
    )
    assert get_provider(settings) is None
    provider = get_provider(Settings(
        _env_file=None, ai_provider="gemini", ai_model="gemini-2.5-flash",
        gemini_api_key="mock-gemini-key",
    ))
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "gemini-2.5-flash"


@pytest.mark.parametrize("spread", [1, 2, 3])
def test_gemini_mock_reading_preserves_draw_and_cache(client, database, monkeypatch, spread):
    path, count = begin_reading(client, spread=spread)
    draw_and_reveal(client, path, count)
    calls = []

    def handler(request):
        assert request.url == httpx.URL(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        )
        assert request.headers["x-goog-api-key"] == "mock-gemini-key"
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["responseJsonSchema"]["additionalProperties"] is False
        assert body["generationConfig"]["maxOutputTokens"] == 6000
        assert "Use only the given cards in order" in body["systemInstruction"]["parts"][0]["text"]
        payload = json.loads(body["contents"][0]["parts"][0]["text"])
        assert payload["card_count"] == count
        result = mock_result(payload)
        calls.append(result)
        return httpx.Response(200, json={
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(result)}]}}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 180, "thoughtsTokenCount": 20},
        })

    settings = Settings(
        _env_file=None, ai_provider="gemini", ai_model="gemini-2.5-flash",
        gemini_api_key="mock-gemini-key",
    )
    monkeypatch.setattr(readings, "get_provider", lambda _: GeminiProvider(settings, httpx.MockTransport(handler)))
    response = client.post(f"{path}/interpret")
    assert response.status_code == 200, response.text
    assert response.json() == calls[0]
    assert client.get(f"{path}/interpretation").json() == calls[0]
    assert client.post(f"{path}/interpret").json() == calls[0]
    assert client.get(path).json()["interpretation_source"] == "ai"
    assert len(calls) == 1
    row, logs = saved_rows(database, path)
    assert row.source == "ai" and row.model == "gemini-2.5-flash"
    assert [(log.status, log.input_tokens, log.output_tokens) for log in logs] == [
        ("success", 900, 200),
    ]


@pytest.mark.parametrize("defect", ["wrong_card", "blocked", "bad_json"])
def test_gemini_invalid_response_falls_back(client, database, monkeypatch, defect):
    path, count = begin_reading(client)
    cards = draw_and_reveal(client, path, count)

    def handler(request):
        payload = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])
        result = mock_result(payload)
        if defect == "wrong_card":
            result["card_interpretations"][0]["card_id"] = result["card_interpretations"][1]["card_id"]
        content = "{broken" if defect == "bad_json" else json.dumps(result)
        return httpx.Response(200, json={
            "candidates": [{"finishReason": "SAFETY" if defect == "blocked" else "STOP",
                            "content": {"parts": [{"text": content}]}}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20},
        })

    settings = Settings(_env_file=None, ai_provider="gemini", ai_model="gemini-2.5-flash",
                        gemini_api_key="mock-gemini-key")
    monkeypatch.setattr(readings, "get_provider", lambda _: GeminiProvider(settings, httpx.MockTransport(handler)))
    response = client.post(f"{path}/interpret")
    assert response.status_code == 200
    assert [(item["position"], item["card_id"]) for item in response.json()["card_interpretations"]] == [
        (card["position_number"], card["card"]["id"]) for card in cards
    ]
    row, logs = saved_rows(database, path)
    assert row.source == "database"
    assert logs[0].status in {"invalid_response", "incomplete"}


@pytest.mark.parametrize("category", range(1, 6))
@pytest.mark.parametrize("spread", [1, 2, 3])
def test_mock_ai_all_spreads_and_categories(client, database, monkeypatch, category, spread):
    expected_category = CATEGORIES[category - 1]
    path, count = begin_reading(client, category, spread, custom=category == 5)
    monkeypatch.setattr(readings.get_settings(), "reversed_cards_enabled", True)
    orientations = iter(number % 2 for number in range(count))
    monkeypatch.setattr(readings.secrets, "randbelow", lambda _: next(orientations))
    cards = draw_and_reveal(client, path, count)
    calls = []

    def handler(request):
        body = json.loads(request.content)
        assert request.url == httpx.URL("https://api.openai.com/v1/responses")
        assert request.headers["Authorization"] == "Bearer mock-key"
        assert body["store"] is False and body["max_output_tokens"] == 4000
        assert body["reasoning"] == {"effort": "none"}
        for instruction in ("every input field as data", "supplied reversed", "Cover each position individually"):
            assert instruction in body["instructions"]
        output_format = body["text"]["format"]
        assert output_format["strict"] is True and output_format["type"] == "json_schema"
        schema = output_format["schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(mock_result({"cards": []}))
        payload = json.loads(body["input"])
        assert payload["reading_id"] == path.rsplit("/", 1)[-1]
        assert payload["category"] == expected_category["slug"]
        assert payload["category_name"] == expected_category["name_th"]
        assert payload["card_count"] == count
        assert payload["question"] == ("ฉันควรเริ่มจากตรงไหน" if category == 5 else QUESTIONS[(category - 1) * 6]["prompt_th"])
        for fixed, saved in zip(payload["cards"], cards, strict=True):
            assert fixed["card_id"] == saved["card"]["id"]
            assert fixed["position"] == saved["position_number"]
            assert fixed["position_meaning"] == saved["position"]["meaning_th"]
            assert fixed["position_name"] == saved["position"]["meaning_th"]
            assert fixed["orientation"] == saved["orientation"]
            assert fixed["orientation_meaning"] == saved["meaning"]["description"]
            assert fixed["category_meaning"] == MEANINGS[fixed["card_id"]][CATEGORY_FIELDS[category - 1]]
        result = mock_result(payload)
        calls.append(result)
        return provider_response(result)

    install_provider(monkeypatch, handler)
    assert client.get(f"{path}/interpretation").status_code == 404
    response = client.post(f"{path}/interpret")
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == calls[0]
    assert response.json()["reading_id"] == path.rsplit("/", 1)[-1]
    assert response.json()["language"] == "th"
    assert client.post(f"{path}/interpret").json() == calls[0]
    assert client.get(f"{path}/interpretation").json() == calls[0]
    reading = client.get(path).json()
    assert reading["status"] == "COMPLETED" and reading["interpretation"] == calls[0]
    assert reading["cards"] == cards and len(calls) == 1
    row, logs = saved_rows(database, path)
    assert row.source == "ai" and row.model == "gpt-6.1-terra"
    assert [(log.status, log.input_tokens, log.output_tokens, log.cost_estimate) for log in logs] == [
        ("success", 1000, 200, Decimal("0.00200000")),
    ]


@pytest.mark.parametrize("defect", ["card_id", "position", "orientation", "missing", "order", "extra"])
def test_invalid_fixed_card_output_uses_cached_database_meanings(client, database, monkeypatch, defect):
    path, count = begin_reading(client, category=3)
    cards = draw_and_reveal(client, path, count)

    def handler(request):
        result = mock_result(json.loads(json.loads(request.content)["input"]))
        entries = result["card_interpretations"]
        if defect == "order":
            entries.reverse()
        elif defect == "missing":
            entries.pop()
        elif defect == "extra":
            entries[0]["another_card"] = 78
        elif defect == "orientation":
            entries[0]["orientation"] = "upright" if cards[0]["orientation"] == "reversed" else "reversed"
        else:
            entries[0][defect] = entries[1][defect]
        return provider_response(result)

    install_provider(monkeypatch, handler)
    response = client.post(f"{path}/interpret")
    assert response.status_code == 200, response.text
    result = response.json()
    for entry, card in zip(result["card_interpretations"], cards, strict=True):
        assert entry["card_id"] == card["card"]["id"] and entry["position"] == card["position_number"]
        assert entry["position_name"] == card["position"]["meaning_th"]
        assert entry["orientation"] == card["orientation"]
        assert card["meaning"]["description"] in entry["interpretation"]
        assert MEANINGS[entry["card_id"]]["love_meaning"] in entry["interpretation"]
    assert client.get(f"{path}/interpretation").json() == result
    assert client.post(f"{path}/interpret").json() == result
    assert client.get(path).json()["interpretation_source"] == "database"
    row, logs = saved_rows(database, path)
    assert row.source == "database" and row.model is None
    assert [(log.status, log.cost_estimate) for log in logs] == [("invalid_response", Decimal("0.00200000"))]


def test_fallback_uses_saved_questions_with_the_same_career_draw(client, monkeypatch):
    monkeypatch.setattr(readings, "get_provider", lambda _: None)
    monkeypatch.setattr(readings, "_shuffled_deck", lambda _: list(range(1, 79)))
    monkeypatch.setattr(readings.get_settings(), "reversed_cards_enabled", False)
    results = []
    for question, answer_topic, action_topic in (
        ({"question_id": 20}, "งานใหม่แก้ปัญหา", "เทียบงานปัจจุบันกับงานที่สนใจ"),
        ({"custom_question": "  ฉันควรพัฒนาทักษะอะไรเพื่อเติบโตในสายงาน  "}, "ทักษะที่ได้ใช้กับงานจริง", "เลือกทักษะ"),
        ({"custom_question": "ควรเริ่มสมัครงานใหม่เมื่อไหร่?"}, "เริ่มสมัครได้", "วันปิดรับสมัคร"),
    ):
        reading = create(client, {"category_id": 4, "spread_id": 1, **question}).json()
        path = f"{ROOT}/{reading['id']}"
        draw_and_reveal(client, path, 3)
        response = client.post(f"{path}/interpret")
        assert response.is_success, response.text
        result = response.json()
        assert answer_topic in result["overall_summary"]
        assert action_topic in result["practical_guidance"][0]
        results.append(result)
    assert len({result["overall_summary"] for result in results}) == len(results)
    assert len({tuple(result["practical_guidance"]) for result in results}) == len(results)
    assert all(result["card_interpretations"] == results[0]["card_interpretations"] for result in results)
    assert len({result["card_connections"] for result in results}) == len(results)
    assert "ย้ายงาน" in results[0]["card_connections"]
    assert "เติบโตในงาน" in results[1]["card_connections"]
    assert "การสมัครงาน" in results[2]["card_connections"]


def test_fallback_answers_job_timing_for_the_five_card_example(client, monkeypatch):
    monkeypatch.setattr(readings, "get_provider", lambda _: None)
    draw = [66, 5, 64, 38, 16]
    deck = draw + [card_id for card_id in range(1, 79) if card_id not in draw]
    monkeypatch.setattr(readings, "_shuffled_deck", lambda _: deck)
    monkeypatch.setattr(readings.get_settings(), "reversed_cards_enabled", False)
    reading = create(client, {"category_id": 4, "spread_id": 2, "question_id": 32}).json()
    path = f"{ROOT}/{reading['id']}"
    draw_and_reveal(client, path, 5)

    response = client.post(f"{path}/interpret")
    assert response.is_success, response.text
    result = response.json()
    assert [entry["card_id"] for entry in result["card_interpretations"]] == draw
    assert "แน่นอนไม่ได้" in result["overall_summary"] and "สัมภาษณ์" in result["overall_summary"]
    assert "สมัคร" in result["practical_guidance"][0] and "เรซูเม่" in result["practical_guidance"][0]
    connections = result["card_connections"]
    assert "สาเหตุเดิม" in connections and "ตัวช่วยที่มี" in connections
    assert MEANINGS[64]["upright_description"] in result["overall_summary"]
    assert "คนที่รู้จักสายงาน" in result["practical_guidance"][1]
    assert any("ผลตอบกลับ" in step for step in result["practical_guidance"])
    assert client.get(f"{path}/interpretation").json() == result


def test_the_same_question_reflects_the_cards_and_their_orientation(client, monkeypatch):
    monkeypatch.setattr(readings, "get_provider", lambda _: None)
    readings_settings = readings.get_settings()
    monkeypatch.setattr(readings_settings, "reversed_cards_enabled", True)

    results = []
    for draw, reversed_cards in (([66, 5, 64, 38, 16], set()), ([66, 5, 64, 38, 16], {3, 4, 5}),
                                 ([3, 12, 19, 9, 6], set()), ([66, 5, 38, 64, 16], set())):
        deck = draw + [card_id for card_id in range(1, 79) if card_id not in draw]
        monkeypatch.setattr(readings, "_shuffled_deck", lambda _: deck)
        flags = iter(int(position in reversed_cards) for position in range(1, 6))
        monkeypatch.setattr(readings.secrets, "randbelow", lambda _: next(flags))
        reading = create(client, {"category_id": 4, "spread_id": 2, "question_id": 32}).json()
        path = f"{ROOT}/{reading['id']}"
        draw_and_reveal(client, path, 5)
        response = client.post(f"{path}/interpret")
        assert response.is_success, response.text
        results.append(response.json())

    upright, reversed_, different, swapped = results
    assert all("แน่นอนไม่ได้" in result["overall_summary"] for result in results)
    assert MEANINGS[64]["upright_description"] in upright["overall_summary"]
    assert MEANINGS[64]["reversed_description"] in reversed_["overall_summary"]
    assert MEANINGS[64]["upright_description"] not in reversed_["overall_summary"]
    assert "ถามผู้ติดต่อว่า" in reversed_["practical_guidance"][1]
    assert MEANINGS[19]["upright_description"] in different["overall_summary"]
    assert MEANINGS[38]["upright_description"] in swapped["overall_summary"]
    assert all("คนที่รู้จักสายงาน" not in step for step in swapped["practical_guidance"])


def test_fallback_answers_private_feelings_with_observable_behaviors(client, monkeypatch):
    monkeypatch.setattr(readings, "get_provider", lambda _: None)
    reading = create(client, {"category_id": 3, "spread_id": 1, "question_id": 31}).json()
    path = f"{ROOT}/{reading['id']}"
    draw_and_reveal(client, path, 3)
    response = client.post(f"{path}/interpret")
    assert response.is_success, response.text
    result = response.json()
    assert result["overall_summary"].startswith("ไพ่บอกแทนเขาไม่ได้")
    assert any("มองความสัมพันธ์ของเรายังไง" in step for step in result["practical_guidance"])
    assert any("รักษาคำพูด" in step for step in result["practical_guidance"])


@pytest.mark.parametrize("spread, guide_topic", [
    (1, "สองใบแรก"), (2, "สาเหตุเดิม"), (3, "ความหวังและความกลัว"),
])
def test_fallback_explains_spread_and_uses_selected_orientation(client, monkeypatch, spread, guide_topic):
    monkeypatch.setattr(readings, "get_provider", lambda _: None)
    monkeypatch.setattr(readings, "_shuffled_deck", lambda _: list(range(1, 79)))
    path, count = begin_reading(client, category=4, spread=spread)
    monkeypatch.setattr(readings.get_settings(), "reversed_cards_enabled", True)
    orientations = iter(number % 2 for number in range(count))
    monkeypatch.setattr(readings.secrets, "randbelow", lambda _: next(orientations))
    cards = draw_and_reveal(client, path, count)
    response = client.post(f"{path}/interpret")
    assert response.is_success, response.text
    result = response.json()
    connections = result["card_connections"]
    assert connections != result["overall_summary"]
    guidance = result["practical_guidance"]
    assert guide_topic in connections
    assert 2 <= len(guidance) <= 3
    for entry, card in zip(result["card_interpretations"], cards, strict=True):
        meaning = MEANINGS[card["card"]["id"]]
        selected = meaning[f"{card['orientation']}_description"]
        other = meaning["upright_description" if card["orientation"] == "reversed" else "reversed_description"]
        prose = entry["interpretation"]
        assert entry["card_id"] == card["card"]["id"]
        assert entry["position"] == card["position_number"] and entry["orientation"] == card["orientation"]
        assert entry["position_name"] == card["position"]["meaning_th"]
        assert prose.index(selected) < prose.index(meaning["career_meaning"])
        assert other not in prose
        assert selected not in connections
        assert card["card"]["name_th"] not in connections
        assert all(step not in prose for step in guidance)


def test_fallback_handles_blank_and_long_meanings(client, database, monkeypatch):
    monkeypatch.setattr(readings, "get_provider", lambda _: None)
    monkeypatch.setattr(readings, "_shuffled_deck", lambda _: list(range(1, 79)))
    monkeypatch.setattr(readings.get_settings(), "reversed_cards_enabled", False)
    question = ("ฉันควรเตรียมตัวอย่างไร" * 50)[:999] + "?"
    reading = create(client, {"category_id": 1, "spread_id": 1, "custom_question": question}).json()
    path = f"{ROOT}/{reading['id']}"
    draw_and_reveal(client, path, 3)
    changes = {
        1: {"upright_description": "  ", "daily_life_meaning": "", "upright_keywords": ["  "]},
        2: {"upright_description": "", "daily_life_meaning": ""},
        3: {"upright_description": "ความหมาย" * 800, "daily_life_meaning": "บริบท" * 900,
            "upright_keywords": ["คำสำคัญ" * 700]},
    }
    originals = {}
    try:
        with Session(database) as session, session.begin():
            for card_id, fields in changes.items():
                meaning = session.get(CardMeaning, card_id)
                originals[card_id] = {field: getattr(meaning, field) for field in fields}
                for field, value in fields.items():
                    setattr(meaning, field, value)
        response = client.post(f"{path}/interpret")
        assert response.is_success, response.text
        result = response.json()
        first, second, third = (entry["interpretation"] for entry in result["card_interpretations"])
        assert question not in result["overall_summary"]
        for paragraph in (first, second, third):
            assert len(paragraph) < 4000
        assert "มีข้อมูลความหมายของทิศนี้ไม่พอ" in first
        assert MEANINGS[2]["upright_keywords"][0] in second
        assert "ความหมาย" * 10 in third and "บริบท" * 10 in third and "…" in third
        assert client.get(f"{path}/interpretation").json() == response.json()
    finally:
        with Session(database) as session, session.begin():
            for card_id, fields in originals.items():
                meaning = session.get(CardMeaning, card_id)
                for field, value in fields.items():
                    setattr(meaning, field, value)


@pytest.mark.parametrize("defect", ["english", "mostly_english", "duplicate_thai", "card_names_only", "minor_rewording", "repeated_ending"])
def test_low_quality_ai_uses_cached_fallback(client, database, monkeypatch, defect):
    path, count = begin_reading(client)
    draw_and_reveal(client, path, count)
    calls = []

    def handler(request):
        payload = json.loads(json.loads(request.content)["input"])
        result = mock_result(payload)
        entries = result["card_interpretations"]
        if defect == "repeated_ending":
            result["card_connections"] = result["overall_summary"]
        elif defect == "duplicate_thai":
            entries[1]["interpretation"] = f"«{entries[0]['interpretation']}»"
        elif defect in {"card_names_only", "minor_rewording"}:
            for entry, card in zip(entries[:2], payload["cards"][:2], strict=True):
                entry["interpretation"] = GENERIC_THAI_PROSE.format(name=card["name_th"])
            if defect == "minor_rewording":
                # A small edit still leaves almost all three-character sequences shared.
                entries[1]["interpretation"] = entries[1]["interpretation"].replace("ลองพิจารณา", "ควรพิจารณา")
        elif defect == "mostly_english":
            entries[0]["interpretation"] = "ไพ่ This is a generic interpretation written entirely in English."
        else:
            result["overall_summary"] = "This is an English summary."
        calls.append(result)
        return provider_response(result)

    install_provider(monkeypatch, handler)
    response = client.post(f"{path}/interpret")
    assert response.is_success, response.text
    result = response.json()
    assert result != calls[0]
    assert client.post(f"{path}/interpret").json() == client.get(f"{path}/interpretation").json() == result
    assert len(calls) == 1
    row, logs = saved_rows(database, path)
    assert row.source == "database" and row.model is None
    assert [(log.status, log.input_tokens, log.output_tokens, log.cost_estimate) for log in logs] == [
        ("invalid_response", 1000, 200, Decimal("0.00200000")),
    ]


@pytest.mark.parametrize("legacy_style", ["english_duplicate", "near_duplicate_thai"])
def test_legacy_cached_prose_is_still_served(client, database, monkeypatch, legacy_style):
    monkeypatch.setattr(readings, "get_provider", lambda _: None)
    path, count = begin_reading(client)
    cards = draw_and_reveal(client, path, count)
    response = client.post(f"{path}/interpret")
    assert response.is_success, response.text
    result = response.json()
    for entry, card in zip(result["card_interpretations"], cards, strict=True):
        entry["interpretation"] = (
            "This is the same legacy paragraph for every card." if legacy_style == "english_duplicate"
            else GENERIC_THAI_PROSE.format(name=card["card"]["name_th"])
        )
    with Session(database) as session, session.begin():
        row = session.scalar(select(ReadingInterpretation).where(
            ReadingInterpretation.reading_id == result["reading_id"],
        ))
        row.result = result
        row.source = "ai"
        row.model = "gpt-6.1-terra"
    monkeypatch.setattr(readings, "get_provider", lambda _: pytest.fail("Cache hit must bypass provider"))
    assert client.get(f"{path}/interpretation").json() == result
    assert client.post(f"{path}/interpret").json() == result
    assert client.get(path).json()["interpretation"] == result


def test_interpret_requires_all_reveals(client, monkeypatch, database):
    monkeypatch.setattr(readings, "get_provider", lambda _: None)
    path, count = begin_reading(client)
    assert client.post(f"{path}/interpret").status_code == 409
    assert client.get(f"{path}/interpretation").status_code == 409
    draw_and_reveal(client, path, count, leave_hidden=1)
    assert client.post(f"{path}/interpret").status_code == 409
    assert client.post(f"{path}/reveal", json={"position_number": count}).is_success
    assert client.post(f"{path}/interpret", headers={"Origin": "https://foreign.example"}).status_code == 403
    assert saved_rows(database, path) == (None, [])
    assert client.post(f"{path}/interpret").is_success
    row, logs = saved_rows(database, path)
    assert row.source == "database" and not logs


@pytest.mark.parametrize("failure", ["http_429", "timeout", "refusal", "incomplete"])
def test_provider_failure_keeps_bounded_attempt_logs(client, database, monkeypatch, failure):
    path, count = begin_reading(client)
    draw_and_reveal(client, path, count)

    async def handler(_):
        if failure == "timeout":
            await asyncio.sleep(1)
        if failure == "http_429":
            return httpx.Response(429)
        body = {
            "status": "incomplete" if failure == "incomplete" else "completed",
            "usage": {"input_tokens": 500, "output_tokens": 16},
            "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "refused"}]}],
        }
        return httpx.Response(200, json=body)

    install_provider(monkeypatch, handler, timeout=0.05)
    assert client.post(f"{path}/interpret").is_success
    row, logs = saved_rows(database, path)
    assert row.source == "database"
    assert [log.status for log in logs] == [failure] * (2 if failure == "http_429" else 1)
    if failure in {"refusal", "incomplete"}:
        assert logs[0].cost_estimate == Decimal("0.00058000")


def test_concurrent_posts_share_claim_and_daily_budget(guest_client, app, database, monkeypatch):
    client = guest_client
    first, count = begin_reading(client)
    draw_and_reveal(client, first, count)
    second, count = begin_reading(client)
    draw_and_reveal(client, second, count)
    user_id = authenticate(client, monkeypatch)
    midnight = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(database) as session:
        used = session.scalar(select(func.count(AIUsageLog.id)).where(
            AIUsageLog.created_at >= midnight, AIUsageLog.created_at < midnight + timedelta(days=1),
        ))
    entered, release = Event(), Event()

    def handler(request):
        entered.set()
        assert release.wait(5), "Test did not release provider"
        return provider_response(mock_result(json.loads(json.loads(request.content)["input"])))

    install_provider(monkeypatch, handler, timeout=10, limit=used + 1)

    def post(path):
        with TestClient(app, base_url="https://testserver", headers=client.headers) as other:
            other.cookies.update(client.cookies)
            return other.post(f"{path}/interpret")

    with ThreadPoolExecutor(max_workers=1) as pool:
        in_flight = pool.submit(post, first)
        try:
            assert entered.wait(5)
            assert post(first).status_code == 409
            assert client.get(f"{first}/interpretation").status_code == 404
            assert post(second).status_code == 200
        finally:
            release.set()
        response = in_flight.result(timeout=5)
    assert response.status_code == 200
    assert post(first).json() == response.json()
    first_row, first_logs = saved_rows(database, first)
    second_row, second_logs = saved_rows(database, second)
    assert first_row.source == "ai" and [log.status for log in first_logs] == ["success"]
    assert first_logs[0].quota_scope == f"user:{user_id}"
    assert second_row.source == "database" and not second_logs


def test_abandoned_claim_recovers_to_fallback_without_replaying_attempt(client, database, monkeypatch):
    path, count = begin_reading(client)
    draw_and_reveal(client, path, count)
    reading_id = path.rsplit("/", 1)[-1]
    with Session(database) as session, session.begin():
        row = session.get(Reading, reading_id)
        row.status = "INTERPRETING"
        row.updated_at = utc_now() - interpretations.CLAIM_MAX_AGE - timedelta(seconds=1)
        session.add(AIUsageLog(reading_id=reading_id, provider="openai", model="gpt-6.1-terra", status="started"))
    monkeypatch.setattr(readings, "get_provider", lambda _: pytest.fail("Abandoned claim must use fallback"))
    assert client.post(f"{path}/interpret").is_success
    row, logs = saved_rows(database, path)
    assert row.source == "database" and [log.status for log in logs] == ["started"]
