import OperatorInsightDetail from "./OperatorInsightDetail";
import OperationalOrb from "./OperationalOrb";

export default function InsightsView({ model, helpers, selectedInsight, onSelectInsight }) {
  const { InsightList, PanelHeader } = helpers;
  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label="Insights">
        <div className="operational-view-identity">
          <PanelHeader eyebrow="Insights" title="Operational Insights" subtitle="Prioritized operational changes requiring investigation." />
          <OperationalOrb state={model.orb} status={model.orb.status} minimal hideVisualLabel />
        </div>
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No active operational insights were detected." : "Insights are generated automatically once a learned operational baseline has been established."}
          emptyTitle="No Operational Insights Yet"
          onOpenInsight={onSelectInsight}
          selectedId={selectedInsight?.id}
          renderInsightDetail={(insight) => <OperatorInsightDetail insight={insight} defaultOpen />}
        />
      </section>
    </div>
  );
}
