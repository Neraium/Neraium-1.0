from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("NERAIUM_RUNTIME_DIR", str(ROOT / ".playwright-runtime"))
os.environ.setdefault("NERAIUM_START_BACKGROUND_WORKERS", "1")
os.environ.setdefault("NERAIUM_START_DATA_POLLER", "0")
os.environ.setdefault("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "e2e-admin@neraium.test")
os.environ.setdefault("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "e2e-password-123")
os.environ.setdefault("NERAIUM_BOOTSTRAP_ADMIN_NAME", "E2E Administrator")
frontend_port = int(os.getenv("PLAYWRIGHT_FRONTEND_PORT", "3012"))
os.environ.setdefault(
    "CORS_ORIGINS",
    f"http://127.0.0.1:{frontend_port},http://localhost:{frontend_port}",
)

runtime_dir = Path(os.environ["NERAIUM_RUNTIME_DIR"])
runtime_dir.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(runtime_dir / "e2e-telemetry.sqlite") as connection:
    connection.execute("DROP TABLE IF EXISTS telemetry")
    connection.execute("CREATE TABLE telemetry (timestamp TEXT, sensor_id TEXT, value REAL, unit TEXT)")
    connection.executemany(
        "INSERT INTO telemetry VALUES (?, ?, ?, ?)",
        [
            ("2026-01-01T00:00:00Z", "supply_temp", 42.5, "f"),
            ("2026-01-01T00:05:00Z", "supply_temp", 42.7, "f"),
        ],
    )

import uvicorn

uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.getenv("PLAYWRIGHT_BACKEND_PORT", "8012")))
