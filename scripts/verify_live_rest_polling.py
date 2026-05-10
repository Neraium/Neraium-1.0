from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


LIVE_URL = "http://18.216.253.180:1880/telemetry/latest"
BACKEND_BASE = os.getenv("NERAIUM_VERIFY_BACKEND_BASE", "http://127.0.0.1:8010")
CONNECTION_ID = "node-red-cultivation-telemetry"


def fetch_json(url: str, method: str = "GET") -> dict:
    request = urllib.request.Request(url, method=method, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str) -> dict:
    request = urllib.request.Request(url, method="POST", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    try:
        first = fetch_json(LIVE_URL)
        time.sleep(5.5)
        second = fetch_json(LIVE_URL)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Live telemetry check failed: {exc}")
        return 1

    print("Live telemetry endpoint responded.")
    print(f"First tick: {first.get('tick')} at {first.get('timestamp')}")
    print(f"Second tick: {second.get('tick')} at {second.get('timestamp')}")

    if first.get("tick") == second.get("tick") and first.get("timestamp") == second.get("timestamp"):
        print("Telemetry did not advance between polls.")
        return 1

    try:
        poll = post_json(f"{BACKEND_BASE}/api/data-connections/{CONNECTION_ID}/poll-once")
        latest = fetch_json(f"{BACKEND_BASE}/api/data/latest-upload")
        facility = fetch_json(f"{BACKEND_BASE}/api/facility/systems")
        evidence = fetch_json(f"{BACKEND_BASE}/api/evidence/latest")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Backend verification failed: {exc}")
        return 1

    print(f"Poll status: {poll['connection']['status']}")
    print(f"Latest source: {latest.get('result_source')}")
    print(f"Facility intelligence source: {facility.get('intelligence', {}).get('source')}")
    print(f"Latest evidence source: {evidence.get('run', {}).get('source_name')}")

    if latest.get("result_source") != "rest_poll":
        print("Latest upload payload did not switch to rest_poll.")
        return 1
    if facility.get("intelligence", {}).get("source") != "rest_poll":
        print("Facility Command did not hydrate from the REST poll result.")
        return 1
    if not evidence.get("run"):
        print("Evidence Trail did not record a run.")
        return 1

    print("Live REST polling verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
