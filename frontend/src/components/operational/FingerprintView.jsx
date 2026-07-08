export default function FingerprintView({ model, helpers }) {
  const { DetailGrid, EmptyOperationalState, PanelHeader, QualityList } = helpers;
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--wide" aria-label="Operational Fingerprint">
        <PanelHeader eyebrow="Operational Fingerprint" title="Operational Fingerprint" subtitle="A learned baseline of how operational systems normally behave together." />
        <div className={`fingerprint-status fingerprint-status--${model.fingerprintDrift.tone}`}>
          <strong>{model.fingerprintStatusLabel}</strong>
          <p>{model.fingerprintSummary}</p>
        </div>
        <div className="operator-interpretation__columns">
          <div className="operator-interpretation__block">
            <h3>Behavior Windows</h3>
            <DetailGrid rows={model.behaviorWindowRows} />
          </div>
          <div className="operator-interpretation__block">
            <h3>Drift Status</h3>
            <DetailGrid rows={model.fingerprintRows} />
          </div>
        </div>
      </section>
      <section className="operational-panel operational-panel--wide" aria-label="Relationship Changes">
        <PanelHeader eyebrow="Relationship Changes" title="System Relationship Changes" subtitle="" />
        {model.relationshipChangeRows.length ? (
          <QualityList title="Changed relationships" items={model.relationshipChangeRows} empty="" />
        ) : (
          <EmptyOperationalState title="No relationship changes available" body={model.analysisComplete ? "No material relationship drift was reported." : "Relationship changes will appear after an Operational Fingerprint is established."} />
        )}
      </section>
    </div>
  );
}
