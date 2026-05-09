import pytest

from app.services.sii_runner import STATE_PATH


@pytest.fixture(autouse=True)
def clear_latest_sii_state():
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    yield
    if STATE_PATH.exists():
        STATE_PATH.unlink()
