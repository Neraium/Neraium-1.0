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
        # Ingestion places analytical sampling limits alongside its timers.
        # They must remain checked even though the timing envelope is excluded.
        performance = result.get('performance', {})
        for key in ('profile_sample_limit_per_signal', 'near_duplicate_comparison_limit'):
            if key in performance:
                totals[key] = performance[key]
    return totals


def main():
    phases = {}
    for phase in ('before', 'after', 'control'):
        results = []
        for path in sorted(RAW.glob(f'{phase}-*-benchmark.json')):
            result = json.loads(path.read_text())
            result['cpu_min'] = min(sample['cpu_seconds'] for sample in result['samples'])
            result['cpu_max'] = max(sample['cpu_seconds'] for sample in result['samples'])
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
    controls = []
    for name, control in phases['control'].items():
        after = phases['after'].get(name)
        if after:
            controls.append({
                'workload': name, 'control': control, 'after': after,
                'wall_seconds_saved': control['wall_median'] - after['wall_median'],
                'wall_reduction_percent': 100 * (1 - after['wall_median'] / control['wall_median']),
                'throughput_gain_percent': 100 * (after['rows_per_second'] / control['rows_per_second'] - 1),
                'rss_bytes_saved': control['peak_rss_bytes'] - after['peak_rss_bytes'],
                'rss_reduction_percent': 100 * (1 - after['peak_rss_bytes'] / control['peak_rss_bytes']),
            })
    (RAW.parent / 'control-comparison.json').write_text(json.dumps(controls, indent=2)+'\n')
    memory = []
    for path in sorted(RAW.glob('memory-control-*-benchmark.json')):
        control = json.loads(path.read_text())
        optimized_path = RAW / f"memory-after-{control['workload']}-benchmark.json"
        if optimized_path.exists():
            after = json.loads(optimized_path.read_text())
            memory.append({
                'workload': control['workload'], 'control': control, 'after': after,
                'rss_bytes_saved': control['peak_rss_bytes'] - after['peak_rss_bytes'],
                'rss_reduction_percent': 100 * (1 - after['peak_rss_bytes'] / control['peak_rss_bytes']),
                'protocol': 'Separate processes, one warm-up and one measured job; RSS read before output serialization/capture. Not used for throughput claims.',
            })
    (RAW.parent / 'memory-comparison.json').write_text(json.dumps(memory, indent=2)+'\n')
    lines = ['# Benchmarks', '', 'One warm-up and three measurements per workload. Every measured run is retained; no outlier removal. Timings exclude fixture generation, imports, runtime initialization, output capture, and profiling. Full samples, CPU times, RSS, work counters, and throughput are in `before.json`, `after.json`, and `comparison.json`.', '', '| Workload | Before median [min–max] s | After median [min–max] s | Saved s | Latency reduction | Rows/s before → after | Peak RSS MiB before → after |', '|---|---:|---:|---:|---:|---:|---:|']
    for item in comparison:
        a,b=item['before'],item['after']
        lines.append(f"| {item['workload']} | {a['wall_median']:.4f} [{a['wall_min']:.4f}–{a['wall_max']:.4f}] | {b['wall_median']:.4f} [{b['wall_min']:.4f}–{b['wall_max']:.4f}] | {item['wall_seconds_saved']:.4f} | {item['wall_reduction_percent']:.1f}% | {a['rows_per_second']:.0f} → {b['rows_per_second']:.0f} | {a['peak_rss_bytes']/2**20:.1f} → {b['peak_rss_bytes']/2**20:.1f} |")
    lines += ['', 'Negative reductions are regressions/noise and are deliberately reported. RSS is process high-water memory including setup, warm-up and prior output retention, not isolated allocation peak. Shared-host timing dispersion limits causal claims for small differences. Incremental rows/s covers 720 new rows; per-window latency is the three-window total divided by three. Relationship throughput counts deeply analyzed unique pairs per call, not all lag/window sub-evaluations; those separate counters are retained in JSON.', '']
    lines += ['The original baseline showed substantial host variation. The following later controls reload only the four original hot-path modules from the frozen commit, verifying their SHA-256 against the initial workspace manifest. All other current workspace code remains the same. Each control is followed by its optimized benchmark. These controls supplement, rather than replace, the original measurements.', '', '| Workload | Later original-code median s | Optimized median s | Saved s | Latency reduction | Throughput gain | RSS reduction |', '|---|---:|---:|---:|---:|---:|---:|']
    for item in controls:
        lines.append(f"| {item['workload']} | {item['control']['wall_median']:.4f} | {item['after']['wall_median']:.4f} | {item['wall_seconds_saved']:.4f} | {item['wall_reduction_percent']:.1f}% | {item['throughput_gain_percent']:.1f}% | {item['rss_reduction_percent']:.1f}% |")
    lines += ['', 'Machine-readable control samples and ranges: `control.json` and `control-comparison.json`. Fresh-process runs use `PYTHONHASHSEED=8675309`; their samples are kept separately in `raw/fresh-*-benchmark.json` and are not pooled into the performance medians.', '']
    lines += ['The repeated benchmark process retains/serializes large results between trials, so its high-water RSS can hide reduced ingestion working memory. The following independent checks use one warm-up and one measured job in separate original/optimized processes, reading RSS before serialization. Their timing samples are retained but are not used to claim throughput gains.', '', '| Workload | Original isolated-job peak MiB | Optimized isolated-job peak MiB | Saved MiB | Reduction |', '|---|---:|---:|---:|---:|']
    for item in memory:
        lines.append(f"| {item['workload']} | {item['control']['peak_rss_bytes']/2**20:.1f} | {item['after']['peak_rss_bytes']/2**20:.1f} | {item['rss_bytes_saved']/2**20:.1f} | {item['rss_reduction_percent']:.1f}% |")
    lines += ['', 'These are process high-water checks including setup and warm-up, not allocation traces. The full repeated-process peaks above remain reported, including regressions. See `memory-comparison.json` for the complete isolated samples.', '']
    (RAW.parent / 'BENCHMARKS.md').write_text('\n'.join(lines))
    verification = []
    for golden in sorted(RAW.glob('before-*-0.json.gz')):
        name = golden.name[len('before-'):-len('-0.json.gz')]
        expected = encode(governed(load_output(golden)))
        expected_counts = counters(load_output(golden))
        for path in sorted(RAW.rglob(f'*-{name}-*.json.gz')):
            if any(parent.name.startswith('harness-attempt-') for parent in path.parents):
                continue
            value = load_output(path)
            actual = encode(governed(value))
            verification.append({'file':str(path.relative_to(RAW)), 'golden':golden.name, 'equal':actual==expected, 'work_counters_equal':counters(value)==expected_counts, 'sha256':hashlib.sha256(actual).hexdigest()})
    (RAW / 'equivalence.json').write_text(json.dumps(verification,indent=2)+'\n')
    failures = [item for item in verification if not item['equal'] or not item['work_counters_equal']]
    print(json.dumps({'comparisons':len(verification), 'failures':failures},indent=2))
    if failures:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
