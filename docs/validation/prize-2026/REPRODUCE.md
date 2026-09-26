# Reproduction

Use Neraium commit `97d267d317fcce4b4424cf2141e97e87680acfc0` with the validation
scripts supplied alongside this report. Keep the analytical source unchanged.
`raw/freeze.json` contains the source manifest and environment. The observed Python
version was 3.11.16; NumPy was 2.2.6. Direct and transitive installed versions are
in `raw/requirements-environment.txt`, including the immutable consequence package
URL from the existing backend requirements. An optional fresh environment can be
installed with `uv venv --python 3.11 .validation-venv` and
`uv pip install --python .validation-venv/bin/python -r docs/validation/prize-2026/raw/requirements-environment.txt`.
Do not replace repository dependencies with ad hoc alternatives.

Run from the repository root. These commands use a fresh output directory and
local temporary runtime storage. They make no Siemens or production API calls.
Allow tens of minutes or longer depending on available CPU and disk performance.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONHASHSEED=0
validation_python="$PWD/.venv/bin/python"
validation_dir="$(mktemp -d /tmp/neraium-prize-reproduction-XXXXXX)"
cp docs/validation/prize-2026/raw/freeze.json "$validation_dir/freeze.json"
cp -r docs/validation/prize-2026/raw/prior-evidence "$validation_dir/prior-evidence"
gzip -dc docs/validation/prize-2026/raw/battery/historical-input.csv.gz > "$validation_dir/historical.csv"

"$validation_python" scripts/validate_prize.py \
  --output "$validation_dir/battery" --freeze "$validation_dir/freeze.json" \
  --historical "$validation_dir/historical.csv"
"$validation_python" scripts/validate_prize_ingestion.py \
  "$validation_dir/ingestion" "$validation_dir/freeze.json"
"$validation_python" scripts/validate_prize_performance.py \
  "$validation_dir/performance" "$validation_dir/freeze.json"
"$validation_python" scripts/benchmark_historical_ingestion.py \
  --rows 100000 --signals 12 --analysis-rows 10000 --iterations 2 \
  > "$validation_dir/historical-ingestion.json"
"$validation_python" scripts/replay_prize_validation.py "$validation_dir"
"$validation_python" scripts/summarize_prize_validation.py "$validation_dir"
```

The commands above run sequentially; the recorded original workloads overlapped.
Timing values are expected to differ. Engine thresholds, graph decisions and source
hashes should remain reproducible under the recorded dependencies. The paired runner
refuses to overwrite its raw output. Keep every attempt in its own directory.

Run the exact focused regression selection without shell expansion ambiguity:

```bash
PYTHONPATH=backend "$validation_python" - <<'PY'
import json, subprocess, sys
files = json.load(open('docs/validation/prize-2026/raw/focused-test-files.json'))
raise SystemExit(subprocess.call([
    sys.executable, '-m', 'pytest', *files,
    '--junitxml=/tmp/neraium-prize-focused.xml',
]))
PY
```

The broader default command was `PYTHONPATH=backend .venv/bin/python -m pytest tests
--junitxml=docs/validation/prize-2026/raw/regression.xml`. That exploratory run was
interrupted after 427 completed tests; it must not be described as a full-suite pass.
The existing selection excludes `slow` and `integration` tests. No browser test
was run; if adding browser tests, first follow `cd frontend && npm run setup:codex`
as required by AGENTS.md.

`raw/run-commands.json` records original commands. Logs are retained as `.txt`
for repository portability. Full analytical records are gzip JSON Lines, not just
aggregate scores. Read them with Python `gzip.open(path, 'rt')`; each line has
`case_id`, `window`, `input`, `input_sha256`, and either `output` or `exception`.
Rejection cases and limited outputs must remain in the denominator.

The independent scorer corrects one runner-summary field lookup: the authoritative
recurrence field is `recurrence_evidence.supported`. The original convenience
`historical.json` recurrence lists must not be used. Complete raw outputs were
never modified. `raw/assessment.json` and the report use the corrected read-only
scorer, whose source is included.

Verify integrity using `SHA256SUMS` from the repository root:

```bash
sha256sum -c docs/validation/prize-2026/SHA256SUMS
```

Checksums verify the local artifact set; they are not independent certification.
The bundle contains saved Siemens aggregate evidence and an export sufficiency
assessment, not credentials or raw sandbox point values. Recreating that historical
API snapshot would require its separately controlled connector environment; no claim
of fresh Siemens connectivity is made by this run.

The default fresh JSON replay returns exit code 1 for the documented CHW key-order
discrepancy. Retain that result. To reproduce the separate diagnostic (without
changing its failed acceptance result):

```bash
"$validation_python" scripts/diagnose_prize_replay.py "$validation_dir"
"$validation_python" scripts/check_prize_row_order.py "$validation_dir"
```

The latter only reconstructs row dictionaries in declared source-column order. It
does not change input values or production code. A canonical JSON input hash does
not encode dictionary insertion order; this is precisely the limitation observed.
The generator/CSV reproduction and the raw JSON replay are distinct checks.
