export default function SystemsView({ model, helpers, onOpenInsight }) {
  const { DetailGrid, EmptyOperationalState, PanelHeader } = helpers;
  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label={model.systemsSectionTitle}>
        <PanelHeader eyebrow="Systems" title={model.systemsSectionTitle} subtitle={model.systemsSectionSubtitle} />
        {model.systemCards.length ? (
          <div className="systems-list systems-list--systems-view">
            {model.systemCards.map((system) => (
              <article className="system-summary-row system-summary-row--systems-view" key={system.id}>
                <div>
                  <div className="system-summary-row__heading">
                    <strong>{system.name}</strong>
                  </div>
                  {system.placeholder ? <small>Expected resort domain example, not a detected system</small> : null}
                  <p>{system.scope}</p>
                  <DetailGrid rows={[
                    ["Status", system.status],
                    ["Active Insights", system.activeInsights],
                    ["Primary Insight", system.primaryFinding],
                    ["Recommended First Action", system.recommendedFirstAction],
                    ["Key Changed Relationship", system.keyChangedRelationship],
                  ]} />
                  {Array.isArray(system.potentialCauses) && system.potentialCauses.length ? (
                    <div className="system-summary-row__briefing">
                      <span>Potential causes</span>
                      <ul className="operator-briefing-list">
                        {system.potentialCauses.map((cause) => <li key={cause}>{cause}</li>)}
                      </ul>
                    </div>
                  ) : null}
                  {Array.isArray(system.observedFacts) && system.observedFacts.length ? (
                    <div className="system-summary-row__briefing">
                      <span>Observed</span>
                      <ul className="operator-briefing-list">
                        {system.observedFacts.map((fact) => <li key={fact}>{fact}</li>)}
                      </ul>
                    </div>
                  ) : null}
                </div>
                <div className="system-summary-row__meta">
                  <span>{system.placeholder ? "Example, not detected" : system.severity}</span>
                  {system.primaryInsightId && typeof onOpenInsight === "function" ? (
                    <button type="button" className="system-summary-row__action" onClick={() => onOpenInsight(system.primaryInsightId)}>Open Insight</button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyOperationalState title={model.systemsSectionTitle} body={model.systemsSectionSubtitle} />
        )}
      </section>
    </div>
  );
}
