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

function confidenceDecomposition(liveOps, drivers, relationships) {
  const driftMagnitude = (liveOps.driftRows ?? [])
    .reduce((sum, row) => sum + Math.abs(Number(row.absolute_change ?? 0)), 0);
  const relationshipMagnitude = (liveOps.relationshipRows ?? [])
    .reduce((sum, row) => sum + Math.abs(Number(row.pair_weight ?? row.change ?? 0)), 0);
  const evidenceDepth = drivers.length;
  const relationshipDepth = relationships.length;

  const signalScore = Math.min(1, driftMagnitude / 0.8);
  const relationshipScore = Math.min(1, relationshipMagnitude / 0.8);
  const evidenceScore = Math.min(1, evidenceDepth / 5);
  const corroborationScore = Math.min(1, relationshipDepth / 4);

  const weights = [
    { label: "Signal intensity", value: signalScore, weight: 0.34 },
    { label: "Relationship divergence", value: relationshipScore, weight: 0.28 },
    { label: "Evidence depth", value: evidenceScore, weight: 0.22 },
    { label: "Cross-check corroboration", value: corroborationScore, weight: 0.16 },
  ];

  const composite = weights.reduce((sum, item) => sum + (item.value * item.weight), 0);
  return { weights, composite: Number((composite * 100).toFixed(1)) };
}

function buildSubsystemAttribution(liveOps, drivers, relationships) {
  const seeds = [
    { key: "hvac", label: "HVAC / airflow" },
    { key: "humidity", label: "Humidity control" },
    { key: "irrigation", label: "Irrigation / fertigation" },
    { key: "lighting", label: "Lighting / photoperiod" },
    { key: "sensor", label: "Sensor continuity" },
  ];
  const corpus = [...drivers, ...relationships, ...(liveOps.evidenceLines ?? [])].map((v) => String(v ?? "").toLowerCase());
  const ranked = seeds.map((seed) => {
    const hits = corpus.reduce((sum, line) => sum + (line.includes(seed.key) ? 1 : 0), 0);
    const score = Math.min(0.99, 0.22 + hits * 0.17);
    return { ...seed, hits, score: Number(score.toFixed(2)) };
  }).sort((a, b) => b.score - a.score);
  return ranked;
}

function buildValidationSummary(liveOps, drivers, relationships, driftRows) {
  const driftCount = driftRows.length;
  const relationshipCount = relationships.length;
  const evidenceCount = drivers.length;
  const quality = String(liveOps.readinessLabel ?? "").toLowerCase();

  const sufficiency = quality.includes("active") || driftCount >= 4
    ? "Sufficient for operator action"
    : "Partial evidence, treat as early warning";
  const uncertainty = driftCount < 3 || relationshipCount < 2
    ? "High uncertainty: limited continuity across signals."
    : "Moderate uncertainty: relationships are present but still evolving.";

  const improve = [];
  if (driftCount < 5) improve.push("Extend upload window to include more baseline and recent samples.");
  if (relationshipCount < 3) improve.push("Increase paired subsystem telemetry coverage for stronger corroboration.");
  if (evidenceCount < 3) improve.push("Capture additional environmental channels to reduce attribution ambiguity.");
  if (improve.length === 0) improve.push("Current data quality is strong; continue monitoring for persistence.");

  return { sufficiency, uncertainty, improve };
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
  const confidenceModel = confidenceDecomposition(liveOps, drivers, relationships);
  const subsystemAttribution = buildSubsystemAttribution(liveOps, drivers, relationships).slice(0, 4);
  const validationSummary = buildValidationSummary(liveOps, drivers, relationships, driftRows);

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
              <li>{`Composite confidence model: ${confidenceModel.composite}%`}</li>
            </ul>
            <div className="technical-bars">
              {confidenceModel.weights.map((part) => (
                <div className="technical-bars__row" key={part.label}>
                  <span>{part.label}</span>
                  <div className="technical-bars__track">
                    <div className="technical-bars__fill" style={{ width: `${Math.round(part.value * 100)}%` }} />
                  </div>
                  <strong>{`${Math.round(part.value * 100)}%`}</strong>
                </div>
              ))}
            </div>
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
            <h3>Subsystem Attribution</h3>
            <ul>
              {subsystemAttribution.map((itemScore) => (
                <li key={itemScore.key}>{`${itemScore.label}: ${(itemScore.score * 100).toFixed(0)}% evidence strength`}</li>
              ))}
            </ul>
          </article>

          <article className="evidence-block">
            <h3>Audit Trace</h3>
            <ul>
              {(auditLines.length ? auditLines : ["No audit trace available yet."]).map((line, idx) => <li key={`audit-${idx}`}>{line}</li>)}
            </ul>
          </article>

          <article className="evidence-block">
            <h3>Validation Summary</h3>
            <ul>
              <li>{`Data sufficiency: ${validationSummary.sufficiency}`}</li>
              <li>{`Uncertainty: ${validationSummary.uncertainty}`}</li>
              {validationSummary.improve.map((line) => (
                <li key={line}>{`Improve certainty: ${line}`}</li>
              ))}
            </ul>
          </article>
        </div>
      )}
    </section>
  );
}
