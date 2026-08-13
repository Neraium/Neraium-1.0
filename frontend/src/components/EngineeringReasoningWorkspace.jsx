import React, { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { buildEngineeringReasoningModel, buildEngineeringReasoningModelsFromEvidenceRuns, buildFacilityLabelContext } from "../viewModels/engineeringReasoning";
import { analysisBelongsToBaseline } from "../viewModels/baselineSelection";
import { deriveEscalationReadiness, deriveWorkspacePresentationState } from "../viewModels/operationsBrief";
import { feedbackForReviewAction, normalizeReviewRecords, reviewRecordFor, reviewRecordFromWorkflow } from "../viewModels/findingReviewState";
import { fetchFinding, fetchFindings, isFindingApiUnavailable, patchFindingWorkflow, postFindingFeedback, resolveFinding } from "../services/api/findingsApi";
import FirstBaselineExperience, { SupportedFormats, WorkflowSteps } from "./FirstBaselineExperience";
import ConfidenceTierChip from "./engineering/ConfidenceTierChip";
import EvidencePackageExport from "./engineering/EvidencePackageExport";
import FindingSummary from "./engineering/FindingSummary";
import GlobalAssetSearch from "./engineering/GlobalAssetSearch";
import PortfolioWorkspace from "./engineering/PortfolioWorkspace";
import OperationsBrief from "./engineering/OperationsBrief";
import { EvidenceRecordWorkspace, FindingReviewWorkspace, InvestigationWorkspace } from "./engineering/FindingCaseWorkspaces";
import TraceTimeline from "./engineering/TraceTimeline";
import "../styles/engineering-reasoning.css";

const WorkQueueWorkspace = lazy(() => import("./work/WorkQueueWorkspace"));

const ROUTES = {
  portfolio: "/portfolio",
  site: "/sites/current",
  systems: "/systems",
  findings: "/findings",
  finding: "/findings",
  work: "/work",
  investigation: "/investigations",
  investigations: "/investigations",
  evidence: "/evidence",
  trace: "/trace",
};

function routeFromLocation() {
  if (typeof window === "undefined") return "portfolio";
  const path = window.location.pathname;
  if (path.startsWith("/systems/")) return "system";
  if (path === "/systems") return "systems";
  if (path.startsWith("/sites/")) return "site";
  if (path.startsWith("/findings/")) return "finding";
  if (path === "/findings") return "findings";
  if (path === "/work" || path.startsWith("/work/")) return "work";
  if (path === "/investigations") return "investigations";
  if (path.startsWith("/investigations")) return "investigation";
  if (path.startsWith("/evidence")) return "evidence";
  if (path.startsWith("/trace")) return "trace";
  if (path === "/portfolio") return "portfolio";
  return "site";
}

function pathIdentity(prefixes) {
  if (typeof window === "undefined") return "";
  const parts = window.location.pathname.split("/").filter(Boolean);
  return prefixes.includes(parts[0]) && parts[1] ? decodeURIComponent(parts[1]) : "";
}

function runIdentity(model, finding) {
  return finding?.runId ?? model?.result?.run_id ?? model?.result?.job_id ?? model?.result?.upload_id ?? null;
}

function statusClass(status) {
  return String(status || "Evidence insufficient").toLowerCase().replace(/\s+/g, "-");
}

function WorkspaceStateNotice({ state, onPrimary }) {
  const [formatsVisible, setFormatsVisible] = useState(false);
  const baselineNeeded = state.key === "noDataset";
  return (
    <section className={"operational-empty operational-empty--" + state.key} aria-labelledby={"workspace-state-" + state.key + "-title"} data-testid={"workspace-state-" + state.key}>
      <span className="operational-empty__mark" aria-hidden="true" />
      <span className="operational-label">Operations Brief · {state.status}</span>
      <h1 id={"workspace-state-" + state.key + "-title"}>{state.headline}</h1>
      <p>{state.body}</p>
      <div className="operational-empty__actions">
        <button type="button" className="forensic-button" onClick={onPrimary}>{state.action}</button>
        {baselineNeeded ? (
          <button type="button" className="forensic-button forensic-button--secondary" aria-expanded={formatsVisible} onClick={() => setFormatsVisible((value) => !value)}>View supported formats</button>
        ) : null}
      </div>
      {baselineNeeded ? <SupportedFormats visible={formatsVisible} /> : null}
      {baselineNeeded ? <WorkflowSteps /> : null}
      <small>Read-only analysis. No control actions.</small>
    </section>
  );
}

function ScopedRouteState({ loading, onBack }) {
  return (
    <section className="case-workspace scoped-route-state" role={loading ? "status" : "alert"} aria-live="polite">
      <span className="forensic-kicker">Facility workspace</span>
      <h1>{loading ? "Loading authorized evidence…" : "Finding unavailable"}</h1>
      <p>{loading
        ? "Checking this finding and its evidence in your current facility workspace."
        : "This finding is unavailable in the current facility workspace."}</p>
      {!loading ? <button type="button" className="forensic-button forensic-button--secondary" onClick={onBack}>Back to findings</button> : null}
    </section>
  );
}

function TechnicalSummary({ model }) {
  const warnings = model.selectedFinding?.technicalLimitations ?? [];
  return (
    <details className="operational-technical">
      <summary>Technical details</summary>
      <div className="operational-technical__content">
        <dl>
          <div><dt>Dataset assignment</dt><dd>{model.site.locationLabel}</dd></div>
          <div><dt>Evidence coverage</dt><dd>{model.coverage === null ? "Not supplied" : model.coverage.toFixed(3)}</dd></div>
          <div><dt>Relationship records</dt><dd>{model.relationships.length}</dd></div>
          <div><dt>Evidence run</dt><dd>{runIdentity(model, model.selectedFinding) ?? "Not persisted"}</dd></div>
          <div><dt>Detected data type</dt><dd>{model.domainLabel}</dd></div>
        </dl>
        {warnings.length ? <section><h3>Processing notes</h3><ul>{warnings.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
      </div>
    </details>
  );
}

function findingCountSummary(findings, status) {
  const changed = findings.filter((finding) => finding.status === "Change detected").length;
  if (changed) return String(changed) + " behavioral " + (changed === 1 ? "change" : "changes") + " detected";
  if (findings.length) return String(findings.length) + " " + (findings.length === 1 ? "finding needs" : "findings need") + " more evidence";
  return status === "Normal" ? "No changes detected" : "Evidence requirements not met";
}

function OverviewHeader({ eyebrow, name, status, confidence, location, summary = status }) {
  return (
    <header className="operational-overview-header">
      <div>
        <span className="forensic-kicker">{eyebrow}</span>
        <h1>{name}</h1>
        {location ? <p>{location}</p> : null}
      </div>
      <div className={`operational-overview-status operational-overview-status--${statusClass(status)}`}>
        <span>Status</span>
        <strong>{summary}</strong>
        <ConfidenceTierChip tier={confidence} />
      </div>
    </header>
  );
}

function SiteOverview({ model, reviewRecords, onReview, onReviewAction }) {
  return <OperationsBrief model={model} reviewRecords={reviewRecords} onReview={onReview} onReviewAction={onReviewAction} />;
}

function SystemOverview({ model, system, reviewRecords = {}, onReview, onReviewAction, onEvidence }) {
  if (!system) return <SystemsOverview model={model} onSystem={() => {}} />;
  return (
    <div className="system-overview operational-overview">
      <OverviewHeader eyebrow="System overview" name={system.name} status={system.status} confidence={system.evidenceTier} location={system.location.join(" / ")} summary={findingCountSummary(system.findings, system.status)} />
      {system.findings.length ? (
        <section className="active-findings" aria-label="Active findings">
          <div>{system.findings.map((finding) => <FindingSummary key={finding.id} finding={finding} reviewRecord={reviewRecordFor(finding, reviewRecords)} onReview={onReview} onReviewAction={onReviewAction} />)}</div>
        </section>
      ) : (
        <section className="normal-summary">
          <span>Current conditions</span>
          <h2>{system.status === "Normal" ? "Within learned behavior." : "More evidence is needed."}</h2>
          <p>{system.status === "Normal" ? "No new unexplained changes require review." : "A reliable system comparison is not available."}</p>
          <button type="button" className="forensic-button" onClick={() => onEvidence(null)}>Open evidence</button>
        </section>
      )}
      <TechnicalSummary model={model} />
    </div>
  );
}

function SystemsOverview({ model, onSystem }) {
  return (
    <div className="systems-overview operational-overview">
      <OverviewHeader eyebrow="Systems" name={model.site.name} status={model.status} confidence={model.evidenceQuality} summary={`${model.subsystems.length} monitored ${model.subsystems.length === 1 ? "system" : "systems"}`} />
      {model.subsystems.length ? <div className="systems-list">{model.subsystems.map((system) => <button type="button" key={system.id} onClick={() => onSystem(system.name)}><span><strong>{system.name}</strong><small>{system.location.join(" / ")}</small></span><span>{system.status}<small>{system.findingCount} active {system.findingCount === 1 ? "finding" : "findings"}</small></span></button>)}</div> : <section className="normal-summary"><span>Systems</span><h2>No mapped systems are available.</h2><p>Import mapped telemetry to establish system-level context.</p></section>}
    </div>
  );
}

function FindingsOverview({ model, reviewRecords, onReview, onReviewAction }) {
  const visible = model.findings.filter((finding) => reviewRecordFor(finding, reviewRecords).state !== "not_useful");
  return (
    <div className="findings-overview operational-overview">
      <OverviewHeader eyebrow="Findings" name="Current findings" status={model.status} confidence={model.evidenceQuality} summary={visible.length ? `${visible.length} active ${visible.length === 1 ? "finding" : "findings"}` : "No active findings"} />
      {visible.length ? <section className="active-findings" aria-label="Current findings"><div>{visible.map((finding) => <FindingSummary key={finding.id} finding={finding} reviewRecord={reviewRecordFor(finding, reviewRecords)} onReview={onReview} onReviewAction={onReviewAction} />)}</div></section> : <section className="normal-summary"><span>Current conditions</span><h2>All monitored systems are within learned behavior.</h2><p>No new unexplained changes require review.</p></section>}
    </div>
  );
}

function EvidenceOutcomesOverview({ model, reviewRecords, onReview, onReviewAction }) {
  return (
    <div className="findings-overview operational-overview">
      <OverviewHeader eyebrow="Evidence & outcomes" name="Finding history" status={model.status} confidence={model.evidenceQuality} summary={model.findings.length ? `${model.findings.length} tracked ${model.findings.length === 1 ? "finding" : "findings"}` : "No finding history"} />
      {model.findings.length ? <section className="active-findings" aria-label="Evidence and outcomes"><div>{model.findings.map((finding) => <FindingSummary key={finding.id} finding={finding} reviewRecord={reviewRecordFor(finding, reviewRecords)} onReview={onReview} onReviewAction={onReviewAction} />)}</div></section> : <section className="normal-summary"><span>Evidence & outcomes</span><h2>No findings have entered review.</h2><p>Evidence packages and operator outcomes will appear here after a finding is surfaced.</p></section>}
    </div>
  );
}

function TraceWorkspace({ model, finding, apiFetch, onBack }) {
  const [selectedId, setSelectedId] = useState(model.trace[0]?.id ?? null);
  const runId = runIdentity(model, finding);
  return (
    <div className="trace-workspace">
      <button type="button" className="evidence-back" onClick={onBack}>Back to evidence</button>
      <header className="forensic-page-header"><div><span className="forensic-kicker">Technical details</span><h1>Trace mode</h1></div></header>
      <div className="trace-actions"><EvidencePackageExport runId={runId} apiFetch={apiFetch} /></div>
      <TraceTimeline steps={model.trace} selectedId={selectedId} onSelect={(step) => setSelectedId(step.id)} />
    </div>
  );
}

const FIRST_BASELINE_STORAGE_PREFIX = "neraium.first-baseline.dismissed";
const REVIEW_STATE_STORAGE_PREFIX = "neraium.operations-brief.review-state";
const LEGACY_ACKNOWLEDGED_STORAGE_PREFIX = "neraium.shift-brief.acknowledged";

function storageScopeFor(user, datasetScopeKey = "anonymous") {
  return `${String(user?.email ?? user?.id ?? "operator")}:${String(datasetScopeKey)}`
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9@._-]+/g, "-");
}

function readStorageValue(key, fallback) {
  if (typeof window === "undefined") return fallback;
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

function scrollWindowTo(top) {
  if (typeof window === "undefined" || /jsdom/i.test(window.navigator?.userAgent ?? "")) return;
  window.scrollTo({ top, behavior: "auto" });
}

function writeStorageValue(key, value) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // The workspace remains usable when browser storage is unavailable.
  }
}

