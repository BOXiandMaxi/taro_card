from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.analytics import router as analytics_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.readings import history_router, router as readings_router
from app.api.routes.reference import router as reference_router
from app.core.config import get_settings
from app.services.analytics import PageViewLimit


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Tarot Reading", version="0.1.0")
    app.state.page_view_limit = PageViewLimit()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "X-CSRF-Token"],
        expose_headers=["Retry-After"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(reference_router, prefix="/api")
    app.include_router(readings_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(analytics_router, prefix="/api")
    return app


app = create_app()
