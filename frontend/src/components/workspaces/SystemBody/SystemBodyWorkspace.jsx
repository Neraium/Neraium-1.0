import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import SystemOrbPanel from "./SystemOrbPanel";
import PageContainer from "../../layout/PageContainer";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";
import { ConfidenceIndicator, StatusBadge } from "../../workspacePrimitives";

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
  telemetrySessionMode = "empty",
  domainDetection = null,
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
  const heartbeat = heartbeatStatus(connectionTone, connectionStatus, lastUpdate, interpretation.hasTelemetry, telemetrySessionMode);
  const stabilitySnapshot = useMemo(
    () => buildStabilitySnapshot({ latestUploadSnapshot, latestUploadResult, latestReplayFrame }),
    [latestReplayFrame, latestUploadResult, latestUploadSnapshot],
  );
  const dataConditions = useMemo(
    () => collectDataConditions(latestUploadResult),
    [latestUploadResult],
  );
  const fallbackFinding = canonicalFinding ?? buildFallbackFinding(interpretation, stabilitySnapshot, dataConditions);
  const assessmentState = useMemo(
    () => resolveAssessmentState({
      interpretation,
      latestUploadSnapshot,
      latestUploadResult,
      latestReplayFrame,
      fallbackFinding,
      stabilitySnapshot,
    }),
    [fallbackFinding, interpretation, latestReplayFrame, latestUploadResult, latestUploadSnapshot, stabilitySnapshot],
  );
  const finding = assessmentState.finding;
  const gateReadiness = systemReadinessStatus({ assessmentState, finding, interpretation });
  const findingDataQuality = flattenDataQuality(finding.dataQuality);
  const canReviewFindings = assessmentState.mode === "analysis_ready";
  const navigationItems = [
    {
      id: "data-connections",
      label: "Data intake",
      description: interpretation.hasTelemetry ? "Swap feeds, upload CSV, or reconnect APIs." : "Upload telemetry or connect a live source.",
    },
    {
      id: finding.exists ? "historical-replay" : "observation-center",
      label: finding.exists ? "Evidence trace" : "Observation review",
      description: finding.exists ? "Open replay and inspect the evidence chain." : "Review current interpretation and monitoring context.",
    },
    {
      id: "help-changelog",
      label: "Help and updates",
      description: "Reference product guidance and recent changes.",
    },
  ];
  const heroStats = [
    { label: "Observation status", value: finding.status },
    { label: "Evidence confidence", value: finding.confidence },
    { label: "Operating pattern", value: assessmentState.stability.regime },
    { label: "Persistence", value: assessmentState.stability.deformationAge },
  ];
  const stabilityRows = [
    { label: "Current operating pattern", value: assessmentState.stability.regime },
    { label: "Behavior has persisted", value: assessmentState.stability.deformationAge },
    { label: "Drift magnitude", value: assessmentState.stability.driftMagnitude },
    { label: "Active observations", value: String(assessmentState.stability.activeObservations) },
  ];
  const insightRows = [
    { label: "Primary driver", value: interpretation.primaryDriver },
    { label: "Why it matters", value: finding.whyItMatters },
    { label: "Review next", value: finding.exists ? finding.reviewNext : finding.emptyState.detail },
    { label: "Latest update", value: lastUpdate || "Awaiting telemetry" },
  ];
  const trustRows = [
    { label: "Control boundary", value: "Read-only. No actuation or writeback." },
    { label: "Analysis mode", value: "Structural relationship monitoring only." },
    { label: "Data posture", value: interpretation.hasTelemetry ? "Live observation aligned to the active session." : "No telemetry attached yet." },
  ];
  const domainSummary = buildDomainDetectionSummary(domainDetection);

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
          {domainSummary ? (
            <p className="system-gate__settings-message">{domainSummary}</p>
          ) : null}
          <ul>
            <li>
              <button data-testid="upload-workspace-entry" type="button" className="system-gate__settings-action" aria-label="Data connections" onClick={() => navigateWorkspace("data-connections")}>
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
          <strong>{assessmentState.headerStatus}</strong>
        </div>

        <button
          type="button"
          className="system-gate__settings"
          data-testid="workspace-menu-button"
          aria-label="Open Gate settings"
          aria-expanded={menuOpen}
          aria-controls="system-body-menu"
          onClick={() => setMenuOpen((v) => !v)}
        >
          Views
        </button>

        <div className="system-gate__layout">
          <section className="system-gate__hero" aria-label="System status overview">
            <div className="system-gate__hero-copy">
              <p className="system-gate__eyebrow">Live system intelligence</p>
              <h1>{finding.title}</h1>
              <p className="system-gate__lede">{finding.summary}</p>
              <div className="system-gate__hero-actions">
                <button
                  type="button"
                  data-testid="primary-upload-entry"
                  className="command-button"
                  onClick={() => navigateWorkspace(finding.exists ? "historical-replay" : (interpretation.hasTelemetry ? "observation-center" : "data-connections"))}
                >
                  {interpretation.hasTelemetry ? finding.evidenceButtonLabel : "Upload Data"}
                </button>
                <button
                  type="button"
                  className="secondary-command-button"
                  disabled={!canReviewFindings}
                  onClick={() => navigateWorkspace("observation-center")}
                >
                  Review Findings
                </button>
              </div>
              <div className="system-gate__stat-grid system-gate__stat-grid--premium">
                <article className="system-gate__stat-card system-gate__stat-card--readiness">
                  <span>Analysis status</span>
                  <StatusBadge {...gateReadiness} />
                </article>
                <article className="system-gate__stat-card system-gate__stat-card--confidence">
                  <span>Evidence confidence</span>
                  <ConfidenceIndicator value={finding.confidence} />
                </article>
                {heroStats.slice(2).map((item) => (
                  <article className="system-gate__stat-card" key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </article>
                ))}
              </div>
            </div>

            <div className="system-gate__hero-visual">
              <div className="system-gate__orb-stage">
                <SystemOrbPanel
                  systemState={systemState}
                  uiState={uiState}
                  coherence={coherence}
                  stateLabel={finding.title}
                  lastUpdate={interpretation.hasTelemetry ? lastUpdate : null}
                  focusLabel={interpretation.primaryDriver}
                  orbData={orbData}
                  compactPreview
                />
              </div>
              <div className="system-gate__orb-caption">
                <p className="system-gate__state">{finding.title}</p>
                <p className="system-gate__orb-note">{finding.whyItMatters}</p>
              </div>
            </div>
          </section>

          <aside className="system-gate__sidebar" aria-label="Current briefing">
            <section className="system-gate__panel">
              <div className="system-gate__panel-header">
                <p className="section-token">Current brief</p>
                <strong>{assessmentState.headerStatus}</strong>
              </div>
              <ul className="system-gate__detail-list">
                {insightRows.map((item) => (
                  <li key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </li>
                ))}
              </ul>
            </section>

            <section className="system-gate__panel">
              <div className="system-gate__panel-header">
                <p className="section-token">Trust boundary</p>
                <strong>Operator safe</strong>
              </div>
              <ul className="system-gate__detail-list">
                {trustRows.map((item) => (
                  <li key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </li>
                ))}
              </ul>
            </section>
          </aside>
        </div>

        <div className="system-gate__lower-grid">
          <section className="system-gate__panel system-gate__panel--wide" aria-label="Operational focus">
            <div className="system-gate__panel-header">
              <p className="section-token">Operational focus</p>
              <strong>{assessmentState.headerStatus}</strong>
            </div>
            <ul className="system-gate__detail-list system-gate__detail-list--dense">
              <li>
                <span>Observation summary</span>
                <strong>{finding.summary}</strong>
              </li>
              <li>
                <span>Review next</span>
                <strong>{finding.exists ? finding.reviewNext : finding.emptyState.detail}</strong>
              </li>
            </ul>
            {Array.isArray(finding.supportingEvidence) && finding.supportingEvidence.length > 0 ? (
              <div className="system-gate__evidence-block" aria-label="Supporting evidence">
                <p className="section-token">Supporting Evidence</p>
                <ul className="compact-list">
                  {finding.supportingEvidence.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ) : null}
            {findingDataQuality.length > 0 ? (
              <div className="system-gate__evidence-block">
                <p className="section-token">Data quality</p>
                <ul className="compact-list">
                  {findingDataQuality.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ) : null}
          </section>

          <section className="system-gate__panel" aria-label="Structural stability snapshot">
            <div className="system-gate__panel-header">
              <p className="section-token">Structural stability snapshot</p>
              <strong>Review baseline</strong>
            </div>
            <ul className="system-gate__detail-list system-gate__detail-list--dense">
              {stabilityRows.map((item) => (
                <li key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </li>
              ))}
            </ul>
          </section>

          <section className="system-gate__panel" aria-label="Workspace navigation">
            <div className="system-gate__panel-header">
              <p className="section-token">Workspace navigation</p>
              <strong>Next actions</strong>
            </div>
            <div className="system-gate__nav-list">
              {navigationItems.map((item) => (
                <button
                  type="button"
                  className="system-gate__nav-card"
                  key={item.id}
                  onClick={() => navigateWorkspace(item.id)}
                >
                  <span>{item.label}</span>
                  <strong>{item.description}</strong>
                </button>
              ))}
            </div>
          </section>
        </div>
      </section>
      {menuOverlay}
    </PageContainer>
  );
}


