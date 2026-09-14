# Governance compatibility result authorities

PR #138's complete-result regression digest became stale at continuous-persistence
commit `2a25a3312bcd01d67550bb259c0fe3605076696c`, before recurrence was added.
The compatibility test now validates both intentional contract transitions before
checking the current complete-result digest. No analytical implementation changes
are part of this test update.

## Independently captured authorities

| Result | Normalized SHA-256 |
| --- | --- |
| Original pin, reproduced at production `b790479f0abcb90aa71f7677d10aa542222b55c8` | `334b6bd43f0ea23f1e8100b075c29cc8c19f5b1852b71bb59591410e36020dc4` |
| Post-continuous `2a25a331`; identical at pre-recurrence `303456053b571d67fd670653185bb576b2fceb11` | `96867ed89a82e29ea47184ec5f3693d3297ccf3457bb1acf6adfe68f0b4700a5` |
| Recurrence `86b5579069486c66376efc8f2bd0d35025a11f9f` | `58fa745062d6ac2a2c3e7918827a8ec16cc2eda5b25506d78c337f06cbf1a671` |

Each result was generated in a separate `git archive` extraction of `backend`,
`tests`, and `pytest.ini`, using the repository virtual environment (Python
3.11.16), `APP_ENV=test`, and the existing pytest runtime-isolation fixture.
The original test's `_stable_rows()` inputs, `_profiles()`, engine arguments,
governance-call prohibitions, and normalization were unchanged. Only its final
digest assertion was replaced in the temporary archives with JSON capture.
The post-continuous and pre-recurrence captures compared exactly equal.

The existing normalization excludes `runtime_seconds`, `total_runtime_seconds`,
`step_timings`, and `performance`, canonicalizes upload run IDs, and checks the
four known entropy scores within an absolute `1e-16` before normalizing the Python
3.11/3.12 summation difference. No additional exclusions or tolerances were added.
Digests use sorted JSON keys, compact separators, and `allow_nan=False`.

## Original to continuous persistence

For this stable, single-window fixture, the recursive comparison found **375
added keys, 51 removed keys, and 21 changed values**. Counts include repeated
transport copies. There were no other differences, including no list-length or
type changes.

| Contract transition | Occurrences |
| --- | ---: |
| Replace `ranking_factors.persistence` with `ranking_factors.sample_sufficiency`, preserving the value `0.0` | 51 removals + 51 additions |
| Add `source_rows` and `time_window` provenance to relationship edges | 51 each |
| Change graph-edge `persistence_factor` from sample sufficiency `1.0` to unconfirmed temporal support `0.0` | 18 |
| Add `sample_sufficiency_factor: 1.0`, retaining the former numerical factor | 18 |
| Add `single_window_change_type: "stable"` | 18 |
| Add `persistent_relationship_change: false` | 18 |
| Add `first_supported_observation` and `latest_supported_observation`, both null | 18 each |
| Add `supporting_windows: []` | 18 |
| Add `temporal_persistence_status: "unconfirmed"` and `temporal_persistence_supported: false` | 18 each |
| Add `temporal_persistence_observations: 1` and `temporal_persistence_supporting_observations: 0` | 18 each |
| Add `temporal_persistence_direction: 0` and `temporal_persistence_direction_agreement: 0.0` | 18 each |
| Add caller-owned `relationship_persistence_state` | 3 |
| Add `thresholds.temporal_persistence` | 3 |
| Rename `persistence` to `sample_sufficiency` in the component-coherence formula text, preserving every weight | 3 |

Temporal policy remains six supporting observations, 75% direction agreement,
0.15 displacement, eight retained observations, and a 30-day horizon. In this
fixture, one neutral observation establishes no continuous support. The prior
sample sufficiency remains available separately; it cannot manufacture history.
See [Temporal relationship evidence](relationship_temporal_persistence.md).

The 18 graph-edge occurrences are three `edges` plus three `eligible_edges` in
each of the main graph, fusion inventory graph, and fusion neutral-evidence graph.
The broader 51 edge occurrences also include baseline, mode-conditioned, and
compatibility copies. Exact paths and before/after values are captured in
[`governance_compatibility_transitions.json`](../tests/fixtures/governance_compatibility_transitions.json).

## Continuous persistence to recurrence

The recursive comparison found **27 added keys, zero removals, and zero changed
preexisting values, types, or list lengths**:

| Recurrence addition | Occurrences |
| --- | ---: |
| Edge `recurrence_evidence`, unconfirmed with no supported episodes | 18 |
| `relationship_recurrence_state`, independent caller-owned continuation state | 3 |
| `recurring_edges: []` | 3 |
| `thresholds.recurrence` policy metadata | 3 |

These occur in `relationship_graph`,
`evidence_fusion.evidence_inventory[7].evidence`, and
`evidence_fusion.neutral_evidence[5].evidence`. No extra processing steps or
compatibility changes occur. Removing exactly these additions restores the
independently captured pre-recurrence result byte-for-byte under canonical JSON.

The non-paired engine result used by this test does not itself include the
governed analysis envelope. Separately projecting the captured old and new results
with their respective `build_sii_evidence_projection` implementations adds only
`relationship_recurrences: []`. Every preexisting governed field compares equal;
the old projection is also saved in the fixture. Independently projecting the
original production capture gives this same pre-recurrence projection, so existing
governed evidence is unchanged across both transitions for this input. Existing paired-engine and
transport tests cover populated episode provenance. See
[Governed relationship recurrence evidence](relationship_recurrence_evidence.md).

## Regression protection

The fixture groups identical changes by operation and exact value, listing each
affected path explicitly. The test checks each current value before reversing
the documented change. It then verifies the immutable pre-recurrence and original
digests. Unknown keys and locations are never removed by a recursive name filter.
Thus a change to `CURRENT_DIGEST` alone cannot conceal a changed existing field or
a modified transition payload.

Readable assertions also check sample versus temporal support, unchanged
classifications, confidence, quality, eligibility, provenance, changed edges,
compatibility, existing persistence analysis, processing trace, findings, and the
frozen governed projection. Exact transition payloads and unchanged existing
content prevent new causal, diagnostic, or prescriptive output; recurrence
payloads are additionally checked for such language. Deliberate mutations of
protected fields and invented output verify that the historical guards reject
regressions independently of the current digest.

This authority is the existing stable-input regression, not proof for every input.
The recurrence, continuous-persistence, SII contract, and evidence-transport suites
remain responsible for supported episodes, displacements, gates, and continuation
behavior. Future contract expansions require their own documented exact changes;
do not refresh either historical digest to make a failure disappear.
