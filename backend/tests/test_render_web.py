import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.render_web import create_render_app


def test_render_serves_api_assets_and_spa_routes():
    with TemporaryDirectory() as directory:
        dist = Path(directory)
        (dist / "index.html").write_text("<!doctype html><title>Tarot</title>", encoding="utf-8")
        (dist / "assets").mkdir()
        (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
        (dist / "assets" / "card.webp").write_bytes(b"RIFFfakeWEBP")
        with patch.dict(os.environ, {"FRONTEND_ORIGINS": "https://tarot.example", "SECRET_KEY": "a" * 40}):
            get_settings.cache_clear()
            try:
                with TestClient(create_render_app(dist), base_url="https://tarot.example") as client:
                    assert client.get("/").status_code == 200
                    assert client.get("/result/example").text == client.get("/").text
                    assert client.get("/assets/app.js").text == "console.log('ok')"
                    assert client.get("/assets/card.webp").headers["content-type"] == "image/webp"
                    assert client.get("/api/health").json() == {"status": "ok"}
                    assert client.get("/api/no-such-route").status_code == 404
                    assert client.get("/assets/missing.js").status_code == 404
                    assert client.get("/", headers={"Host": "untrusted.example"}).status_code == 400
            finally:
                get_settings.cache_clear()


def test_render_ingress_uses_edge_appended_ip_for_rate_limits():
    from app.render_web import RenderIngress

    captured = {}

    async def probe(scope, receive, send):
        captured.update(scope)

    scope = {
        "type": "http", "scheme": "http", "client": ("10.0.0.1", 1234),
        "headers": [(b"x-forwarded-for", b"203.0.113.10, 198.51.100.20")],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        pass

    import asyncio
    asyncio.run(RenderIngress(probe)(scope, receive, send))
    assert captured["scheme"] == "https"
    assert captured["client"] == ("198.51.100.20", 1234)
