import PanelSkeleton from "./PanelSkeleton";
import LoadingPulseBlock from "./LoadingPulseBlock";

export default function SystemBodySkeleton() {
  return (
    <section className="system-body--loading" aria-label="Loading system body">
      <div className="hero-panel system-body-hero system-body-hero--loading">
        <div className="system-body-hero__copy">
          <div className="loading-panel">
            <LoadingPulseBlock className="loading-line loading-line--sm" />
            <LoadingPulseBlock className="loading-line loading-line--lg" />
            <LoadingPulseBlock className="loading-line" />
          </div>
          <PanelSkeleton />
        </div>
        <div className="system-body-orb-panel">
          <LoadingPulseBlock className="loading-orb" />
        </div>
      </div>
      <div className="layout-metric-grid system-body-metric-grid">
        <PanelSkeleton />
        <PanelSkeleton />
        <PanelSkeleton />
        <PanelSkeleton />
      </div>
      <div className="system-body-evidence-grid">
        <PanelSkeleton />
        <PanelSkeleton />
        <PanelSkeleton />
      </div>
    </section>
  );
}
