# Analytical preservation

**18 focused regressions passed** (raw/analytical-regression.xml): semantic order/determinism, runtime-ID invariance, explicit source/Phase 4 identity, supplied-order exact ties, source-bound connector identity, historical v1 replay, corrected affected-signal order and terminal attempt metadata, canonical artifact tamper rejection/full consequence replay, quantifiable consequence/provenance and quality barriers, and four Aletheia retirement/historical compatibility cases.

All analytical files and existing comparator/bridge/worker remain byte-identical to the certified baseline. Stack #1/#2/#3/#5 unchanged; #3 ACCEPT_WITH_LIMITATIONS; #4 absent (runner function AST equality to validated SOURCE checked before gate). Four target-only behaviors preserved. Security edits affect HTTP/auth/configuration only.

## One complete 10K gate

The unchanged test_complete_10000_upload_repeat passed once (raw/complete-10k-tests.xml; 41.60 seconds pytest duration). Two full uploads, 10,000 rows × 3 signals each. No additional workload. Frozen methodology/hashes: raw/GATE_PREDECLARATION.json. Full returned and semantic outputs, provenance records and empty audit logs retained under raw/gate/. No resource stop.

The existing test verifies repeat equality, both retained SOURCE analytical snapshots, complete SOURCE equivalence under the predeclared version/build bridge, evidence-store hash and four provenance links, and zero EVPs/no active gate.

Additional read-only saved-output comparison uses **certified TARGET as authority**: each new output against each of the two certified outputs, direct semantic_content equality, no bridge or added exclusions. Four comparisons pass, zero differences (raw/target-semantic-mismatches.json). All twelve analytical component groups also match directly. Semantic digest `bd70db4d53f6a28d262834e1f7cd5e55a8bf3f6661f0a0c6a17720496ddbf907` and result digest `e41a27d2c2b953b13321fdc0d54207f75ec76f8c14b9158c8297619d24566aac` are unchanged. Canonical evidence, governed result, numerical graph/evidence/ranking, persistence/recurrence, contexts, sufficiency, summaries/state, source/behavioral identity, provenance/replay and Measurable Consequence match. Security transport headers never enter governed payloads.

No gate rerun, 500K, 1M, LBNL, scale benchmark, commit, merge or push. The retained 121.610119-second SOURCE 500K reference was not reproduced in TARGET and is not a security-campaign performance measurement.
