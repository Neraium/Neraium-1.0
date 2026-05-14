import os

import uvicorn


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BACKEND_HOST", "127.0.0.1")
os.environ.setdefault("BACKEND_PORT", "8010")
os.environ.setdefault("NERAIUM_PROCESS_ROLE", "monolith")
os.environ.setdefault("NERAIUM_START_BACKGROUND_WORKERS", "true")
os.environ.setdefault("NERAIUM_START_DATA_POLLER", "true")
os.environ.setdefault("NERAIUM_RUNTIME_DIR", "./runtime")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ["BACKEND_HOST"],
        port=int(os.environ["BACKEND_PORT"]),
        reload=True,
    )
