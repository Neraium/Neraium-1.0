function includeForTarget(line, target) {
  if (!target) {
    return true;
  }
  const text = String(line ?? "").toLowerCase();
  if (target.type === "node") {
    return text.includes(String(target.label ?? target.id).toLowerCase()) || text.includes(String(target.id).toLowerCase());
  }
  return true;
}

function rowsForTarget(rows, target) {
  if (!target || target.type !== "edge") {
    return rows ?? [];
  }
  const keySet = new Set(target.pairKeys ?? []);
  if (keySet.size === 0) {
    return rows ?? [];
  }
  return (rows ?? []).filter((row) => keySet.has(row.pair_key));
}

export default function EvidenceConsoleWorkspace({ liveOps, selectedTarget }) {
  const item = liveOps.interventionItems?.[0];
  const matchedRows = rowsForTarget(liveOps.relationshipRows, selectedTarget);
  const relationshipSource = matchedRows.length > 0
    ? matchedRows.map((row) => row.detail)
    : item?.relationshipEvidence?.length
      ? item.relationshipEvidence
      : (liveOps.relationshipRows?.map((row) => row.detail) ?? []);

  const driverSource = item?.supportingEvidence?.length ? item.supportingEvidence : (liveOps.evidenceLines ?? []);

  const relationships = relationshipSource.filter((line) => includeForTarget(line, selectedTarget)).slice(0, 5);
  const drivers = driverSource.filter((line) => includeForTarget(line, selectedTarget)).slice(0, 5);

  const targetLabel = selectedTarget
    ? (selectedTarget.type === "edge"
      ? `${selectedTarget.from.toUpperCase()} -> ${selectedTarget.to.toUpperCase()}`
      : `${selectedTarget.label ?? selectedTarget.id}`)
    : "Facility-wide";

  return (
    <section className="evidence-console-view">
      <div className="evidence-console-view__header">
        <p className="system-body__kicker">Interpretability View</p>
        <h2>Evidence Console</h2>
        <p>Directional reasoning behind every hidden drift call.</p>
      </div>

      <div className="evidence-console-view__grid">
        <article className="evidence-block">
          <h3>Focus</h3>
          <p>{targetLabel}</p>
          {selectedTarget?.evidence ? <p className="evidence-block__meta">{selectedTarget.evidence}</p> : null}
        </article>

        <article className="evidence-block">
          <h3>Relationships Changed</h3>
          <ul>
            {(relationships.length ? relationships : ["No relationship evidence for selected target yet."]).map((line, idx) => <li key={`rel-${idx}`}>{line}</li>)}
          </ul>
        </article>

        <article className="evidence-block">
          <h3>Supporting Evidence</h3>
          <ul>
            {(drivers.length ? drivers : ["No supporting evidence for selected target yet."]).map((line, idx) => <li key={`driver-${idx}`}>{line}</li>)}
          </ul>
        </article>

        <article className="evidence-block">
          <h3>Operator Action</h3>
          <p>{item?.recommendation ?? liveOps.connectionActionHint ?? "Continue monitoring structural coherence."}</p>
          <p className="evidence-block__meta">{liveOps.windowContext}</p>
        </article>
      </div>
    </section>
  );
}
