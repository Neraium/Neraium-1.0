#!/usr/bin/env python
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "telemetry_corruption"
OUTPUT_DIR = ROOT / "output" / "pilot-rehearsal"
TERMINAL_STATES = {"COMPLETE", "FAILED"}


@dataclass
class RehearsalConfig:
    base_url: str
    timeout_seconds: float
    poll_interval_seconds: float
    poll_timeout_seconds: float
    include_bad_fixtures: bool
    include_primary_smoke_upload: bool
    access_code: str | None
    api_token: str | None


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_config() -> RehearsalConfig:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    timeout_seconds = float(os.getenv("REHEARSAL_TIMEOUT_SECONDS", "20"))
    poll_interval_seconds = float(os.getenv("REHEARSAL_POLL_INTERVAL_SECONDS", "0.5"))
    poll_timeout_seconds = float(os.getenv("REHEARSAL_POLL_TIMEOUT_SECONDS", "60"))
    include_bad_fixtures = os.getenv("REHEARSAL_SKIP_BAD_FIXTURES", "0") != "1"
    include_primary_smoke_upload = os.getenv("REHEARSAL_SKIP_PRIMARY_UPLOAD", "0") != "1"
    return RehearsalConfig(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        poll_timeout_seconds=poll_timeout_seconds,
        include_bad_fixtures=include_bad_fixtures,
        include_primary_smoke_upload=include_primary_smoke_upload,
        access_code=os.getenv("NERAIUM_ACCESS_CODE"),
        api_token=os.getenv("NERAIUM_API_TOKEN"),
    )


def build_headers(config: RehearsalConfig, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if config.api_token:
        headers["Authorization"] = f"Bearer {config.api_token}"
    if config.access_code:
        headers["X-Neraium-Access-Code"] = config.access_code
    if extra:
        headers.update(extra)
    return headers


def fetch_json(config: RehearsalConfig, path: str, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    url = f"{config.base_url}{path}"
    req = request.Request(url=url, data=body, method=method, headers=build_headers(config, headers))
    try:
        with request.urlopen(req, timeout=config.timeout_seconds) as response:
            raw = response.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            return response.status, payload
    except error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw.decode("utf-8", errors="replace")}
        return exc.code, payload


def encode_multipart(field_name: str, filename: str, content_type: str, payload: bytes) -> tuple[bytes, str]:
    boundary = f"----NeraiumBoundary{uuid.uuid4().hex}"
    chunks = [
      f"--{boundary}\r\n".encode("utf-8"),
      f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("utf-8"),
      f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
      payload,
      b"\r\n",
      f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(chunks), boundary


def upload_csv_and_wait(config: RehearsalConfig, csv_name: str, csv_payload: bytes) -> dict[str, Any]:
    body, boundary = encode_multipart("file", csv_name, "text/csv", csv_payload)
    status, upload_payload = fetch_json(
      config,
      "/api/data/upload",
      method="POST",
      body=body,
      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if status not in (200, 202):
      return {"accepted": False, "status": status, "payload": upload_payload}

    status_url = upload_payload.get("status_url")
    if not status_url:
      return {"accepted": False, "status": status, "payload": upload_payload, "error": "missing_status_url"}

    deadline = time.time() + config.poll_timeout_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
      poll_status, poll_payload = fetch_json(config, status_url)
      last = {"status": poll_status, "payload": poll_payload}
      if poll_status == 200 and str(poll_payload.get("status", "")).upper() in TERMINAL_STATES:
        return {
          "accepted": True,
          "upload_status": status,
          "upload_payload": upload_payload,
          "terminal": poll_payload,
        }
      time.sleep(config.poll_interval_seconds)

    return {
      "accepted": True,
      "upload_status": status,
      "upload_payload": upload_payload,
      "terminal_timeout": True,
      "last_poll": last,
    }


def build_primary_smoke_csv() -> bytes:
    rows = [
      "timestamp,room,temperature,humidity,flow_rate,orp,ph",
      "2026-05-01T08:00:00Z,Pool Deck,81.2,54,118,690,7.35",
      "2026-05-01T08:05:00Z,Pool Deck,81.4,55,117,688,7.34",
      "2026-05-01T08:10:00Z,Pool Deck,81.6,55,116,687,7.33",
      "2026-05-01T08:15:00Z,Pool Deck,81.8,56,116,686,7.32",
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def run_rehearsal() -> int:
    config = parse_config()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()

    report: dict[str, Any] = {
      "started_at": started_at,
      "base_url": config.base_url,
      "checks": {},
      "uploads": {},
      "summary": {},
    }

    for path in ("/api/health", "/api/ready", "/api/data/latest-upload"):
      status, payload = fetch_json(config, path)
      report["checks"][path] = {"status": status, "payload": payload}

    if config.include_primary_smoke_upload:
      report["uploads"]["primary_smoke"] = upload_csv_and_wait(
        config,
        f"pilot-rehearsal-primary-{int(time.time())}.csv",
        build_primary_smoke_csv(),
      )

    if config.include_bad_fixtures:
      fixture_results: dict[str, Any] = {}
      for fixture in ("missing_timestamps.csv", "flatlined_signal.csv", "out_of_order.csv"):
        payload = (FIXTURE_DIR / fixture).read_bytes()
        fixture_results[fixture] = upload_csv_and_wait(config, fixture, payload)
      report["uploads"]["bad_telemetry_fixtures"] = fixture_results

    status, latest_upload_after = fetch_json(config, "/api/data/latest-upload")
    report["checks"]["/api/data/latest-upload (after)"] = {"status": status, "payload": latest_upload_after}

    readiness_pass = all(
      report["checks"].get(endpoint, {}).get("status") == 200
      for endpoint in ("/api/health", "/api/ready", "/api/data/latest-upload")
    )
    primary_terminal = str(report.get("uploads", {}).get("primary_smoke", {}).get("terminal", {}).get("status", "")).upper()
    primary_ok = primary_terminal in TERMINAL_STATES or not config.include_primary_smoke_upload
    report["summary"] = {
      "readiness_endpoints_ok": readiness_pass,
      "primary_upload_terminal_contract_ok": primary_ok,
      "completed_at": now_iso(),
    }

    output_name = f"pilot-rehearsal-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    output_path = OUTPUT_DIR / output_name
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Pilot rehearsal report written: {output_path}")

    if not readiness_pass or not primary_ok:
      print("Pilot rehearsal check FAILED.")
      return 1

    print("Pilot rehearsal check PASSED.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run_rehearsal())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
