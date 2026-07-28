from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.connectors.models import ConnectorHealthStatus
from app.connectors.store import (
    ConnectorHealthStore,
    ConnectorStorePathError,
    InvalidConnectorTypeError,
)
from app.core.config import Settings
from app.main import create_app
from app.routers.connectors import validate_csv_upload_filename


def _status(connector_type: str = "csv") -> ConnectorHealthStatus:
    return ConnectorHealthStatus(
        connector_type=connector_type,
        display_name="Test connector",
        functional=True,
        connection_status="ready",
    )


def _client(runtime_dir: Path) -> TestClient:
    settings = Settings(
        app_env="development",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://localhost:5173"],
        runtime_dir=runtime_dir,
    )
    return TestClient(create_app(settings))


def test_connector_store_uses_only_fixed_paths_below_canonical_runtime_root(tmp_path: Path) -> None:
    runtime_root = tmp_path / "nested" / "runtime"
    store = ConnectorHealthStore(runtime_root)

    store.upsert(_status())

    expected_path = (runtime_root / "connectors" / "health.json").resolve()
    assert store.state_path == expected_path
    assert expected_path.is_file()
    assert json.loads(expected_path.read_text(encoding="utf-8"))["connectors"]["csv"]["connector_type"] == "csv"


@pytest.mark.parametrize(
    "connector_type",
    [
        "../secret",
        "nested/../../secret",
        "/etc/passwd",
        "C:/Windows/win.ini",
        r"..\secret",
        "%2e%2e%2fsecret",
        "nested/%2e%2e/%2e%2e/secret",
        "%252e%252e%252fsecret",
        "csv\x00../secret",
        "unknown",
    ],
)
def test_connector_store_rejects_non_allowlisted_connector_identifiers(
    tmp_path: Path,
    connector_type: str,
) -> None:
    store = ConnectorHealthStore(tmp_path / "runtime")

    with pytest.raises(InvalidConnectorTypeError, match="not supported"):
        store.upsert(_status(connector_type))

    assert not store.state_path.exists()


def test_connector_store_rejects_connector_directory_symlink_escape(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    outside = tmp_path / "outside"
    runtime_root.mkdir(exist_ok=True)
    outside.mkdir()
    try:
        (runtime_root / "connectors").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    with pytest.raises(ConnectorStorePathError, match="symbolic link"):
        ConnectorHealthStore(runtime_root)


def test_connector_store_rejects_health_file_symlink_escape(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    connector_root = runtime_root / "connectors"
    outside_file = tmp_path / "outside.json"
    connector_root.mkdir(parents=True)
    outside_file.write_text('{"secret": true}', encoding="utf-8")
    try:
        (connector_root / "health.json").symlink_to(outside_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")
    store = ConnectorHealthStore(runtime_root)

    with pytest.raises(ConnectorStorePathError, match="symbolic link"):
        store.read()
    with pytest.raises(ConnectorStorePathError, match="symbolic link"):
        store.upsert(_status())

    assert outside_file.read_text(encoding="utf-8") == '{"secret": true}'


def test_connector_store_rejects_directory_symlink_swap_after_initialization(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    outside = tmp_path / "outside"
    store = ConnectorHealthStore(runtime_root)
    connector_root = runtime_root / "connectors"
    outside.mkdir()
    connector_root.rmdir()
    try:
        connector_root.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment.")

    with pytest.raises(ConnectorStorePathError, match="approved root"):
        store.read()
    with pytest.raises(ConnectorStorePathError, match="approved root"):
        store.upsert(_status())

    assert not (outside / "health.json").exists()


@pytest.mark.parametrize(
    "filename",
    [
        "../telemetry.csv",
        "nested/../../telemetry.csv",
        "/tmp/telemetry.csv",
        "C:telemetry.csv",
        r"C:\Windows\telemetry.csv",
        r"..\telemetry.csv",
        "%2e%2e%2ftelemetry.csv",
        "nested/%2e%2e/%2e%2e/telemetry.csv",
        "%252e%252e%252ftelemetry.csv",
        "telemetry\x00.csv",
    ],
)
def test_csv_filename_identifier_rejects_traversal_forms(filename: str) -> None:
    with pytest.raises(HTTPException) as error:
        validate_csv_upload_filename(filename)

    assert error.value.status_code == 400


@pytest.mark.parametrize(
    "connector_type",
    [
        "../csv",
        "nested/../../csv",
        "/etc/passwd",
        r"..\csv",
        "%2e%2e%2fcsv",
        "unknown",
    ],
)
def test_connector_request_rejects_invalid_connector_names(
    tmp_path: Path,
    connector_type: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    client = _client(runtime_root)

    response = client.post(
        "/api/connectors/test",
        json={"connector_type": connector_type, "config": {}},
    )

    assert response.status_code == 422
    assert not (runtime_root / "connectors" / "health.json").exists()
