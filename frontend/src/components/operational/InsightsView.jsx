import { useEffect, useRef } from "react";

export default function InsightsView({ model, helpers, selectedInsight, onSelectInsight }) {
  const { InsightDetail, InsightList, PanelHeader } = helpers;
  const selectedDetailRef = useRef(null);

  useEffect(() => {
    if (!selectedInsight?.id || !selectedDetailRef.current) return;
    selectedDetailRef.current.scrollIntoView?.({ block: "start", behavior: "smooth" });
    selectedDetailRef.current.focus?.({ preventScroll: true });
  }, [selectedInsight?.id]);

  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label="Insights">
        <PanelHeader eyebrow="Insights" title="Operational Insights" subtitle="Prioritized system-level changes with evidence and recommended investigation." />
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No active operational insights were detected." : "Operational insights will appear after an Operational Fingerprint is established."}
          emptyTitle={model.analysisComplete ? "No active insights" : "No telemetry analyzed"}
          onOpenInsight={onSelectInsight}
          selectedId={selectedInsight?.id}
        />
        {selectedInsight ? (
          <div ref={selectedDetailRef} tabIndex={-1}>
            <InsightDetail insight={selectedInsight} />
          </div>
        ) : null}
      </section>
    </div>
  );
}
