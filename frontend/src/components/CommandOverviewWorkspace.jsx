import * as uploadStateView from "../viewModels/uploadState";

export default function CommandOverviewWorkspace({
  Panel,
  MetricGrid,
  CompactList,
  InterventionGrid,
  WhyPanel,
  buildGuidanceForItem,
  formatFacilityPlainState,
  formatScoreReadiness,
  latestUploadSnapshot,
  liveOps,
  selectedInterventionId,
  onSelectIntervention,
  onNavigateWorkspace,
  operatorActions,
  onOperatorAction,
}) {
  const findings = liveOps.findings.slice(0, 3);
  const selectedRoom = liveOps.interventionItems.find((item) => item.id === selectedInterventionId) ?? liveOps.interventionItems[0];
  const primaryRoom = liveOps.primaryWindow ?? selectedRoom;
  const primaryGuidance = buildGuidanceForItem(primaryRoom);
  const heroHeadline = formatFacilityPlainState(liveOps.facilityTone, primaryRoom);
  const heroSubline = liveOps.heroSubline ?? "Neraium is monitoring the current facility state.";
  const uploadDiffSummary = uploadStateView.buildUploadDiffSummary(latestUploadSnapshot?.history ?? []);
  const inspectionFocus = primaryRoom?.label ?? selectedRoom?.label ?? "Facility overview";
  const nextMove = primaryRoom?.primaryAction ?? primaryRoom?.recommendation ?? "Continue monitoring";
  const evidenceItems = [
    primaryGuidance.primaryDriver,
    primaryGuidance.whyFlagged,
    ...(primaryRoom?.supportingEvidence ?? []),
    ...findings.map((finding) => finding.detail),
  ].filter(Boolean);
  const uniqueEvidenceItems = evidenceItems.filter((item, index, list) => list.indexOf(item) === index).slice(0, 5);

  return (
    <div className="workspace-grid workspace-grid--overview workspace-grid--overview-simple workspace-grid--operator-flow">
      <Panel
        title="Current Operating Condition"
        className="span-12 overview-panel overview-panel--hero overview-panel--command"
      >
        <div className="overview-hero">
          <div className="overview-hero__lead">
            <span className={`overview-pill overview-pill--${liveOps.facilityTone}`}>{liveOps.heroTag}</span>
            <h2 className="overview-hero__headline">{heroHeadline}</h2>
            <p>{heroSubline}</p>
          </div>

          <div className="operator-story">
            <div className="operator-story__item operator-story__item--score">
              <span>Severity</span>
              <strong>{liveOps.neraiumScore}</strong>
              <p>{formatScoreReadiness(liveOps.neraiumScore)}</p>
            </div>
            <div className="operator-story__item">
              <span>Decision window</span>
              <strong>{primaryRoom?.window ?? "Monitoring"}</strong>
              <p>{inspectionFocus}</p>
            </div>
            <div className="operator-story__item">
              <span>Inspect next</span>
              <strong>{inspectionFocus}</strong>
              <p>{nextMove}</p>
            </div>
          </div>

          <div className="operating-state-next">
            <span>Recommended operator move</span>
            <strong>{nextMove}</strong>
            <div className="operator-guidance-brief">
              <p><b>Why:</b> {primaryGuidance.primaryDriver}</p>
              <ul>
                {primaryGuidance.whatToCheck.slice(0, 3).map((check) => (
                  <li key={check}>{check}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </Panel>

      <Panel
        title="Inspection Priority"
        className="span-7 overview-panel overview-panel--rooms overview-panel--room-first"
      >
        <InterventionGrid
          items={liveOps.interventionItems}
          selectedId={selectedRoom?.id ?? null}
          onSelect={onSelectIntervention}
          compact
          limit={4}
        />
      </Panel>

      <Panel
        title="Why It Matters"
        className="span-5 overview-panel overview-panel--findings overview-panel--detail"
      >
        <WhyPanel
          item={selectedRoom}
          findings={findings}
          actionStatus={operatorActions[selectedRoom?.targetId ?? selectedRoom?.id]}
          onOperatorAction={onOperatorAction}
          compact
        />
      </Panel>

      <Panel
        title="What Changed"
        className="span-6 overview-panel overview-panel--detail overview-panel--change"
      >
        <CompactList items={uploadDiffSummary.lines} emptyText="No completed comparison yet. Upload or connect telemetry to establish the first change record." />
      </Panel>

      <Panel
        title="Evidence To Review"
        className="span-6 overview-panel overview-panel--detail overview-panel--evidence"
      >
        <CompactList items={uniqueEvidenceItems} emptyText="Evidence will appear after telemetry is connected or an upload completes." />
        <div className="room-first-actions">
          <button className="secondary-command-button" type="button" onClick={() => onNavigateWorkspace("facility-systems")}>
            Open System Detail
          </button>
          <button className="secondary-command-button" type="button" onClick={() => onNavigateWorkspace("intelligence-console")}>
            Open Evidence Console
          </button>
        </div>
      </Panel>

      <Panel
        title="Technical Diagnostics"
        className="span-12 overview-panel overview-panel--detail overview-panel--technical"
      >
        <details className="technical-summary-panel">
          <summary>Show raw status and source details</summary>
          <MetricGrid
            metrics={[
              { label: "Score Delta", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta ?? "n/a" },
              { label: "Tracked Rooms", value: liveOps.interventionItems.length },
              { label: "Drift Signals", value: findings.length },
              { label: "Data Source", value: liveOps.dataSourceLabel },
            ]}
            compact
          />
          <p>{liveOps.scoreContext}</p>
        </details>
      </Panel>
    </div>
  );
}
