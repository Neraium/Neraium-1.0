# SII Ecosystem Standard

Neraium is the read-only platform. Its Systemic Infrastructure Intelligence (SII) analyzes context from BMS, SCADA, historians, telemetry pipelines, and digital-twin environments.

## Core principles
- Read-only integration only.
- Evidence lineage attached to every SII output.
- Replayable evidence with timeline reconstruction.
- Operator-centric interpretation over autonomous action.

## Ecosystem contracts
- Runtime state export (`/api/ecosystem/runtime/state`)
- Context entity and relationship export (`/api/ecosystem/context/*`)
- System relationship graph snapshot/evolution export (`/api/ecosystem/graph/*`)
- Replay/evidence/ontology export (`/api/ecosystem/*/export`)
- Simulation scenario export (`/api/ecosystem/simulation/scenarios`)

## Non-permitted behaviors
- Control signals or actuation commands.
- Deterministic failure claims.
- Autonomous maintenance actions.
