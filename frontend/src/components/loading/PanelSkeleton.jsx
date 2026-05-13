import LoadingPulseBlock from "./LoadingPulseBlock";

export default function PanelSkeleton() {
  return (
    <div className="section-card loading-panel" aria-label="Loading panel">
      <LoadingPulseBlock className="loading-line loading-line--sm" />
      <LoadingPulseBlock className="loading-line loading-line--lg" />
      <LoadingPulseBlock className="loading-line" />
    </div>
  );
}
