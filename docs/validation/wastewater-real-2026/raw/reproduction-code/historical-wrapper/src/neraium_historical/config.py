from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ReplayConfig:
    reference_rows: int
    comparison_rows: int
    step_rows: int
    signal_units: dict[str, str | None] = field(default_factory=dict)

    def validate(self, signal_names: list[str]) -> None:
        for name in ('reference_rows', 'comparison_rows', 'step_rows'):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f'{name} must be a positive integer')
        for name in ('reference_rows', 'comparison_rows'):
            if not 16 <= getattr(self, name) <= 12_000:
                raise ValueError(f'{name} must be between 16 and 12000')
        if self.step_rows > self.comparison_rows:
            raise ValueError('step_rows must not exceed comparison_rows (replay gaps are unsupported)')
        if not isinstance(self.signal_units, dict) or set(self.signal_units) != set(signal_names):
            raise ValueError('signal_units must explicitly declare exactly every numeric signal; use null for unknown units')
        if any(v is not None and (not isinstance(v, str) or not v.strip()) for v in self.signal_units.values()):
            raise ValueError('signal units must be nonblank strings or null; units are never inferred or converted')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate configuration key: {key}')
        result[key] = value
    return result


def load_config(path: str | Path) -> ReplayConfig:
    payload = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    allowed = {'reference_rows', 'comparison_rows', 'step_rows', 'signal_units'}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError('configuration must be an object containing only replay sizes and signal_units')
    if not {'reference_rows', 'comparison_rows', 'signal_units'} <= set(payload):
        raise ValueError('configuration requires reference_rows, comparison_rows and signal_units')
    config = ReplayConfig(payload['reference_rows'], payload['comparison_rows'],
                          payload.get('step_rows', payload['comparison_rows']), payload['signal_units'])
    config.validate(list(config.signal_units) if isinstance(config.signal_units, dict) else [])
    return config
