from __future__ import annotations

import hashlib
import importlib
import inspect
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


AUTHORITATIVE_ENGINE_COMMIT = '86b5579069486c66376efc8f2bd0d35025a11f9f'


class EngineContractError(RuntimeError):
    """The installed authority did not return the supplied-reference contract."""


def _git(path: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(['git', '-C', str(path), *args], stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


@dataclass(frozen=True)
class EngineAdapter:
    evaluate: Callable[..., dict[str, Any]]
    engine_path: str
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, engine_path: str | None = None) -> 'EngineAdapter':
        requested = engine_path or os.environ.get('NERAIUM_ENGINE_PATH')
        backend = None
        if requested:
            backend = Path(requested).expanduser().resolve()
            if (backend / 'backend').is_dir():
                backend /= 'backend'
            expected = backend / 'app/engine/sii_engine.py'
            if not expected.is_file():
                raise ValueError(f'Neraium evaluate_sii source not found: {expected}')
            cached = sys.modules.get('app.engine.sii_engine')
            if cached is not None and Path(cached.__file__).resolve() != expected:
                raise EngineContractError('A different Neraium engine is already imported; start a fresh process')
            sys.path.insert(0, str(backend))
        try:
            module = importlib.import_module('app.engine.sii_engine')
        except ImportError as exc:
            raise RuntimeError(f'Cannot import Neraium-1.0 ({exc}). Set --engine-path and install its locked dependencies.') from exc
        source = Path(module.__file__).resolve()
        if backend is not None and source != backend / 'app/engine/sii_engine.py':
            raise EngineContractError(f'Imported engine {source} does not match requested checkout')
        evaluate = getattr(module, 'evaluate_sii', None)
        if not callable(evaluate):
            raise EngineContractError('Neraium-1.0 evaluate_sii is unavailable')
        if 'relationship_persistence_state' not in inspect.signature(evaluate).parameters:
            raise EngineContractError('Neraium-1.0 lacks cross-window relationship persistence; use commit '
                                      '2a25a3312bcd01d67550bb259c0fe3605076696c or a compatible successor')
        if 'relationship_recurrence_state' not in inspect.signature(evaluate).parameters:
            raise EngineContractError('Neraium-1.0 lacks independent relationship recurrence; use commit '
                                      + AUTHORITATIVE_ENGINE_COMMIT)
        root = source.parents[3]
        dirty = _git(root, 'status', '--porcelain', '--untracked-files=normal')
        provenance = {'module': 'app.engine.sii_engine', 'callable': 'evaluate_sii',
                      'source_file': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                      'commit': _git(root, 'rev-parse', 'HEAD'),
                      'dirty': None if dirty is None else bool(dirty)}
        return cls(evaluate, str(source.parents[2]), provenance)

    def evaluate_pair(self, *, columns, reference_rows, comparison_rows, numeric_profiles,
                      timestamp_column, signal_units,
                      relationship_persistence_state: dict[str, Any] | None = None,
                      relationship_recurrence_state: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.evaluate(columns=columns, reference_rows=reference_rows,
                               comparison_rows=comparison_rows, numeric_profiles=numeric_profiles,
                               timestamp_column=timestamp_column, signal_units=signal_units,
                               relationship_persistence_state=relationship_persistence_state,
                               relationship_recurrence_state=relationship_recurrence_state)
        validate_result(result)
        graph = result.get('relationship_graph', {})
        for channel in ('relationship_persistence_state', 'relationship_recurrence_state'):
            if not isinstance(graph, dict) or not isinstance(graph.get(channel), dict):
                raise EngineContractError(f'Missing engine-owned {channel}')
        return result


def validate_result(result: Any) -> None:
    if not isinstance(result, dict):
        raise EngineContractError('evaluate_sii must return an object')
    analysis = result.get('analysis_result')
    if not isinstance(analysis, dict) or not isinstance(analysis.get('insights'), list):
        raise EngineContractError('Missing governed analysis_result.insights')
    evidence = analysis.get('evidence_index')
    if not isinstance(evidence, dict):
        raise EngineContractError('Missing governed evidence_index')
    for insight in analysis['insights']:
        if not isinstance(insight, dict) or not isinstance(insight.get('evidence_refs', []), list):
            raise EngineContractError('Malformed governed insight')
        for ref in insight.get('evidence_refs', []):
            if not isinstance(ref, str) or not isinstance(evidence.get(ref), dict):
                raise EngineContractError(f'Unresolved governed evidence reference: {ref!r}')
    supplied = result.get('supplied_reference')
    if not isinstance(supplied, dict) or supplied.get('contract_version') not in {'supplied-reference-v1', 'supplied-reference-v1.1'}:
        raise EngineContractError('Missing or unsupported supplied-reference contract')
    for role in ('reference', 'comparison'):
        if not isinstance(supplied.get(role), dict) or not supplied[role].get('input_hash'):
            raise EngineContractError(f'Missing supplied-reference {role} provenance')
    if not isinstance(result.get('processing_trace'), dict) or not isinstance(result.get('engine'), dict):
        raise EngineContractError('Missing engine identity or processing trace')
