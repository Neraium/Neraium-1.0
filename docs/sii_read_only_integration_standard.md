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
`backend/safety/read_only_guard.py` rejects payloads containing control or actuation intent and is required in runtime and adapter boundary checks.
