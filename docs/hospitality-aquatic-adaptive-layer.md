# Neraium Hospitality Aquatic Extension (Governed, Read-Only)

## Scope
This change adapts existing Neraium SII architecture for commercial resort pool/spa operations without redesigning the platform, removing admission doctrine, or introducing any actuation.

## What Was Added
- Commercial aquatic telemetry signal schema (`ORP`, `pH`, pool/spa thermal, flow, pressure, pump/heater runtime, feed, level, valves, occupancy, ambient).
- Aquatic simulation and replay dataset builder with:
  - daily cycling behavior
  - high bather load spikes
  - heat-coupled daytime stress
  - overnight stabilization
  - gradual degradation and operational noise
- Relationship map and instability archetype layer for aquatic operations.
- Bounded, explainable, corroborated instability candidate scoring integrated into upload processing.
- Integration stubs for Pentair, Hayward, MQTT, Modbus, Node-RED, REST, BAS/BMS.

## Read-Only and Governance Boundary
- No actuation paths were introduced.
- No autonomous control behavior was introduced.
- No operator authority changes were introduced.
- Existing Aletheia Gate admission flow remains in place.
- Added domain logic only contributes explainable evidence candidates and operator checks.

## Detection and Admission Behavior
- No static threshold-only alerting was added.
- Aquatic instability candidates require multi-signal relationship support and persistence indicators.
- Weak/transient candidates are filtered using bounded support-score logic.
- Candidate records include subsystem, timeline, contributing signals, evidence graph, severity trajectory, relationship explanation, and confidence persistence score.

## API and UI Impact
- Replay API now supports `mode=aquatic_demo`.
- Facility response now includes aquatic-oriented system taxonomy and integration stubs.
- Home gate state language aligns to `Stable / Watch / Admission`.
- Layout polish expands the orb stage across desktop while preserving responsive behavior.

## Files Added/Updated
- Added:
  - `backend/app/services/aquatic_domain.py`
  - `docs/hospitality-aquatic-adaptive-layer.md`
- Updated:
  - `backend/app/services/upload_jobs.py`
  - `backend/app/routers/replay.py`
  - `backend/app/routers/facility.py`
  - `backend/app/connectors/placeholders.py`
  - `backend/app/connectors/registry.py`
  - `frontend/src/config/workspaces.js`
  - `frontend/src/components/workspaces/SystemBody/SystemBodyWorkspace.jsx`
  - `frontend/src/styles/system-body/system-body-hero.css`

## Future ML Modularity
Current aquatic layer remains lightweight. It exposes clean handoff points for future optional modules:
- clustering
- anomaly ranking
- sequence models
- similarity search
- probabilistic calibration

All future modules are expected to remain operator-governed and evidence-explainable.
