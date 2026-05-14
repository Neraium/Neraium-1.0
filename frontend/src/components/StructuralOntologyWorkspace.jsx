import React, { useMemo } from "react";

export default function StructuralOntologyWorkspace({ intelligence, Panel, EmptyState }) {
  const ontology = intelligence?.structural_ontology ?? null;
  const activeArchetypes = intelligence?.active_archetypes ?? [];
  const domainPack = intelligence?.domain_cognition_pack ?? null;
  const vocabulary = ontology?.vocabulary ?? [];
  const relationships = ontology?.archetype_relationships ?? [];
  const primitives = ontology?.ontology_primitives?.instability_lifecycle ?? [];

  const activeRelationshipRows = useMemo(() => {
    const activeNames = new Set(activeArchetypes.map((item) => item.name));
    return relationships.filter((entry) => activeNames.has(entry.source)).slice(0, 8);
  }, [activeArchetypes, relationships]);

  if (!ontology) {
    return (
      <div className="workspace-grid workspace-grid--console">
        <Panel title="Structural Ontology" className="span-12">
          <EmptyState
            title="Ontology pending"
            body="Connect telemetry or upload a structural data window to activate ontology visualization."
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Structural Ontology Graph" className="span-12 workspace-hero-panel">
        <div className="canonical-flow">
          {primitives.map((phase) => (
            <div key={phase} className="canonical-flow__step">
              <span>{phase.replaceAll("_", " ")}</span>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Active Archetypes" className="span-6">
        <ul className="system-body-timeline-list">
          {(activeArchetypes.length ? activeArchetypes : [{ name: "No active archetypes" }]).map((item) => (
            <li key={item.name}>
              <span className="metadata-text">{item.evidence_strength ?? "developing"}</span>
              <strong>{item.name?.replaceAll("_", " ")}</strong>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Ontology Relationships" className="span-6">
        <ul className="system-body-timeline-list">
          {(activeRelationshipRows.length ? activeRelationshipRows : relationships.slice(0, 6)).map((item) => (
            <li key={item.source}>
              <span className="metadata-text">{item.interaction_pattern}</span>
              <strong>{item.source.replaceAll("_", " ")} {"->"} {(item.targets ?? []).join(", ").replaceAll("_", " ")}</strong>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Domain Cognition Pack" className="span-6">
        <p className="evidence-lineage-panel__title">{domainPack?.domain?.replaceAll("_", " ") ?? "domain unavailable"}</p>
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">Subsystem Types</span><strong>{(domainPack?.subsystem_types ?? []).join(" | ")}</strong></li>
          <li><span className="metadata-text">Propagation Pathways</span><strong>{(domainPack?.propagation_pathways ?? []).join(" | ")}</strong></li>
          <li><span className="metadata-text">Operational Timing</span><strong>{(domainPack?.operational_timing_patterns ?? []).join(" | ")}</strong></li>
        </ul>
      </Panel>

      <Panel title="Operational Cognition Language" className="span-6">
        <div className="evidence-interaction-panel__chips">
          {vocabulary.map((term) => (
            <div key={term} className="evidence-chip">
              <strong>{term}</strong>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
