import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import SystemOrbPanel from "./SystemOrbPanel";
import PageContainer from "../../layout/PageContainer";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";

export default function SystemBodyWorkspace({
  systemState,
  uiState,
  coherence,
  stateLabel,
  subtitle,
  connectionStatus,
  connectionTone,
  dataFreshness = null,
  siiVerification = null,
  primaryMessage,
  lastUpdate,
  focusLabel,
  orbData = null,
  statusLight = "gray",
  governedDetail = null,
  onWorkspaceNavigate = null,
  isLoading = false,
  isEmptyStructuralState = false,
  latestUploadSnapshot = null,
  latestUploadResult = null,
  liveSnapshot = null,
  latestReplayFrame = null,
  canonicalFinding = null,
}) {
  void dataFreshness;
  void siiVerification;

  const [menuOpen, setMenuOpen] = useState(false);
  const resolvedStatusLight = statusLight === "red" || statusLight === "amber" ? "yellow" : statusLight;

  const interpretation = useMemo(() => {
    const backendSystemInterpretation = latestUploadSnapshot?.system_interpretation;
    const mappedBackendInterpretation = mapBackendSystemInterpretation(backendSystemInterpretation);
    if (mappedBackendInterpretation) {
      return mappedBackendInterpretation;
    }
    return buildSystemInterpretation({
      latestUploadSnapshot,
      latestUploadResult,
      liveSnapshot,
      latestReplayFrame,
      fallback: {
        stateLabel,
        primaryMessage,
        focusLabel,
        statusLight: resolvedStatusLight,
        subtitle,
        lastUpdate,
        isLoading,
        isEmptyStructuralState,
        governedDetail,
        connectionTone,
        connectionStatus,
      },
    });
  },
    [
      latestUploadSnapshot,
      latestUploadResult,
      liveSnapshot,
      latestReplayFrame,
      stateLabel,
      primaryMessage,
      focusLabel,
      resolvedStatusLight,
      subtitle,
      lastUpdate,
      isLoading,
      isEmptyStructuralState,
      governedDetail,
      connectionTone,
      connectionStatus,
    ],
  );
  const heartbeat = heartbeatStatus(connectionTone, connectionStatus, lastUpdate, interpretation.hasTelemetry);
  const stabilitySnapshot = useMemo(
    () => buildStabilitySnapshot({ latestUploadSnapshot, latestUploadResult, latestReplayFrame }),
    [latestReplayFrame, latestUploadResult, latestUploadSnapshot],
  );
  const dataConditions = useMemo(
    () => collectDataConditions(latestUploadResult),
    [latestUploadResult],
  );
  const finding = canonicalFinding ?? buildFallbackFinding(interpretation, stabilitySnapshot, dataConditions);
  const findingDataQuality = flattenDataQuality(finding.dataQuality);

  function navigateWorkspace(workspaceId) {
    if (typeof onWorkspaceNavigate === "function") {
      onWorkspaceNavigate(workspaceId);
    }
    setMenuOpen(false);
  }

  useEffect(() => {
    if (!menuOpen || typeof document === "undefined") {
      return undefined;
    }

    const { body, documentElement } = document;
    const previousBodyOverflow = body.style.overflow;
    const previousDocumentOverflow = documentElement.style.overflow;

    body.classList.add("views-overlay-open");
    documentElement.classList.add("views-overlay-open");
    body.style.overflow = "hidden";
    documentElement.style.overflow = "hidden";

    return () => {
      body.classList.remove("views-overlay-open");
      documentElement.classList.remove("views-overlay-open");
      body.style.overflow = previousBodyOverflow;
      documentElement.style.overflow = previousDocumentOverflow;
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen || typeof window === "undefined") {
      return undefined;
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [menuOpen]);

  const menuOverlay = menuOpen && typeof document !== "undefined"
    ? createPortal(
      <div
        className="system-gate__settings-overlay"
        data-testid="views-overlay"
        onClick={() => setMenuOpen(false)}
      >
        <aside
          id="system-body-menu"
          className="system-gate__settings-panel"
          aria-label="System body navigation menu"
          aria-modal="true"
          role="dialog"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="system-gate__settings-panel-header">
            <p className="system-gate__settings-panel-title">Views</p>
            <button
              type="button"
              className="system-gate__settings-close"
              aria-label="Close workspace menu"
              onClick={() => setMenuOpen(false)}
            >
              Close
            </button>
          </div>
          <ul>
            <li>
              <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("data-connections")}>
                Upload CSV / Connect Data
              </button>
            </li>
            <li>
              <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("data-connections")}>
                Connect API
              </button>
            </li>
            <li>
              <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("historical-replay")}>
                Structural Replay
              </button>
            </li>
            <li>
              <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("observation-center")}>
                Observation Review
              </button>
            </li>
            <li>
              <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("help-changelog")}>
                Help / Changelog
              </button>
            </li>
          </ul>
        </aside>
      </div>,
      document.body,
    )
    : null;

  return (
    <PageContainer className="system-body system-body--gate">
      <section className={`system-gate system-gate--${resolvedStatusLight} ui-state-surface ui-state-surface--${uiState}`} aria-label="System interpretation view">
        <div className={`system-gate__heartbeat system-gate__heartbeat--${heartbeat.tone}`} aria-label={`Neraium platform status: ${heartbeat.label}`}>
          <span className="system-gate__heartbeat-dot" />
          <strong>{heartbeat.label}</strong>
        </div>

        <button
          type="button"
          className="system-gate__settings"
          aria-label="Open workspace menu"
          aria-expanded={menuOpen}
          aria-controls="system-body-menu"
          onClick={() => setMenuOpen((v) => !v)}
        >
          Views
        </button>

        <div className="system-gate__layout">
          <div className="system-gate__column system-gate__column--left">
            <section className="panel system-gate__plate system-gate__plate--summary" aria-label="System body home summary">
              <div className="panel-body">
                <ul className="onboarding-summary">
                  <li><span>Current Status</span><strong>{finding.status}</strong></li>
                  <li><span>Evidence Confidence</span><strong>{finding.confidence}</strong></li>
                  <li><span>Observation Summary</span><strong>{finding.summary}</strong></li>
                </ul>
              </div>
            </section>
          </div>

          <div className="system-gate__center" style={{ cursor: "default" }}>
            <SystemOrbPanel
              systemState={systemState}
              uiState={uiState}
              coherence={coherence}
              stateLabel={finding.status}
              lastUpdate={interpretation.hasTelemetry ? lastUpdate : null}
              focusLabel={interpretation.primaryDriver}
              orbData={orbData}
              compactPreview
            />
            <p className="system-gate__state">{finding.status}</p>
          </div>

          <div className="system-gate__column system-gate__column--right">
            <section className="panel system-gate__plate system-gate__plate--snapshot" aria-label="Structural stability snapshot">
              <div className="panel-body">
                <ul className="onboarding-summary">
                  <li><span>Why it matters</span><strong>{finding.whyItMatters}</strong></li>
                  <li><span>Review next</span><strong>{finding.exists ? finding.reviewNext : finding.emptyState.detail}</strong></li>
                  <li><span>Current operating pattern</span><strong>{stabilitySnapshot.regime}</strong></li>
                  <li><span>Behavior has persisted</span><strong>{stabilitySnapshot.deformationAge}</strong></li>
                </ul>
                {findingDataQuality.length > 0 ? (
                  <div style={{ marginTop: "0.8rem" }}>
                    <p className="section-token">Data Quality</p>
                    <ul className="compact-list">
                      {findingDataQuality.slice(0, 3).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                ) : null}
              </div>
            </section>

            <section className="panel system-gate__plate system-gate__plate--trust" aria-label="Instrument trust boundaries">
              <div className="panel-body">
                <ul className="onboarding-summary">
                  <li><span>Control Boundary</span><strong>Read-only. No actuation possible.</strong></li>
                  <li><span>Observation Method</span><strong>Structural change only. No severity or instructions.</strong></li>
                  <li><span>Latest Update</span><strong>Current observation aligned with the active analysis.</strong></li>
                </ul>
              </div>
            </section>

            <div className="system-gate__actions">
              <button
                type="button"
                className="command-button"
                onClick={() => navigateWorkspace("observation-center")}
              >
                Review Findings
              </button>
            </div>
          </div>
        </div>

        <section className="panel system-gate__plate system-gate__plate--summary system-gate__plate--operator" aria-label="System status summary">
          <div className="panel-body">
            <ul className="onboarding-summary">
              <li><span>Current Status</span><strong>{finding.status}</strong></li>
              <li><span>Confidence</span><strong>{finding.confidence}</strong></li>
              <li><span>Observation Summary</span><strong>{finding.summary}</strong></li>
              <li><span>Why it matters</span><strong>{finding.whyItMatters}</strong></li>
              <li><span>Review next</span><strong>{finding.exists ? finding.reviewNext : finding.emptyState.detail}</strong></li>
            </ul>
            <p className="system-gate__boundary-note">Read-only monitoring. No controls.</p>
          </div>
        </section>

        {Array.isArray(finding.supportingEvidence) && finding.supportingEvidence.length > 0 ? (
          <section className="panel system-gate__plate system-gate__plate--summary" aria-label="Supporting evidence">
            <div className="panel-body">
              <p className="section-token">Supporting Evidence</p>
              <ul className="compact-list">
                {finding.supportingEvidence.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          </section>
        ) : null}

        <div className="system-gate__primary-action">
          <button
            type="button"
            className="command-button"
            onClick={() => navigateWorkspace(finding.exists ? "historical-replay" : (interpretation.hasTelemetry ? "observation-center" : "data-connections"))}
          >
            {interpretation.hasTelemetry ? finding.evidenceButtonLabel : "Upload Data"}
          </button>
        </div>
      </section>
      {menuOverlay}
    </PageContainer>
  );
}


function flattenDataQuality(dataQuality) {
  const groups = dataQuality && typeof dataQuality === "object" ? dataQuality : {};
  return [
    ...(groups.missingBaselineValues || []).map((item) => `Missing baseline values: ${item}`),
    ...(groups.missingRecentValues || []).map((item) => `Missing recent values: ${item}`),
    ...(groups.unavailableTelemetry || []).map((item) => `Unavailable telemetry: ${item}`),
  ];
}

function buildFallbackFinding(interpretation, stabilitySnapshot, dataConditions) {
  const exists = interpretation.structuralState !== "Monitoring" && interpretation.structuralState !== "No data yet";
  return {
    exists,
    status: exists ? interpretation.structuralState : "Normal",
    confidence: interpretation.confidence === "Pending" ? "Low" : interpretation.confidence,
    summary: exists ? interpretation.relationshipSummary.text : "No current observations.",
    whyItMatters: exists ? interpretation.relationshipSummary.text : "Telemetry is being monitored.",
    reviewNext: interpretation.nextStep,
    emptyState: {
      title: "No current observations.",
      subtitle: "Telemetry is being monitored.",
      detail: "No structural changes detected.",
    },
    evidenceButtonLabel: "Review Evidence",
    supportingEvidence: [],
    dataQuality: {
      missingBaselineValues: [],
      missingRecentValues: dataConditions || [],
      unavailableTelemetry: [],
    },
    technicalDetails: [
      { label: "Drift magnitude", value: stabilitySnapshot.driftMagnitude },
      { label: "Behavior duration", value: stabilitySnapshot.deformationAge },
    ],
  };
}

function buildStabilitySnapshot({ latestUploadSnapshot, latestUploadResult, latestReplayFrame }) {
  const hasActiveDataset = hasUsableTelemetry({ latestUploadResult, latestUploadSnapshot, latestReplayFrame });
  if (!hasActiveDataset) {
    return {
      regime: "—",
      driftMagnitude: "—",
      activeObservations: 0,
      deformationAge: "—",
    };
  }

  const sii = latestUploadResult?.sii_intelligence ?? {};
  const replay = latestUploadResult?.replay_timeline?.timeline ?? sii?.replay_timeline?.timeline ?? [];
  const frame = latestReplayFrame ?? replay?.[replay.length - 1] ?? null;
  const driftMagnitude = frame?.baseline_distance
    ?? frame?.topology_state?.drift_index
    ?? sii?.instability_index
    ?? null;
  const startedAt = frame?.timestamp_start
    ?? latestUploadResult?.timestamp_profile?.first_timestamp
    ?? null;
  const regime = labelOrFallback(sii?.baseline_regime ?? sii?.regime_label, "—");
  const hasObservationPayload = Boolean(
    latestUploadResult?.observation_type
    || latestUploadResult?.operator_report
    || latestUploadResult?.finding_evidence_chains?.length
    || latestReplayFrame
    || replay.length > 0
    || latestUploadResult?.sii_reliable_enough_to_show,
  );
  return {
    regime,
    driftMagnitude: Number.isFinite(Number(driftMagnitude)) ? Number(driftMagnitude).toFixed(2) : "—",
    activeObservations: hasObservationPayload && String(latestUploadResult?.drift_status ?? "").toLowerCase() !== "info" ? 1 : 0,
    deformationAge: ageLabel(startedAt),
  };
}

function collectDataConditions(latestUploadResult) {
  const result = latestUploadResult ?? {};
  const dataQualityWarnings = Array.isArray(result?.data_quality?.warnings) ? result.data_quality.warnings : [];
  const timestampWarnings = Array.isArray(result?.timestamp_profile?.warnings) ? result.timestamp_profile.warnings : [];
  return [...new Set([...dataQualityWarnings, ...timestampWarnings].filter(Boolean).map(String))];
}

function ageLabel(value) {
  if (!value) return "—";
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const hours = Math.round(ms / 3600000);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function mapBackendSystemInterpretation(contract, expectedJobId = null, reliableEnoughToShow = false) {
  const value = contract && typeof contract === "object" ? contract : null;
  if (!value) return null;

  const lineage = value.lineage && typeof value.lineage === "object" ? value.lineage : {};
  const aligned = Boolean(lineage.aligned && value.run_alignment_verified !== false);
  if (!aligned) return null;
  if (expectedJobId && String(lineage.job_id ?? "") !== String(expectedJobId)) return null;

  const divergence = value.relationship_divergence || {};
  const backendSummary = value.relationship_summary || {};
  const fallbackSummary = divergence.summary || value.state_derivation_reason || EMPTY_VALUE;

  return {
    structuralState: normalizeStructuralLabel(value.facility_state_label, "No data yet"),
    confidence: String(value.confidence || EMPTY_VALUE),
    primaryDriver: String(value.primary_driver || "None"),
    relationshipSummary: {
      text: simplifyOperatorSummary(backendSummary.text || fallbackSummary || EMPTY_VALUE),
      divergence_severity: String(divergence.severity || backendSummary.divergence_severity || EMPTY_VALUE),
      confidence: String(divergence.confidence || backendSummary.confidence || value.confidence || EMPTY_VALUE),
      affected_systems: Array.isArray(divergence.affected_systems)
        ? divergence.affected_systems
        : (Array.isArray(backendSummary.affected_systems) ? backendSummary.affected_systems : []),
    },
    findingEvidenceChains: Array.isArray(value.finding_evidence_chains)
      ? value.finding_evidence_chains
      : [],
    hasTelemetry: true,
    nextStep: reliableEnoughToShow && Array.isArray(value.finding_evidence_chains) && value.finding_evidence_chains.length > 0
      ? "Review evidence."
      : "Check evidence packet.",
  };
}

export function buildSystemInterpretation({ latestUploadSnapshot, latestUploadResult, liveSnapshot, latestReplayFrame = null, fallback = {} }) {
  const latestFrame = latestReplayFrame ?? null;
  const hasTelemetry = hasUsableTelemetry({ latestUploadResult, latestUploadSnapshot, latestReplayFrame: latestFrame });
  const connectionDegraded = isConnectionDegraded(fallback.connectionTone, fallback.connectionStatus);
  const backendSystemInterpretation = latestUploadSnapshot?.system_interpretation
    ?? latestUploadResult?.system_interpretation
    ?? liveSnapshot?.latestUploadSnapshot?.system_interpretation
    ?? null;
  const expectedJobId = latestUploadSnapshot?.current_upload?.job_id ?? latestUploadResult?.job_id ?? latestUploadSnapshot?.job_id ?? null;
  const mappedBackendInterpretation = mapBackendSystemInterpretation(backendSystemInterpretation, expectedJobId, Boolean(latestUploadResult?.sii_reliable_enough_to_show));
  if (mappedBackendInterpretation) {
    return mappedBackendInterpretation;
  }

  if (!hasTelemetry) {
    return {
      structuralState: "No data yet",
      primaryDriver: "No data yet",
      relationshipSummary: { text: "Upload data to begin." },
      confidence: "Pending",
      nextStep: "Upload data.",
      hasTelemetry: false,
    };
  }

  if (connectionDegraded) {
    return {
      structuralState: "Telemetry interrupted",
      primaryDriver: "Connection degraded",
      relationshipSummary: { text: "Connection is degraded. Latest interpretation may be stale." },
      confidence: "Pending",
      nextStep: "Check connection, then refresh telemetry.",
      hasTelemetry: true,
    };
  }

  const uploadStatus = String(
    latestUploadSnapshot?.status
    ?? latestUploadSnapshot?.processing_state
    ?? latestUploadResult?.processing_state
    ?? "",
  ).toLowerCase();
  const processingLike = ["processing", "queued", "pending", "running_sii", "parsing", "baseline_modeling", "structural_scoring", "generating_replay", "cognition_ready", "writing_state"];
  const hasUploadInFlight = processingLike.some((token) => uploadStatus.includes(token));

  if (hasUploadInFlight) {
    return {
      structuralState: "Processing data",
      confidence: "Interpretation Unavailable",
      primaryDriver: "Interpretation Unavailable",
      relationshipSummary: {
        text: "Review will appear when processing completes.",
        divergence_severity: EMPTY_VALUE,
        confidence: "Interpretation Unavailable",
        affected_systems: [],
      },
      nextStep: "Wait for processing to finish.",
      hasTelemetry: true,
    };
  }

  const sii = latestUploadResult?.sii_intelligence ?? {};
  const rawStructuralState = labelOrFallback(
    latestFrame?.state_label
      ?? latestFrame?.cognition_state?.facility_state
      ?? latestFrame?.cognition_state?.canonical_phase
      ?? sii?.facility_state
      ?? sii?.state_label
      ?? latestUploadResult?.operating_state
      ?? latestUploadSnapshot?.status
      ?? fallback.stateLabel,
    "Monitoring",
  );
  const structuralState = normalizeStructuralLabel(rawStructuralState, "Monitoring");
  const driver = labelOrFallback(
    latestFrame?.primary_driver
      ?? latestFrame?.topology_state?.primary_driver
      ?? sii?.primary_driver
      ?? sii?.dominant_driver
      ?? latestUploadResult?.primary_driver
      ?? fallback.focusLabel,
    "Structural relationship",
  );
  const hasDriftState = describesDrift(structuralState) || describesDrift(driver);
  const relationship = buildRelationshipSummary({ latestUploadResult, latestReplayFrame, sii, fallback, hasDriftState });
  const confidence = formatConfidence(
    latestFrame?.confidence
      ?? latestFrame?.evidence_state?.confidence
      ?? sii?.confidence
      ?? latestUploadResult?.confidence
      ?? null,
    { hasDriftState },
  );

  const canShowEvidenceBackedFinding = Boolean(latestUploadResult?.sii_reliable_enough_to_show) && hasDriftState;

  return {
    structuralState,
    primaryDriver: driver,
    relationshipSummary: relationship,
    confidence,
    findingEvidenceChains: [],
    nextStep: canShowEvidenceBackedFinding ? "Review evidence." : (hasDriftState ? "Check evidence traceability." : "Continue monitoring."),
    hasTelemetry: true,
  };
}

function buildRelationshipSummary({ latestUploadResult, latestReplayFrame, sii, fallback, hasDriftState = false }) {
  const candidates = [
    latestReplayFrame?.why_summary,
    latestReplayFrame?.relationship_summary,
    latestReplayFrame?.topology_state?.relationship_summary,
    latestReplayFrame?.evidence_state?.summary,
    sii?.why_summary,
    sii?.relationship_summary,
    latestUploadResult?.relationship_summary,
    fallback.primaryMessage,
    fallback.subtitle,
  ];
  const selected = candidates.find((item) => typeof item === "string" && item.trim());
  const text = selected ? simplifyOperatorSummary(selected.trim()) : "Interpretation unavailable";
  if (hasDriftState && describesStable(text)) return { text: "Change detected." };
  return { text };
}


function heartbeatStatus(connectionTone, connectionStatus, lastUpdate, hasTelemetry) {
  if (!hasTelemetry) return { tone: "pending", label: "Awaiting telemetry" };
  if (isConnectionDegraded(connectionTone, connectionStatus)) return { tone: "offline", label: "Connection degraded" };
  const text = `${connectionTone ?? ""} ${connectionStatus ?? ""} ${lastUpdate ?? ""}`.toLowerCase();
  if (text.includes("replay")) return { label: "Replay running", tone: "syncing" };
  if (text.includes("sync")) return { label: "Data stream active", tone: "syncing" };
  if (lastUpdate) return { tone: "online", label: "Telemetry active" };
  return { tone: "pending", label: "Awaiting telemetry" };
}

function hasUsableTelemetry({ latestUploadResult, latestUploadSnapshot, latestReplayFrame }) {
  if (latestReplayFrame && Object.keys(latestReplayFrame).length > 0) return true;
  if (latestUploadResult && Object.keys(latestUploadResult).length > 0) return true;
  const status = String(latestUploadSnapshot?.status ?? latestUploadSnapshot?.processing_state ?? "").trim().toLowerCase();
  if (!status || ["empty", "idle", "none", "reset", "no_active_session"].includes(status)) return false;
  return Boolean(latestUploadSnapshot?.last_filename || latestUploadSnapshot?.job_id || latestUploadSnapshot?.latest_result || latestUploadSnapshot?.sii_completed);
}

function normalizeStructuralLabel(value, fallback = EMPTY_VALUE) {
  const text = String(value ?? "").trim();
  const normalized = text.toLowerCase().replaceAll("_", " ");
  if (!text || ["empty", "idle", "none", "null", "undefined"].includes(normalized)) return fallback;
  if (normalized === "no active session" || normalized.includes("baseline pending")) return "No data yet";
  if (normalized.includes("stable") || normalized.includes("nominal")) return "Monitoring";
  if (normalized.includes("drift") || normalized.includes("degrad") || normalized.includes("topology") || normalized.includes("fragment")) return "Change Detected";
  if (normalized.includes("recover")) return "Recovery tracking";
  return simplifyOperatorSummary(text);
}

function simplifyOperatorSummary(value) {
  const replacements = [
    ["structural drift", "system behavior change"],
    ["topology", "relationship pattern"],
    ["regime", "operating pattern"],
    ["baseline separation", "change from the usual pattern"],
    ["deformation", "change"],
    ["drift velocity", "change direction"],
    ["drift acceleration", "change momentum"],
  ];
  return replacements.reduce(
    (text, [term, replacement]) => text.replaceAll(new RegExp(term, "gi"), replacement),
    String(value ?? ""),
  );
}

function isConnectionDegraded(connectionTone, connectionStatus) {
  const text = `${connectionTone ?? ""} ${connectionStatus ?? ""}`.toLowerCase();
  return text.includes("degrad") || text.includes("offline") || text.includes("error") || text.includes("fail") || text.includes("disconnected");
}

function labelOrFallback(value, fallback = EMPTY_VALUE) {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text ? text : fallback;
}

function formatConfidence(value, { hasDriftState = false } = {}) {
  const number = Number(value);
  if (!Number.isFinite(number) || (hasDriftState && number <= 0)) return "Pending";
  if (number <= 0) return "Pending";
  if (number <= 1) return `${Math.round(number * 100)}%`;
  return `${Math.round(number)}%`;
}

function describesDrift(value) {
  const text = String(value ?? "").toLowerCase();
  return text.includes("drift") || text.includes("degrad") || text.includes("unstable") || text.includes("watch") || text.includes("alert");
}

function describesStable(value) {
  const text = String(value ?? "").trim().toLowerCase();
  return text === "stable" || text === "normal" || text === "monitoring" || text === "within range";
}
