# SII Read-Only Integration Standard

All partner adapters are interface-first and explicitly read-only:
- `bms_adapter`
- `scada_adapter`
- `historian_adapter`
- `digital_twin_adapter`
- `enterprise_reporting_adapter`

## Allowed operations
- Pull normalized telemetry/context.
- Export cognition state, replay frames, evidence lineage, and ontology payloads.
- Publish integration readiness.

## Disallowed operations
- Control writes.
- Actuation commands.
- Autonomous action generation.

## Enforcement
Runtime readiness is evaluated through `backend/runtime/runtime_contracts.py`. Adapter boundary checks must keep payloads read-only and reject control or actuation intent before data enters the analysis path.
