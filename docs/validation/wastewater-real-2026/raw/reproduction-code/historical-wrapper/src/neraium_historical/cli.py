from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .config import load_config
from .csv_loader import load_csv
from .engine_adapter import EngineAdapter
from .findings import consolidate
from .replay import replay
from .report import build_payload, write_html, write_json


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog='neraium-historical')
    sub = root.add_subparsers(dest='command', required=True)
    analyze = sub.add_parser('analyze', help='Replay a historical CSV through Neraium-1.0')
    analyze.add_argument('csv')
    analyze.add_argument('--config', required=True, help='JSON replay configuration')
    analyze.add_argument('--timestamp', default=None)
    analyze.add_argument('--engine-path', default=None, help='Neraium-1.0 repository or backend path')
    analyze.add_argument('--output-dir', default='output')
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        output = Path(args.output_dir)
        names = ('historical-analysis.json', 'historical-analysis.html')
        # Refuse accidental overwrite and stale-success ambiguity on failed reruns.
        if any((output / name).exists() for name in names):
            raise ValueError('output reports already exist; choose a fresh --output-dir')
        output.mkdir(parents=True, exist_ok=True)
        config = load_config(args.config)
        dataset = load_csv(args.csv, timestamp_column=args.timestamp)
        engine = EngineAdapter.load(args.engine_path)
        evaluations = replay(dataset, config, engine)
        payload = build_payload(dataset=dataset, config=config, evaluations=evaluations,
                                episodes=consolidate(evaluations), engine_path=engine.engine_path,
                                engine_provenance=engine.provenance)
        # Serialize both in a staging directory before publishing either report.
        import tempfile
        with tempfile.TemporaryDirectory(dir=output) as staging:
            json_path = write_json(payload, Path(staging) / names[0])
            html_path = write_html(payload, Path(staging) / names[1])
            json_path.replace(output / names[0])
            try:
                html_path.replace(output / names[1])
            except OSError:
                (output / names[0]).unlink()
                raise
        print(f'JSON report: {output / names[0]}')
        print(f'HTML report: {output / names[1]}')
        print(f'Evaluations: {len(evaluations)}; finding episodes: {payload["summary"]["finding_episode_count"]}')
        print(f'Run status: {payload["run_status"]}')
        return 1 if payload['run_status'] == 'degraded' else 0
    except (ValueError, OSError, RuntimeError, csv.Error) as exc:
        print(f'Historical replay failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
