import OperationalOrb from "./OperationalOrb";

function confidenceFallback(severity) {
  const text = String(severity ?? "").toLowerCase();
  if (text.includes("high") || text.includes("critical")) return "High";
  if (text.includes("moderate") || text.includes("review")) return "Moderate";
  return "Low";
}


function dashboardInsightTitle(insight, relationships, fallback) {
  const supplied = String(insight?.summary || insight?.rawSummary || fallback || "").trim();
  if (supplied && !/relationship\s+(changed|shifted)|behavior\s+changed/i.test(supplied)) return supplied;
  const relationshipContext = (relationships ?? []).join(" ").toLowerCase();
  const context = [insight?.system, insight?.rawSystemName, insight?.title, insight?.summary, relationshipContext].join(" ").toLowerCase();
  if (/pump.*(filter|pressure|flow)|filter.*(pump|pressure)|hydraulic/.test(context)) return "Pump Efficiency Degrading";
  if (/conductivity|chemical|chlor|dose|quality|ph|orp/.test(relationshipContext)) return "Water Quality Control Drift";
  if (/pump|vfd|hydraulic/.test(context)) return "Pump Efficiency Degrading";
  if (/(flow|pressure|dp|differential pressure|filter)/.test(relationshipContext)) return "Hydraulic Resistance Increasing";
  if (/cool|chill|tower|thermal|condenser/.test(context)) return "Heat Transfer Performance Degrading";
  return String(fallback ?? "Operating Behavior Changed").replace(/Relationship Changed/i, "Behavior Changed");
}

