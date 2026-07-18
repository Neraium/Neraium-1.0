import OperatorInsightDetail from "./OperatorInsightDetail";
import OperationalOrb from "./OperationalOrb";

export default function InsightsView({ model, helpers, selectedInsight, onSelectInsight }) {
  const { InsightList, PanelHeader } = helpers;
  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label="Insights">
        <div className="operational-view-identity">
          <PanelHeader eyebrow="Insights" title="Operational Insights" subtitle="Highest priority first." />
          <OperationalOrb state={model.orb} status={model.orb.status} minimal hideVisualLabel />
        </div>
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No active insights." : "Import telemetry to establish the baseline."}
          emptyTitle="No insights yet"
          onOpenInsight={onSelectInsight}
          selectedId={selectedInsight?.id}
          renderInsightDetail={(insight) => <OperatorInsightDetail insight={insight} defaultOpen />}
        />
      </section>
    </div>
  );
}
