"""
Shared test fixtures and configuration.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.main import create_app
from app.core.config import Settings


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        app_env="testing",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://127.0.0.1:3010"],
        cors_origin_regex="^http://",
        start_background_workers=False,
        start_data_connection_poller=False,
    )


@pytest.fixture
def app(settings):
    """Create test app."""
    return create_app(settings)


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)
