export default function AdvancedDetailsView({ model, helpers, selectedInsightId, onAnalyzeSystem, onResumePreviousSession, onReopenHistoricalAnalysis, onDeleteHistoricalAnalysis }) {
  const { DetailGrid, EvidencePanel, PanelHeader, QualityList, StatusBadge, Timeline, formatConfidenceDisplay, prioritizeEvidenceGroups, severityToTone } = helpers;
  const groups = prioritizeEvidenceGroups(model.evidenceGroups, selectedInsightId);
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--wide" aria-label="Analysis Details">
        <PanelHeader eyebrow="Analysis Details" title="Analysis Details" subtitle="Use this view when a finding needs diagnostics, evidence metadata, or raw result verification." />
        <details className="advanced-details-panel">
          <summary>Analysis Metadata</summary>
          <DetailGrid rows={model.analysisMetadataRows} technical />
        </details>
        <details className="advanced-details-panel">
          <summary>Behavior Windows</summary>
          <DetailGrid rows={model.behaviorWindowRows} technical />
        </details>
        <details className="advanced-details-panel">
          <summary>Service Diagnostics</summary>
          <QualityList title="Warnings" items={model.qualityWarnings} empty={model.analysisComplete ? "No data quality warnings reported." : model.uiState.status.detail} />
          <QualityList title="Missing values" items={model.missingValues} empty={model.analysisComplete ? "No missing value summary reported." : model.uiState.status.detail} />
          <QualityList title="Timestamp quality" items={model.timestampNotes} empty={model.analysisComplete ? "Timestamp quality is acceptable or not yet reported." : model.uiState.status.detail} />
        </details>
        {model.advancedRelationshipDetails.length ? (
          <details className="advanced-details-panel">
            <summary>Relationship Identifiers</summary>
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
          <summary>Analysis Result JSON</summary>
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
          <button type="button" className="command-button" onClick={onAnalyzeSystem} disabled={model.analyzeDisabled} title={model.analyzeDisabled ? "Analysis is already in progress. Wait for it to finish before starting another." : "Open historical telemetry analysis."}>{model.primaryCtaLabel}</button>
        </div>
      </section>

      <section className="operational-panel" aria-label="Analysis history">
        <PanelHeader eyebrow="History" title="Analysis History" subtitle="Reopen completed analyses." />
        <AnalysisHistoryList
          history={model.analysisHistory}
          onReopen={onReopenHistoricalAnalysis}
          onDelete={onDeleteHistoricalAnalysis}
        />
      </section>

      <section className="operational-panel" aria-label="Recent activity">
        <PanelHeader eyebrow="Activity" title="Recent Activity" subtitle="" />
        <Timeline items={model.historyItems} state={model.orb} status={model.orb.status} />
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


function AnalysisHistoryList({ history = [], onReopen, onDelete }) {
  if (!history.length) {
    return <div className="operational-empty"><strong>No saved analyses</strong><p>No completed analysis has been saved in this browser session. Import telemetry or reopen a persisted session to build history.</p></div>;
  }
  return (
    <div className="analysis-history-list">
      {history.map((entry) => (
        <article className="analysis-history-card" key={entry.id}>
          <div className="analysis-history-card__main">
            <span className="section-token">{formatHistoryTimestamp(entry.timestamp)}</span>
            <strong>{entry.datasetName}</strong>
            <dl>
              <div><dt>Baseline</dt><dd>{entry.fingerprintStatus}</dd></div>
              <div><dt>Systems</dt><dd>{entry.systemsCount}</dd></div>
              <div><dt>Insights</dt><dd>{entry.insightsCount}</dd></div>
            </dl>
          </div>
          <div className="analysis-history-card__actions">
            <button type="button" className="secondary-command-button" onClick={() => onReopen?.(entry.id)}>Reopen</button>
            <button type="button" className="operational-link-button operational-link-button--danger" onClick={() => onDelete?.(entry.id)}>Delete</button>
          </div>
        </article>
      ))}
    </div>
  );
}

function formatHistoryTimestamp(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "Analysis saved";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
}
