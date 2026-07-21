from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from app.core.path_safety import (
    StoragePathError,
    resolve_existing_storage_path,
    resolve_storage_path,
    safe_upload_suffix,
    storage_key_for_server_path,
)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        " ",
        ".",
        "../secret.csv",
        "nested/../../secret.csv",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "C:\\Windows\\win.ini",
        "..\\secret.csv",
        "%2e%2e%2fsecret.csv",
        "nested/%2e%2e/%2e%2e/secret.csv",
        "%252e%252e%252fsecret.csv",
        "bad%zz.csv",
        "bad\x00.csv",
    ],
)
def test_storage_path_rejects_traversal_absolute_encoded_and_malformed_values(tmp_path: Path, value: str | None) -> None:
    with pytest.raises(StoragePathError):
        resolve_storage_path(tmp_path, value)


def test_storage_path_accepts_valid_nested_path(tmp_path: Path) -> None:
    nested = tmp_path / "valid" / "nested"
    nested.mkdir(parents=True)
    expected = nested / "telemetry.csv"
    expected.write_text("timestamp,value\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")

    assert resolve_existing_storage_path(tmp_path, "valid/nested/telemetry.csv") == expected.resolve()


def test_storage_key_for_server_path_prevents_filename_collisions(tmp_path: Path) -> None:
    with NamedTemporaryFile(delete=False, dir=tmp_path, prefix="job-a-", suffix=safe_upload_suffix("../upload.csv")) as first:
        first_path = Path(first.name)
    with NamedTemporaryFile(delete=False, dir=tmp_path, prefix="job-b-", suffix=safe_upload_suffix("../upload.csv")) as second:
        second_path = Path(second.name)

    first_key = storage_key_for_server_path(tmp_path, first_path)
    second_key = storage_key_for_server_path(tmp_path, second_path)

    assert first_key != second_key
    assert first_key.endswith(".csv")
    assert second_key.endswith(".csv")
    assert "/" not in first_key
    assert "/" not in second_key


def test_storage_path_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    root = tmp_path / "root"
    outside.mkdir()
    root.mkdir()
    (outside / "secret.csv").write_text("secret", encoding="utf-8")
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported in this environment")

    with pytest.raises(StoragePathError):
        resolve_existing_storage_path(root, "link/secret.csv")
