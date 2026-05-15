# Cultivation Pilot Overview

## Purpose
Neraium provides **structural cognition** for controlled cultivation environments. It helps operators understand how environmental systems are evolving over time through environmental topology, propagation pathway behavior, replay evidence, and continuation window context.

## What Neraium Does
- Tracks structural drift across room systems and relationships.
- Surfaces propagation pathway movement between subsystems.
- Provides replay evidence for how deterioration progression unfolded.
- Highlights compensation masking and delayed convergence/recovery behavior.
- Supports operator review with evidence lineage and continuation window framing.

## What Neraium Does Not Do
- Does not provide yield guarantees.
- Does not perform automated grow control.
- Does not predict exact failures.
- Does not provide AI optimization directives.

## Read-Only Architecture
Neraium is a **read-only** operational cognition layer:
- Ingests telemetry and status signals.
- Produces cognition state, replay, and evidence outputs.
- Does not send control commands to HVAC, dehumidification, irrigation, or other facility systems.

## Pilot Scope
This pilot validates whether structural cognition improves day-to-day environmental review quality in cultivation operations by:
- increasing early visibility into structural environmental change,
- improving replay-supported room investigation,
- improving confidence in evidence-backed operator prioritization.

## Expected Data Sources
- Facility telemetry exports or live read-only feeds.
- Room-level environmental signals and runtime/status signals.
- Timestamped records with room identifiers.

See [data_requirements.md](/C:/Users/Owner/Documents/Neraium-1.0/docs/pilot/data_requirements.md) for full detail.

## Operator Workflow
1. Facility State
2. Room Drift
3. Propagation
4. Replay
5. Evidence
6. Continuation Window
7. Operator Review

See [operator_workflow.md](/C:/Users/Owner/Documents/Neraium-1.0/docs/pilot/operator_workflow.md).

## Weekly Review Cadence
- Run one structured weekly pilot review session.
- Review facility-wide structural cognition summary.
- Review room-level drift and propagation pathway changes.
- Inspect replay evidence and compensation masking context.
- Record operator observations, open questions, and follow-up checks.

Use [weekly_report_template.md](/C:/Users/Owner/Documents/Neraium-1.0/docs/pilot/weekly_report_template.md) to keep reviews consistent.
