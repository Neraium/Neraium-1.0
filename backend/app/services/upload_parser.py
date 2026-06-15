from __future__ import annotations

import csv
import io
import json
from typing import Any


def json_payload_to_csv_text(payload: Any) -> str:
    if isinstance(payload, bytes):
        payload = json.loads(payload.decode("utf-8"))
    if isinstance(payload, str):
        payload = json.loads(payload)

    if isinstance(payload, dict) and isinstance(payload.get("readings"), list):
        grouped: dict[str, dict[str, Any]] = {}
        for reading in payload.get("readings", []):
            if not isinstance(reading, dict):
                continue
            ts = str(reading.get("timestamp") or payload.get("timestamp") or "")
            record = grouped.setdefault(ts, {"timestamp": ts})
            sensor_name = str(reading.get("sensor_name") or reading.get("sensor_id") or "value")
            record[sensor_name] = reading.get("value")
        rows = list(grouped.values())
    else:
        rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("data") or []
        if not rows:
            rows = [payload if isinstance(payload, dict) else {"value": payload}]

    columns = sorted({key for row in rows if isinstance(row, dict) for key in row.keys()})
    if not columns:
        columns = ["timestamp", "value"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        if isinstance(row, dict):
            writer.writerow([row.get(col, "") for col in columns])
        else:
            writer.writerow(["", row])
    return output.getvalue()
