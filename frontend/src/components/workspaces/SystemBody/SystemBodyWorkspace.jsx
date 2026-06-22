import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
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
  telemetrySessionMode = "empty",
  domainDetection = null,
  persistedLatestUpload = null,
  previousUploadHistory = [],
  onResumePreviousUpload = null,
}) {
  void dataFreshness;
  void siiVerification;
  void systemState;
  void coherence;
  void orbData;

  const [menuOpen, setMenuOpen] = useState(false);
  const [activeResultSection, setActiveResultSection] = useState("overview");
  const [showAllWarnings, setShowAllWarnings] = useState(false);
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
  const telemetryUsable = assessmentState.mode === "analysis_ready" || assessmentState.mode === "analysis_degraded_ready";
  const heartbeat = heartbeatStatus(connectionTone, connectionStatus, lastUpdate, telemetryUsable, telemetrySessionMode);
  const findingDataQuality = flattenDataQuality(finding.dataQuality);
  const canReviewFindings = telemetryUsable && finding.exists;
  const overviewStatus = formatOverviewStatus(assessmentState.mode);
  const dataQualityReport = buildDataQualityReport(latestUploadResult, latestUploadSnapshot, findingDataQuality);
  const evidenceReport = buildEvidenceReport({
    latestUploadResult,
    latestUploadSnapshot,
    latestReplayFrame,
    assessmentState,
    finding,
    stabilitySnapshot,
  });
  const technicalReport = buildTechnicalReport({ latestUploadResult, latestUploadSnapshot, assessmentState });
  const overviewSummary = buildOverviewSummary(assessmentState.mode);
  const metricTiles = compactRows([
    { label: "Rows loaded", value: dataQualityReport.rowsLoaded },
    { label: "Signals detected", value: dataQualityReport.signalsDetected },
    { label: "Confidence", value: evidenceReport.confidence },
  ]);
  const overviewNextAction = buildOverviewNextAction({ assessmentState, dataQualityReport, evidenceReport, finding });
  const visibleWarnings = showAllWarnings ? dataQualityReport.warnings : dataQualityReport.warnings.slice(0, 3);
  const resultSections = [
    { id: "overview", label: "Overview" },
    { id: "findings", label: "Findings" },
    { id: "quality", label: "Data Quality" },
    { id: "evidence", label: "Evidence" },
    { id: "technical", label: "Technical" },
  ];
  const domainSummary = buildDomainDetectionSummary(domainDetection);
  const hasPostUploadDashboard = assessmentState.mode !== "awaiting_telemetry";
  const previousUploadSummary = buildPreviousUploadSummary(persistedLatestUpload, previousUploadHistory);
  const canResumePreviousUpload = Boolean(previousUploadSummary && typeof onResumePreviousUpload === "function");

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

        {hasPostUploadDashboard ? (
          <>
        <nav className="result-section-tabs" aria-label="Post-upload result sections">
          {resultSections.map((section) => (
            <button
              key={section.id}
              type="button"
              className={activeResultSection === section.id ? "is-active" : ""}
              aria-current={activeResultSection === section.id ? "page" : undefined}
              onClick={() => setActiveResultSection(section.id)}
            >
              {section.label}
            </button>
          ))}
        </nav>

        <div className="post-upload-result" data-testid="post-upload-result">
          {activeResultSection === "overview" ? (
            <section className="post-upload-overview" aria-label="Post-upload overview">
              <div className="post-upload-overview__header">
                <span className={`post-upload-status post-upload-status--${overviewStatus.tone}`}>{overviewStatus.label}</span>
                <h1>{overviewSummary}</h1>
                <p>{assessmentState.dataPosture}</p>
              </div>

              <div className="post-upload-metrics" aria-label="Upload metrics">
                {metricTiles.map((item) => (
                  <article className="post-upload-metric" key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </article>
                ))}
              </div>

              <section className="post-upload-review-next" aria-label="Review next">
                <span>Next action</span>
                <strong>{overviewNextAction.label}</strong>
              </section>

              {overviewNextAction.section ? (
                <div className="post-upload-actions" aria-label="Primary result action">
                  <button type="button" className="command-button" onClick={() => setActiveResultSection(overviewNextAction.section)}>{overviewNextAction.button}</button>
                </div>
              ) : null}
            </section>
          ) : null}

          {activeResultSection === "findings" ? (
            <section className="post-upload-section" aria-label="Findings">
              <div className="post-upload-section__header">
                <p className="section-token">Findings</p>
                <h2>{finding.exists ? "Active finding" : "No urgent findings."}</h2>
              </div>
              {finding.exists ? (
                <article className="finding-card">
                  <div className="finding-card__topline">
                    <h3>{finding.title}</h3>
                    <span>{finding.status}</span>
                  </div>
                  <dl className="result-detail-grid">
                    {compactRows([
                      { label: "Why it matters", value: finding.whyItMatters },
                      { label: "Review next", value: finding.reviewNext },
                      { label: "Affected variables", value: evidenceReport.affectedVariables },
                    ]).map((item) => (
                      <div key={item.label}>
                        <dt>{item.label}</dt>
                        <dd>{item.value}</dd>
                      </div>
                    ))}
                  </dl>
                  {canReviewFindings ? (
                    <button type="button" className="command-button" onClick={() => navigateWorkspace("observation-center")}>Open Finding Review</button>
                  ) : null}
                </article>
              ) : (
                <article className="finding-empty-state">
                  <h3>No urgent findings.</h3>
                  <p>Telemetry is usable. Review data quality warnings before relying on this analysis.</p>
                </article>
              )}
            </section>
          ) : null}

          {activeResultSection === "quality" ? (
            <section className="post-upload-section" aria-label="Data Quality">
              <div className="post-upload-section__header">
                <p className="section-token">Data Quality</p>
                <h2>{dataQualityReport.summary}</h2>
              </div>
              <dl className="result-detail-grid">
                {dataQualityReport.rows.map((item) => (
                  <div key={item.label}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
              <ResultList title="Warnings" items={visibleWarnings} empty="No data quality warnings reported." />
              {dataQualityReport.warnings.length > 3 ? (
                <button type="button" className="secondary-command-button post-upload-inline-action" onClick={() => setShowAllWarnings((value) => !value)}>
                  {showAllWarnings ? "Show top 3" : `Show all ${dataQualityReport.warnings.length}`}
                </button>
              ) : null}
              <ResultList title="Missing values" items={dataQualityReport.missingValues} />
              <ResultList title="Interpolation and imputation" items={dataQualityReport.imputationNotes} />
            </section>
          ) : null}

          {activeResultSection === "evidence" ? (
            <section className="post-upload-section" aria-label="Evidence">
              <div className="post-upload-section__header">
                <p className="section-token">Evidence</p>
                <h2>Evidence packet</h2>
              </div>
              <dl className="result-detail-grid">
                {evidenceReport.rows.map((item) => (
                  <div key={item.label}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
              {evidenceReport.hasReplay ? (
                <div className="post-upload-actions" aria-label="Evidence replay action">
                  <button type="button" className="command-button" onClick={() => navigateWorkspace("historical-replay")}>Open Replay</button>
                </div>
              ) : null}
            </section>
          ) : null}

          {activeResultSection === "technical" ? (
            <section className="post-upload-section" aria-label="Technical diagnostics">
              <div className="post-upload-section__header">
                <p className="section-token">Technical</p>
                <h2>Operator diagnostics</h2>
              </div>
              <dl className="result-detail-grid">
                {technicalReport.rows.map((item) => (
                  <div key={item.label}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
              <ResultList title="Traceability" items={technicalReport.traceability} />
              <ResultList title="Processing trace" items={technicalReport.processingTrace} empty="No processing trace reported." />
              <ResultList title="Backend warnings" items={technicalReport.backendWarnings} empty="No backend warnings reported." />
              <details className="technical-details-panel">
                <summary>Raw metadata</summary>
                <pre>{technicalReport.rawMetadata}</pre>
              </details>
            </section>
          ) : null}
        </div>
          </>
        ) : (
          <section className="post-upload-empty" aria-label="No upload state">
            <div className="post-upload-overview__header">
              <span className="post-upload-status post-upload-status--pending">No Current Upload</span>
              <h1>No telemetry uploaded yet</h1>
              <p>Upload telemetry in this browser session to generate current results.</p>
            </div>
            <div className="post-upload-actions" aria-label="Upload actions">
              <button type="button" className="command-button" onClick={() => navigateWorkspace("data-connections")}>Upload Data</button>
              {canResumePreviousUpload ? (
                <button type="button" className="secondary-command-button" onClick={onResumePreviousUpload}>Resume Previous Upload</button>
              ) : null}
            </div>
            {previousUploadSummary ? (
              <section className="previous-upload-summary" aria-label="Previous upload">
                <span>Previous upload</span>
                <strong>{previousUploadSummary.title}</strong>
                <p>{previousUploadSummary.detail}</p>
              </section>
            ) : null}
          </section>
        )}
      </section>
      {menuOverlay}
    </PageContainer>
  );
}


function ResultList({ title, items, empty = "" }) {
  const safeItems = Array.isArray(items) ? items.filter((item) => !isPlaceholderValue(item)) : [];
  if (safeItems.length === 0 && !empty) return null;
  return (
    <section className="result-list-block">
      <h3>{title}</h3>
      {safeItems.length > 0 ? (
        <ul className="compact-list">
          {safeItems.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </section>
  );
}

function compactRows(rows) {
  return (Array.isArray(rows) ? rows : []).filter((row) => row && !isPlaceholderValue(row.value));
}

function isPlaceholderValue(value) {
  if (value === null || value === undefined) return true;
  if (Array.isArray(value)) return value.length === 0;
  const text = String(value).trim();
  if (!text) return true;
  const normalized = text.toLowerCase();
  return normalized === "-"
    || normalized === "--"
    || normalized === "—"
    || normalized === "null"
    || normalized === "undefined"
    || normalized === "pending"
    || normalized === "unavailable"
    || normalized === "no traceability notes reported"
    || normalized === "no affected variables reported."
    || normalized === "not enough history";
}

function buildOverviewNextAction({ assessmentState, dataQualityReport, evidenceReport, finding }) {
  if (assessmentState.mode === "analysis_error") {
    return { label: "Return to data intake and correct the upload.", section: null, button: "" };
  }
  if (assessmentState.mode === "analysis_pending") {
    return { label: "Wait for ingestion and analysis to finish.", section: null, button: "" };
  }
  if (dataQualityReport.warnings.length > 0) {
    return { label: "Review data quality warnings.", section: "quality", button: "View Data Quality" };
  }
  if (finding.exists) {
    return { label: finding.reviewNext, section: "findings", button: "View Findings" };
  }
  if (evidenceReport.hasReplay) {
    return { label: "Open the replay when you need supporting context.", section: "evidence", button: "View Evidence" };
  }
  return { label: "Continue monitoring.", section: null, button: "" };
}

function formatOverviewStatus(mode) {
  if (mode === "analysis_error") return { label: "Error", tone: "error" };
  if (mode === "analysis_pending") return { label: "Pending", tone: "pending" };
  if (mode === "analysis_degraded_ready") return { label: "Ready With Warnings", tone: "warning" };
  if (mode === "analysis_ready") return { label: "Analysis Ready", tone: "ready" };
  return { label: "Pending", tone: "pending" };
}

function buildOverviewSummary(mode) {
  if (mode === "analysis_error") return "Analysis needs attention.";
  if (mode === "analysis_pending") return "Processing is still running.";
  if (mode === "analysis_degraded_ready") return "Warnings found, but analysis can proceed.";
  if (mode === "analysis_ready") return "Usable telemetry is available.";
  return "Upload telemetry to begin.";
}

function buildDataQualityReport(latestUploadResult, latestUploadSnapshot, findingDataQuality) {
  const result = latestUploadResult ?? {};
  const dataQuality = result.data_quality ?? {};
  const timestampProfile = result.timestamp_profile ?? {};
  const rowsLoaded = firstPresent(
    result.row_count,
    result.rows_processed,
    result.rows_loaded,
    dataQuality.rows_loaded,
    latestUploadSnapshot?.rows_processed,
    "0",
  );
  const columns = Array.isArray(result.columns) ? result.columns : [];
  const columnsDetected = firstPresent(
    result.columns_detected,
    dataQuality.columns_detected,
    latestUploadSnapshot?.columns_detected,
    columns.length || null,
    "0",
  );
  const warnings = dedupeText([
    ...(Array.isArray(dataQuality.warnings) ? dataQuality.warnings : []),
    ...(Array.isArray(timestampProfile.warnings) ? timestampProfile.warnings : []),
  ]);
  const missingValues = dedupeText([
    ...(Array.isArray(dataQuality.missing_values) ? dataQuality.missing_values : []),
    ...(Array.isArray(dataQuality.missing_value_warnings) ? dataQuality.missing_value_warnings : []),
    ...(Array.isArray(result.missing_values) ? result.missing_values : []),
    ...(Array.isArray(findingDataQuality) ? findingDataQuality : []),
  ]);
  const imputationNotes = dedupeText([
    ...(Array.isArray(dataQuality.interpolation_notes) ? dataQuality.interpolation_notes : []),
    ...(Array.isArray(dataQuality.imputation_notes) ? dataQuality.imputation_notes : []),
    dataQuality.interpolation_note,
    dataQuality.imputation_note,
  ]);
  const timestampMode = timestampProfile.first_timestamp || timestampProfile.last_timestamp
    ? `${timestampProfile.first_timestamp ?? "Unknown start"} to ${timestampProfile.last_timestamp ?? "Unknown end"}`
    : (timestampProfile.mode || result.timestamp_mode || "Row-order mode");
  const droppedRows = firstPresent(dataQuality.dropped_rows, result.dropped_rows, "0");
  return {
    rowsLoaded: formatScalar(rowsLoaded),
    signalsDetected: formatScalar(columnsDetected),
    qualityLabel: warnings.length > 0 ? "Review" : "Ready",
    summary: warnings.length > 0 ? "Review data quality before making decisions." : "CSV load is ready for review.",
    rows: compactRows([
      { label: "Rows loaded", value: formatScalar(rowsLoaded) },
      { label: "Columns detected", value: formatScalar(columnsDetected) },
      { label: "Timestamp mode", value: formatScalar(timestampMode) },
      { label: "Dropped rows", value: formatScalar(droppedRows) },
    ]),
    warnings,
    missingValues,
    imputationNotes,
  };
}

function buildEvidenceReport({ latestUploadResult, latestUploadSnapshot, latestReplayFrame, assessmentState, finding, stabilitySnapshot }) {
  const result = latestUploadResult ?? {};
  const sii = result.sii_intelligence ?? {};
  const replay = result.replay_timeline?.timeline ?? sii.replay_timeline?.timeline ?? [];
  const frame = latestReplayFrame ?? replay?.[replay.length - 1] ?? null;
  const affectedVariables = dedupeText([
    ...(Array.isArray(finding?.affectedVariables) ? finding.affectedVariables : []),
    ...(Array.isArray(finding?.variables) ? finding.variables : []),
    ...(Array.isArray(result.system_interpretation?.relationship_divergence?.affected_systems) ? result.system_interpretation.relationship_divergence.affected_systems : []),
    ...(Array.isArray(result.system_interpretation?.relationship_summary?.affected_systems) ? result.system_interpretation.relationship_summary.affected_systems : []),
    frame?.primary_driver,
    sii.primary_driver,
  ]);
  const traceability = dedupeText([
    ...(Array.isArray(finding?.supportingEvidence) ? finding.supportingEvidence : []),
    ...(Array.isArray(result.operator_report?.evidence_summary) ? result.operator_report.evidence_summary : []),
  ]);
  const confidence = normalizeReadyConfidence({
    value: finding.confidence,
    fallback: frame?.confidence ?? frame?.evidence_state?.confidence ?? sii.confidence ?? result.confidence ?? result.drift_metrics?.confidence,
    mode: assessmentState.mode,
  });
  return {
    affectedVariables: affectedVariables.length > 0 ? affectedVariables.join(", ") : "",
    confidence,
    hasReplay: replay.length > 0,
    traceability,
    replayFrameCount: replay.length,
    rows: compactRows([
      { label: "Baseline comparison", value: formatScalar(assessmentState.stability.regime) },
      { label: "Drift metrics", value: formatScalar(stabilitySnapshot.driftMagnitude) },
      { label: "Behavior has persisted", value: formatScalar(stabilitySnapshot.deformationAge) },
      { label: "Evidence confidence", value: confidence },
    ]),
  };
}

function buildTechnicalReport({ latestUploadResult, latestUploadSnapshot, assessmentState }) {
  const result = latestUploadResult ?? {};
  const processingTrace = result.processing_trace && typeof result.processing_trace === "object"
    ? Object.entries(result.processing_trace).map(([key, value]) => `${formatKey(key)}: ${formatScalar(value)}`)
    : [];
  const schemaDetection = result.schema_detection ?? result.detected_schema ?? result.domain_detection ?? null;
  const runtime = result.runtime_metadata ?? result.processing_stats ?? {};
  const sii = result.sii_intelligence ?? {};
  const replay = result.replay_timeline?.timeline ?? sii.replay_timeline?.timeline ?? [];
  const runId = firstPresent(result.run_id, result.job_id, latestUploadSnapshot?.current_upload?.job_id, latestUploadSnapshot?.job_id, "Unavailable");
  const backendWarnings = dedupeText([
    ...(Array.isArray(result.warnings) ? result.warnings : []),
    ...(Array.isArray(result.backend_warnings) ? result.backend_warnings : []),
    ...(Array.isArray(result.data_quality?.warnings) ? result.data_quality.warnings : []),
  ]);
  const traceability = dedupeText([
    ...(Array.isArray(result.operator_report?.evidence_summary) ? result.operator_report.evidence_summary : []),
    ...(Array.isArray(result.finding_evidence_chains) ? result.finding_evidence_chains : []),
    result.replay_id ? `Replay ID: ${result.replay_id}` : null,
    result.replay_reference ? `Replay reference: ${result.replay_reference}` : null,
  ]);
  return {
    rows: compactRows([
      { label: "Run ID", value: formatScalar(runId) },
      { label: "Raw analysis gate state", value: formatScalar(result.data_quality?.analysis_gate_state ?? result.analysis_gate_state ?? assessmentState.mode) },
      { label: "Schema detection", value: formatScalar(schemaDetection ? compactJson(schemaDetection) : "Unavailable") },
      { label: "Runtime metadata", value: formatScalar(Object.keys(runtime).length ? compactJson(runtime) : "Unavailable") },
      { label: "Result source", value: formatScalar(latestUploadSnapshot?.result_source ?? result.result_source ?? "Unavailable") },
      { label: "Raw replay frame count", value: replay.length ? String(replay.length) : "" },
    ]),
    traceability,
    processingTrace,
    backendWarnings,
    rawMetadata: compactJson({ latestUploadSnapshot, latestUploadResult }, 2),
  };
}

function normalizeReadyConfidence({ value, fallback, mode }) {
  const selected = !isPlaceholderValue(value) ? value : fallback;
  const numeric = Number(selected);
  if (Number.isFinite(numeric)) {
    const normalized = numeric > 1 ? numeric / 100 : numeric;
    if (normalized >= 0.82) return "High";
    if (normalized >= 0.62) return "Moderate";
    return "Low";
  }
  const text = String(selected ?? "").trim();
  if (!isPlaceholderValue(text)) return normalizeConfidenceLabel(text);
  if (mode === "analysis_ready" || mode === "analysis_degraded_ready") return "Low";
  return "Pending";
}

function firstPresent(...values) {
  return values.find((value) => value !== null && value !== undefined && String(value).trim() !== "") ?? "Unavailable";
}

function dedupeText(items) {
  return [...new Set(items.filter((item) => item !== null && item !== undefined).map((item) => formatScalar(item)).filter(Boolean))];
}

function formatScalar(value) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "Unavailable";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return compactJson(value);
  return String(value);
}

function compactJson(value, space = 0) {
  try {
    return JSON.stringify(value, null, space);
  } catch {
    return "Unavailable";
  }
}

function formatKey(value) {
  return String(value ?? "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
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

function buildPreviousUploadSummary(persistedLatestUpload, previousUploadHistory = []) {
  const latest = persistedLatestUpload ?? null;
  const historyEntry = Array.isArray(previousUploadHistory) ? previousUploadHistory[0] : null;
  const title = latest?.filename ?? historyEntry?.filename ?? latest?.jobId ?? historyEntry?.job_id ?? "Previous upload available";
  const processedAt = latest?.processedAt ?? historyEntry?.last_processed_at ?? historyEntry?.processed_at ?? null;
  if (!latest && !historyEntry) return null;
  return {
    title: formatScalar(title),
    detail: [
      processedAt ? "Processed " + formatScalar(processedAt) : null,
    ].filter(Boolean).join(" - ") || "Available from recent history.",
  };
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
    confidence: normalizeConfidenceLabel(interpretation.confidence),
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
  const analysisState = resolveAnalysisGateState({ latestUploadSnapshot, latestUploadResult });
  const observationsExist = hasCompletedObservations({ latestUploadResult, latestReplayFrame, stabilitySnapshot });
  const dataConditions = collectDataConditions(latestUploadResult);

  if (!interpretation.hasTelemetry) {
    return {
      mode: "awaiting_telemetry",
      headerStatus: "Awaiting Telemetry",
      dataPosture: "No telemetry attached yet.",
      finding: {
        ...fallbackFinding,
        exists: false,
        title: "No Analysis",
        status: "Not Assessed",
        confidence: "Pending",
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

  if (analysisState === "ERROR") {
    const errorMessage = String(latestUploadResult?.error ?? latestUploadResult?.message ?? latestUploadSnapshot?.message ?? "").trim();
    return {
      mode: "analysis_error",
      headerStatus: "Analysis Error",
      dataPosture: "Uploaded telemetry cannot be trusted until the error is resolved.",
      finding: {
        ...fallbackFinding,
        exists: false,
        title: "Analysis Error",
        status: "Error",
        confidence: "Pending",
        summary: errorMessage || "Analysis could not complete for the uploaded telemetry.",
        whyItMatters: "The upload cannot be used for operator review until the error is resolved.",
        reviewNext: "Return to data intake and correct the upload.",
        emptyState: {
          title: "Analysis Error",
          subtitle: "Upload requires attention.",
          detail: errorMessage || "Return to data intake and correct the upload.",
        },
      },
      stability: {
        ...stabilitySnapshot,
        deformationAge: "Not enough history",
      },
    };
  }

  if (analysisState === "PENDING") {
    return {
      mode: "analysis_pending",
      headerStatus: "Analysis Pending",
      dataPosture: "Telemetry is present, but backend analysis is still pending.",
      finding: {
        ...fallbackFinding,
        exists: false,
        title: "Analysis Pending",
        status: "Pending",
        confidence: "Pending",
        summary: "Backend processing has not finished for this upload.",
        whyItMatters: "Findings are blocked until the backend reports READY or DEGRADED_READY.",
        reviewNext: "Wait for ingestion and analysis to finish.",
        emptyState: {
          title: "Analysis Pending",
          subtitle: "Findings are not available yet.",
          detail: "Wait for ingestion and analysis to finish.",
        },
      },
      stability: {
        ...stabilitySnapshot,
        activeObservations: 0,
      },
    };
  }

  const degraded = analysisState === "DEGRADED_READY";
  if (!observationsExist || !fallbackFinding.exists) {
    return {
      mode: degraded ? "analysis_degraded_ready" : "analysis_ready",
      headerStatus: degraded ? "Ready With Warnings" : "Analysis Ready",
      dataPosture: degraded ? "Uploaded telemetry is usable with data-quality warnings." : "Uploaded telemetry is usable for analysis.",
      finding: {
        ...fallbackFinding,
        exists: false,
        title: degraded ? "Ready With Warnings" : "Analysis Ready",
        status: degraded ? "Warnings Present" : "No Findings",
        confidence: normalizeConfidenceLabel(fallbackFinding.confidence),
        summary: degraded ? "Usable telemetry is available with warnings." : "Usable telemetry is available. No findings are currently flagged.",
        whyItMatters: degraded
          ? "Warnings may limit confidence, but they do not block review of available evidence."
          : "The uploaded dataset passed analysis readiness without a flagged structural finding.",
        reviewNext: degraded ? "Review data quality warnings before acting on findings." : "Continue monitoring or upload more telemetry.",
        emptyState: {
          title: degraded ? "Ready With Warnings" : "Analysis Ready",
          subtitle: degraded ? "Usable telemetry has data-quality warnings." : "No findings are currently flagged.",
          detail: degraded ? "Review the warnings below before making operational decisions." : "Continue monitoring or upload more telemetry.",
        },
        dataQuality: {
          ...fallbackFinding.dataQuality,
          missingRecentValues: dataConditions,
        },
      },
      stability: stabilitySnapshot,
    };
  }

  return {
    mode: degraded ? "analysis_degraded_ready" : "analysis_ready",
    headerStatus: degraded ? "Ready With Warnings" : "Analysis Ready",
    dataPosture: degraded ? "Uploaded telemetry is usable with data-quality warnings." : "Uploaded telemetry is usable for analysis.",
    finding: fallbackFinding,
    stability: stabilitySnapshot,
  };
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
  const endedAt = frame?.timestamp_end
    ?? frame?.timestamp
    ?? latestUploadResult?.timestamp_profile?.last_timestamp
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
    deformationAge: durationLabel(startedAt, endedAt),
  };
}

function collectDataConditions(latestUploadResult) {
  const result = latestUploadResult ?? {};
  const dataQualityWarnings = Array.isArray(result?.data_quality?.warnings) ? result.data_quality.warnings : [];
  const timestampWarnings = Array.isArray(result?.timestamp_profile?.warnings) ? result.timestamp_profile.warnings : [];
  return [...new Set([...dataQualityWarnings, ...timestampWarnings].filter(Boolean).map(String))];
}

function durationLabel(startValue, endValue) {
  if (!startValue || !endValue) return "Not enough history";
  const start = new Date(startValue).getTime();
  const end = new Date(endValue).getTime();
  const ms = end - start;
  if (!Number.isFinite(ms) || ms <= 0) return "Not enough history";
  const minutes = Math.round(ms / 60000);
  if (minutes < 60) return String(minutes) + "m";
  const hours = Math.round(ms / 3600000);
  if (hours < 48) return String(hours) + "h";
  return String(Math.round(hours / 24)) + "d";
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
  const analysisState = resolveAnalysisGateState({ latestUploadSnapshot, latestUploadResult });

  if (analysisState === "PENDING" || (hasUploadInFlight && analysisState !== "READY" && analysisState !== "DEGRADED_READY")) {
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
  if (lastUpdate) return { tone: "online", label: "Telemetry usable" };
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
  const text = String(value ?? "").trim().toLowerCase();
  if (text.includes("high")) return "High";
  if (text.includes("moderate") || text.includes("medium")) return "Moderate";
  if (text.includes("low")) return "Low";
  if (text.includes("pending") || text.includes("unavailable") || text === EMPTY_VALUE.toLowerCase()) return "Pending";
  const number = Number(value);
  if (!Number.isFinite(number) || (hasDriftState && number <= 0)) return "Pending";
  if (number <= 0) return "Pending";
  const percent = number <= 1 ? number * 100 : number;
  if (percent >= 82) return "High";
  if (percent >= 62) return "Moderate";
  return "Low";
}

function normalizeConfidenceLabel(value) {
  return formatConfidence(value);
}

function resolveAnalysisGateState({ latestUploadSnapshot, latestUploadResult }) {
  const candidates = [
    latestUploadResult?.data_quality?.analysis_gate_state,
    latestUploadResult?.analysis_gate_state,
    latestUploadResult?.operator_report?.data_readiness,
    latestUploadSnapshot?.latest_result?.data_quality?.analysis_gate_state,
    latestUploadSnapshot?.data_quality?.analysis_gate_state,
  ];
  const explicit = candidates.map(normalizeGateToken).find(Boolean);
  if (explicit) return explicit;

  const status = normalizeGateToken(
    latestUploadResult?.processing_state
      ?? latestUploadResult?.status
      ?? latestUploadSnapshot?.status
      ?? latestUploadSnapshot?.processing_state
      ?? "",
  );
  if (status === "ERROR" || status === "PENDING") return status;

  const completed = latestUploadResult?.processing_trace?.sii_completed === true
    || latestUploadResult?.sii_completed === true
    || latestUploadSnapshot?.sii_completed === true
    || status === "READY";
  if (!completed) return "PENDING";

  const warnings = collectDataConditions(latestUploadResult);
  return warnings.length > 0 ? "DEGRADED_READY" : "READY";
}

function normalizeGateToken(value) {
  const token = String(value ?? "").trim().toUpperCase().replaceAll("-", "_").replaceAll(" ", "_");
  if (!token) return null;
  if (["READY", "COMPLETE", "COMPLETED", "SUCCESS", "READY_WITH_FINDINGS", "READY_READY"].includes(token)) return "READY";
  if (["DEGRADED_READY", "NEEDS_REVIEW", "WARNING", "WARNINGS_PRESENT", "READY_WITH_WARNINGS"].includes(token)) return "DEGRADED_READY";
  if (["PENDING", "QUEUED", "PROCESSING", "RUNNING", "RUNNING_SII", "PARSING", "BASELINE_MODELING", "STRUCTURAL_SCORING", "GENERATING_REPLAY", "COGNITION_READY", "WRITING_STATE"].includes(token)) return "PENDING";
  if (["ERROR", "FAILED", "FAILURE", "VALIDATION_ERROR", "NOT_READY"].includes(token)) return "ERROR";
  return null;
}

function describesDrift(value) {
  const text = String(value ?? "").toLowerCase();
  return text.includes("drift") || text.includes("degrad") || text.includes("unstable") || text.includes("watch") || text.includes("alert");
}

function describesStable(value) {
  const text = String(value ?? "").trim().toLowerCase();
  return text === "stable" || text === "normal" || text === "monitoring" || text === "within range";
}
