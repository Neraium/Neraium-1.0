from __future__ import annotations

import io
import time
import tracemalloc
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, UploadFile

from app.connectors.limits import (
    MAX_CONNECTOR_NORMALIZED_RECORDS,
    MAX_CONNECTOR_RESPONSE_BYTES,
    MAX_CONNECTOR_SOURCE_ROWS,
)
from app.connectors.rest_connector import RESTConnector
from app.routers import connectors as connectors_router


def _wide_rows(row_count: int, sensor_count: int) -> list[dict]:
    return [
        {
            "timestamp": f"2025-01-{1 + (index // 1440):02d}T{(index // 60) % 24:02d}:{index % 60:02d}:00+00:00",
            **{f"sensor_{sensor}": index + sensor / 10 for sensor in range(sensor_count)},
        }
        for index in range(row_count)
    ]


def test_rest_normalization_rejects_oversized_expansion_before_allocating_models() -> None:
    rows = _wide_rows(5_000, 10)
    connector = RESTConnector({"source_id": "benchmark", "system_id": "benchmark-system"})

    tracemalloc.start()
    started = time.perf_counter()
    with pytest.raises(ValueError, match="normalized readings"):
        connector.normalize(rows)
    elapsed_ms = (time.perf_counter() - started) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(rows) * 10 > MAX_CONNECTOR_NORMALIZED_RECORDS
    assert elapsed_ms < 250, f"oversized connector failure took {elapsed_ms:.1f} ms"
    assert peak_bytes < 2 * 1024 * 1024


def test_rest_connector_rejects_declared_oversized_response_before_json_decode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": str(MAX_CONNECTOR_RESPONSE_BYTES + 1)},
            content=b"{}",
            request=request,
        )

    connector = RESTConnector(
        {"endpoint": "https://telemetry.example.test/readings"},
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="response exceeds"):
        connector.fetch_historical()


def test_rest_connector_caps_source_row_count() -> None:
    connector = RESTConnector({})
    records = [{"timestamp": "2025-01-01T00:00:00Z", "sensor": 1}] * (MAX_CONNECTOR_SOURCE_ROWS + 1)

    with pytest.raises(ValueError, match="source rows"):
        connector._extract_records(records)


@pytest.mark.asyncio
async def test_csv_connector_upload_stops_reading_at_byte_limit(monkeypatch) -> None:
    monkeypatch.setattr(connectors_router, "MAX_CONNECTOR_RESPONSE_BYTES", 1024)
    upload = UploadFile(filename="telemetry.csv", file=io.BytesIO(b"x" * 1025))

    with pytest.raises(HTTPException) as exc_info:
        await connectors_router.upload_csv_connector(
            SimpleNamespace(),
            upload,
            source_id="source",
            system_id="system",
        )

    assert exc_info.value.status_code == 413