export default function EngineeringReasoningWorkspace({ liveOps, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, domainDetection, apiFetch, comparisonAnalysisId = null, datasetScopeKey = "anonymous", workspaceSession = null, currentWorkspace = null, onWorkspaceChange, onWorkspaceNavigate, onSignOut, signOutPending = false, currentUser }) {
  const [route, setRoute] = useState(routeFromLocation);
  const [selectedFindingId, setSelectedFindingId] = useState(() => pathIdentity(["findings", "evidence", "investigations"]));
  const [selectedSystemName, setSelectedSystemName] = useState(() => pathIdentity(["systems"]));
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [compactNavigation, setCompactNavigation] = useState(() => typeof window !== "undefined" && window.matchMedia?.("(max-width: 1024px)")?.matches);
  const mobileMenuButtonRef = useRef(null);
  const mobileSidebarRef = useRef(null);
  const restoreScrollRef = useRef(0);
  const [selectedSiteId, setSelectedSiteId] = useState(() => pathIdentity(["sites"]) || null);
  const [portfolioRuns, setPortfolioRuns] = useState([]);
  const [portfolioLoading, setPortfolioLoading] = useState(true);
  const [facilityLabelContext, setFacilityLabelContext] = useState({});
  const [findingWorkflowRecords, setFindingWorkflowRecords] = useState({});
  const storageScope = storageScopeFor(currentUser, datasetScopeKey);
  const firstBaselineStorageKey = FIRST_BASELINE_STORAGE_PREFIX + "." + storageScope;
  const reviewStorageKey = REVIEW_STATE_STORAGE_PREFIX + "." + storageScope;
  const legacyAcknowledgedStorageKey = LEGACY_ACKNOWLEDGED_STORAGE_PREFIX + "." + storageScope;
  const [firstBaselineDismissed, setFirstBaselineDismissed] = useState(() => readStorageValue(firstBaselineStorageKey, false) === true);
  const [reviewRecords, setReviewRecords] = useState(() => {
    const records = normalizeReviewRecords(readStorageValue(reviewStorageKey, {}));
    const legacy = readStorageValue(legacyAcknowledgedStorageKey, []);
    if (Array.isArray(legacy)) {
      for (const id of legacy.map(String)) if (!records[id]) records[id] = { state: "acknowledged", reason: "", note: "", reviewedAt: "", owner: "", persisted: false };
    }
    return records;
  });
  const verifiedComparisonResult = useMemo(() => (
    analysisBelongsToBaseline(effectiveLatestUploadResult, { analysisRunId: comparisonAnalysisId })
      ? effectiveLatestUploadResult
      : null
  ), [comparisonAnalysisId, effectiveLatestUploadResult]);
  const currentModel = useMemo(() => buildEngineeringReasoningModel({ liveOps: {}, canonicalFinding: verifiedComparisonResult ? canonicalFinding : null, currentSession: {}, result: verifiedComparisonResult ?? {}, snapshot: effectiveLatestUploadSnapshot, domainDetection, labelContext: facilityLabelContext }), [canonicalFinding, domainDetection, effectiveLatestUploadSnapshot, facilityLabelContext, verifiedComparisonResult]);
  const portfolioModels = useMemo(() => {
    const persisted = buildEngineeringReasoningModelsFromEvidenceRuns(portfolioRuns, facilityLabelContext);
    const currentName = currentModel.site.name.trim().toLowerCase();
    const withoutCurrent = persisted.filter((item) => item.site.id !== currentModel.site.id && item.site.name.trim().toLowerCase() !== currentName);
    if (currentModel.hasAnalysis) return [currentModel, ...withoutCurrent];
    return persisted.length ? persisted : [currentModel];
  }, [currentModel, facilityLabelContext, portfolioRuns]);
  const portfolioSites = useMemo(() => portfolioModels.map((item) => item.site), [portfolioModels]);
  const model = portfolioModels.find((item) => item.site.id === selectedSiteId) ?? currentModel;
  const routeRequiresExactFinding = ["investigation", "evidence"].includes(route) && Boolean(selectedFindingId && selectedFindingId !== "__overview__");
  const exactSelectedFinding = selectedFindingId && selectedFindingId !== "__overview__"
    ? model.findings.find((finding) => finding.id === selectedFindingId)
    : null;
  const selectedFinding = selectedFindingId === "__overview__"
    ? null
    : routeRequiresExactFinding
      ? exactSelectedFinding ?? null
      : exactSelectedFinding ?? model.selectedFinding;
  const effectiveReviewRecords = useMemo(() => ({ ...reviewRecords, ...findingWorkflowRecords }), [findingWorkflowRecords, reviewRecords]);
  const selectedReviewRecord = selectedFinding ? reviewRecordFor(selectedFinding, effectiveReviewRecords) : null;
  const selectedSystem = model.subsystems.find((system) => system.name === selectedSystemName) ?? null;
  const presentationState = useMemo(() => deriveWorkspacePresentationState(model), [model]);
  const showFirstBaseline = presentationState.key === "noDataset" && !firstBaselineDismissed;
  const effectiveRoute = route === "portfolio" && portfolioModels.length <= 1 ? "site" : route;
  const activeNavigation = ["finding", "findings"].includes(effectiveRoute) ? "findings" : ["investigation", "evidence", "trace"].includes(effectiveRoute) ? "investigations" : ["system", "systems"].includes(effectiveRoute) ? "systems" : effectiveRoute;
  const navItems = [
    ["work", "Work"],
    ["site", "System Status"],
    ["live-monitoring", "Live Monitoring"],
    ["systems", "Systems"],
    ["findings", "Analysis Findings"],
    ["investigations", "Evidence & Outcomes"],
    ["data-connections", "Data"],
    ...(portfolioModels.length > 1 ? [["portfolio", "Sites"]] : []),
    ...(currentUser?.role === "admin" ? [["governance-admin", "Administration"]] : []),
  ];
  const availableWorkspaces = (Array.isArray(workspaceSession?.workspaces)
    ? workspaceSession.workspaces
    : Array.isArray(currentUser?.workspaces) ? currentUser.workspaces : [])
    .filter((workspace) => workspace?.is_active !== false);
  const currentWorkspaceId = String(currentWorkspace?.workspace_id ?? currentWorkspace?.workspaceId ?? workspaceSession?.default_workspace_id ?? "default");

  useEffect(() => {
    let cancelled = false;
    setPortfolioRuns([]);
    setPortfolioLoading(true);
    Promise.resolve(apiFetch?.("/api/evidence/runs?limit=100"))
      .then((response) => response?.ok ? response.json() : null)
      .then((payload) => { if (!cancelled && Array.isArray(payload?.runs)) setPortfolioRuns(payload.runs); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setPortfolioLoading(false); });
    return () => { cancelled = true; };
  }, [apiFetch, datasetScopeKey]);

  useEffect(() => {
    let cancelled = false;
    setFacilityLabelContext({});
    Promise.resolve(apiFetch?.("/api/facility/context"))
      .then((response) => response?.ok ? response.json() : null)
      .then((payload) => { if (!cancelled && payload) setFacilityLabelContext(buildFacilityLabelContext(payload)); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [apiFetch, datasetScopeKey]);

  useEffect(() => {
    let cancelled = false;
    const runId = runIdentity(model, model.selectedFinding);
    setFindingWorkflowRecords({});
    if (!runId || !model.findings.length || typeof apiFetch !== "function") return () => { cancelled = true; };
    fetchFindings({ apiFetch, sourceKind: "evidence_run", sourceRunId: runId })
      .then((payload) => {
        if (cancelled) return;
        const records = {};
        for (const item of payload.findings) {
          const sourceKey = String(item.workflow.source?.finding_key ?? "");
          const finding = model.findings.find((candidate) => candidate.sourceFindingKey === sourceKey || candidate.id === sourceKey || candidate.mergedFindingIds?.includes(sourceKey));
          const record = reviewRecordFromWorkflow(item.workflow);
          if (finding && record) records[finding.id] = record;
        }
        setFindingWorkflowRecords(records);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [apiFetch, datasetScopeKey, model]);

  useEffect(() => {
    const onPop = (event) => {
      setRoute(routeFromLocation());
      setSelectedFindingId(pathIdentity(["findings", "evidence", "investigations"]));
      setSelectedSystemName(pathIdentity(["systems"]));
      setSelectedSiteId(pathIdentity(["sites"]) || null);
      restoreScrollRef.current = Number(event.state?.scrollY ?? 0);
      window.requestAnimationFrame?.(() => scrollWindowTo(restoreScrollRef.current));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    const keyHandler = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        document.querySelector(".global-asset-search input")?.focus();
      }
    };
    window.addEventListener("keydown", keyHandler);
    return () => window.removeEventListener("keydown", keyHandler);
  }, []);

  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 1024px)");
    if (!media) return undefined;
    const syncNavigationMode = () => {
      setCompactNavigation(media.matches);
      if (!media.matches) setMobileNavOpen(false);
    };
    syncNavigationMode();
    media.addEventListener?.("change", syncNavigationMode);
    return () => media.removeEventListener?.("change", syncNavigationMode);
  }, []);

  useEffect(() => {
    if (!mobileNavOpen) return undefined;
    const sidebar = mobileSidebarRef.current;
    const previousOverflow = document.body.style.overflow;
    const focusable = Array.from(sidebar?.querySelectorAll("button:not([disabled])") ?? []);
    const activeNavigationItem = sidebar?.querySelector('nav[aria-label="Primary navigation"] [aria-current="page"]');
    (activeNavigationItem ?? focusable[0])?.focus();
    if (window.matchMedia?.("(max-width: 1024px)")?.matches) document.body.style.overflow = "hidden";

    function handleMenuKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileNavOpen(false);
        mobileMenuButtonRef.current?.focus();
        return;
      }
      if (event.key !== "Tab" || !focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleMenuKeyDown);
    return () => {
      document.removeEventListener("keydown", handleMenuKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileNavOpen]);

  function pushRoute(path, nextRoute) {
    const scrollY = typeof window === "undefined" ? 0 : window.scrollY;
    window.history.replaceState({ ...window.history.state, scrollY }, "", window.location.pathname);
    window.history.pushState({ neraiumRoute: true }, "", path);
    setRoute(nextRoute);
    setMobileNavOpen(false);
    window.requestAnimationFrame?.(() => scrollWindowTo(0));
    if (mobileNavOpen) window.requestAnimationFrame?.(() => mobileMenuButtonRef.current?.focus());
  }

  function navigate(target) {
    if (["live-monitoring", "data-connections", "governance-admin"].includes(target)) {
      onWorkspaceNavigate?.(target);
      return;
    }
    const path = target === "site" ? `/sites/${encodeURIComponent(model.site.id)}` : ROUTES[target];
    pushRoute(path, target === "investigations" ? "investigation" : target);
  }

  function goBack(fallback) {
    if (window.history.state?.neraiumRoute) window.history.back();
    else navigate(fallback);
  }

  function openFinding(finding) {
    setSelectedFindingId(finding?.id || "__overview__");
    pushRoute(finding ? `/findings/${encodeURIComponent(finding.id)}` : "/findings", finding ? "finding" : "findings");
  }

  function openInvestigation(finding) {
    setSelectedFindingId(finding?.id || "__overview__");
    pushRoute(finding ? `/investigations/${encodeURIComponent(finding.id)}` : "/investigations", "investigation");
  }

  function openEvidence(finding) {
    setSelectedFindingId(finding?.id || "__overview__");
    pushRoute(finding ? `/evidence/${encodeURIComponent(finding.id)}` : "/evidence", "evidence");
  }

  function openSystem(name) {
    setSelectedSystemName(name);
    pushRoute(`/systems/${encodeURIComponent(name)}`, "system");
  }

  function routeWorkFinding(findingId) {
    pushRoute(findingId ? `/work/${encodeURIComponent(findingId)}` : "/work", "work");
  }

  function technicalFindingFor(workFinding) {
    return model.findings.find((candidate) => candidate.id === workFinding.sourceFindingKey
      || candidate.sourceFindingKey === workFinding.sourceFindingKey
      || candidate.workflowFindingId === workFinding.findingId
      || candidate.mergedFindingIds?.includes(workFinding.sourceFindingKey)) ?? null;
  }

  function handleSearch(item) {
    if (item.target === "system") {
      openSystem(item.systemName);
      return;
    }
    if (item.target === "evidence") {
      const finding = model.findings.find((candidate) => candidate.id === item.findingId)
        ?? model.findings.find((candidate) => candidate.variables.includes(item.nodeId))
        ?? selectedFinding;
      openEvidence(finding);
      return;
    }
    navigate(item.target);
  }

  function handleSelectSite(site) {
    setSelectedSiteId(site.id);
    pushRoute(`/sites/${encodeURIComponent(site.id)}`, "site");
  }

  function dismissFirstBaseline() {
    writeStorageValue(firstBaselineStorageKey, true);
    setFirstBaselineDismissed(true);
  }

  function beginFirstBaseline() {
    dismissFirstBaseline();
    navigate("data-connections");
  }

  function storeFindingWorkflow(analyticalId, workflow) {
    const record = reviewRecordFromWorkflow(workflow);
    if (!record) return;
    setFindingWorkflowRecords((current) => ({ ...current, [String(analyticalId)]: record }));
  }

  async function handleWorkflowSave({ findingId, expectedVersion, changes }) {
    const result = await patchFindingWorkflow({ apiFetch, findingId, expectedVersion, changes });
    storeFindingWorkflow(selectedFinding?.id ?? findingId, result.workflow);
    return result;
  }

  async function handleWorkflowResolve({ findingId, expectedVersion, outcome, note }) {
    const result = await resolveFinding({ apiFetch, findingId, expectedVersion, outcome, note });
    storeFindingWorkflow(selectedFinding?.id ?? findingId, result.workflow);
    return result;
  }

  async function handleWorkflowFeedback({ findingId, expectedVersion, category, note, actionTaken }) {
    const result = await postFindingFeedback({ apiFetch, findingId, expectedVersion, category, note, actionTaken });
    storeFindingWorkflow(selectedFinding?.id ?? findingId, result.workflow);
    return result;
  }

  async function reloadSelectedFindingWorkflow() {
    const findingId = selectedReviewRecord?.workflowFindingId ?? selectedReviewRecord?.findingId ?? selectedFinding?.workflowFindingId;
    if (!findingId) return null;
    const result = await fetchFinding({ apiFetch, findingId });
    storeFindingWorkflow(selectedFinding?.id ?? findingId, result.workflow);
    return result;
  }

  async function handleFindingReviewAction(finding, action) {
    const id = String(finding?.id ?? "");
    if (!id) return { persisted: false };
    const existingWorkflow = effectiveReviewRecords[id];
    const workflowFindingId = existingWorkflow?.workflowFindingId;
    if (workflowFindingId && existingWorkflow?.persisted && typeof apiFetch === "function") {
      try {
        const caseState = action.state === "new" ? "open"
          : action.state === "not_useful" ? "dismissed"
            : action.state;
        const result = action.state === "explained" || action.state === "closed"
          ? await resolveFinding({
            apiFetch,
            findingId: workflowFindingId,
            expectedVersion: existingWorkflow.version,
            outcome: action.reason === "known_sensor_issue" ? "sensor_issue" : action.reason === "maintenance_activity" ? "maintenance_performed" : "operational_change",
            note: action.note || feedbackForReviewAction(action)?.note || "Known operational explanation recorded.",
          })
          : await patchFindingWorkflow({ apiFetch, findingId: workflowFindingId, expectedVersion: existingWorkflow.version, changes: { status: caseState } });
        storeFindingWorkflow(id, result.workflow);
        return { persisted: true };
      } catch (error) {
        if (!isFindingApiUnavailable(error)) throw error;
      }
    }
    const record = {
      state: action.state,
      reason: action.reason ?? "",
      note: action.note ?? "",
      reviewedAt: new Date().toISOString(),
      owner: currentUser?.name || currentUser?.email || "Signed-in engineer",
      persisted: false,
    };
    setReviewRecords((current) => {
      const next = { ...current, [id]: record };
      writeStorageValue(reviewStorageKey, next);
      return next;
    });
    const runId = runIdentity(model, finding);
    if (!runId || typeof apiFetch !== "function") return { persisted: false };
    const caseState = action.state === "new" ? "open"
      : action.state === "explained" || action.state === "closed" ? "resolved"
        : action.state === "not_useful" ? "dismissed"
          : action.state;
    try {
      const response = await apiFetch(`/api/evidence/runs/${encodeURIComponent(runId)}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: caseState, note: action.note || null, owner: record.owner }),
      });
      if (!response?.ok) return { persisted: false };
      const feedback = feedbackForReviewAction(action);
      if (feedback) {
        await apiFetch(`/api/evidence/runs/${encodeURIComponent(runId)}/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(feedback),
        });
      }
      const persistedRecord = { ...record, persisted: true };
      setReviewRecords((current) => {
        const next = { ...current, [id]: persistedRecord };
        writeStorageValue(reviewStorageKey, next);
        return next;
      });
      return { persisted: true };
    } catch {
      return { persisted: false };
    }
  }

  function presentationPrimaryAction() {
    if (["insufficientEvidence", "legacyAnalysis"].includes(presentationState.key)) {
      openEvidence(model.selectedFinding);
      return;
    }
    navigate("data-connections");
  }

  return (
    <div className="forensic-shell" data-testid="engineering-reasoning-platform">
      <a className="skip-link" href="#forensic-main">Skip to main content</a>
      <aside id="forensic-navigation" ref={mobileSidebarRef} className={`forensic-sidebar${mobileNavOpen ? " is-open" : ""}`} aria-label="Application sidebar" aria-hidden={compactNavigation && !mobileNavOpen} inert={compactNavigation && !mobileNavOpen ? "" : undefined}>
        <div className="forensic-brand"><span className="forensic-brand__mark" aria-hidden="true">N</span><div><strong>Neraium</strong><small>Operational evidence</small></div></div>
        <nav aria-label="Primary navigation">
          {navItems.map(([id, label]) => <button key={id} type="button" className={activeNavigation === id ? "is-active" : ""} aria-current={activeNavigation === id ? "page" : undefined} onClick={() => navigate(id)}><span aria-hidden="true" className={`nav-glyph nav-glyph--${id}`} />{label}</button>)}
        </nav>
        <div className="forensic-sidebar__account">
          <span>{currentUser?.name || currentUser?.email || "Signed in"}</span><small>{currentUser?.role || "engineer"}</small>
          {availableWorkspaces.length > 1 ? <label className="forensic-workspace-selector forensic-workspace-selector--sidebar"><span>Facility workspace</span><select value={currentWorkspaceId} onChange={(event) => onWorkspaceChange?.(event.target.value)}>{availableWorkspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.display_name}</option>)}</select></label> : null}
          {onSignOut ? <button type="button" onClick={onSignOut} disabled={signOutPending}>{signOutPending ? "Signing out..." : "Sign out"}</button> : null}
        </div>
      </aside>
      {mobileNavOpen ? <button type="button" className="forensic-sidebar-scrim" aria-label="Close navigation" onClick={() => { setMobileNavOpen(false); mobileMenuButtonRef.current?.focus(); }} /> : null}
      <div className="forensic-app">
        <header className="forensic-topbar" aria-label="Workspace controls">
          <button
            ref={mobileMenuButtonRef}
            type="button"
            className="forensic-mobile-menu"
            aria-expanded={mobileNavOpen}
            aria-controls="forensic-navigation"
            aria-label={mobileNavOpen ? "Close menu" : "Open menu"}
            onClick={() => setMobileNavOpen((value) => !value)}
          ><span className="forensic-mobile-menu__label">Menu</span><svg className="forensic-mobile-menu__icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button>
          <GlobalAssetSearch items={model.searchItems} onSelect={handleSearch} />
          <div className="forensic-topbar__site">
            {availableWorkspaces.length > 1 ? <label className="forensic-workspace-selector"><span>Facility</span><select aria-label="Current facility workspace" value={currentWorkspaceId} onChange={(event) => onWorkspaceChange?.(event.target.value)}>{availableWorkspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.display_name}</option>)}</select></label> : <span>{currentWorkspace?.display_name ?? currentWorkspace?.displayName ?? model.site.name}</span>}
            {model.selectedFinding?.confidenceContract && Object.keys(model.selectedFinding.confidenceContract).length ? null : <ConfidenceTierChip tier={model.evidenceQuality} />}
          </div>
        </header>
        <main id="forensic-main" aria-label="Neraium operational workspace" tabIndex={-1} data-route={effectiveRoute}>
          {effectiveRoute === "work" ? <Suspense fallback={<p className="case-unavailable">Loading work…</p>}><WorkQueueWorkspace apiFetch={apiFetch} currentUser={currentUser} currentWorkspace={currentWorkspace} findingId={pathIdentity(["work"])} onRouteFinding={routeWorkFinding} technicalFindingFor={technicalFindingFor} onOpenInvestigation={openInvestigation} onOpenEvidence={openEvidence} /></Suspense>
            : routeRequiresExactFinding && !selectedFinding ? <ScopedRouteState loading={portfolioLoading} onBack={() => navigate("findings")} />
            : showFirstBaseline ? <FirstBaselineExperience onImport={beginFirstBaseline} onExit={dismissFirstBaseline} />
            : ["noDataset", "datasetReady", "analysisRunning"].includes(presentationState.key) ? <WorkspaceStateNotice state={presentationState} onPrimary={presentationPrimaryAction} />
              : effectiveRoute === "finding" ? <FindingReviewWorkspace model={model} finding={selectedFinding} reviewRecord={selectedReviewRecord} onReviewAction={handleFindingReviewAction} onWorkflowSave={handleWorkflowSave} onWorkflowFeedback={handleWorkflowFeedback} onWorkflowResolve={handleWorkflowResolve} onWorkflowReload={reloadSelectedFindingWorkflow} onOpenInvestigation={openInvestigation} onBack={() => goBack("site")} />
                : effectiveRoute === "investigation" ? <InvestigationWorkspace model={model} finding={selectedFinding} reviewRecord={selectedReviewRecord} escalated={deriveEscalationReadiness(selectedFinding, model.result).serious} onReviewAction={handleFindingReviewAction} onOpenEvidence={openEvidence} onTrace={() => navigate("trace")} onBack={() => goBack("findings")} />
                  : effectiveRoute === "evidence" ? <EvidenceRecordWorkspace model={model} finding={selectedFinding} reviewRecord={selectedReviewRecord} apiFetch={apiFetch} onTrace={() => navigate("trace")} onBack={() => goBack("investigations")} />
                    : effectiveRoute === "trace" ? <TraceWorkspace model={model} finding={selectedFinding} apiFetch={apiFetch} onBack={() => goBack("investigations")} />
                      : effectiveRoute === "portfolio" ? <PortfolioWorkspace sites={portfolioSites} onSelectSite={handleSelectSite} />
                        : effectiveRoute === "systems" ? <SystemsOverview model={model} onSystem={openSystem} />
                          : effectiveRoute === "findings" ? <FindingsOverview model={model} reviewRecords={effectiveReviewRecords} onReview={openFinding} onReviewAction={handleFindingReviewAction} />
                            : effectiveRoute === "investigations" ? <EvidenceOutcomesOverview model={model} reviewRecords={effectiveReviewRecords} onReview={openFinding} onReviewAction={handleFindingReviewAction} />
                            : effectiveRoute === "system" ? <SystemOverview model={model} system={selectedSystem} reviewRecords={effectiveReviewRecords} onReview={openFinding} onReviewAction={handleFindingReviewAction} onEvidence={openEvidence} />
                              : ["insufficientEvidence", "legacyAnalysis"].includes(presentationState.key) ? <WorkspaceStateNotice state={presentationState} onPrimary={presentationPrimaryAction} />
                                : <SiteOverview model={model} reviewRecords={effectiveReviewRecords} onReview={openFinding} onReviewAction={handleFindingReviewAction} />}
        </main>
      </div>
    </div>
  );
}
