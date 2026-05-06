from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import app_info, facility, health


def create_app() -> FastAPI:
    app = FastAPI(
        title="Neraium API",
        version="0.1.0",
        description="Customer-facing API for the Neraium application.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3010",
            "http://127.0.0.1:3010",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(app_info.router, prefix="/api")
    app.include_router(facility.router, prefix="/api")

    return app


app = create_app()