function FingerprintMark() {
  return (
    <svg className="fingerprint-summary-mark" viewBox="0 0 44 54" aria-hidden="true" focusable="false">
      <path d="M22 6c9 0 16 7 16 17 0 12-6 22-16 25" />
      <path d="M14 12c5-5 14-6 20-1 6 5 8 14 4 23" />
      <path d="M10 23c0-8 5-14 12-14 7 0 12 5 12 12 0 9-6 16-14 17" />
      <path d="M17 22c0-3 2-5 5-5s5 2 5 5c0 6-5 10-10 10" />
      <path d="M22 24c-1 6-4 11-9 14" />
    </svg>
  );
}
export default function CommandCenterView({ model, helpers, onOpenInsight, onAnalyzeHistoricalData, onConnectLiveData, onResumePreviousSession, onViewSystems, onViewFingerprint }) {
  const { EmptyOperationalState, PanelHeader, SummaryRows, Timeline, StatusBadge, formatActiveInsightCount, formatConfidenceDisplay, formatInsightTitle, insightRelationshipLabels, operatorSummaryBriefing, severityToTone } = helpers;
  const primaryInsight = model.insights[0] ?? null;
  const systems = model.analysisComplete ? model.dashboardSystemCards : [];
  const showHeroStatusChip = model.commandCenterStatus?.label && model.commandCenterStatus.label !== model.commandCenterTitle;
  const primaryInsightRelationships = primaryInsight ? insightRelationshipLabels(primaryInsight) : [];
  const primaryInsightBriefing = primaryInsight ? operatorSummaryBriefing(primaryInsight, primaryInsightRelationships) : [];
  const primaryInsightConfidence = primaryInsight
    ? (formatConfidenceDisplay(primaryInsight.confidence, primaryInsight.confidenceScore) || confidenceFallback(primaryInsight.severity))
    : "";
  const primaryInsightTitle = primaryInsight ? dashboardInsightTitle(primaryInsight, primaryInsightRelationships, formatInsightTitle(primaryInsight)) : "No Operational Insights Yet";
  const primaryObservedFacts = Array.isArray(primaryInsight?.observedFacts) ? primaryInsight.observedFacts.slice(0, 3) : [];
  const primaryFirstAction = primaryInsight?.recommendedFirstAction || primaryInsight?.recommendedAction || primaryInsight?.operatorCheck || "";

  function reviewCurrentInsight() {
    if (primaryInsight && typeof onOpenInsight === "function") {
      onOpenInsight(primaryInsight.id);
      return;
    }
    if (model.analysisComplete) onViewSystems();
  }

  return (
    <div className="operational-grid operational-grid--dashboard">
      <section className="operational-panel operational-panel--command" aria-label="Command Center">
        <div className="command-center-hero">
          <OperationalOrb
            state={model.orb}
            status={model.orb.status}
            hotspotCount={model.orb.hotspotCount}
            hotspots={model.orb.hotspots}
          />
          <div className="command-center-hero__copy">
            <span className="section-token">Operational Status</span>
            <h2>{model.commandCenterTitle}</h2>
            {showHeroStatusChip ? (
              <StatusBadge
                label={model.commandCenterStatus.label}
                tone={model.commandCenterStatus.tone}
                statusKey={model.commandCenterStatus.statusKey}
              />
            ) : null}
            <p>{model.commandCenterMessage}</p>
            <div className="operational-actions operational-actions--dashboard" aria-label="Primary actions">
              {model.analysisComplete ? (
                <button type="button" className="command-button" onClick={reviewCurrentInsight}>Review Insights</button>
              ) : (
                <button type="button" className="command-button" onClick={onAnalyzeHistoricalData} disabled={model.analyzeDisabled}>{model.primaryCtaLabel}</button>
              )}
              {model.analysisComplete ? (
                <button type="button" className="secondary-command-button" onClick={onAnalyzeHistoricalData} disabled={model.analyzeDisabled}>Analyze Dataset</button>
              ) : null}
              <button type="button" className="secondary-command-button secondary-command-button--outline" onClick={onConnectLiveData} disabled={model.analyzeDisabled}>Connect Live Telemetry</button>
            </div>
            {model.canResumePrevious && typeof onResumePreviousSession === "function" ? (
              <button type="button" className="operational-dashboard-resume" onClick={onResumePreviousSession}>Resume Previous Analysis</button>
            ) : null}
          </div>
        </div>
      </section>

      <section className="operational-panel operational-panel--state" aria-label="System Readiness">
        <PanelHeader eyebrow="Operational State" title="System Readiness" subtitle="" />
        <SummaryRows rows={model.dashboardSummaryRows} />
      </section>


      {model.analysisComplete ? (
        <section className="operational-panel operational-panel--fingerprint-summary" aria-label="Operational Fingerprint">
          <PanelHeader eyebrow="Operational Fingerprint" title="Established" subtitle="" />
          <div className="fingerprint-summary-card">
            <FingerprintMark />
            <SummaryRows rows={model.dashboardFingerprintRows} />
            <button type="button" className="secondary-command-button" onClick={onViewFingerprint}>View History</button>
          </div>
        </section>
      ) : null}

      <section className="operational-panel operational-panel--top-insight" aria-label="Top Operational Insight">
        <PanelHeader eyebrow="Highest Priority" title={primaryInsightTitle} subtitle="" />
        {primaryInsight ? (
          <div className="command-center-insight">
            <p>{primaryInsightBriefing[0] || "Operating behavior changed from the learned operating pattern."}</p>
            <dl className="top-insight-facts">
              <div>
                <dt>Confidence</dt>
                <dd>{primaryInsightConfidence}</dd>
              </div>
              <div>
                <dt>Severity</dt>
                <dd><span className={`severity-chip severity-chip--${severityToTone(primaryInsight.severity)}`}>{primaryInsight.severity}</span></dd>
              </div>
              {primaryFirstAction ? (
                <div>
                  <dt>First check</dt>
                  <dd>{primaryFirstAction}</dd>
                </div>
              ) : null}
            </dl>
            {primaryObservedFacts.length ? (
              <ul className="operator-briefing-list command-center-insight__observed">
                {primaryObservedFacts.map((fact) => <li key={fact}>{fact}</li>)}
              </ul>
            ) : null}
            <button type="button" className="secondary-command-button" onClick={() => onOpenInsight?.(primaryInsight.id)}>Open Insight</button>
          </div>
        ) : (
          <EmptyOperationalState title="No Operational Insights Yet" body={model.emptyInsightMessage} />
        )}
      </section>

      {!model.analysisComplete ? (
        <section className="operational-panel operational-panel--value-prop" aria-label="Operational Intelligence">
          <PanelHeader
            eyebrow="What Neraium Does"
            title="Operational Intelligence"
            subtitle="Neraium establishes a behavioral baseline from facility telemetry, automatically identifies operational systems, and detects changes in system behavior before traditional alarms indicate a problem."
          />
        </section>
      ) : null}

      <section className="operational-panel operational-panel--dashboard-systems operational-panel--wide" aria-label="Systems requiring attention">
        {model.analysisComplete ? (
          <>
            <PanelHeader eyebrow="Systems" title={model.systemsSectionTitle} subtitle="" />
            <div className="systems-list systems-list--dashboard">
              {systems.map((system) => (
                <article className="system-summary-row system-summary-row--dashboard" key={system.id}>
                  <div className="system-summary-row__primary">
                    <strong>{system.name}</strong>
                    <dl className="system-card-status">
                      <div>
                        <dt>Status</dt>
                        <dd>{system.status}</dd>
                      </div>
                      {system.hasActiveIssue ? (
                        <div>
                          <dt>Severity</dt>
                          <dd><span className={`severity-chip severity-chip--${severityToTone(system.severity)}`}>{system.severity}</span></dd>
                        </div>
                      ) : null}
                    </dl>
                  </div>
                  <div className="system-summary-row__meta">
                    <strong>{formatActiveInsightCount(system.activeInsights)}</strong>
                    <small>{system.recommendedFirstAction || system.operationalSummary}</small>
                  </div>
                </article>
              ))}
            </div>
          </>
        ) : (
          <div className="systems-list systems-list--dashboard">
            <article className="system-summary-row system-summary-row--dashboard system-summary-row--awaiting-telemetry">
              <div>
                <strong>{model.systemsSectionTitle}</strong>
                <span>{model.systemsSectionSubtitle}</span>
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
