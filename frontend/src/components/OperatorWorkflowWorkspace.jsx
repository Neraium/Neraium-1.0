import React, { useEffect, useState } from "react";
import { fetchCanonicalCognitionState } from "../services/api/cognitionApi";
import StructuralReplayWorkspace from "./StructuralReplayWorkspace";
import EvidenceLineagePanel from "./EvidenceLineagePanel";

export default function OperatorWorkflowWorkspace({
  apiFetch,
  accessCode,
  Panel,
  EmptyState,
  MetricGrid,
  formatClockTime,
  normalizeErrorMessage,
}) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const result = await fetchCanonicalCognitionState({
          apiFetch,
          accessCode,
        });
        if (!cancelled) {
          setPayload(result);
          setError("");
        }
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
  }, [accessCode, apiFetch, normalizeErrorMessage]);

  if (error) {
    return <EmptyState title="Cognition state unavailable" body={error} />;
  }
  if (!payload) {
    return <Panel title="Current Cognition State" subtitle="Loading canonical structural cognition contract." />;
  }

  const summaryMetrics = [
    { label: "Cognition State", value: payload.cognition_state ?? "Monitoring" },
    { label: "Structural Stability", value: payload.structural_stability ?? "WATCH" },
    { label: "Active Archetypes", value: (payload.active_archetypes ?? []).length || 0 },
    { label: "Propagation Pathways", value: (payload.propagation_pathways ?? []).length || 0 },
    { label: "Replay Frames", value: payload.replay_summary?.frame_count ?? 0 },
    { label: "Source", value: payload.source_mode ?? "live" },
  ];

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Current Cognition State" className="span-12 workspace-hero-panel" subtitle="Operator workflow: state -> replay -> propagation -> evidence -> memory -> continuation -> convergence -> review">
        <MetricGrid metrics={summaryMetrics} />
        <p className="narrative-text">{payload.operator_explanation}</p>
      </Panel>

      <Panel title="Active Propagation Pathway" className="span-6">
        <ul className="system-body-timeline-list">
          {(payload.propagation_pathways ?? []).map((path) => (
            <li key={path}>
              <span className="metadata-text">Pathway</span>
              <strong>{String(path)}</strong>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Structural Memory Match" className="span-6">
        <ul className="system-body-timeline-list">
          {(payload.structural_memory_matches ?? []).slice(0, 4).map((match) => (
            <li key={match.fingerprint_id ?? match.label}>
              <span className="metadata-text">{match.confidence_band ?? "confidence band"}</span>
              <strong>{match.label ?? match.fingerprint_id ?? "memory match"}</strong>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Continuation Window" className="span-6">
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">Window</span><strong>{payload.continuation_windows?.window ?? "Monitoring"}</strong></li>
          <li><span className="metadata-text">Pathways</span><strong>{(payload.continuation_windows?.structural_pathways ?? []).join(" | ") || "developing"}</strong></li>
        </ul>
      </Panel>

      <Panel title="Recovery / Convergence State" className="span-6">
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">Convergence quality</span><strong>{payload.recovery_convergence?.convergence_quality ?? "developing"}</strong></li>
          <li><span className="metadata-text">Stabilization progression</span><strong>{payload.recovery_convergence?.stabilization_progression ?? "tracking"}</strong></li>
        </ul>
      </Panel>

      <Panel title="Evidence Lineage" className="span-12">
        <EvidenceLineagePanel lineage={payload.evidence_lineage} />
      </Panel>

      <StructuralReplayWorkspace
        apiFetch={apiFetch}
        accessCode={accessCode}
        normalizeErrorMessage={normalizeErrorMessage}
        formatClockTime={formatClockTime}
        Panel={Panel}
        MetricGrid={MetricGrid}
        EmptyState={EmptyState}
        mode="live"
      />
    </div>
  );
}
