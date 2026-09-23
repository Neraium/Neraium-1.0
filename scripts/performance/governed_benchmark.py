"""Reproducible current-system benchmark; run with the repository virtualenv."""
from __future__ import annotations
import argparse, cProfile, fcntl, gzip, hashlib, json, math, os, pstats, resource, shutil, statistics, sys, time
import importlib.abc
import importlib.util
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
RAW = ROOT / 'docs/performance/2026-optimization/raw'
RUNTIME = Path('/tmp/neraium-performance-runtime')
os.environ['NERAIUM_RUNTIME_DIR'] = str(RUNTIME)
os.environ['NERAIUM_PROCESS_ROLE'] = 'all'

HOT_PATH_MODULES = {
    'app.services.behavioral_baseline',
    'app.services.data_quality',
    'app.services.historical_ingestion',
    'app.services.sii_runner',
}


class ReferenceLoader(importlib.abc.Loader):
    def __init__(self, source, filename):
        self.source = source
        self.filename = filename

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        exec(compile(self.source, self.filename, 'exec'), module.__dict__)


class ReferenceFinder(importlib.abc.MetaPathFinder):
    """Load only the four originally clean hot-path modules from the frozen commit."""
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in HOT_PATH_MODULES:
            return None
        relative = 'backend/' + fullname.replace('.', '/') + '.py'
        revision = (RAW / 'initial-commit.txt').read_text().strip()
        source = subprocess.check_output(['git', 'show', f'{revision}:{relative}'], cwd=ROOT)
        expected = json.loads((RAW / 'baseline-source-hashes.json').read_text())[relative]
        if hashlib.sha256(source).hexdigest() != expected:
            raise RuntimeError(f'Frozen commit does not reproduce baseline source: {relative}')
        filename = str(ROOT / relative)
        return importlib.util.spec_from_file_location(fullname, filename, loader=ReferenceLoader(source, filename))

class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 1, tzinfo=timezone.utc).astimezone(tz)


def rows_for(n, changed=False):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        load = 50 + 12 * math.sin(i / 37) + 3 * math.cos(i / 13)
        flow = 80 + load * 1.7 + math.sin(i / 11)
        pressure = 12 + flow * .08 + .1 * math.cos(i / 7)
        if changed and i >= n * .7:
            pressure += 8 + 3 * math.sin(i / 5)
        rows.append({'timestamp': (start + timedelta(minutes=i)).isoformat(), 'load_pct': f'{load:.8f}', 'flow_gpm': f'{flow:.8f}', 'pressure_psi': f'{pressure:.8f}'})
    return rows


