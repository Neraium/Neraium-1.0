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
          empty={model.analysisComplete ? "Analysis completed and no relationships are outside the learned baseline. Import a newer dataset when the next operating period is ready." : "No completed telemetry analysis exists yet. Import a dataset to establish the baseline and generate evidence-backed insights."}
          emptyTitle={model.analysisComplete ? "No active findings" : "Analysis required"}
          onOpenInsight={onSelectInsight}
          selectedId={selectedInsight?.id}
          renderInsightDetail={(insight) => <OperatorInsightDetail insight={insight} defaultOpen />}
        />
      </section>
    </div>
  );
}
