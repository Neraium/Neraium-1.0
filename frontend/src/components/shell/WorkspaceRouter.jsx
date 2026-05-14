import React from 'react';
import SystemTopologyWorkspace from '../SystemTopologyWorkspace';
import DriftTimelineWorkspace from '../DriftTimelineWorkspace';
import EvidenceConsoleWorkspace from '../EvidenceConsoleWorkspace';
import DataConnectionsWorkspace from '../DataConnectionsWorkspace';
import StructuralReplayWorkspace from '../StructuralReplayWorkspace';
import FleetWorkspace from '../FleetWorkspace';
import EcosystemWorkspace from '../EcosystemWorkspace';

export default function WorkspaceRouter(props) {
  const {
    activeWorkspace,
    liveOps,
    selectedTopologyTarget,
    setSelectedTopologyTarget,
    driftHistory,
    autoReplay,
    dataConnectionsProps,
    evidenceTrailProps,
    fleetProps,
    ecosystemProps,
  } = props;

  if (activeWorkspace === 'system-body') {
    return <SystemTopologyWorkspace liveOps={liveOps} selectedTarget={selectedTopologyTarget} onSelectTarget={setSelectedTopologyTarget} />;
  }
  if (activeWorkspace === 'drift-timeline') {
    return <DriftTimelineWorkspace liveOps={liveOps} driftHistory={driftHistory} autoReplay={autoReplay} />;
  }
  if (activeWorkspace === 'data-connections') {
    return <DataConnectionsWorkspace {...dataConnectionsProps} />;
  }
  if (activeWorkspace === 'historical-replay') {
    return <StructuralReplayWorkspace {...evidenceTrailProps} />;
  }
  if (activeWorkspace === 'fleet-view') {
    return <FleetWorkspace {...fleetProps} />;
  }
  if (activeWorkspace === 'ecosystem-workspace') {
    return <EcosystemWorkspace {...ecosystemProps} />;
  }
  return <EvidenceConsoleWorkspace liveOps={liveOps} selectedTarget={selectedTopologyTarget} />;
}
