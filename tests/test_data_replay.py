from pathlib import Path

from app.routers.data import rebuild_upload_replay_from_source


def test_rebuild_upload_replay_from_source(tmp_path: Path) -> None:
    csv_path = tmp_path / "telemetry.csv"
    rows = "\n".join(
        f"2026-05-21T08:{minute:02d}:00Z,{72 + (minute % 5)},{48 + (minute % 7)}"
        for minute in range(60)
    )
    csv_path.write_text(f"timestamp,temperature,humidity\n{rows}\n", encoding="utf-8")

    payload = rebuild_upload_replay_from_source({
        "job_id": "job-123",
        "file_path": str(csv_path),
        "filename": "telemetry.csv",
    })

    assert payload is not None
    assert payload["job_id"] == "job-123"
    assert payload["frame_count"] > 0
    assert payload["timeline"]
    assert payload["message"] == "Replay reconstructed from the retained source CSV."
