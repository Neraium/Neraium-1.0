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
  const findingBriefing = buildFindingBriefing(finding, evidenceReport);
  const technicalReport = buildTechnicalReport({ latestUploadResult, latestUploadSnapshot, assessmentState });
  const overviewSummary = buildOverviewSummary(assessmentState.mode);
  const healthMetrics = buildHealthMetrics({ assessmentState, finding });
  const whatChangedToday = buildWhatChangedToday({ finding, assessmentState, evidenceReport });
  const actionGroups = buildActionGroups({ finding, evidenceReport });
  const overviewNextAction = buildOverviewNextAction({ assessmentState, dataQualityReport, evidenceReport, finding });
  const visibleWarnings = showAllWarnings ? dataQualityReport.warnings : dataQualityReport.warnings.slice(0, 3);
  const resultSections = [
    { id: "overview", label: "Health" },
    { id: "findings", label: "Issues" },
    { id: "story", label: "Evidence" },
    { id: "actions", label: "Actions" },
    { id: "quality", label: "Data Quality" },
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
                Telemetry Intake
              </button>
            </li>
            {resultSections.map((section) => (
              <li key={section.id}>
                <button
                  type="button"
                  className="system-gate__settings-action"
                  onClick={() => {
                    setActiveResultSection(section.id);
                    setMenuOpen(false);
                  }}
                >
                  {section.label}
                </button>
              </li>
            ))}
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
        <nav className="result-section-tabs" aria-label="Analysis result sections">
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
            <section className="post-upload-overview" aria-label="Analysis overview">
              <div className="post-upload-overview__header">
                <p className="section-token">System Status</p>
                <span className={"post-upload-status post-upload-status--" + overviewStatus.tone}>{overviewStatus.label}</span>
                <h1>{overviewSummary}</h1>
                <p>{assessmentState.dataPosture}</p>
              </div>

              <div className="post-upload-metrics" aria-label="Building and system health">
                {healthMetrics.map((item) => (
                  <article className="post-upload-metric" key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </article>
                ))}
              </div>

              <section className="post-upload-review-next" aria-label="What changed today">
                <span>What changed today?</span>
                <strong>{whatChangedToday}</strong>
              </section>

              <section className="post-upload-review-next" aria-label="Recommended priorities">
                <span>Recommended priorities</span>
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
            <section className="post-upload-section" aria-label="Issues">
              <div className="post-upload-section__header">
                <p className="section-token">Issues</p>
                <h2>{finding.exists ? finding.title : "No operational issues found."}</h2>
              </div>
              {finding.exists ? (
                <article className="finding-card finding-briefing">
                  <div className="finding-card__topline">
                    <h3>{finding.title}</h3>
                    <div className="finding-card__status-row" aria-label="Issue status">
                      <span>Severity {formatIssueSeverity(finding.status)}</span>
                      <span>Confidence {finding.confidence}</span>
                    </div>
                  </div>
                  <section className="result-list-block" aria-label="Summary">
                    <h3>Summary</h3>
                    {findingBriefing.summary.map((line) => <p key={line}>{line}</p>)}
                  </section>
                  <ResultList title="Possible Operational Causes" items={findingBriefing.possibleCauses} />
                  <ResultList title="Relationships Involved" items={findingBriefing.relationships} />
                  <ResultList title="Recommended Actions" items={findingBriefing.investigation} />
                  <details className="technical-details-panel finding-evidence-drawer">
                    <summary>Advanced Details</summary>
                    <dl className="result-detail-grid">
                      {evidenceReport.rows.map((item) => (
                        <div key={item.label}>
                          <dt>{item.label}</dt>
                          <dd>{item.value}</dd>
                        </div>
                      ))}
                    </dl>
                    <ResultList title="Raw Evidence" items={evidenceReport.traceability} empty="No supporting evidence reported." />
                  </details>
                  {canReviewFindings ? (
                    <button type="button" className="command-button" onClick={() => navigateWorkspace("observation-center")}>View Issues</button>
                  ) : null}
                </article>
              ) : (
                <article className="finding-empty-state">
                  <h3>No operational issues found.</h3>
                  <p>Telemetry analyzed successfully. Data-quality warnings are available separately if an engineer needs them.</p>
                  <section className="post-upload-review-next" aria-label="Recommended next checks">
                    <span>Recommended next check</span>
                    <strong>{dataQualityReport.warnings.length > 0 ? "Review missing sensor values and timestamp quality." : "Continue monitoring normal equipment behavior."}</strong>
                  </section>
                </article>
              )}
            </section>
          ) : null}

          {activeResultSection === "story" ? (
            <section className="post-upload-section" aria-label="Evidence">
              <div className="post-upload-section__header">
                <p className="section-token">Evidence</p>
                <h2>{finding.exists ? "Review the evidence behind this issue." : "Review behavior evidence for this telemetry window."}</h2>
              </div>
              <details className="technical-details-panel finding-evidence-drawer">
                <summary>Advanced Details</summary>
                <dl className="result-detail-grid">
                  {evidenceReport.rows.map((item) => (
                    <div key={item.label}>
                      <dt>{item.label}</dt>
                      <dd>{item.value}</dd>
                    </div>
                  ))}
                </dl>
                <ResultList title="Raw Evidence" items={evidenceReport.traceability} empty="No supporting evidence reported." />
              </details>
              <section className="post-upload-review-next" aria-label="Recommended next checks">
                <span>What to inspect next</span>
                <strong>{finding.exists ? finding.reviewNext : "Review supporting evidence when an engineer needs the operating narrative."}</strong>
              </section>
            </section>
          ) : null}

          {activeResultSection === "actions" ? (
            <section className="post-upload-section" aria-label="Actions">
              <div className="post-upload-section__header">
                <p className="section-token">Actions</p>
                <h2>Inspection checklist</h2>
              </div>
              <div className="action-checklist-groups">
                {actionGroups.map((group) => (
                  <section className="action-checklist-group" key={group.equipment}>
                    <h3>{group.equipment}</h3>
                    <div className="system-story-checklist">
                      {group.items.map((item) => (
                        <label key={item}>
                          <input type="checkbox" />
                          <span>{item}</span>
                        </label>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
              <label className="action-note-field">
                <span>Inspection notes</span>
                <textarea rows={4} placeholder="Add field notes or repair outcome" />
              </label>
              <section className="post-upload-review-next" aria-label="Did the repair fix it">
                <span>Did the repair fix it?</span>
                <strong>After inspection, analyze a new telemetry file and compare the operating pattern.</strong>
              </section>
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
              <ResultList title="Top warnings" items={visibleWarnings} empty="No data quality warnings reported." />
              {dataQualityReport.warnings.length > 3 ? (
                <button type="button" className="secondary-command-button post-upload-inline-action" onClick={() => setShowAllWarnings((value) => !value)}>
                  {showAllWarnings ? "Show top 3" : `Show all ${dataQualityReport.warnings.length}`}
                </button>
              ) : null}
              <ResultList title="Missing data summary" items={dataQualityReport.missingValues} />
              <ResultList title="Filled gaps" items={dataQualityReport.imputationNotes} />
              <section className="post-upload-review-next" aria-label="Recommended next checks">
                <span>Recommended next check</span>
                <strong>{dataQualityReport.warnings.length > 0 ? "Fix the highest-volume missing telemetry before trend review." : "Use the Issues page to confirm there are no active equipment concerns."}</strong>
              </section>
            </section>
          ) : null}

          {activeResultSection === "technical" ? (
            <section className="post-upload-section" aria-label="Technical diagnostics">
              <div className="post-upload-section__header">
                <p className="section-token">Technical</p>
                <h2>Technical details</h2>
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
              <section className="post-upload-review-next" aria-label="Recommended next checks">
                <span>Recommended next check</span>
                <strong>Return to Health unless a support engineer requested these details.</strong>
              </section>
            </section>
          ) : null}
        </div>
          </>
        ) : (
          <section className="post-upload-empty" aria-label="No telemetry state">
            <div className="post-upload-overview__header">
              <span className="post-upload-status post-upload-status--pending">No telemetry source</span>
              <h1>Start operational intelligence</h1>
              <p>Select a telemetry source to learn behavior, monitor relationships, and review operational changes.</p>
            </div>
            <div className="post-upload-actions" aria-label="Telemetry actions">
              <button type="button" className="command-button" onClick={() => navigateWorkspace("data-connections")}>Analyze New Telemetry</button>
              {canResumePreviousUpload ? (
                <button type="button" className="secondary-command-button" onClick={onResumePreviousUpload}>Resume Previous Analysis</button>
              ) : null}
            </div>
            {previousUploadSummary ? (
              <section className="previous-upload-summary" aria-label="Previous analysis">
                <span>Previous analysis</span>
                <strong>{previousUploadSummary.title}</strong>
                <p>{previousUploadSummary.detail}</p>
              </section>
            ) : null}
            <section className="post-upload-review-next" aria-label="Recommended next checks">
              <span>Recommended next check</span>
              <strong>Analyze the latest live stream, historian export, connector feed, or telemetry import from the systems you want to review.</strong>
            </section>
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

function buildFindingBriefing(finding, evidenceReport) {
  return {
    summary: buildFindingSummaryLines(finding),
    possibleCauses: buildPossibleOperationalCauses(finding, evidenceReport),
    relationships: buildFindingRelationships(finding, evidenceReport),
    investigation: buildRecommendedInvestigation(finding, evidenceReport),
  };
}

function buildFindingSummaryLines(finding) {
  const lines = splitSentences(finding?.summary).slice(0, 2);
  return lines.length ? lines : ["The subsystem no longer follows its historical operating pattern."];
}

function buildPossibleOperationalCauses(finding, evidenceReport) {
  const text = briefingSearchText(finding, evidenceReport);
  const causes = [];
  if (/filter|pressure|dp|differential/.test(text)) causes.push("Filter loading", "Increased hydraulic resistance");
  if (/pump|speed|vfd|flow/.test(text)) causes.push("Pump operating point changed", "VFD control adjustment");
  if (/valve|damper/.test(text)) causes.push("Valve position changed");
  if (/temperature|cool|chw|thermal/.test(text)) causes.push("Heat transfer changed", "Process load changed");
  if (/sensor|missing|timestamp|telemetry/.test(text)) causes.push("Sensor calibration drift", "Telemetry quality issue");
  causes.push("Demand shift", "Recent maintenance activity", "Operating setpoint changed");
  return dedupeText(causes).slice(0, 6);
}

function buildFindingRelationships(finding, evidenceReport) {
  const supplied = [
    ...(Array.isArray(finding?.relationships) ? finding.relationships : []),
    ...(Array.isArray(finding?.affectedRelationships) ? finding.affectedRelationships : []),
  ].map(formatRelationshipLabel).filter(Boolean);
  if (supplied.length) return dedupeText(supplied).slice(0, 6);

  const variables = dedupeText([
    ...(Array.isArray(finding?.affectedVariables) ? finding.affectedVariables : []),
    ...(Array.isArray(finding?.variables) ? finding.variables : []),
    ...String(evidenceReport?.affectedVariables ?? "").split(","),
  ].map(cleanSignalLabel)).filter(Boolean);

  const relationships = [];
  for (let index = 0; index < variables.length - 1 && relationships.length < 6; index += 1) {
    relationships.push(variables[index] + " ↔ " + variables[index + 1]);
  }
  return relationships;
}

function buildRecommendedInvestigation(finding, evidenceReport) {
  const text = briefingSearchText(finding, evidenceReport);
  if (/filter|pressure|dp|differential|pump|flow|valve|vfd/.test(text)) {
    return [
      "Review filter differential pressure trend",
      "Verify valve positions",
      "Compare with recent maintenance activity",
    ];
  }
  if (/temperature|cool|chw|thermal/.test(text)) {
    return [
      "Review temperature approach trend",
      "Verify equipment staging and valve positions",
      "Compare with recent load changes",
    ];
  }
  return dedupeText([
    cleanSentence(finding?.reviewNext),
    "Review affected signal trends",
    "Verify current operating mode and setpoints",
    "Compare with recent maintenance activity",
  ]).slice(0, 3);
}

function briefingSearchText(finding, evidenceReport) {
  return String([
    finding?.title,
    finding?.summary,
    finding?.reviewNext,
    evidenceReport?.affectedVariables,
    ...(Array.isArray(finding?.supportingEvidence) ? finding.supportingEvidence : []),
  ].filter(Boolean).join(" ")).toLowerCase();
}

function splitSentences(value) {
  const text = cleanSentence(value);
  if (!text) return [];
  return (text.match(/[^.!?]+[.!?]?/g) ?? [text]).map(cleanSentence).filter(Boolean);
}

function cleanSentence(value) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return /[.!?]$/.test(text) ? text : text + ".";
}

function cleanSignalLabel(value) {
  return String(value ?? "").replace(/^Affected variables:\s*/i, "").replace(/[.]/g, "").replace(/_/g, " ").trim();
}

function formatRelationshipLabel(value) {
  return cleanSignalLabel(value)
    .replace(/\s*<->\s*/g, " ↔ ")
    .replace(/\s+\/\s+/g, " ↔ ")
    .replace(/\s+vs\.?\s+/gi, " ↔ ");
}

function buildHealthMetrics({ assessmentState, finding }) {
  const issueCount = finding?.exists ? 1 : 0;
  const criticalCount = issueCount && /critical|alert|error|unstable|needs action/i.test(String(finding?.status ?? "")) ? 1 : 0;
  const reviewCount = issueCount && criticalCount === 0 ? 1 : 0;
  const normalCount = Math.max(0, 1 - issueCount);
  return compactRows([
    { label: "Systems normal", value: String(normalCount) },
    { label: "Need review", value: String(reviewCount) },
    { label: "Critical issues", value: String(criticalCount) },
    { label: "Health status", value: formatOverviewStatus(assessmentState.mode).label },
  ]);
}

function buildWhatChangedToday({ finding, assessmentState, evidenceReport }) {
  if (assessmentState.mode === "analysis_error") return "Telemetry could not be analyzed for this system.";
  if (assessmentState.mode === "analysis_pending") return "Processing telemetry and building the system story.";
  if (finding?.exists) return finding.summary || finding.title || "Operating behavior changed from historical behavior.";
  if (evidenceReport?.affectedVariables) return `${evidenceReport.affectedVariables} remained inside the expected operating pattern.`;
  return "Telemetry analyzed successfully. No operational issue was detected.";
}

function formatIssueSeverity(status) {
  const text = String(status ?? "").trim();
  if (!text) return "Review";
  if (/critical|alert|unstable|needs action|error/i.test(text)) return "Critical";
  if (/warning|degraded|watch|review|change/i.test(text)) return "Review";
  if (/normal|stable|no findings/i.test(text)) return "Normal";
  return text;
}

function buildActionGroups({ finding, evidenceReport }) {
  const equipmentText = String(evidenceReport?.affectedVariables || finding?.title || "Building system");
  const equipment = inferEquipmentLabel(equipmentText);
  const text = `${equipmentText} ${finding?.summary ?? ""} ${finding?.reviewNext ?? ""}`.toLowerCase();
  const checks = ["Compare BAS values", "Verify sensor calibration"];
  if (text.includes("valve")) checks.push("Review valve position");
  if (text.includes("pump") || text.includes("speed") || text.includes("flow")) checks.push("Check pump speed vs flow");
  if (text.includes("filter") || text.includes("pressure")) checks.push("Inspect filter pressure");
  checks.push("Review recent maintenance");
  return [{ equipment, items: [...new Set(checks)] }];
}

function inferEquipmentLabel(text) {
  const value = String(text ?? "").toLowerCase();
  if (value.includes("pump")) return "Pumps";
  if (value.includes("valve")) return "Valves";
  if (value.includes("filter")) return "Filters";
  if (value.includes("chw") || value.includes("chiller") || value.includes("temperature")) return "Chilled water loop";
  if (value.includes("flow")) return "Flow loop";
  return "Building system";
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
    return { label: "Return to telemetry intake and correct the source.", section: null, button: "" };
  }
  if (assessmentState.mode === "analysis_pending") {
    return { label: "Wait for ingestion and analysis to finish.", section: null, button: "" };
  }
  if (finding.exists) {
    return { label: finding.reviewNext, section: "findings", button: "View Issues" };
  }
  if (dataQualityReport.warnings.length > 0) {
    return { label: "Review missing sensor values before relying on trend analysis.", section: "quality", button: "View Data Quality" };
  }
  if (evidenceReport.hasReplay) {
    return { label: "Review supporting evidence when an engineer needs the operating narrative.", section: "story", button: "Review Details" };
  }
  return { label: "Continue monitoring normal equipment behavior.", section: null, button: "" };
}

function formatOverviewStatus(mode) {
  if (mode === "analysis_error") return { label: "Needs Attention", tone: "error" };
  if (mode === "analysis_pending") return { label: "Processing", tone: "pending" };
  if (mode === "analysis_degraded_ready") return { label: "Ready with warnings", tone: "warning" };
  if (mode === "analysis_ready") return { label: "Ready", tone: "ready" };
  return { label: "Pending", tone: "pending" };
}

function buildOverviewSummary(mode) {
  if (mode === "analysis_error") return "Telemetry needs attention.";
  if (mode === "analysis_pending") return "Telemetry is still processing.";
  if (mode === "analysis_degraded_ready") return "Telemetry analyzed with warnings.";
  if (mode === "analysis_ready") return "Telemetry analyzed successfully.";
  return "Analyze telemetry to begin.";
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
    summary: warnings.length > 0 ? "Review data quality before making decisions." : "Telemetry file is ready for review.",
    rows: compactRows([
      { label: "Rows loaded", value: formatScalar(rowsLoaded) },
      { label: "Signals detected", value: formatScalar(columnsDetected) },
      { label: "Time range", value: formatScalar(timestampMode) },
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
      { label: "Historical comparison", value: formatScalar(assessmentState.stability.regime) },
      { label: "Change strength", value: formatScalar(stabilitySnapshot.driftMagnitude) },
      { label: "Operating pattern duration", value: formatScalar(stabilitySnapshot.deformationAge) },
      { label: "Evidence readiness", value: confidence },
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
  const runId = firstPresent(result.run_id, result.job_id, latestUploadSnapshot?.current_upload?.job_id, latestUploadSnapshot?.job_id, "Unavailable");
  const backendWarnings = dedupeText([
    ...(Array.isArray(result.warnings) ? result.warnings : []),
    ...(Array.isArray(result.backend_warnings) ? result.backend_warnings : []),
    ...(Array.isArray(result.data_quality?.warnings) ? result.data_quality.warnings : []),
  ]);
  const traceability = dedupeText([
    ...(Array.isArray(result.operator_report?.evidence_summary) ? result.operator_report.evidence_summary : []),
    ...(Array.isArray(result.finding_evidence_chains) ? result.finding_evidence_chains : []),
  ]);
  return {
    rows: compactRows([
      { label: "Run ID", value: formatScalar(runId) },
      { label: "Raw data readiness state", value: formatScalar(result.data_quality?.analysis_gate_state ?? result.analysis_gate_state ?? assessmentState.mode) },
      { label: "Schema detection", value: formatScalar(schemaDetection ? compactJson(schemaDetection) : "Unavailable") },
      { label: "Runtime metadata", value: formatScalar(Object.keys(runtime).length ? compactJson(runtime) : "Unavailable") },
      { label: "Result source", value: formatScalar(latestUploadSnapshot?.result_source ?? result.result_source ?? "Unavailable") },
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
  const title = latest?.filename ?? historyEntry?.filename ?? latest?.jobId ?? historyEntry?.job_id ?? "Previous analysis available";
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
    ...(groups.missingBaselineValues || []).map((item) => `Missing reference values: ${item}`),
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
    summary: exists ? interpretation.relationshipSummary.text : "No current issues.",
    whyItMatters: exists ? interpretation.relationshipSummary.text : "Telemetry is being monitored.",
    reviewNext: interpretation.nextStep,
    emptyState: {
      title: "No current issues.",
      subtitle: "Telemetry is being monitored.",
      detail: "No equipment issues detected.",
    },
    evidenceButtonLabel: "Review Details",
    supportingEvidence: [],
    dataQuality: {
      missingBaselineValues: [],
      missingRecentValues: dataConditions || [],
      unavailableTelemetry: [],
    },
    technicalDetails: [
      { label: "Change strength", value: stabilitySnapshot.driftMagnitude },
      { label: "Operating pattern duration", value: stabilitySnapshot.deformationAge },
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
      dataPosture: "No telemetry source connected yet.",
      finding: {
        ...fallbackFinding,
        exists: false,
        title: "No analysis",
        status: "Not Assessed",
        confidence: "Pending",
        summary: "Analyze telemetry to generate a system review.",
        whyItMatters: "Analyze telemetry to generate a system review.",
        reviewNext: "Analyze telemetry to generate a system review.",
        emptyState: {
          title: "No analysis",
          subtitle: "Analyze telemetry to generate a system review.",
          detail: "Analyze telemetry to generate a system review.",
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
      dataPosture: "Telemetry cannot be trusted until the error is resolved.",
      finding: {
        ...fallbackFinding,
        exists: false,
        title: "Analysis Error",
        status: "Error",
        confidence: "Pending",
        summary: errorMessage || "Analysis could not complete for the selected telemetry.",
        whyItMatters: "The telemetry source cannot be used for operator review until the error is resolved.",
        reviewNext: "Return to telemetry intake and correct the source.",
        emptyState: {
          title: "Analysis Error",
          subtitle: "Telemetry source requires attention.",
          detail: errorMessage || "Return to telemetry intake and correct the source.",
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
      headerStatus: "Analysis running",
      dataPosture: "Telemetry is present, but analysis is still running.",
      finding: {
        ...fallbackFinding,
        exists: false,
        title: "Analysis running",
        status: "Pending",
        confidence: "Pending",
        summary: "Processing has not finished for this telemetry source.",
        whyItMatters: "Issues appear when data readiness is complete.",
        reviewNext: "Wait for ingestion and analysis to finish.",
        emptyState: {
          title: "Analysis running",
          subtitle: "Issues are not available yet.",
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
      headerStatus: degraded ? "Ready with warnings" : "Analysis ready",
      dataPosture: degraded ? "Telemetry is usable with data-quality warnings." : "Telemetry is ready for review.",
      finding: {
        ...fallbackFinding,
        exists: false,
        title: degraded ? "Ready with warnings" : "Analysis ready",
        status: degraded ? "Warnings Present" : "No issues",
        confidence: normalizeConfidenceLabel(fallbackFinding.confidence),
        summary: degraded ? "Usable telemetry is available with warnings." : "Usable telemetry is available. No operational issues are currently flagged.",
        whyItMatters: degraded
          ? "Warnings may limit confidence, but they do not block review of available operating patterns."
          : "Telemetry is ready and no operational issue is flagged.",
        reviewNext: degraded ? "Review data quality warnings before acting on issues." : "Continue monitoring or analyze another telemetry source.",
        emptyState: {
          title: degraded ? "Ready with warnings" : "Analysis ready",
          subtitle: degraded ? "Usable telemetry has data-quality warnings." : "No operational issues are currently flagged.",
          detail: degraded ? "Review the warnings below before making operational decisions." : "Continue monitoring or analyze another telemetry source.",
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
    headerStatus: degraded ? "Ready with warnings" : "Analysis ready",
    dataPosture: degraded ? "Telemetry is usable with data-quality warnings." : "Telemetry is ready for review.",
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
      ? "Review supporting evidence."
      : "Check technical details.",
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
      nextStep: "Upload data to begin.",
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
  const processingLike = ["processing", "queued", "pending", "running_sii", "parsing", "baseline_modeling", "structural_scoring", "saving_result", "cognition_ready", "writing_state"];
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
    "System behavior",
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
    nextStep: canShowEvidenceBackedFinding ? "Review supporting evidence." : (hasDriftState ? "Review supporting evidence." : "Continue monitoring."),
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
  if (text.includes("replay")) return { label: "Analysis finalizing", tone: "syncing" };
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
