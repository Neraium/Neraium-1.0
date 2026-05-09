import pytest

from app.services.sii_runner import STATE_PATH
from app.services.upload_jobs import JOB_DIR, UPLOAD_DIR, latest_upload_path


@pytest.fixture(autouse=True)
def clear_runtime_state():
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    if latest_upload_path().exists():
        latest_upload_path().unlink()
    for directory in (JOB_DIR, UPLOAD_DIR):
        if directory.exists():
            for path in directory.glob("*"):
                if path.is_file():
                    path.unlink()
    yield
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    if latest_upload_path().exists():
        latest_upload_path().unlink()
    for directory in (JOB_DIR, UPLOAD_DIR):
        if directory.exists():
            for path in directory.glob("*"):
                if path.is_file():
                    path.unlink()
