"""Expose measured category entry points without adding overlapping inclusive costs."""
import json
import pstats
from pathlib import Path
RAW = Path(__file__).resolve().parents[2] / 'docs/performance/2026-optimization/raw'
CATEGORIES = {
    'parsing_normalization': ['parse_numeric_value', '_parse_number', 'normalize_rows', 'build_normalization_report'],
    'dataframe_operations': ['dataframe_from_rows'],
    'statistical_calculations': ['_correlation', '_signal_characteristics', '_column_entropy'],
    'relationship_graph': ['_learn_relationship_graph', 'build_relationship_graph'],
    'baseline_calculations': ['_identify_modes', '_learn_distributions', '_fit_expected_models'],
    'covariance_correlation': ['_regularized_covariance_matrix', '_baseline_mahalanobis_distances', '_correlation_drift'],
    'temporal_persistence': ['evaluate_temporal_math', 'analyze_adaptive_persistence', 'evaluate_adaptive_persistence'],
    'operating_context': ['analyze_mode_conditioned_baseline', 'describe_mode', '_operating_context', '_row_summaries'],
    'serialization_deserialization': ['dumps', 'loads', 'iterencode', '_stable_json'],
    'provenance_evidence': ['_digest', 'build_evidence_package', 'fuse_evidence', 'build_evidence_fusion'],
    'file_database_io': ['file_sha256', 'preserve_raw_source', 'persist_immutable_derived_artifact', 'write_local_json', 'upsert_latest_payload'],
    'copying_conversion': ['deepcopy', '<built-in method numpy.asarray>', '<built-in method numpy.fromiter>', '_sequential_product_sum'],
}
output = {}
for path in sorted(RAW.glob('*.prof')):
    stats = pstats.Stats(str(path))
    categories = {}
    for category, names in CATEGORIES.items():
        entries = []
        for (filename, line, name), (primitive, total, own, inclusive, callers) in stats.stats.items():
            if name in names:
                entries.append({'file': filename, 'line': line, 'function': name, 'calls': total,
                                'self_seconds': own, 'inclusive_seconds': inclusive})
        categories[category] = sorted(entries, key=lambda item: -item['inclusive_seconds'])
    output[path.name] = {'profile_seconds': stats.total_tt, 'categories': categories}
(RAW / 'profile-categories.json').write_text(json.dumps(output, indent=2)+'\n')
