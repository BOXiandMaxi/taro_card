import unittest
import os
from unittest.mock import patch


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fastapi.testclient import TestClient
            from app.main import create_app
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"Backend dependencies unavailable: {exc}") from exc
        cls.client_type = TestClient
        cls.create_app = staticmethod(create_app)

    def test_health_without_database(self):
        with patch("app.database.session.get_engine", side_effect=AssertionError("Health must not access DB")):
            with self.client_type(self.create_app()) as client:
                response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("application/json", response.headers["content-type"])

    def test_openapi_health_contract(self):
        with self.client_type(self.create_app()) as client:
            schema = client.get("/openapi.json").json()
        self.assertIn("/api/health", schema["paths"])
        self.assertIn("200", schema["paths"]["/api/health"]["get"]["responses"])

    def test_cors(self):
        from app.core.config import get_settings

        with self.client_type(self.create_app()) as client:
            for origin, expected in ((get_settings().cors_origins[0], 200), ("https://untrusted.invalid", 400)):
                response = client.options("/api/health", headers={
                    "Origin": origin, "Access-Control-Request-Method": "GET",
                })
                self.assertEqual(response.status_code, expected)
                if expected == 200:
                    self.assertEqual(response.headers["access-control-allow-origin"], origin)
                    self.assertEqual(response.headers["access-control-allow-credentials"], "true")


class ConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from app.core.config import Settings
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"Backend dependencies unavailable: {exc}") from exc
        cls.settings_type = Settings

    def test_reject_unsupported_database(self):
        with self.assertRaises(ValueError):
            self.settings_type(_env_file=None, database_url="sqlite://")

    def test_explicit_origins(self):
        settings = self.settings_type(
            _env_file=None, frontend_origins="http://localhost:5173, https://tarot.example",
            secret_key="a" * 40,
        )
        self.assertEqual(settings.cors_origins, ["http://localhost:5173", "https://tarot.example"])
        for origin in ("*", "https://*.example", "https://example/path", "https://user:pass@example", ""):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                self.settings_type(_env_file=None, frontend_origins=origin)

    def test_production_requires_private_secret(self):
        for secret in ("", "replace-with-a-long-random-secret"):
            with self.subTest(secret=bool(secret)), self.assertRaises(ValueError):
                self.settings_type(_env_file=None, frontend_origins="https://tarot.example", secret_key=secret)

    def test_default_origins_cover_local_frontend_addresses(self):
        with patch.dict(os.environ, {}, clear=True):
            origins = self.settings_type(_env_file=None).cors_origins
        self.assertIn("http://localhost:5173", origins)
        self.assertIn("http://127.0.0.1:5173", origins)
