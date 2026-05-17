import { DataTable, EmptyState, MetricGrid, Panel } from "../workspacePrimitives";

export default function DiagnosticsPanel({ latestUploadResult, uploadStateView, uploadHistoryRows }) {
  return (
    <Panel title="Diagnostics" className="span-12">
      <details className="technical-summary-panel">
        <summary>Show active result and upload history</summary>
        <MetricGrid
          metrics={[
            { label: "Score", value: latestUploadResult?.sii_intelligence?.neraium_score ?? "No Active Session" },
            { label: "State", value: latestUploadResult?.sii_intelligence?.facility_state ?? "No Active Session" },
            { label: "Drift", value: latestUploadResult?.sii_intelligence?.urgency ?? "No Active Session" },
            { label: "Timestamp", value: uploadStateView.deriveTimeCoverage(latestUploadResult).summary },
          ]}
          compact
        />
        <Panel title="Upload History" className="span-12">
          {uploadHistoryRows.length > 0 ? (
            <DataTable
              columns={["Result", "Status", "Score", "State", "Room", "Delta"]}
              rows={uploadHistoryRows.map((row) => [row.filename, row.status, row.score, row.state, row.room, row.scoreDelta ?? "Pending"])}
            />
          ) : (
            <EmptyState title="No ingestion history" body="Completed uploads and structural analysis sessions will appear here." compact />
          )}
        </Panel>
      </details>
    </Panel>
  );
}
