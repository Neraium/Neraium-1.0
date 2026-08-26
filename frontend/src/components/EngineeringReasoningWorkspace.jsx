import React, { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { buildEngineeringReasoningModel, buildEngineeringReasoningModelsFromEvidenceRuns, buildFacilityLabelContext } from "../viewModels/engineeringReasoning";
import { analysisBelongsToBaseline } from "../viewModels/baselineSelection";
import { deriveWorkspacePresentationState } from "../viewModels/operationsBrief";
import { projectAnalysisEvidenceRecord, projectAnalysisInvestigation, projectEvidenceRecord, projectFindingReview, projectInvestigation, projectResults, projectSystems } from "../viewModels/resultsPresentation";
import { normalizeReviewRecords, reviewRecordFor, reviewRecordFromWorkflow } from "../viewModels/findingReviewState";
import { fetchFindings } from "../services/api/findingsApi";
import ConfidenceTierChip from "./engineering/ConfidenceTierChip";
import EvidencePackageExport from "./engineering/EvidencePackageExport";
import GlobalAssetSearch from "./engineering/GlobalAssetSearch";
import PortfolioWorkspace from "./engineering/PortfolioWorkspace";
import OperationsBrief from "./engineering/OperationsBrief";
import TraceTimeline from "./engineering/TraceTimeline";
import SkipToMainContent from "./SkipToMainContent";
import "../styles/engineering-reasoning.css";

const WorkQueueWorkspace = lazy(() => import("./work/WorkQueueWorkspace"));
const FindingReviewWorkspace = lazy(() => import("./engineering/FindingCaseWorkspaces").then((module) => ({ default: module.FindingReviewWorkspace })));
const InvestigationWorkspace = lazy(() => import("./engineering/FindingCaseWorkspaces").then((module) => ({ default: module.InvestigationWorkspace })));
const EvidenceRecordWorkspace = lazy(() => import("./engineering/FindingCaseWorkspaces").then((module) => ({ default: module.EvidenceRecordWorkspace })));

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
  if (path === "/evidence") return "investigations";
  if (path.startsWith("/evidence/")) return "evidence";
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
  const baselineNeeded = state.key === "noDataset";
  const customerState = baselineNeeded ? {
    status: "Setup needed",
    headline: "Connect a data source",
    body: "Add a read-only telemetry connection, discover its signals, and map them into a defined physical system.",
    action: "Add data source",
  } : state.key === "datasetReady" ? {
    status: "Setup in progress",
    headline: "Prepare the system reference",
    body: "Review the connection, mapped system coverage, units, timestamps, and telemetry cadence before continued analysis.",
    action: "Open Data Connections",
  } : state;
  return (
    <section className={"operational-empty operational-empty--" + state.key} aria-labelledby={"workspace-state-" + state.key + "-title"} data-testid={"workspace-state-" + state.key}>
      <span className="operational-empty__mark" aria-hidden="true" />
      <span className="operational-label">Operations Brief · {customerState.status}</span>
      <h1 id={"workspace-state-" + state.key + "-title"}>{customerState.headline}</h1>
      <p>{customerState.body}</p>
      <div className="operational-empty__actions">
        <button type="button" className="forensic-button" onClick={onPrimary}>{customerState.action}</button>
      </div>
      <small>Read-only analysis. No control actions.</small>
    </section>
  );
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

function SiteOverview({ projection, onReview, onOpenInvestigation, onOpenEvidence }) {
  return <OperationsBrief projection={projection} onReview={onReview} onOpenInvestigation={onOpenInvestigation} onOpenEvidence={onOpenEvidence} />;
}

function SystemOverview({ system, systemsProjection, onReview, onOpenInvestigation, onOpenEvidence, onSystem }) {
  if (!system) return <SystemsOverview projection={systemsProjection} onSystem={onSystem} />;
  return <OperationsBrief projection={system.results} onReview={onReview} onOpenInvestigation={onOpenInvestigation} onOpenEvidence={onOpenEvidence} />;
}

function SystemsOverview({ projection, onSystem }) {
  if (!projection || projection.variant !== "ready") {
    return <section className="systems-overview operational-overview operations-result-state"><span className="forensic-kicker">Systems</span><h1>Systems unavailable</h1><p>The modeled-system summary cannot be presented from this analysis record.</p></section>;
  }
  return (
    <div className="systems-overview operational-overview">
      <OverviewHeader eyebrow="Systems" name={projection.header.systemLabel} status={projection.header.status} confidence={projection.header.evidenceQuality} summary={projection.header.summary} />
      {projection.systems.length ? <div className="systems-list">{projection.systems.map((system) => <button type="button" key={system.systemKey} onClick={() => onSystem(system.systemKey)}><span><strong>{system.name}</strong><small>{system.locationLabel}</small></span><span>{system.status}<small>{system.findingsForReview} for review</small></span></button>)}</div> : <section className="normal-summary"><span>Systems</span><h2>No modeled systems are available.</h2><p>Connect a telemetry source and map its signals into a defined physical system.</p></section>}
    </div>
  );
}

function FindingsOverview({ projection, onReview, onOpenInvestigation, onOpenEvidence }) {
  return <OperationsBrief projection={projection} onReview={onReview} onOpenInvestigation={onOpenInvestigation} onOpenEvidence={onOpenEvidence} />;
}

function EvidenceOutcomesOverview({ projection, onReview, onOpenInvestigation, onOpenEvidence }) {
  return <OperationsBrief projection={projection} onReview={onReview} onOpenInvestigation={onOpenInvestigation} onOpenEvidence={onOpenEvidence} />;
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

export default function EngineeringReasoningWorkspace({ liveOps, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, canonicalConnectorResult = null, domainDetection, apiFetch, comparisonAnalysisId = null, datasetScopeKey = "anonymous", workspaceSession = null, currentWorkspace = null, onWorkspaceChange, onWorkspaceNavigate, onSignOut, signOutPending = false, currentUser }) {
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
  const [facilityLabelContext, setFacilityLabelContext] = useState({});
  const [findingWorkflowRecords, setFindingWorkflowRecords] = useState({});
  const storageScope = storageScopeFor(currentUser, datasetScopeKey);
  const reviewStorageKey = REVIEW_STATE_STORAGE_PREFIX + "." + storageScope;
  const legacyAcknowledgedStorageKey = LEGACY_ACKNOWLEDGED_STORAGE_PREFIX + "." + storageScope;
  const [reviewRecords] = useState(() => {
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
  const activeResult = useMemo(() => canonicalConnectorResult ?? verifiedComparisonResult ?? {}, [canonicalConnectorResult, verifiedComparisonResult]);
  const activeResultId = canonicalConnectorResult ? String(canonicalConnectorResult.result_id ?? "") : "";
  const currentModel = useMemo(() => buildEngineeringReasoningModel({ liveOps: {}, canonicalFinding: verifiedComparisonResult && !canonicalConnectorResult ? canonicalFinding : null, currentSession: {}, result: activeResult, snapshot: effectiveLatestUploadSnapshot, domainDetection, labelContext: facilityLabelContext }), [activeResult, canonicalConnectorResult, canonicalFinding, domainDetection, effectiveLatestUploadSnapshot, facilityLabelContext, verifiedComparisonResult]);
  const portfolioModels = useMemo(() => {
    const persisted = buildEngineeringReasoningModelsFromEvidenceRuns(portfolioRuns, facilityLabelContext);
    const currentName = currentModel.site.name.trim().toLowerCase();
    const withoutCurrent = persisted.filter((item) => item.site.id !== currentModel.site.id && item.site.name.trim().toLowerCase() !== currentName);
    if (currentModel.hasAnalysis) return [currentModel, ...withoutCurrent];
    return persisted.length ? persisted : [currentModel];
  }, [currentModel, facilityLabelContext, portfolioRuns]);
  const portfolioSites = useMemo(() => portfolioModels.map((item) => item.site), [portfolioModels]);
  const model = portfolioModels.find((item) => item.site.id === selectedSiteId) ?? currentModel;
  const exactSelectedFinding = selectedFindingId && selectedFindingId !== "__overview__"
    ? model.findings.find((finding) => finding.id === selectedFindingId)
    : null;
  const selectedFinding = selectedFindingId === "__overview__"
    ? null
    : exactSelectedFinding ?? model.selectedFinding;
  const effectiveReviewRecords = useMemo(() => ({ ...reviewRecords, ...findingWorkflowRecords }), [findingWorkflowRecords, reviewRecords]);
  const resultsProjection = useMemo(() => projectResults(model, effectiveReviewRecords, { analysisResultId: activeResultId }), [activeResultId, effectiveReviewRecords, model]);
  const systemsProjection = useMemo(() => projectSystems(model, effectiveReviewRecords), [effectiveReviewRecords, model]);
  const selectedReviewRecord = selectedFinding ? reviewRecordFor(selectedFinding, effectiveReviewRecords) : null;
  const reviewProjection = useMemo(() => projectFindingReview(model, selectedFindingId, selectedReviewRecord ?? {}), [model, selectedFindingId, selectedReviewRecord]);
  const analysisRouteSelected = Boolean(activeResultId && selectedFindingId === activeResultId && !exactSelectedFinding);
  const investigationProjection = useMemo(() => analysisRouteSelected ? projectAnalysisInvestigation(model, selectedFindingId) : projectInvestigation(model, selectedFindingId, selectedReviewRecord ?? {}), [analysisRouteSelected, model, selectedFindingId, selectedReviewRecord]);
  const evidenceProjection = useMemo(() => analysisRouteSelected ? projectAnalysisEvidenceRecord(model, selectedFindingId) : projectEvidenceRecord(model, selectedFindingId, selectedReviewRecord ?? {}), [analysisRouteSelected, model, selectedFindingId, selectedReviewRecord]);
  const selectedSystem = systemsProjection.systems.find((system) => system.systemKey === selectedSystemName) ?? null;
  const presentationState = useMemo(() => deriveWorkspacePresentationState(model), [model]);
  const effectiveRoute = route === "portfolio" && portfolioModels.length <= 1 ? "site" : route;
  const scopedDetailRoute = ["finding", "investigation", "evidence"].includes(effectiveRoute);
  const activeNavigation = ["finding", "findings"].includes(effectiveRoute) ? "findings" : ["investigation", "evidence", "trace"].includes(effectiveRoute) ? "investigations" : ["system", "systems"].includes(effectiveRoute) ? "systems" : effectiveRoute;
  const navItems = [
    ["work", "Work"],
    ["site", "System Status"],
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
    Promise.resolve(apiFetch?.("/api/evidence/runs?limit=100"))
      .then((response) => response?.ok ? response.json() : null)
      .then((payload) => { if (!cancelled && Array.isArray(payload?.runs)) setPortfolioRuns(payload.runs); })
      .catch(() => {});
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
    if (["data-connections", "governance-admin"].includes(target)) {
      onWorkspaceNavigate?.(target);
      return;
    }
    const path = target === "site" ? `/sites/${encodeURIComponent(model.site.id)}` : ROUTES[target];
    pushRoute(path, target);
  }

  function goBack(fallback) {
    if (window.history.state?.neraiumRoute) window.history.back();
    else navigate(fallback);
  }

  function openFinding(findingOrKey) {
    const findingKey = typeof findingOrKey === "string" ? findingOrKey : findingOrKey?.id;
    setSelectedFindingId(findingKey || "__overview__");
    pushRoute(findingKey ? `/findings/${encodeURIComponent(findingKey)}` : "/findings", findingKey ? "finding" : "findings");
  }

  function openInvestigation(findingKey) {
    setSelectedFindingId(findingKey || "__overview__");
    pushRoute(findingKey ? `/investigations/${encodeURIComponent(findingKey)}` : "/investigations", findingKey ? "investigation" : "investigations");
  }

  function openEvidence(findingKey) {
    setSelectedFindingId(findingKey || "__overview__");
    pushRoute(findingKey ? `/evidence/${encodeURIComponent(findingKey)}` : "/investigations", findingKey ? "evidence" : "investigations");
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
      openEvidence(finding?.id);
      return;
    }
    navigate(item.target);
  }

  function handleSelectSite(site) {
    setSelectedSiteId(site.id);
    pushRoute(`/sites/${encodeURIComponent(site.id)}`, "site");
  }

  function presentationPrimaryAction() {
    if (presentationState.key === "legacyAnalysis") {
      openEvidence(model.selectedFinding?.id);
      return;
    }
    navigate("data-connections");
  }

  return (
    <div className="forensic-shell" data-testid="engineering-reasoning-platform">
      <SkipToMainContent targetId="forensic-main" />
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
          {effectiveRoute === "work" ? <Suspense fallback={<p className="case-unavailable">Loading work…</p>}><WorkQueueWorkspace apiFetch={apiFetch} currentUser={currentUser} currentWorkspace={currentWorkspace} findingId={pathIdentity(["work"])} onRouteFinding={routeWorkFinding} technicalFindingFor={technicalFindingFor} onOpenInvestigation={(finding) => openInvestigation(finding?.id)} onOpenEvidence={(finding) => openEvidence(finding?.id)} /></Suspense>
            : scopedDetailRoute ? <Suspense fallback={<p className="case-unavailable">Loading finding evidence…</p>}>{effectiveRoute === "finding"
              ? <FindingReviewWorkspace projection={reviewProjection} onOpenInvestigation={openInvestigation} onBack={() => goBack("site")} />
              : effectiveRoute === "investigation"
                ? <InvestigationWorkspace projection={investigationProjection} onOpenEvidence={openEvidence} onBack={() => goBack("findings")} />
                : <EvidenceRecordWorkspace projection={evidenceProjection} apiFetch={apiFetch} onTrace={() => navigate("trace")} onBack={() => goBack("investigations")} />}</Suspense>
            : ["noDataset", "datasetReady", "analysisRunning"].includes(presentationState.key) ? <WorkspaceStateNotice state={presentationState} onPrimary={presentationPrimaryAction} />
              : effectiveRoute === "trace" ? <TraceWorkspace model={model} finding={selectedFinding} apiFetch={apiFetch} onBack={() => goBack("investigations")} />
                      : effectiveRoute === "portfolio" ? <PortfolioWorkspace sites={portfolioSites} onSelectSite={handleSelectSite} />
                        : effectiveRoute === "systems" ? <SystemsOverview projection={systemsProjection} onSystem={openSystem} />
                            : effectiveRoute === "findings" ? <FindingsOverview projection={resultsProjection} onReview={openFinding} onOpenInvestigation={openInvestigation} onOpenEvidence={openEvidence} />
                            : effectiveRoute === "investigations" ? <EvidenceOutcomesOverview projection={resultsProjection} onReview={openFinding} onOpenInvestigation={openInvestigation} onOpenEvidence={openEvidence} />
                            : effectiveRoute === "system" ? <SystemOverview system={selectedSystem} systemsProjection={systemsProjection} onReview={openFinding} onOpenInvestigation={openInvestigation} onOpenEvidence={openEvidence} onSystem={openSystem} />
                              : presentationState.key === "legacyAnalysis" ? <WorkspaceStateNotice state={presentationState} onPrimary={presentationPrimaryAction} />
                                : <SiteOverview projection={resultsProjection} onReview={openFinding} onOpenInvestigation={openInvestigation} onOpenEvidence={openEvidence} />}
        </main>
      </div>
    </div>
  );
}
