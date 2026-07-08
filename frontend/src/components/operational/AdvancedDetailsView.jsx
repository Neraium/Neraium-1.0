export default function AdvancedDetailsView({ model, helpers, selectedInsightId, onAnalyzeSystem, onResumePreviousSession }) {
  const { DetailGrid, EvidencePanel, PanelHeader, QualityList, StatusBadge, Timeline, formatConfidenceDisplay, prioritizeEvidenceGroups, severityToTone } = helpers;
  const groups = prioritizeEvidenceGroups(model.evidenceGroups, selectedInsightId);
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--wide" aria-label="Advanced Details">
        <PanelHeader eyebrow="Advanced Details" title="Advanced Details" subtitle="Technical fields are collapsed until opened." />
        <details className="advanced-details-panel">
          <summary>Model Metadata</summary>
          <DetailGrid rows={model.analysisMetadataRows} technical />
        </details>
        <details className="advanced-details-panel">
          <summary>Behavior Windows</summary>
          <DetailGrid rows={model.behaviorWindowRows} technical />
        </details>
        <details className="advanced-details-panel">
          <summary>Technical Diagnostics</summary>
          <QualityList title="Warnings" items={model.qualityWarnings} empty={model.analysisComplete ? "No data quality warnings reported." : model.uiState.status.detail} />
          <QualityList title="Missing values" items={model.missingValues} empty={model.analysisComplete ? "No missing value summary reported." : model.uiState.status.detail} />
          <QualityList title="Timestamp quality" items={model.timestampNotes} empty={model.analysisComplete ? "Timestamp quality is acceptable or not yet reported." : model.uiState.status.detail} />
        </details>
        {model.advancedRelationshipDetails.length ? (
          <details className="advanced-details-panel">
            <summary>Raw Relationship Identifiers</summary>
            <QualityList title="Identifiers" items={model.advancedRelationshipDetails} empty="" codeItems />
          </details>
        ) : null}
        {groups.length ? (
          <details className="advanced-details-panel">
            <summary>Evidence</summary>
            <div className="evidence-group-list">
              {groups.map((group) => (
                <article className={group.id === selectedInsightId ? "evidence-group is-selected" : "evidence-group"} key={group.id}>
                  <div className="evidence-group__header">
                    <div>
                      <span className="section-token">{group.system}</span>
                      <h3>{group.title}</h3>
                    </div>
                    <div className="evidence-group__badges">
                      {group.severity ? <StatusBadge label={group.severity} tone={severityToTone(group.severity)} /> : null}
                      {group.confidence ? <StatusBadge label={formatConfidenceDisplay(group.confidence, group.confidenceScore)} tone="unknown" /> : null}
                    </div>
                  </div>
                  <div className="evidence-group__items">
                    {group.evidence.map((item, index) => <EvidencePanel key={item.evidence_id ?? index} evidence={item} />)}
                  </div>
                </article>
              ))}
            </div>
          </details>
        ) : null}
        <details className="advanced-details-panel">
          <summary>Raw Result JSON</summary>
          <pre className="advanced-json"><code>{model.rawResultJson}</code></pre>
        </details>
      </section>

      <section className="operational-panel" aria-label="Telemetry source details">
        <PanelHeader eyebrow="Telemetry" title="Telemetry Source" subtitle="" />
        <StatusBadge label={model.telemetryStatus.label} tone={model.telemetryStatus.tone} />
        <DetailGrid rows={[
          ["Source", model.sourceLabel],
          ["Last analysis", model.lastAnalysis],
          ["Detected data type", model.domainLabel],
        ]} technical />
        <div className="operational-actions">
          <button type="button" className="command-button" onClick={onAnalyzeSystem} disabled={model.analyzeDisabled}>{model.primaryCtaLabel}</button>
        </div>
      </section>

      <section className="operational-panel" aria-label="Analysis history">
        <PanelHeader eyebrow="History" title="History" subtitle="" />
        <Timeline items={model.historyItems} />
      </section>

      {model.canResumePrevious && typeof onResumePreviousSession === "function" ? (
        <section className="operational-panel" aria-label="Previous analysis">
          <PanelHeader eyebrow="Previous" title="Previous Analysis" subtitle="" />
          <button type="button" className="secondary-command-button" onClick={onResumePreviousSession}>Resume Previous Analysis</button>
        </section>
      ) : null}
    </div>
  );
}