def setup(n, kind):
    from app.services import upload_jobs, runtime_db, sii_runner
    from app.services.dataset_scope import set_current_dataset_scope, build_dataset_scope
    shutil.rmtree(RUNTIME, ignore_errors=True)
    RUNTIME.mkdir()
    runtime_db.configure_runtime_dir(RUNTIME)
    upload_jobs.configure_runtime_dir(RUNTIME)
    sii_runner.configure_runtime_dir(RUNTIME)
    set_current_dataset_scope(build_dataset_scope(user_id='performance'))
    runtime_db.init_runtime_db()
    rows = rows_for(n, kind in ('engine', 'incremental'))
    columns = list(rows[0]); numeric = columns[1:]
    profiles = [{'column': c, 'constant_or_stuck': False, 'missing_count': 0, 'non_numeric_count': 0} for c in numeric]
    if kind == 'ingestion':
        import csv
        source = RUNTIME / 'historian.csv'
        with source.open('w') as f:
            writer = csv.DictWriter(f, fieldnames=columns); writer.writeheader(); writer.writerows(rows)
        from app.services.historical_ingestion import build_historical_ingestion
        return lambda: build_historical_ingestion(source, dataset_id='performance', filename='historian.csv', max_analysis_rows=n)
    if kind == 'baseline':
        from app.services.behavioral_baseline import build_behavioral_baseline
        return lambda: build_behavioral_baseline(job_id='performance', filename='historian.csv', columns=columns, rows=rows, numeric_columns=numeric, timestamp_column='timestamp', row_count_total=n, numeric_profiles=profiles)
    if kind == 'governance':
        sys.path.insert(0, str(ROOT / 'tests'))
        from test_evidence_package_v1 import _comparison, _with_operating_context
        from app.services.evidence_package import build_evidence_package
        from app.services.evidence_package_fingerprint import build_fingerprint
        from app.services.operating_context import build_operating_context_inputs
        catalog = {'load_pct': {'canonical_role': 'process_demand', 'engineering_units': '%'}}
        def packages():
            context = build_operating_context_inputs(rows=rows, telemetry_signal_catalog=catalog, baseline_model={}, comparison_window={})
            cases = [_comparison(), _with_operating_context(_comparison())]
            insufficient = _comparison(); insufficient['baseline_analysis']['relationship_drift'][0]['persistence_score'] = None
            cases.append(insufficient)
            outputs = [build_evidence_package(case) for case in cases]
            return {'context_inputs': context, 'packages': outputs, 'fingerprints': [build_fingerprint(item).model_dump(mode='json') for item in outputs]}
        return packages
    from app.engine.sii_engine import evaluate_sii
    from app.engine.sii.behavioral_model_store import InMemoryBehavioralModelStore
    from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
    def evaluate(selected, store, run):
        return evaluate_sii(columns=columns, rows=selected, numeric_profiles=profiles, timestamp_column='timestamp', phase4_scope=AuthenticatedPhase4Scope(tenant_scope_id='perf', workspace_id='perf'), operating_mode=_mode() if kind == 'incremental' else None, sensor_health=_health() if kind == 'incremental' else None, data_quality={'readiness': 'ready', 'warnings': [], 'data_confidence': {'rating': 'high'}} if kind == 'incremental' else None, config={'numeric_columns': numeric, 'source_run_id': run, 'infrastructure_identity': {'organization_id': 'perf', 'facility_id': 'perf', 'system_id': 'perf'}, 'behavioral_model_store': store})
    if kind == 'incremental':
        sys.path.insert(0, str(ROOT / 'tests'))
        from test_sii_engine_phase_4 import _rows, _profiles, _mode, _health
        columns, rows = _rows()
        numeric = columns[1:]
        profiles = _profiles()
        store = InMemoryBehavioralModelStore()
        trained = evaluate(rows, store, 'baseline')
        assert trained['behavioral_model']['status'] == 'complete', trained['behavioral_model']
        # Fixed trained memory; each invocation is a new three-window sequence.
        import copy
        seed = copy.deepcopy(store._state)
        windows = []
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(3):
            _, window = _rows(violation=30.0 if i == 2 else 0.0)
            for j, row in enumerate(window):
                row['timestamp'] = (start + timedelta(minutes=240*(i+1)+j)).isoformat()
            windows.append(window)
        def run_windows():
            active = InMemoryBehavioralModelStore()
            active._state = copy.deepcopy(seed)
            return [evaluate(window, active, f'window-{i}') for i, window in enumerate(windows)]
        return run_windows
    return lambda: evaluate(rows, InMemoryBehavioralModelStore(), 'performance')


# Only observational runtime measurements are excluded. Dict/list ordering and all
# analytical numbers, evidence, provenance, timestamps and counters stay exact.
MEASUREMENTS = {'processing_time_seconds', 'runtime_seconds', 'total_runtime_seconds', 'step_timings'}
def governed(value):
    if isinstance(value, dict):
        return {k: governed(v) for k, v in value.items() if k not in MEASUREMENTS and k != 'performance'}
    if isinstance(value, (list, tuple)):
        return [governed(v) for v in value]
    return value


def json_default(item):
    if isinstance(item, datetime):
        return item.isoformat()
    raise TypeError(f'Unsupported output type: {type(item).__name__}')


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False, default=json_default).encode()


