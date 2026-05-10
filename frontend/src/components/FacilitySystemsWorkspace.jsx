import {
  CompactList,
  DriftMonitor,
  FleetSummary,
  Panel,
  SystemsMatrix,
  TargetSelector,
  TelemetryCardGrid,
} from "./workspacePrimitives";

export default function FacilitySystemsWorkspace({
  systems,
  systemsState,
  roomContext,
  liveOps,
  selectedInterventionId,
  onSelectIntervention,
  buildFleetSummary,
  buildGuidanceForItem,
  formatOperationalTone,
  systemRoomContext,
}) {
  const telemetryCards = liveOps.telemetryCards;
  const driftRows = liveOps.driftRows;
  const irrigationPanel = telemetryCards.find((card) => card.label === "Irrigation") ?? null;
  const systemsFocus = liveOps.interventionItems.find((item) => item.id === selectedInterventionId) ?? liveOps.interventionItems[0] ?? null;
  const fleetSummary = buildFleetSummary(liveOps.interventionItems, liveOps.neraiumScore, liveOps.facilityTone);

  return (
    <div className="workspace-grid workspace-grid--systems">
      <Panel title="Facility Overview" className="span-8">
        <FleetSummary summary={fleetSummary} />
      </Panel>

      <Panel title="Rooms to Review" className="span-4">
        <TargetSelector
          items={liveOps.interventionItems}
          selectedId={systemsFocus?.id ?? null}
          onSelect={onSelectIntervention}
          buildGuidanceForItem={buildGuidanceForItem}
        />
      </Panel>

      <Panel title="Room Drivers" className="span-8">
        <TelemetryCardGrid cards={telemetryCards.slice(0, 6)} formatOperationalTone={formatOperationalTone} />
      </Panel>

      <Panel title="Room Trends" className="span-6">
        <DriftMonitor rows={driftRows} />
      </Panel>

      <Panel title="Irrigation" className="span-6">
        <TelemetryCardGrid cards={irrigationPanel ? [irrigationPanel] : []} compact formatOperationalTone={formatOperationalTone} />
        <CompactList items={liveOps.irrigationNotes} emptyText="Awaiting additional room telemetry." />
      </Panel>

      <Panel title="Systems in Scope" className="span-12">
        <SystemsMatrix
          systems={systems}
          systemsState={systemsState}
          roomContext={roomContext}
          rows={liveOps.systemRows}
          systemRoomContext={systemRoomContext}
        />
      </Panel>
    </div>
  );
}
