"""Parallel audit orchestration must preserve sequential engine inputs/state."""
from copy import deepcopy

from scripts.validate_relationship_qualification import evaluate_sequence, parallel_sequences
from app.services.output_semantics import semantic_content
from test_sii_supplied_reference import contract


def test_parallel_cases_preserve_sequential_state_and_result_order():
    cases = [{"inputs": [contract(16), contract(16)]}, {"inputs": [contract(24)]}]
    before = deepcopy(cases)
    expected = [record for case in cases for record in evaluate_sequence(case["inputs"])]
    actual = list(parallel_sequences(cases, 2))
    assert len(actual) == len(expected)
    for (a_hash, a_result, a_error), (b_hash, b_result, b_error) in zip(actual, expected):
        assert a_hash == b_hash
        assert a_error is b_error is None
        assert semantic_content(a_result["relationship_graph"]) == semantic_content(b_result["relationship_graph"])
        assert semantic_content(a_result["relationship_analysis"]) == semantic_content(b_result["relationship_analysis"])
    assert cases == before