def capture_ingestion_artifacts(result, name):
    """Materialize artifact bytes whose digests were frozen before optimization."""
    with gzip.open(RAW / f'before-{name}-0.json.gz', 'rb') as f:
        frozen = json.load(f)[0]
    record = result[0]
    canonical = list(RUNTIME.glob(f"historical_ingestion/scopes/*/canonical/{record['dataset_identity']}.jsonl"))
    assert len(canonical) == 1
    manifest = {}
    for kind, source, expected, suffix in (
        ('source', RUNTIME / 'historian.csv', frozen['raw_source']['sha256'], 'csv'),
        ('canonical', canonical[0], frozen['canonical_dataset']['sha256'], 'jsonl'),
    ):
        with source.open('rb') as f:
            actual = hashlib.file_digest(f, 'sha256').hexdigest()
        assert actual == expected, (kind, expected, actual)
        target = RAW / f'golden-artifact-{name}-{kind}.{suffix}.gz'
        with source.open('rb') as src, gzip.open(target, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        manifest[kind] = {'file': target.name, 'sha256': actual, 'bytes': source.stat().st_size}
    (RAW / f'golden-artifact-{name}-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', required=True)
    parser.add_argument('--kind', choices=['ingestion', 'baseline', 'engine', 'incremental', 'governance'], required=True)
    parser.add_argument('--rows', type=int, default=10000)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--reference', action='store_true', help='Control run with frozen original hot-path modules')
    args = parser.parse_args()
    if args.reference:
        sys.meta_path.insert(0, ReferenceFinder())
    RAW.mkdir(parents=True, exist_ok=True)
    name = f'{args.kind}-{args.rows}'
    # Freeze wall-clock metadata only; telemetry timestamps remain real fixtures.
    from app.services import historical_ingestion, behavioral_baseline, behavioral_model_repository, sii_runner
    with patch.object(sii_runner, 'datetime', FixedDateTime), patch.object(historical_ingestion, 'datetime', FixedDateTime), patch.object(behavioral_baseline, 'datetime', FixedDateTime), patch.object(behavioral_model_repository, 'datetime', FixedDateTime):
        run = setup(args.rows, args.kind)
        run() # warm-up; reset runtime for measured samples below
        samples = []
        for i in range(args.repeats):
            run = setup(args.rows, args.kind)
            cpu = time.process_time(); wall = time.perf_counter()
            result = run()
            sample = {'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu, 'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
            payload = encode(governed(result))
            digest = hashlib.sha256(payload).hexdigest()
            sample['governed_sha256'] = digest
            samples.append(sample)
            path = RAW / f'{args.phase}-{name}-{i}.json.gz'
            with gzip.open(path, 'wb') as f: f.write(encode(result))
            golden = RAW / f'before-{name}-0.json.gz'
            if args.phase != 'before' or i:
                with gzip.open(golden, 'rb') as f: expected = encode(governed(json.load(f)))
                sample['golden_equal'] = expected == payload
            if args.phase == 'fresh' and args.kind == 'ingestion' and i == 0:
                capture_ingestion_artifacts(result, name)
            print(name, i, sample, flush=True)
        if args.profile:
            run = setup(args.rows, args.kind)
            profiler = cProfile.Profile(); profiler.runcall(run)
            profiler.dump_stats(str(RAW / f'{args.phase}-{name}.prof'))
            with (RAW / f'{args.phase}-{name}-profile.txt').open('w') as f:
                stats = pstats.Stats(profiler, stream=f).strip_dirs()
                stats.sort_stats('cumulative').print_stats(90)
                stats.sort_stats('tottime').print_stats(60)
            profile_text = RAW / f'{args.phase}-{name}-profile.txt'
            profile_text.write_text(profile_text.read_text().rstrip()+'\n')
        walls = [s['wall_seconds'] for s in samples]
        output = {'phase': args.phase, 'implementation': 'frozen-reference' if args.reference else 'working-tree', 'workload': name, 'rows': 720 if args.kind == 'incremental' else args.rows, 'samples': samples, 'wall_median': statistics.median(walls), 'wall_min': min(walls), 'wall_max': max(walls), 'cpu_median': statistics.median(s['cpu_seconds'] for s in samples), 'peak_rss_bytes': max(s['peak_rss_bytes'] for s in samples)}
        output['rows_per_second'] = output['rows'] / output['wall_median']
        (RAW / f'{args.phase}-{name}-benchmark.json').write_text(json.dumps(output, indent=2)+'\n')
        if any(s.get('golden_equal') is False for s in samples):
            raise SystemExit('Golden comparison failed; inspect retained outputs.')

if __name__ == '__main__':
    # The deterministic scratch path is owned by this driver; never share a run.
    with Path('/tmp/neraium-performance.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
