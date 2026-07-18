import OperationalOrb from "./OperationalOrb";

export default function FingerprintView({ model, helpers }) {
  const { DetailGrid, EmptyOperationalState, PanelHeader, QualityList } = helpers;
  return (
    <div className="operational-grid operational-grid--overview">
      <section className="operational-panel operational-panel--wide" aria-label="Behavior Baseline">
        <div className="operational-view-identity operational-view-identity--fingerprint">
          <PanelHeader eyebrow="Behavior Baseline" title="Behavior Baseline" subtitle="Current operating pattern." />
          <OperationalOrb state={model.orb} status={model.orb.status} minimal hideVisualLabel />
        </div>
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
        <PanelHeader eyebrow="Relationship Changes" title="What changed" subtitle="" />
        {model.relationshipChangeRows.length ? (
          <QualityList title="Changed relationships" items={model.relationshipChangeRows} empty="" />
        ) : (
          <EmptyOperationalState title="No relationship changes" body={model.analysisComplete ? "No material relationship changes." : "Import telemetry to establish the baseline."} />
        )}
      </section>
    </div>
  );
}
