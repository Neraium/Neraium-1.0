import React, { useEffect, useState } from "react";
import { fetchReplayTimeline } from "../services/api/replayApi";
import PropagationMap from "./PropagationMap";

export default function PropagationWorkspace({
  apiFetch,
  accessCode,
  isDemoMode,
  expertMode = false,
  Panel,
  EmptyState,
  normalizeErrorMessage,
}) {
  const [frame, setFrame] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const replay = await fetchReplayTimeline({
          apiFetch,
          accessCode,
          intervals: 24,
          mode: isDemoMode ? "demo" : "live",
        });
        if (cancelled) return;
        const activeFrame = (replay.timeline ?? [])[Math.max(0, (replay.timeline ?? []).length - 1)] ?? null;
        setFrame(activeFrame);
        setError("");
      } catch (loadError) {
        if (!cancelled) {
          setError(normalizeErrorMessage(loadError?.message ?? loadError));
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch, isDemoMode, normalizeErrorMessage]);

  if (error) {
    return <EmptyState title="Propagation workspace unavailable" body={error} />;
  }
  if (!frame) {
    return <Panel title="Propagation Map" subtitle="Loading active propagation pathway state." />;
  }

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel
        title="Propagation Map"
        className="span-12 workspace-hero-panel"
        subtitle="Where environmental pressure is spreading and where recovery is holding."
      >
        <PropagationMap frame={frame} />
      </Panel>
      <Panel title="Active Structural Changes" className="span-6">
        <ul className="system-body-timeline-list">
          {(frame?.propagation_state?.dominant_paths ?? []).map((path) => (
            <li key={path}>
              <span className="metadata-text">Spread pathway</span>
              <strong>{String(path).replaceAll("_", " -> ")}</strong>
            </li>
          ))}
          {(frame?.propagation_state?.dominant_paths ?? []).length === 0 && (
            <li>
              <span className="metadata-text">Spread pathway</span>
              <strong>No active propagation pathway.</strong>
            </li>
          )}
        </ul>
      </Panel>
      <Panel title="Operator Awareness" className="span-6">
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">System stability</span><strong>{frame?.topology_state?.stability_state ?? "Monitoring"}</strong></li>
          <li><span className="metadata-text">Recovery signal</span><strong>{frame?.propagation_state?.recovery_convergence ?? "Tracking"}</strong></li>
          <li><span className="metadata-text">Attention priority</span><strong>{frame?.propagation_state?.propagation_acceleration ?? "Watching"}</strong></li>
        </ul>
      </Panel>
      {expertMode ? (
        <Panel title="Technical propagation context" className="span-12">
          <ul className="system-body-timeline-list">
            <li><span className="metadata-text">Topology phase</span><strong>{frame?.topology_state?.phase ?? "n/a"}</strong></li>
            <li><span className="metadata-text">Fragmentation indicator</span><strong>{frame?.topology_state?.fragmentation_indicator ?? "n/a"}</strong></li>
            <li><span className="metadata-text">Propagation acceleration</span><strong>{frame?.propagation_state?.propagation_acceleration ?? "n/a"}</strong></li>
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}
