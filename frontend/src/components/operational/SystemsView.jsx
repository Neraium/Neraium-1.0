export default function SystemsView({ model, helpers, onOpenInsight }) {
  const { DetailGrid, EmptyOperationalState, PanelHeader } = helpers;
  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label={model.systemsSectionTitle}>
        <PanelHeader title={model.systemsSectionTitle} />
        {model.systemCards.length ? (
          <div className="systems-list systems-list--systems-view">
            {model.systemCards.map((system) => (
              <article className="system-summary-row system-summary-row--systems-view" key={system.id}>
                <div className="system-summary-row__main">
                  <div className="system-summary-row__heading">
                    <strong>{system.name}</strong>
                    <span>{system.status}</span>
                  </div>
                  {system.placeholder ? <small>Expected example, not detected</small> : null}
                  <DetailGrid rows={[
                    ["Active findings", system.activeInsights],
                    ["Next check", system.recommendedFirstAction],
                  ]} />
                  <details className="system-summary-row__details">
                    <summary>System evidence</summary>
                    <DetailGrid rows={[
                      ["Scope", system.scope],
                      ["Primary finding", system.primaryFinding],
                      ["Changed relationship", system.keyChangedRelationship],
                    ]} />
                    {Array.isArray(system.potentialCauses) && system.potentialCauses.length ? (
                      <div className="system-summary-row__briefing"><span>Alternative explanations</span><ul className="operator-briefing-list">{system.potentialCauses.map((cause) => <li key={cause}>{cause}</li>)}</ul></div>
                    ) : null}
                    {Array.isArray(system.observedFacts) && system.observedFacts.length ? (
                      <div className="system-summary-row__briefing"><span>Supporting evidence</span><ul className="operator-briefing-list">{system.observedFacts.map((fact) => <li key={fact}>{fact}</li>)}</ul></div>
                    ) : null}
                  </details>
                </div>
                {system.primaryInsightId && typeof onOpenInsight === "function" ? (
                  <button type="button" className="system-summary-row__action" onClick={() => onOpenInsight(system.primaryInsightId)}>Review finding</button>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyOperationalState title="No systems detected" body="Import telemetry to establish system ownership." />
        )}
      </section>
    </div>
  );
}
