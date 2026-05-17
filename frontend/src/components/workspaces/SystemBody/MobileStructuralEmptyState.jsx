import React from "react";
import SystemOrbPanel from "./SystemOrbPanel";

export default function MobileStructuralEmptyState({ lifecycleRail = [] }) {
  const chips = lifecycleRail.length > 0
    ? lifecycleRail
    : [
        { label: "Intake", status: "-" },
        { label: "Baseline", status: "-" },
        { label: "Monitoring", status: "-" },
        { label: "Drift", status: "-" },
        { label: "Review", status: "-" },
      ];

  function goToUploadWorkspace() {
    if (typeof window === "undefined") return;
    const next = new URL(window.location.href);
    next.searchParams.set("workspace", "data-connections");
    window.location.assign(next.toString());
  }

  return (
    <section className="system-body-mobile-empty" aria-label="Structural State empty view">
      <div className="system-status-rail" aria-label="Operational lifecycle status rail">
        {chips.map((item) => (
          <article className="system-status-rail__item" key={item.label}>
            <span>{item.label}</span>
            <strong>{item.status}</strong>
          </article>
        ))}
      </div>

      <header className="system-body-mobile-empty__header">
        <p className="workspace-header__kicker">Primary System State</p>
        <h2 className="workspace-header__title">No active analysis</h2>
        <p className="workspace-header__subtitle">
          Upload telemetry or connect a historian source to begin structural analysis.
        </p>
      </header>

      <button type="button" className="command-button system-body-mobile-empty__cta" onClick={goToUploadWorkspace}>
        Upload Data
      </button>

      <div className="system-body-mobile-empty__orb-preview">
        <SystemOrbPanel
          systemState="unknown"
          uiState="neutral"
          coherence={1}
          stateLabel="No active analysis"
          lastUpdate=""
          focusLabel=""
          compactPreview
        />
      </div>
    </section>
  );
}
