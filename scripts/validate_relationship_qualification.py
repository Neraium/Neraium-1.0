#!/usr/bin/env python3
"""Observe both evidence endpoints while running the unmodified development scorer.

Only frozen_v2/development and saved development-v2 results are read. Nothing is
added to engine kwargs. Qualification abstentions are reported separately from
the scorer's required binary projection.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))


def input_digest(kwargs):
    return sha256(json.dumps(kwargs, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def evaluate_sequence(sequence):
    """Independent cases can run concurrently; temporal windows cannot."""
    from app.engine.sii_engine import evaluate_sii
    state = recurrence = None
    records = []
    for source_kwargs in sequence:
        kwargs = dict(source_kwargs, relationship_persistence_state=state, relationship_recurrence_state=recurrence)
        fingerprint = input_digest(kwargs)
        try:
            result = evaluate_sii(**kwargs)
            records.append((fingerprint, result, None))
            graph = result.get("relationship_graph", {})
            state = graph.get("relationship_persistence_state", state)
            recurrence = graph.get("relationship_recurrence_state", recurrence)
        except Exception as exc:
            records.append((fingerprint, None, exc))
    return records


def parallel_sequences(inputs, workers):
    """Bound memory and preserve original scorer ordering."""
    from collections import deque
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        cases = iter(inputs)
        pending = deque()
        for _ in range(workers):
            case = next(cases, None)
            if case is not None: pending.append(pool.submit(evaluate_sequence, case["inputs"]))
        while pending:
            result = pending.popleft().result()
            case = next(cases, None)
            if case is not None: pending.append(pool.submit(evaluate_sequence, case["inputs"]))
            yield from result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    output_dir = args.output.resolve()
    if output_dir.exists():
        raise RuntimeError("output_must_be_new")
    from benchmarks.false_positive_v1 import evaluate
    from app.engine import sii_engine
    frozen = ROOT / "benchmarks/false_positive_v1/frozen_v2/development"
    manifest = json.loads((frozen / "manifest.json").read_text())
    inputs = evaluate.load_jsonl(frozen / manifest["inputs_file"])
    call_plan = [(item["case_id"], i + 1) for item in inputs for i in range(len(item["inputs"]))]
    if not 1 <= args.workers <= 4:
        raise ValueError("workers_must_be_between_one_and_four")
    evaluated = parallel_sequences(inputs, args.workers) if args.workers > 1 else None
    del inputs
    plan = iter(call_plan)
    before = evaluate.load_jsonl(ROOT / "benchmarks/false_positive_v1/results/development-v2/cases.jsonl")
    observed = {}
    windows = []
    original = sii_engine.evaluate_sii

    def observe(**kwargs):
        case_id, ordinal = next(plan)
        record = observed.setdefault(case_id, {"directional": False, "qualified": False, "promoted": False,
            "promoted_with_qualified_support": False, "limited": False, "insufficient": False, "reasons": set()})
        try:
            if evaluated is None:
                result = original(**kwargs)
            else:
                fingerprint, result, error = next(evaluated)
                if fingerprint != input_digest(kwargs):
                    # Bypass the scorer's normal engine-error recording: this is
                    # an audit orchestration defect and must abort the whole run.
                    raise SystemExit("parallel_evaluation_input_or_state_mismatch")
                if error is not None: raise error
        except Exception:
            record["insufficient"] = True
            record["reasons"].add("engine_rejected_inputs")
            windows.append({"case_id": case_id, "window": ordinal, "engine_rejected": True})
            raise
        edges = result.get("relationship_graph", {}).get("edges", [])
        summaries = []
        for edge in edges:
            directional = edge.get("directional_persistence_supported") is True
            qualified = edge.get("qualified_persistence_supported") is True
            promoted = edge.get("promoted_changed_edge") is True
            status = edge.get("qualification_status", "unavailable")
            reasons = edge.get("qualified_persistence", {}).get("reason_codes", [])
            record["directional"] |= directional
            record["qualified"] |= qualified
            record["promoted"] |= promoted
            record["promoted_with_qualified_support"] |= promoted and qualified
            record["limited"] |= status == "limited"
            record["insufficient"] |= status in {"insufficient", "unavailable"}
            record["reasons"].update(reasons)
            summaries.append({"columns": edge.get("columns"), "directional": directional,
                "qualified": qualified, "promoted_changed_edge": promoted,
                "qualification_status": status, "reason_codes": reasons,
                "signed_delta": edge.get("signed_correlation_delta"),
                "support_count": edge.get("temporal_persistence_supporting_observations"),
                "persistence_factor": edge.get("persistence_factor")})
        if not edges:
            record["insufficient"] = True
            record["reasons"].add("no_relationship_estimate")
        windows.append({"case_id": case_id, "window": ordinal, "edges": summaries})
        return result

    sii_engine.evaluate_sii = observe
    saved_argv = sys.argv
    try:
        sys.argv = ["evaluate", "--split", "development", "--frozen", str(frozen.parent),
                    "--output", str(output_dir)]
        evaluate.main()
    finally:
        sii_engine.evaluate_sii = original
        sys.argv = saved_argv
        if evaluated is not None: evaluated.close()
    assert len(windows) == len(call_plan)
    after = evaluate.load_jsonl(output_dir / "cases.jsonl")
    aggregate = {"baseline": {}, "directional": {}, "qualified_binary_projection": {},
                 "qualified_abstentions": 0, "by_evidence_class": {}, "by_binary_truth": {}, "directional_changes": [],
                 "known_directional_false_supports": [], "positive_controls": {},
                 "interpretation": "Missing profiles are abstentions, not improved false-positive performance."}
    for name, predicate in (("baseline", lambda r: r["prediction"] == "positive"),
                            ("directional", lambda r: observed[r["case_id"]]["directional"]),
                            ("qualified_binary_projection", lambda r: observed[r["case_id"]]["qualified"])):
        counts = Counter()
        for row in before:
            if row["evidence_class"] == "binary":
                key = ("TP" if predicate(row) else "FN") if row["truth"] == "positive" else ("FP" if predicate(row) else "TN")
                counts[key] += 1
        aggregate[name] = {k: counts[k] for k in ("TP", "FP", "TN", "FN")}
    for row in before:
        current = observed[row["case_id"]]
        cls = row["evidence_class"]
        counts = aggregate["by_evidence_class"].setdefault(cls, Counter())
        counts["cases"] += 1
        counts["before_supported"] += row["prediction"] == "positive"
        counts["before_any_promotion"] += bool(row["promoted_events"])
        counts["before_persistent_promotion"] += any(e["persistent"] for e in row["promoted_events"])
        for key in ("directional", "qualified", "promoted", "promoted_with_qualified_support", "limited", "insufficient"):
            counts[key] += current[key]
        if cls == "binary": aggregate["qualified_abstentions"] += (current["limited"] or current["insufficient"]) and not current["qualified"]
        if cls == "binary":
            truth_counts = aggregate["by_binary_truth"].setdefault(row["truth"], Counter())
            truth_counts["cases"] += 1
            truth_counts["before_any_promotion"] += bool(row["promoted_events"])
            truth_counts["before_persistent_promotion"] += any(e["persistent"] for e in row["promoted_events"])
            for key in ("directional", "qualified", "promoted", "promoted_with_qualified_support", "limited", "insufficient"):
                truth_counts[key] += current[key]
        if (row["prediction"] == "positive") != current["directional"]:
            aggregate["directional_changes"].append(row["case_id"])
        if cls == "binary" and row["truth"] == "negative" and row["prediction"] == "positive":
            aggregate["known_directional_false_supports"].append({"case_id": row["case_id"],
                **{k: v for k, v in current.items() if k != "reasons"}, "reasons": sorted(current["reasons"]),
                "before_promoted": bool(row["promoted_events"])})
        if cls == "binary" and row["truth"] == "positive":
            for key in ("directional", "qualified", "promoted", "limited", "insufficient"):
                aggregate["positive_controls"][key] = aggregate["positive_controls"].get(key, 0) + current[key]
    aggregate["engine_limited_cases_before"] = sum(r["engine_insufficient_evidence"] for r in before)
    aggregate["engine_limited_cases_after"] = sum(r["engine_insufficient_evidence"] for r in after)
    aggregate["qualification_reason_case_counts"] = dict(Counter(reason for record in observed.values() for reason in record["reasons"]))
    (output_dir / "endpoint-comparison.json").write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n")
    with (output_dir / "window-evidence.jsonl").open("w") as stream:
        for window in windows: stream.write(json.dumps(window, sort_keys=True) + "\n")
    lines = ["# Development-v2 qualification audit", "", "Frozen inputs and scorer were unchanged.", "",
             "Missing acquisition profiles are abstentions; zero qualified positives is not an FPR improvement.", "",
             "| Endpoint | TP | FP | TN | FN |", "|---|---:|---:|---:|---:|"]
    for key in ("baseline", "directional", "qualified_binary_projection"):
        values = aggregate[key]
        lines.append(f"| {key} | {values['TP']} | {values['FP']} | {values['TN']} | {values['FN']} |")
    lines += ["", f"Binary qualification abstentions: {aggregate['qualified_abstentions']}.",
              f"Directional case changes: {len(aggregate['directional_changes'])}.", "",
              "| Ground truth | Cases | Promotions before | Promotions after | Qualified | Limited | Insufficient |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for cls, values in {**aggregate["by_binary_truth"], **{k:v for k,v in aggregate["by_evidence_class"].items() if k != 'binary'}}.items():
        lines.append(f"| {cls} | {values['cases']} | {values['before_any_promotion']} | {values['promoted']} | {values['qualified']} | {values['limited']} | {values['insufficient']} |")
    lines += ["", "## Original directional false supports", ""]
    for record in aggregate["known_directional_false_supports"]:
        lines.append(f"- {record['case_id']}: directional={record['directional']}, qualified={record['qualified']}, "
                     f"promoted={record['before_promoted']} → {record['promoted']}; {', '.join(record['reasons'])}.")
    lines += ["", "## Qualification limitations", ""]
    lines.extend(f"- {reason}: {count} cases." for reason, count in sorted(aggregate["qualification_reason_case_counts"].items()))
    (output_dir / "qualification-report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(aggregate, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
