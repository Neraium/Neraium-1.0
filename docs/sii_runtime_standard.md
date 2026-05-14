# SII Runtime Standard

The SII runtime layer is implemented by `SIIRuntime`, `SIIRuntimeState`, and `SIIRuntimeContract`.

## Runtime responsibilities
- Build portable cognition runtime state for cloud, on-prem, edge, and disconnected replay contexts.
- Publish topology cognition state, propagation state, structural memory state, continuation windows, evidence lineage state, replay frame state, behavioral twin state, and cognition confidence state.
- Enforce read-only processing posture.

## Execution compatibility
- Local execution
- Cloud execution
- On-prem execution
- Edge-compatible execution
- Disconnected replay mode

## Runtime evaluation
`RuntimeEvaluationResult` reports contract alignment, missing capabilities, and read-only posture validation.
