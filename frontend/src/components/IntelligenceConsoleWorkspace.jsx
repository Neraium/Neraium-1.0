import {
  DriftFeed,
  EngineIdentityPanel,
  Panel,
  RelationshipMonitor,
  TimelineFeed,
} from "./workspacePrimitives";

export default function IntelligenceConsoleWorkspace({
  latestUploadResult,
  liveOps,
  engineIdentity,
  intelligenceStatus,
  formatRelationshipPair,
  relationshipDetail,
  relationshipConsistencyLabel,
  runnerTraceLines,
  processingTraceLines,
}) {
  const driftRows = liveOps.driftRows;
  const relationshipRows = liveOps.relationshipRows;
  const timeline = liveOps.timeline;

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Room Trend Feed" className="span-6 workspace-hero-panel">
        <DriftFeed rows={driftRows} />
      </Panel>

      <Panel title="Relationship Shifts" className="span-3">
        <RelationshipMonitor
          rows={relationshipRows}
          formatRelationshipPair={formatRelationshipPair}
          relationshipDetail={relationshipDetail}
          relationshipConsistencyLabel={relationshipConsistencyLabel}
        />
      </Panel>

      <Panel title="Recent Changes" className="span-3">
        <TimelineFeed items={timeline} />
      </Panel>

      <Panel title="Engine Identity" className="span-12">
        <EngineIdentityPanel
          identity={engineIdentity}
          latestUploadResult={latestUploadResult}
          intelligenceStatus={intelligenceStatus}
          runnerTraceLines={runnerTraceLines}
          processingTraceLines={processingTraceLines}
        />
      </Panel>
    </div>
  );
}
