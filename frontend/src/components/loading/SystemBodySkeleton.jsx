import PanelSkeleton from "./PanelSkeleton";
import LoadingPulseBlock from "./LoadingPulseBlock";

export default function SystemBodySkeleton() {
  return (
    <section className="system-body--loading" aria-label="Loading system body">
      <div className="hero-panel system-body-hero system-body-hero--loading">
        <div className="system-body-hero__copy">
          <div className="loading-panel loading-panel--hero">
            <LoadingPulseBlock className="loading-line loading-line--sm" />
            <LoadingPulseBlock className="loading-line loading-line--hero" />
            <LoadingPulseBlock className="loading-line loading-line--lg" />
            <LoadingPulseBlock className="loading-chip" />
          </div>
          <PanelSkeleton className="loading-panel--narrative" lines={5} />
        </div>
        <div className="system-body-orb-panel system-body-orb-panel--loading">
          <LoadingPulseBlock className="loading-orb" />
        </div>
      </div>
      <div className="layout-metric-grid system-body-metric-grid">
        <PanelSkeleton className="loading-panel--telemetry" />
        <PanelSkeleton className="loading-panel--telemetry" />
        <PanelSkeleton className="loading-panel--telemetry" />
        <PanelSkeleton className="loading-panel--telemetry" />
      </div>
      <div className="system-body-evidence-grid">
        <PanelSkeleton className="loading-panel--evidence" lines={4} />
        <PanelSkeleton className="loading-panel--evidence" lines={4} />
        <PanelSkeleton className="loading-panel--evidence" lines={4} />
      </div>
      <PanelSkeleton className="loading-panel--timeline" lines={4} />
    </section>
  );
}
