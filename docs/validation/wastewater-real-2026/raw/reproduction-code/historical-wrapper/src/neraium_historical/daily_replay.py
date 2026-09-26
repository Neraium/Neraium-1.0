"""Chronological engine handoff and provenance-bound checkpoints; no detector logic."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
from pathlib import Path

from .engine_adapter import EngineContractError, validate_result
from .quality_source import file_hash
from .report import _atomic_write, write_json
from .timeparse import parse_source_timestamp

DAY = timedelta(days=1)
STATE_PROTOCOL = 'engine-owned-chronological-daily-v2'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_checkpoint(value, path):
    """Compact durable JSON; hashes and decoded evidence are format-independent."""
    return _atomic_write(Path(path), json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n')


def input_hash(source, units, rows):
    return digest({'columns': source.columns, 'units': units, 'rows': rows})


def engine_state(result, channel="relationship_persistence_state"):
    graph = result.get('relationship_graph')
    if not isinstance(graph, dict) or not isinstance(graph.get(channel), dict):
        raise EngineContractError(f'Missing engine-owned {channel}')
    return graph[channel]


def reporting_result(result):
    projected = {k: result[k] for k in ('status', 'analysis_result', 'supplied_reference',
        'processing_trace', 'uncertainty', 'engine', 'compatibility', 'relationship_graph') if k in result}
    projected['compatibility'] = {'relationship_model': {'top_relationship_changes':
        result.get('compatibility', {}).get('relationship_model', {}).get('top_relationship_changes', [])}}
    return projected


class DailyReplay:
    """Each engine window is evaluated once, after every preceding daily attempt.

    State is an opaque engine value. Hashes bind its handoff to the complete
    checkpoint history and source policy, without inspecting its observations.
    """
    def __init__(self, source, engine, config, ref_start, ref_end, end, output, prior=None):
        config.validate(source.numeric_columns)
        if ref_end <= ref_start or end <= ref_end or (end-ref_end) % DAY:
            raise ValueError('Replay requires positive reference and complete daily time steps')
        self.total = (end-ref_end)//DAY
        if self.total > 1000:
            raise ValueError('Replay exceeds 1000 evaluations')
        self.source, self.engine, self.config = source, engine, config
        self.ref_end, self.output = ref_end, Path(output)
        self.reference, self.reference_provenance = source.window(ref_start, ref_end)
        if len(self.reference) > config.reference_rows:
            raise ValueError('Reference exceeds selected policy row cap')
        self.reference_hash = input_hash(source, config.signal_units, self.reference)
        self.policy = {'state_protocol': STATE_PROTOCOL, 'source_sha256': source.sha256,
            'engine': engine.provenance, 'config': asdict(config),
            'columns': source.columns, 'timestamp_column': source.timestamp_column,
            'numeric_profiles': source.numeric_profiles,
            'reference_start': ref_start.isoformat(), 'reference_end_exclusive': ref_end.isoformat(),
            'end_exclusive': end.isoformat(), 'step_seconds': 86400, 'view_rule': source.audit['rule'],
            'wrapper_code_sha256': {p.name: file_hash(p) for p in sorted(Path(__file__).parent.glob('*.py'))}}
        identity = {k: v for k, v in self.policy.items() if k != 'wrapper_code_sha256'}
        self.policy_hash = digest(identity)
        self.paths = {}
        directories = [Path(prior), self.output] if prior is not None and Path(prior) != self.output else [self.output]
        for directory in directories:
            manifest = directory/'manifest.json'
            files = sorted(directory.glob('[0-9][0-9][0-9].json'))
            if manifest.exists():
                previous = json.loads(manifest.read_text())
                if {k: v for k, v in previous.items() if k != 'wrapper_code_sha256'} != identity:
                    raise ValueError('Checkpoint provenance/policy mismatch; use a new checkpoint directory')
            elif files:
                raise ValueError('Checkpoint manifest missing; use a new checkpoint directory')
            for path in files:
                index = int(path.stem)
                if index >= self.total:
                    raise ValueError('Checkpoint window outside source-time policy')
                if index in self.paths and json.loads(self.paths[index].read_text()) != json.loads(path.read_text()):
                    raise ValueError('Conflicting duplicate-window checkpoints')
                self.paths[index] = path
        if self.paths and sorted(self.paths) != list(range(max(self.paths)+1)):
            raise ValueError('Checkpoint history is not a contiguous chronological prefix')
        self.output.mkdir(parents=True, exist_ok=True)
        manifest = self.output/'manifest.json'
        if not manifest.exists():
            write_json(self.policy, manifest)
        elif json.loads(manifest.read_text()) != self.policy:
            write_json(self.policy, self.output/('resume-' + digest(self.policy)[:12] + '.json'))
        self.records, self.reused, self.executed = {}, set(), set()
        self.state, self.recurrence_state, self.previous_hash = None, None, None

    def get(self, index):
        if type(index) is not int or not 0 <= index < self.total:
            raise ValueError('Window outside source-time policy')
        # Older requests are cache reads only, never backward engine calls.
        for current in range(len(self.records), index+1):
            self._next(current)
        return self.records[index][1]

    def _next(self, index):
        start = self.ref_end + index*DAY
        stop = start + DAY
        attempt = {'index': index, 'boundary_start': start.isoformat(),
            'boundary_end_exclusive': stop.isoformat(), 'status': 'failed', 'engine_called': False}
        link = {'state_protocol': STATE_PROTOCOL, 'policy_sha256': self.policy_hash,
            'previous_checkpoint_sha256': self.previous_hash, 'incoming_state_sha256': digest(self.state),
            'incoming_recurrence_state_sha256': digest(self.recurrence_state),
            'incoming_states_sha256': digest([self.state, self.recurrence_state])}
        existing = self.paths.get(index)
        if existing is not None:
            saved = json.loads(existing.read_text())
            checksum = saved.get('checkpoint_sha256')
            if checksum != digest({k: v for k, v in saved.items() if k != 'checkpoint_sha256'}):
                raise ValueError('Checkpoint integrity mismatch')
            if any(saved.get('handoff', {}).get(k) != v for k, v in link.items()):
                raise ValueError('Checkpoint chronological state handoff mismatch')
            a, result = saved['attempt'], saved['result']
            if any(a.get(k) != attempt[k] for k in ('index', 'boundary_start', 'boundary_end_exclusive')):
                raise ValueError('Checkpoint step mismatch')
            if a.get('input_provenance') is not None:
                comparison, provenance = self.source.window(start, stop)
                if provenance != a['input_provenance']:
                    raise ValueError('Checkpoint input provenance mismatch')
            if result is not None:
                comparison, provenance = self.source.window(start, stop)
                if a.get('input_provenance') != provenance:
                    raise ValueError('Checkpoint input provenance mismatch')
                self._validate(result, comparison)
            attempt = a
            outgoing = engine_state(result) if result is not None else self.state
            recurrence = engine_state(result, "relationship_recurrence_state") if result is not None else self.recurrence_state
            if saved['handoff'].get('outgoing_state_sha256') != digest(outgoing):
                raise ValueError('Checkpoint outgoing state mismatch')
            if (saved['handoff'].get('outgoing_recurrence_state_sha256') != digest(recurrence) or
                    saved['handoff'].get('outgoing_states_sha256') != digest([outgoing, recurrence])):
                raise ValueError('Checkpoint outgoing recurrence state mismatch')
            # Copy validated prior checkpoints so this output can resume independently.
            if existing != self.output/f'{index:03d}.json':
                write_checkpoint(saved, self.output/f'{index:03d}.json')
            self.reused.add(index)
        else:
            result = None
            try:
                comparison, provenance = self.source.window(start, stop)
                attempt['input_provenance'] = provenance
                if len(comparison) > self.config.comparison_rows:
                    raise ValueError('Comparison exceeds selected policy row cap')
                if parse_source_timestamp(self.reference[-1][self.source.timestamp_column]) >= parse_source_timestamp(comparison[0][self.source.timestamp_column]):
                    raise ValueError('Reference/comparison overlap')
                attempt['engine_called'] = True
                result = self.engine.evaluate(columns=self.source.columns, reference_rows=self.reference,
                    comparison_rows=comparison, numeric_profiles=self.source.numeric_profiles,
                    timestamp_column=self.source.timestamp_column, signal_units=self.config.signal_units,
                    relationship_persistence_state=deepcopy(self.state),
                    relationship_recurrence_state=deepcopy(self.recurrence_state))
                self._validate(result, comparison)
                trace = result['processing_trace']
                failed = trace.get('modules_failed') or result.get('status') in {'failed', 'error'} or result['analysis_result'].get('errors')
                limited = trace.get('modules_limited') or result.get('status') in {'limited', 'unavailable', 'insufficient_evidence'}
                attempt['status'] = 'failed' if failed else 'limited' if limited else 'completed'
            except Exception as exc:
                attempt['error'] = {'type': type(exc).__name__, 'message': str(exc)}
                result = None
            outgoing = engine_state(result) if result is not None else self.state
            recurrence = engine_state(result, "relationship_recurrence_state") if result is not None else self.recurrence_state
            saved = {'attempt': attempt, 'result': result,
                'handoff': {**link, 'outgoing_state_sha256': digest(outgoing),
                            'outgoing_recurrence_state_sha256': digest(recurrence),
                            'outgoing_states_sha256': digest([outgoing, recurrence])}}
            saved['checkpoint_sha256'] = digest(saved)
            write_checkpoint(saved, self.output/f'{index:03d}.json')
            self.executed.add(index)
        # Advance only after the entire response and handoff are durable.
        self.state = deepcopy(outgoing)
        self.recurrence_state = deepcopy(recurrence)
        self.previous_hash = saved['checkpoint_sha256']
        self.records[index] = (attempt, reporting_result(result) if result is not None else None)
        print(f'Step {index+1}/{self.total}: {"resumed " if existing else ""}{attempt["status"]}', flush=True)

    def _validate(self, result, comparison):
        validate_result(result)
        supplied = result['supplied_reference']
        if (supplied['reference']['input_hash'] != self.reference_hash or
                supplied['comparison']['input_hash'] != input_hash(self.source, self.config.signal_units, comparison)):
            raise ValueError('Checkpoint engine input hash mismatch')
        engine_state(result)
        engine_state(result, "relationship_recurrence_state")
