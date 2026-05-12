import { useMemo, useState } from "react";

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
  const [activeTab, setActiveTab] = useState("operator");
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

  const driftRows = (liveOps.driftRows ?? []).slice(0, 8);
  const driftScale = useMemo(() => {
    const max = driftRows.reduce((acc, row) => Math.max(acc, Math.abs(Number(row.absolute_change ?? 0))), 0);
    return max > 0 ? max : 1;
  }, [driftRows]);

  const relationshipRows = (matchedRows.length > 0 ? matchedRows : (liveOps.relationshipRows ?? [])).slice(0, 8);
  const auditLines = (item?.rawEvidenceLines?.length ? item.rawEvidenceLines : (liveOps.evidenceLines ?? [])).slice(0, 10);
  const confidence = Number.isFinite(item?.confidence) ? `${item.confidence}%` : (liveOps.readinessLabel ?? "Building");
  const evidenceCount = drivers.length + relationships.length;
  const recommendation = item?.recommendation ?? liveOps.connectionActionHint ?? "Continue monitoring structural coherence.";

  return (
    <section className="evidence-console-view">
      <div className="evidence-console-view__header">
        <p className="system-body__kicker">Interpretability View</p>
        <h2>Evidence Console</h2>
        <p>Human-readable reasoning for what is wrong, where it is happening, and why the platform believes it.</p>
      </div>

      <div className="evidence-tabs" role="tablist" aria-label="Evidence view mode">
        <button
          className={`evidence-tab ${activeTab === "operator" ? "evidence-tab--active" : ""}`}
          type="button"
          role="tab"
          aria-selected={activeTab === "operator"}
          onClick={() => setActiveTab("operator")}
        >
          Operator
        </button>
        <button
          className={`evidence-tab ${activeTab === "technical" ? "evidence-tab--active" : ""}`}
          type="button"
          role="tab"
          aria-selected={activeTab === "technical"}
          onClick={() => setActiveTab("technical")}
        >
          Technical
        </button>
      </div>

      {activeTab === "operator" ? (
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
            <p>{recommendation}</p>
            <p className="evidence-block__meta">{liveOps.windowContext}</p>
          </article>
        </div>
      ) : (
        <div className="evidence-console-view__grid">
          <article className="evidence-block">
            <h3>Decision Math</h3>
            <ul>
              <li>{`Evidence quality: ${confidence}`}</li>
              <li>{`Evidence count: ${evidenceCount}`}</li>
              <li>{`Facility tone: ${liveOps.facilityTone}`}</li>
              <li>{`Window context: ${liveOps.windowContext ?? "n/a"}`}</li>
            </ul>
          </article>

          <article className="evidence-block">
            <h3>Drift Magnitudes</h3>
            <div className="technical-bars">
              {(driftRows.length ? driftRows : [{ label: "No drift rows", absolute_change: 0 }]).map((row, idx) => {
                const value = Number(row.absolute_change ?? 0);
                const width = Math.max(2, Math.round((Math.abs(value) / driftScale) * 100));
                return (
                  <div className="technical-bars__row" key={`drift-${idx}`}>
                    <span>{row.label ?? row.column ?? `Metric ${idx + 1}`}</span>
                    <div className="technical-bars__track">
                      <div className="technical-bars__fill" style={{ width: `${width}%` }} />
                    </div>
                    <strong>{value.toFixed(3)}</strong>
                  </div>
                );
              })}
            </div>
          </article>

          <article className="evidence-block">
            <h3>Relationship Deltas</h3>
            <ul>
              {(relationshipRows.length
                ? relationshipRows.map((row) => `${row.pair_key ?? row.detail}: ${Number(row.pair_weight ?? row.change ?? 0).toFixed(3)}`)
                : ["No relationship rows available."]).map((line, idx) => <li key={`tech-rel-${idx}`}>{line}</li>)}
            </ul>
          </article>

          <article className="evidence-block">
            <h3>Audit Trace</h3>
            <ul>
              {(auditLines.length ? auditLines : ["No audit trace available yet."]).map((line, idx) => <li key={`audit-${idx}`}>{line}</li>)}
            </ul>
          </article>
        </div>
      )}
    </section>
  );
}
