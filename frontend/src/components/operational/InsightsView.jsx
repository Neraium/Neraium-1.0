import { useEffect, useRef } from "react";

import OperatorInsightDetail from "./OperatorInsightDetail";

export default function InsightsView({ model, helpers, selectedInsight, onSelectInsight }) {
  const { InsightList, PanelHeader } = helpers;
  const selectedDetailRef = useRef(null);

  useEffect(() => {
    if (!selectedInsight?.id || !selectedDetailRef.current) return;
    selectedDetailRef.current.scrollIntoView?.({ block: "start", behavior: "smooth" });
    selectedDetailRef.current.focus?.({ preventScroll: true });
  }, [selectedInsight?.id]);

  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label="Insights">
        <PanelHeader eyebrow="Insights" title="Operational Insights" subtitle="Prioritized operational changes requiring investigation." />
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No active operational insights were detected." : "Insights are generated automatically once an Operational Fingerprint has been established."}
          emptyTitle="No Operational Insights Yet"
          onOpenInsight={onSelectInsight}
          selectedId={selectedInsight?.id}
        />
        {selectedInsight ? (
          <div ref={selectedDetailRef} tabIndex={-1}>
            <OperatorInsightDetail insight={selectedInsight} />
          </div>
        ) : null}
      </section>
    </div>
  );
}
