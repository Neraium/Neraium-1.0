"""Summarize all retained runs, without removing outliers."""
import gzip
import hashlib
import json
import statistics
from pathlib import Path
from governed_benchmark import RAW, governed, encode


def load_output(path):
    with gzip.open(path, 'rb') as f:
        return json.load(f)


def counters(output):
    results = output if isinstance(output, list) else [output]
    totals = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        for key, value in result.get('processing_trace', {}).get('performance', {}).get('totals', {}).items():
            totals[key] = totals.get(key, 0) + value
    return totals


def main():
    phases = {}
    for phase in ('before', 'after'):
        results = []
        for path in sorted(RAW.glob(f'{phase}-*-benchmark.json')):
            result = json.loads(path.read_text())
            output = load_output(RAW / f"{phase}-{result['workload']}-0.json.gz")
            result['work_counters'] = counters(output)
            pair_count = result['work_counters'].get('relationship_pairs_deeply_analyzed')
            result['relationship_pairs_per_second'] = pair_count / result['wall_median'] if pair_count is not None else None
            if result['workload'].startswith('incremental'):
                result['mean_window_latency_seconds'] = result['wall_median'] / 3
            results.append(result)
        phases[phase] = {item['workload']: item for item in results}
        (RAW.parent / f'{phase}.json').write_text(json.dumps(results, indent=2)+'\n')
    comparison = []
    for name, before in phases['before'].items():
        after = phases['after'].get(name)
        if not after:
            continue
        comparison.append({'workload': name, 'before': before, 'after': after, 'wall_seconds_saved': before['wall_median']-after['wall_median'], 'wall_reduction_percent': 100*(1-after['wall_median']/before['wall_median']), 'throughput_gain_percent': 100*(after['rows_per_second']/before['rows_per_second']-1), 'rss_bytes_saved': before['peak_rss_bytes']-after['peak_rss_bytes'], 'rss_reduction_percent': 100*(1-after['peak_rss_bytes']/before['peak_rss_bytes'])})
    (RAW.parent / 'comparison.json').write_text(json.dumps(comparison, indent=2)+'\n')
    lines = ['# Benchmarks', '', 'One warm-up and three measurements per workload. Every measured run is retained; no outlier removal. Timings exclude fixture generation, imports, runtime initialization, output capture, and profiling. Full samples, CPU times, RSS, work counters, and throughput are in `before.json`, `after.json`, and `comparison.json`.', '', '| Workload | Before median [min–max] s | After median [min–max] s | Saved s | Latency reduction | Rows/s before → after | Peak RSS MiB before → after |', '|---|---:|---:|---:|---:|---:|---:|']
    for item in comparison:
        a,b=item['before'],item['after']
        lines.append(f"| {item['workload']} | {a['wall_median']:.4f} [{a['wall_min']:.4f}–{a['wall_max']:.4f}] | {b['wall_median']:.4f} [{b['wall_min']:.4f}–{b['wall_max']:.4f}] | {item['wall_seconds_saved']:.4f} | {item['wall_reduction_percent']:.1f}% | {a['rows_per_second']:.0f} → {b['rows_per_second']:.0f} | {a['peak_rss_bytes']/2**20:.1f} → {b['peak_rss_bytes']/2**20:.1f} |")
    lines += ['', 'Negative reductions are regressions/noise and are deliberately reported. RSS is process high-water memory including setup, warm-up and prior output retention, not isolated allocation peak. Shared-host timing dispersion limits causal claims for small differences. Incremental rows/s covers 720 new rows; per-window latency is the three-window total divided by three. Relationship throughput counts deeply analyzed unique pairs per call, not all lag/window sub-evaluations; those separate counters are retained in JSON.', '']
    (RAW.parent / 'BENCHMARKS.md').write_text('\n'.join(lines))
    verification = []
    for golden in sorted(RAW.glob('before-*-0.json.gz')):
        name = golden.name[len('before-'):-len('-0.json.gz')]
        expected = encode(governed(load_output(golden)))
        expected_counts = counters(load_output(golden))
        for path in sorted(RAW.glob(f'*-{name}-*.json.gz')):
            value = load_output(path)
            actual = encode(governed(value))
            verification.append({'file':path.name, 'golden':golden.name, 'equal':actual==expected, 'work_counters_equal':counters(value)==expected_counts, 'sha256':hashlib.sha256(actual).hexdigest()})
    (RAW / 'equivalence.json').write_text(json.dumps(verification,indent=2)+'\n')
    failures = [item for item in verification if not item['equal'] or not item['work_counters_equal']]
    print(json.dumps({'comparisons':len(verification), 'failures':failures},indent=2))
    if failures:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
