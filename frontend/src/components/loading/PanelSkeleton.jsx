import LoadingPulseBlock from "./LoadingPulseBlock";

export default function PanelSkeleton({ className = "", lines = 3 }) {
  const classes = `section-card loading-panel ${className}`.trim();

  return (
    <div className={classes} aria-label="Loading panel">
      <LoadingPulseBlock className="loading-line loading-line--sm" />
      <LoadingPulseBlock className="loading-line loading-line--lg" />
      {Array.from({ length: Math.max(lines - 2, 0) }).map((_, index) => (
        <LoadingPulseBlock className="loading-line" key={index} />
      ))}
    </div>
  );
}
