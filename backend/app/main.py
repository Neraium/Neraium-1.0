from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.routers import app_info, data, facility, health


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Neraium API",
        version="0.1.0",
        description="Customer-facing API for the Neraium application.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(app_info.router, prefix="/api")
    app.include_router(facility.router, prefix="/api")
    app.include_router(data.router, prefix="/api")

    return app


app = create_app()


@app.get("/health")
def health_check_alias():
    return {"status": "ok", "service": "neraium-api"}
