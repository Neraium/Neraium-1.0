export default function InsightsView({ model, helpers, selectedInsight, onSelectInsight }) {
  const { InsightList, PanelHeader } = helpers;
  return (
    <div className="operational-grid operational-grid--command-center">
      <section className="operational-panel operational-panel--wide" aria-label="Engineering Findings">
        <PanelHeader title="Engineering Findings" />
        <InsightList
          insights={model.insights}
          empty={model.analysisComplete ? "No new unexplained system changes." : "Import telemetry to establish the baseline."}
          emptyTitle={model.analysisComplete ? "No active findings" : "Analysis required"}
          onOpenInsight={onSelectInsight}
          selectedId={selectedInsight?.id}
        />
      </section>
    </div>
  );
}
