# Synthetic blind PoV dry run — NON-HENDERSON

These files contain **no Henderson data or facts**. They demonstrate the existing
`historical-pov.v1` adapter and `relationship-qualification.v2` transport/state
contract. They do not demonstrate Henderson detection performance or establish
independence for real telemetry.

* `telemetry-example.csv`: 112 deterministic synthetic records, with only
  `timestamp,s01,s02`. Values are two bounded pseudorandom draws per record
  (`random.Random(271828)`, rounded to six decimal places). Timestamps start at
  an arbitrary synthetic origin, 2000-01-01 UTC, one minute apart.
* `acquisition-example.json`: explicit **hypothetical** acquisition declarations.
  Independent draws are an assumed fixture model, not inferred from cadence or
  certified by a pseudorandom generator. Never copy these declarations as facts
  about a real export.

The predeclared plan uses the first 16 records as two eight-record reference
epochs and the remaining records as six consecutive 16-record comparisons.
T is a hypothetical 420 seconds. No event was used to select any boundary;
there are no truth labels, event times, outcomes or failure types. The required
`plan.event_independent: true` is a policy declaration, not hidden event metadata.

## Run locally

From the repository root, using the repository environment:

```bash
PYTHONPATH=backend .venv/bin/python - <<'PY'
import json
from pathlib import Path
from app.services.historical_pov import prepare_historical_pov, run_historical_pov

root = Path("examples/henderson-pov")
prepared = prepare_historical_pov(
    csv_bytes=(root / "telemetry-example.csv").read_bytes(),
    metadata=json.loads((root / "acquisition-example.json").read_text()),
)
result = run_historical_pov(prepared)
# Serialize a detached result/checkpoint snapshot; this example writes no files.
frozen_result = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
print(json.dumps({
    "slots": len(result["slots"]),
    "completed_slots": result["checkpoint"]["completed_slots"],
    "not_quantifiable": result["not_quantifiable"],
    "qualification_statuses": [s["assessments"][0]["qualification_status"] for s in result["slots"]],
    "qualified_support": [s["assessments"][0]["qualified_persistence_supported"] for s in result["slots"]],
}, indent=2))
PY
```

Expected: six chronological slots, a checkpoint through slot six,
`not_quantifiable: true`, and no qualified persistence. The small reference
cannot resolve the bounded relationship evidence. This is an expected abstention,
not a negative fault verdict. The returned profile, source bytes (as UTF-8 text),
source hash, record mappings and checkpoint digest preserve the frozen inputs
and state. A serialized snapshot is not an authenticated or write-once archive;
the caller must retain it without alteration before unblinding.

Optional continuation uses `run_historical_pov(prepared, stop_after_slots=1)` and
then `run_historical_pov(prepared, checkpoint=first_result["checkpoint"])`.
Both calls must use the same frozen prepared bundle. Real handoff requirements
are in [the Henderson data request](../../docs/henderson_pov_data_request.md);
the full schema is in [the adapter documentation](../../docs/historical_pov_adapter.md).

## Targeted verification

```bash
.venv/bin/python -m pytest tests/test_henderson_pov_example.py -q
```

This reads only the synthetic package and runs the local paired engine. It does
not call upload APIs, deploy anything or use cloud services.
