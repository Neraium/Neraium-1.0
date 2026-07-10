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
                  <strong>{system.name}</strong>
                  {system.placeholder ? <small>Expected resort domain example, not a detected system</small> : null}
                  <p>{system.scope}</p>
                  <DetailGrid rows={[
                    ["Status", system.status],
                    ["Active Insights", system.activeInsights],
                    ["Relationship Drift", system.relationshipDrift],
                    ["Key Changed Relationship", system.keyChangedRelationship],
                  ]} />
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
