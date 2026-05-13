import PanelSkeleton from "./PanelSkeleton";
import LoadingPulseBlock from "./LoadingPulseBlock";

export default function SystemBodySkeleton() {
  return (
    <section className="system-body--loading" aria-label="Loading system body">
      <div className="hero-panel system-body-orb-panel">
        <LoadingPulseBlock className="loading-orb" />
        <LoadingPulseBlock className="loading-line loading-line--sm" />
        <LoadingPulseBlock className="loading-line loading-line--lg" />
      </div>
      <PanelSkeleton />
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
