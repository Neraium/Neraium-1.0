import OperationalOrb from "./OperationalOrb";

export default function CommandCenterView({ model, helpers, onOpenInsight, onAnalyzeHistoricalData, onConnectLiveData, onResumePreviousSession, onViewSystems }) {
  const { EmptyOperationalState, PanelHeader, SummaryRows, Timeline, formatActiveInsightCount, formatInsightTitle, insightRelationshipLabels, operatorSummaryBriefing } = helpers;
  const primaryInsight = model.insights[0] ?? null;
  const systems = model.analysisComplete ? model.dashboardSystemCards : [];

  function reviewCurrentInsight() {
    if (primaryInsight) {
      onOpenInsight(primaryInsight.id);
      return;
    }
    if (model.analysisComplete) onViewSystems();
  }

  return (
    <div className="operational-grid operational-grid--dashboard">
      <section className="operational-panel operational-panel--command" aria-label="Command Center">
        <div className="command-center-hero">
          <OperationalOrb state={model.orb} />
          <div className="command-center-hero__copy">
            <span className="section-token">Neraium</span>
            <h2>{model.commandCenterTitle}</h2>
            <p>{model.commandCenterMessage}</p>
            <div className="operational-actions operational-actions--dashboard" aria-label="Primary actions">
              <button type="button" className="command-button" onClick={onAnalyzeHistoricalData} disabled={model.analyzeDisabled}>Analyze Historical Data</button>
              <button type="button" className="secondary-command-button" onClick={onConnectLiveData} disabled={model.analyzeDisabled}>Connect Live Data</button>
              {model.analysisComplete ? <button type="button" className="secondary-command-button" onClick={reviewCurrentInsight}>Review Current Insight</button> : null}
            </div>
            {model.canResumePrevious && typeof onResumePreviousSession === "function" ? (
              <button type="button" className="operational-dashboard-resume" onClick={onResumePreviousSession}>Resume Previous Analysis</button>
            ) : null}
          </div>
        </div>
      </section>

      <section className="operational-panel operational-panel--state" aria-label="Operational State">
        <PanelHeader eyebrow="Operational State" title="Current Operating Picture" subtitle="" />
        <SummaryRows rows={model.dashboardSummaryRows} />
      </section>

      <section className="operational-panel operational-panel--top-insight" aria-label="Top Operational Insight">
        <PanelHeader eyebrow="Top Insight" title="Operational Insight" subtitle="" />
        {primaryInsight ? (
          <div className="command-center-insight">
            <strong>{formatInsightTitle(primaryInsight)}</strong>
            <p>{operatorSummaryBriefing(primaryInsight, insightRelationshipLabels(primaryInsight))[0]}</p>
            <button type="button" className="secondary-command-button" onClick={() => onOpenInsight(primaryInsight.id)}>Open Insight</button>
          </div>
        ) : (
          <EmptyOperationalState title="No active operational insight" body={model.emptyInsightMessage} />
        )}
      </section>

      <section className="operational-panel operational-panel--dashboard-systems operational-panel--wide" aria-label="Systems requiring attention">
        {model.analysisComplete ? (
          <>
            <PanelHeader eyebrow="Systems" title="Systems Monitored" subtitle="" />
            <div className="systems-list systems-list--dashboard">
              {systems.map((system) => (
                <article className="system-summary-row system-summary-row--dashboard" key={system.id}>
                  <div>
                    <strong>{system.name}</strong>
                    <span>{system.status}</span>
                  </div>
                  <div className="system-summary-row__meta">
                    <strong>{formatActiveInsightCount(system.activeInsights)}</strong>
                    <span>{system.severity}</span>
                    <small>{system.keyChangedRelationship}</small>
                  </div>
                </article>
              ))}
            </div>
          </>
        ) : (
          <div className="systems-list systems-list--dashboard">
            <article className="system-summary-row system-summary-row--dashboard system-summary-row--awaiting-telemetry">
              <div>
                <strong>Systems Awaiting Discovery</strong>
                <span>Operational systems will automatically be identified after telemetry has been analyzed.</span>
              </div>
            </article>
          </div>
        )}
      </section>

      <section className="operational-panel operational-panel--recent-activity operational-panel--wide" aria-label="Recent Activity">
        <PanelHeader eyebrow="Recent Activity" title="Recent Operational Activity" subtitle="" />
        <Timeline items={model.dashboardActivityItems} />
      </section>
    </div>
  );
}
