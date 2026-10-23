"""FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="CF Coach API",
        version="0.1.0",
        description="Personal Codeforces training dashboards built from the public Codeforces API.",
    )
    origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"]
        )
    app.include_router(router)
    return app


app = create_app()
