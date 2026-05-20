from pathlib import Path
import time

from fastapi.testclient import TestClient

from app.main import create_app


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "telemetry_corruption"


def wait_for_terminal_upload_status(client: TestClient, status_url: str, timeout_seconds: float = 5.0) -> dict:
  deadline = time.time() + timeout_seconds
  last_payload = None
  while time.time() < deadline:
    response = client.get(status_url)
    assert response.status_code == 200
    last_payload = response.json()
    if last_payload["status"] in {"COMPLETE", "FAILED"}:
      return last_payload
    time.sleep(0.05)
  raise AssertionError(f"Upload did not reach terminal status. Last payload: {last_payload}")


def post_fixture_csv(client: TestClient, fixture_name: str):
  fixture_path = FIXTURE_DIR / fixture_name
  content = fixture_path.read_text(encoding="utf-8")
  return client.post(
    "/api/data/upload",
    files={"file": (fixture_name, content, "text/csv")},
  )


def test_missing_timestamps_fixture_returns_graceful_terminal_state() -> None:
  client = TestClient(create_app())
  response = post_fixture_csv(client, "missing_timestamps.csv")
  assert response.status_code == 202
  terminal = wait_for_terminal_upload_status(client, response.json()["status_url"])
  assert terminal["status"] in {"COMPLETE", "FAILED"}
  assert terminal.get("message")


def test_flatlined_signal_fixture_returns_graceful_terminal_state() -> None:
  client = TestClient(create_app())
  response = post_fixture_csv(client, "flatlined_signal.csv")
  assert response.status_code == 202
  terminal = wait_for_terminal_upload_status(client, response.json()["status_url"])
  assert terminal["status"] in {"COMPLETE", "FAILED"}
  assert terminal.get("message")


def test_out_of_order_fixture_returns_graceful_terminal_state() -> None:
  client = TestClient(create_app())
  response = post_fixture_csv(client, "out_of_order.csv")
  assert response.status_code == 202
  terminal = wait_for_terminal_upload_status(client, response.json()["status_url"])
  assert terminal["status"] in {"COMPLETE", "FAILED"}
  assert terminal.get("message")
