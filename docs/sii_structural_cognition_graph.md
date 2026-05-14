# SII Structural Cognition Graph

The structural cognition graph captures infrastructure behavior evolution, not raw telemetry snapshots.

## Graph components
- Nodes: subsystems, archetypes, pressures, facility states, and recovery markers.
- Edges: propagation pathways, dependency interactions, and corroborated transitions.
- Snapshots: replayable graph states at cognition checkpoints.
- Evolution: graph diff/evolution records over time.

## Engines
- `structural_cognition_graph.py`
- `graph_memory_store.py`
- `graph_query_engine.py`
- `graph_evolution_engine.py`

## Required capabilities
- Graph snapshot persistence
- Graph evolution tracking
- Similarity and recurring pathway queries
- Cross-domain archetype matching
- Evidence lineage attachment to graph transitions
