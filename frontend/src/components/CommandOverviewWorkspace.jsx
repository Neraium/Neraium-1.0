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

  return (
    <div className="workspace-grid workspace-grid--overview workspace-grid--overview-simple workspace-grid--operator-flow">
      <Panel
        title="Operating State"
        className="span-12 overview-panel overview-panel--hero overview-panel--command"
      >
        <div className="overview-hero">
          <div className="overview-hero__lead">
            <span className={`overview-pill overview-pill--${liveOps.facilityTone}`}>{liveOps.heroTag}</span>
            <h2 className="overview-hero__headline">{heroHeadline}</h2>
            <p>{heroSubline}</p>
          </div>

          <div className="countdown-hero">
            <div className="countdown-hero__score">
              <span>Neraium Score</span>
              <strong>{liveOps.neraiumScore}</strong>
              <p className="countdown-hero__readiness">{formatScoreReadiness(liveOps.neraiumScore)}</p>
              <p className="countdown-hero__context">{liveOps.scoreContext}</p>
            </div>
            <div className="countdown-hero__window">
              <span>Window</span>
              <strong>{primaryRoom?.window ?? "Monitoring"}</strong>
              <p>{primaryRoom?.label ?? "The facility"} before intervention.</p>
              <p className="countdown-hero__context">{primaryRoom?.primaryAction ?? primaryRoom?.recommendation ?? "Continue monitoring"}</p>
            </div>
          </div>

          <div className="operating-state-next">
            <span>Next Move</span>
            <strong>{primaryRoom?.primaryAction ?? primaryRoom?.recommendation ?? "Continue monitoring"}</strong>
            <div className="operator-guidance-brief">
              <p><b>Primary driver:</b> {primaryGuidance.primaryDriver}</p>
              <p><b>Why flagged:</b> {primaryGuidance.whyFlagged}</p>
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
        title="Rooms"
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
        title="Operator Focus"
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
        title="Change Summary"
        className="span-12 overview-panel overview-panel--detail overview-panel--technical"
      >
        <MetricGrid
          metrics={[
            { label: "Score Delta", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta ?? "n/a" },
            { label: "Tracked Rooms", value: liveOps.interventionItems.length },
            { label: "Drift Signals", value: findings.length },
            { label: "Data Source", value: liveOps.dataSourceLabel },
          ]}
          compact
        />
        <CompactList items={uploadDiffSummary.lines} emptyText="Upload two files to compare changes." />

        <div className="room-first-actions">
          <button className="secondary-command-button" type="button" onClick={() => onNavigateWorkspace("facility-systems")}>
            System Detail
          </button>
          <button className="secondary-command-button" type="button" onClick={() => onNavigateWorkspace("intelligence-console")}>
            Evidence
          </button>
        </div>
      </Panel>
    </div>
  );
}
