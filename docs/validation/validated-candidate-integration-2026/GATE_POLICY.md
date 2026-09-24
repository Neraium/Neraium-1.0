# Frozen gate policy — declared before the only complete 10K execution

Use the existing test_complete_10000_upload_repeat and retained worker, unchanged 10,000-observation/three-signal input, two executions with live clocks. No 500K/1M/LBNL controller invocation.

Current-to-current: exact complete semantic_content equality and semantic_digest equality under governed-output-semantics.v2. No comparator filters added. Runtime envelopes may differ only at production-declared paths.

Retained-to-current: the existing analytical snapshot remains intact. The complete repaired pre-retirement output is compared after the same two previously declared Aletheia removals. A pure copy-only bridge changes v1 output declarations to v2, adds complete-upload producer identity to the governed root, relocates the upload producer's request/session/attempt correlation through its normal encoder, maps the known SOURCE build commit to the actual TARGET build commit, and recomputes semantic provenance links for that new comparison view. No historical file/hash is rewritten. No ranking, numbers, evidence IDs, primary references, chronological lists, qualification or state is altered. No reference output is rebuilt through analytical production functions.

The original retained complete-upload result hash was verified unchanged before the gate. The bridge does not assert that a v2 hash equals a historical v1 hash. Both current evidence-store links and all four current provenance links must equal the current result_digest.

Companion targeted tests establish exact-tie and producer-ID behavior because this 10K input is not an exact-tie experiment. The gate itself must preserve every supplied rank, primary, graph, state and consequence value it contains. Zero new Aletheia EVP records and no active gate are required.

If either execution, complete comparison or retained analytical comparison fails, retain the failure and do not rerun the complete gate or change exclusions in response.
