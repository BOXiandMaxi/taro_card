"""Render entry point: one HTTPS origin for the SPA and the API."""

import ipaddress
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

# Render supplies the canonical HTTPS URL at runtime. An explicitly configured
# origin still takes precedence (for example, when using a custom domain).
if os.environ.get("RENDER") == "true" and not os.environ.get("FRONTEND_ORIGINS"):
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        os.environ["FRONTEND_ORIGINS"] = render_url

from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
mimetypes.add_type("image/webp", ".webp")


class SPAFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # Keep unknown API paths and missing assets as real 404 responses.
            requested_path = scope.get("path", "")
            if exc.status_code != 404 or requested_path == "/api" or requested_path.startswith("/api/") or "." in Path(path).name:
                raise
            return await super().get_response("index.html", scope)


class RenderIngress:
    """Use Render's TLS edge and the last, edge-appended client IP."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            # Render redirects public HTTP to HTTPS before forwarding to the app.
            scope["scheme"] = "https"
            for name, value in scope.get("headers", ()):
                if name.lower() == b"x-forwarded-for":
                    try:
                        # Render appends the visitor IP. Earlier values may be
                        # supplied by a caller and must not control rate limits.
                        host = str(ipaddress.ip_address(value.rsplit(b",", 1)[-1].strip().decode("ascii")))
                    except (UnicodeDecodeError, ValueError):
                        break
                    client = scope.get("client") or ("", 0)
                    scope["client"] = (host, client[1])
                    break
        await self.app(scope, receive, send)


def create_render_app(frontend_dist=FRONTEND_DIST):
    web = create_app()
    allowed_hosts = [urlsplit(origin).hostname for origin in get_settings().cors_origins]
    web.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    web.mount("/", SPAFiles(directory=str(frontend_dist), html=True, check_dir=False), name="frontend")
    return RenderIngress(web)


app = create_render_app()