function buildDomainDetectionSummary(domainDetection) {
  const rawMode = String(domainDetection?.mode ?? "").trim();
  if (!rawMode) return "";
  const label = rawMode
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
  return label ? "Detected data type: " + label : "";
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
    title: exists ? interpretation.structuralState : "Normal",
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

function resolveAssessmentState({
  interpretation,
  latestUploadSnapshot,
  latestUploadResult,
  latestReplayFrame,
  fallbackFinding,
  stabilitySnapshot,
}) {
  const analysisCompleted = hasCompletedAnalysis({ latestUploadSnapshot, latestUploadResult });
  const observationsExist = hasCompletedObservations({ latestUploadResult, latestReplayFrame, stabilitySnapshot });
  if (!interpretation.hasTelemetry || !analysisCompleted || !observationsExist) {
    return {
      mode: "awaiting_telemetry",
      headerStatus: "Awaiting Telemetry",
      finding: {
        ...fallbackFinding,
        exists: false,
        title: "No Analysis",
        status: "Not Assessed",
        confidence: "Unknown",
        summary: "Upload telemetry to generate an assessment.",
        whyItMatters: "Upload telemetry to generate an assessment.",
        reviewNext: "Upload telemetry to generate an assessment.",
        emptyState: {
          title: "No Analysis",
          subtitle: "Upload telemetry to generate an assessment.",
          detail: "Upload telemetry to generate an assessment.",
        },
      },
      stability: {
        regime: "No telemetry",
        driftMagnitude: "No telemetry",
        activeObservations: 0,
        deformationAge: "No telemetry",
      },
    };
  }

  return {
    mode: "analysis_ready",
    headerStatus: "Telemetry active",
    finding: fallbackFinding,
    stability: stabilitySnapshot,
  };
}

function hasCompletedAnalysis({ latestUploadSnapshot, latestUploadResult }) {
  if (latestUploadResult?.processing_trace?.sii_completed === true) return true;
  if (latestUploadResult?.sii_completed === true) return true;
  if (String(latestUploadResult?.processing_state ?? latestUploadResult?.status ?? "").toLowerCase() === "complete") return true;
  if (latestUploadSnapshot?.sii_completed === true) return true;
  return String(latestUploadSnapshot?.status ?? latestUploadSnapshot?.processing_state ?? "").toLowerCase() === "complete";
}

function hasCompletedObservations({ latestUploadResult, latestReplayFrame, stabilitySnapshot }) {
  if (stabilitySnapshot.activeObservations > 0) return true;
  if (latestReplayFrame && Object.keys(latestReplayFrame).length > 0) return true;
  if (String(latestUploadResult?.observation_type ?? "").trim()) return true;
  if (Array.isArray(latestUploadResult?.finding_evidence_chains) && latestUploadResult.finding_evidence_chains.length > 0) return true;
  if (Array.isArray(latestUploadResult?.operator_report?.evidence_summary) && latestUploadResult.operator_report.evidence_summary.length > 0) return true;
  return false;
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


function systemReadinessStatus({ assessmentState, finding, interpretation }) {
  if (!interpretation?.hasTelemetry) {
    return {
      status: "pending",
      label: "PENDING",
      explanation: "Upload or connect telemetry to activate analysis.",
    };
  }
  if (assessmentState?.mode === "analysis_ready" && finding?.exists) {
    return {
      status: "ready",
      label: "READY",
      explanation: "Evidence-backed finding is ready for operator review.",
    };
  }
  if (assessmentState?.mode === "analysis_ready") {
    return {
      status: "degraded_ready",
      label: "DEGRADED_READY",
      explanation: "Telemetry is available. Continue monitoring or review supporting context.",
    };
  }
  return {
    status: "pending",
    label: "PENDING",
    explanation: "Analysis is forming from the current telemetry session.",
  };
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


function heartbeatStatus(connectionTone, connectionStatus, lastUpdate, hasTelemetry, telemetrySessionMode = "empty") {
  if (!hasTelemetry) return { tone: "pending", label: "Awaiting telemetry" };
  if (isConnectionDegraded(connectionTone, connectionStatus)) return { tone: "offline", label: "Connection degraded" };
  const text = `${connectionTone ?? ""} ${connectionStatus ?? ""} ${lastUpdate ?? ""}`.toLowerCase();
  if (text.includes("replay")) return { label: "Replay running", tone: "syncing" };
  if (text.includes("sync")) return { label: "Data stream active", tone: "syncing" };
  if (lastUpdate) return { tone: "online", label: "Telemetry active" };
  if (telemetrySessionMode === "persisted") return { tone: "watch", label: "Persisted telemetry available" };
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
  if (!text || ["empty", "idle", "none", "null", "undefined", "complete", "completed", "success", "ok"].includes(normalized)) return fallback;
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
