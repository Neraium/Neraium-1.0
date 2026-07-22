import React, { useEffect, useMemo, useState } from "react";
import { buildEngineeringReasoningModel, buildEngineeringReasoningModelsFromEvidenceRuns } from "../viewModels/engineeringReasoning";
import CmmsExportReview from "./engineering/CmmsExportReview";
import ConfidenceTierChip from "./engineering/ConfidenceTierChip";
import EvidenceDrawer from "./engineering/EvidenceDrawer";
import EvidenceLineage from "./engineering/EvidenceLineage";
import EvidencePackageExport from "./engineering/EvidencePackageExport";
import FindingSummary from "./engineering/FindingSummary";
import GlobalAssetSearch from "./engineering/GlobalAssetSearch";
import InvestigationOutcome from "./engineering/InvestigationOutcome";
import ObservationInterpretationBlock from "./engineering/ObservationInterpretationBlock";
import PortfolioWorkspace from "./engineering/PortfolioWorkspace";
import ReadOnlyIndicator from "./engineering/ReadOnlyIndicator";
import RelationshipGraph from "./engineering/RelationshipGraph";
import SiteStabilitySummary from "./engineering/SiteStabilitySummary";
import SubsystemStatusRow from "./engineering/SubsystemStatusRow";
import TimeShiftSlider from "./engineering/TimeShiftSlider";
import TraceTimeline from "./engineering/TraceTimeline";
import "../styles/engineering-reasoning.css";

const ROUTES = {
  portfolio: "/portfolio",
  site: "/sites/current",
  investigations: "/investigations",
  evidence: "/evidence",
  trace: "/trace",
};

const NAV_ITEMS = [
  ["portfolio", "Portfolio"], ["site", "Site Overview"], ["investigations", "Investigations"],
  ["evidence", "Evidence"], ["trace", "Trace Mode"], ["data-connections", "Data Connections"],
];

function routeFromLocation() {
  if (typeof window === "undefined") return "portfolio";
  const path = window.location.pathname;
  if (path.startsWith("/sites/")) return "site";
  if (path.startsWith("/investigations")) return "investigations";
  if (path.startsWith("/evidence")) return "evidence";
  if (path.startsWith("/trace")) return "trace";
  return "portfolio";
}

function runIdentity(model, finding) {
  return finding?.runId ?? model?.result?.run_id ?? model?.result?.job_id ?? model?.result?.upload_id ?? null;
}

function WorkspaceEmpty({ onConnect }) {
  return <section className="forensic-empty"><span className="forensic-kicker">Evidence unavailable</span><h1>No analyzed telemetry is available</h1><p>Connect a read-only data source or import telemetry to establish a learned relationship baseline. Neraium will not infer a site conclusion without evidence.</p><button type="button" className="forensic-button" onClick={onConnect}>Open data connections</button></section>;
}

function SiteOverview({ model, onInvestigate, onEvidence }) {
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const highest = model.selectedFinding;
  const additional = model.findings.slice(1);
  return <div className="site-overview">
    <header className="forensic-page-header"><div><span className="forensic-kicker">Site overview</span><h1>{model.site.name}</h1><p>Current comparison window: {highest?.comparison.current ?? "No evidence window supplied"}</p></div><div className="forensic-window"><span>Baseline</span><strong>{highest?.comparison.baseline ?? "Not established"}</strong></div></header>
    <SiteStabilitySummary site={model.site} />
    <section className="site-priority" aria-labelledby="site-priority-title"><div className="site-priority__heading"><div><span className="forensic-kicker">Where should I spend the next hour?</span><h2 id="site-priority-title">{highest ? "Highest-priority evidence" : "No active investigation"}</h2></div>{highest ? <ConfidenceTierChip tier={highest.tier} /> : null}</div><FindingSummary finding={highest} primary onInvestigate={onInvestigate} onEvidence={onEvidence} /></section>
    <section className="subsystem-summary" aria-labelledby="subsystem-summary-title"><header><div><span className="forensic-kicker">Compact system read</span><h2 id="subsystem-summary-title">Subsystems</h2></div><span>{model.subsystems.length} mapped</span></header><div>{model.subsystems.map((subsystem) => <SubsystemStatusRow key={subsystem.id} subsystem={subsystem} onSelect={subsystem.findingCount ? () => onInvestigate(model.findings.find((finding) => finding.system === subsystem.name)) : undefined} />)}</div></section>
    {additional.length ? <section className="additional-findings"><header><div><span className="forensic-kicker">Additional findings</span><h2>Other evidence requiring review</h2></div></header>{additional.map((finding) => <FindingSummary key={finding.id} finding={finding} onInvestigate={onInvestigate} onEvidence={onEvidence} />)}</section> : null}
    <section className="technical-collapse"><button type="button" aria-expanded={technicalOpen} onClick={() => setTechnicalOpen((value) => !value)}><span><span className="forensic-kicker">Technical details</span><strong>Scores, identifiers, and processing metadata</strong></span><span>{technicalOpen ? "Hide" : "Show"}</span></button>{technicalOpen ? <dl><div><dt>Site identity</dt><dd>{model.site.id}</dd></div><div><dt>Evidence coverage</dt><dd>{model.coverage === null ? "Not supplied" : model.coverage.toFixed(3)}</dd></div><div><dt>Relationship records</dt><dd>{model.relationships.length}</dd></div><div><dt>Evidence run</dt><dd>{runIdentity(model, highest) ?? "Not persisted"}</dd></div><div><dt>Detected data type</dt><dd>{model.domainLabel}</dd></div></dl> : null}</section>
  </div>;
}

function InvestigationList({ model, onOpen }) {
  return <div><header className="forensic-page-header"><div><span className="forensic-kicker">Investigations</span><h1>Operational findings</h1><p>Each finding is shown once, bounded by its evidence, contradictions, and limitations.</p></div></header>{model.findings.length ? <div className="investigation-index">{model.findings.map((finding) => <FindingSummary key={finding.id} finding={finding} onInvestigate={onOpen} />)}</div> : <section className="forensic-empty"><h2>No active operational findings</h2><p>The available comparison does not support an investigation.</p></section>}</div>;
}

function relationshipState(value) {
  const state = String(value ?? "").toLowerCase();
  if (/emerg|new|unusual/.test(state)) return "emerging";
  if (/weaken|drift|change|degrad|shift/.test(state)) return "weakening";
  if (/histor|inactive/.test(state)) return "historical";
  if (/stable|normal/.test(state)) return "stable";
  return "insufficient";
}

function historicalRelationships(model, hoursBeforeNow) {
  if (!hoursBeforeNow) return model.relationships;
  const dated = model.timelineFrames.map((frame) => ({ frame, timestamp: new Date(frame?.timestamp ?? frame?.timestamp_start ?? "").getTime() })).filter((item) => Number.isFinite(item.timestamp));
  if (!dated.length) return model.relationships.map((edge) => ({ ...edge, state: "insufficient", current: null, delta: null, confidence: "Historical relationship evidence not supplied" }));
  const latest = Math.max(...dated.map((item) => item.timestamp));
  const target = latest - hoursBeforeNow * 3600000;
  const selectedFrame = dated.reduce((best, item) => Math.abs(item.timestamp - target) < Math.abs(best.timestamp - target) ? item : best).frame;
  const snapshots = selectedFrame?.relationships ?? selectedFrame?.relationship_drift ?? selectedFrame?.topology_state?.relationships ?? [];
  if (!Array.isArray(snapshots) || !snapshots.length) return model.relationships.map((edge) => ({ ...edge, state: "insufficient", current: null, delta: null, confidence: "Historical relationship evidence not supplied" }));
  return model.relationships.map((edge) => {
    const snapshot = snapshots.find((item) => String(item?.id ?? item?.relationship_id ?? "") === edge.id || String(item?.label ?? item?.name ?? "") === edge.label);
    if (!snapshot) return { ...edge, state: "insufficient", current: null, delta: null, confidence: "Relationship was not present in this evidence frame" };
    return { ...edge, state: relationshipState(snapshot?.state ?? snapshot?.status ?? snapshot?.change_type), current: snapshot?.current_strength ?? snapshot?.current ?? null, delta: snapshot?.delta ?? snapshot?.correlation_delta ?? null, confidence: snapshot?.confidence ?? edge.confidence };
  });
}

function InvestigationWorkspace({ model, finding, apiFetch, currentUser, onTrace, onBack }) {
  const [timeValue, setTimeValue] = useState(0);
  const [selected, setSelected] = useState(finding?.relationships?.[0] ?? model.relationships[0] ?? null);
  const [drawerOpen, setDrawerOpen] = useState(true);
  const runId = runIdentity(model, finding);
  const findingRelationships = finding?.relationships;
  const displayRelationships = useMemo(() => historicalRelationships(model, timeValue), [model, timeValue]);
  const selectedEdge = displayRelationships.find((edge) => edge.id === selected?.id);
  const relationship = selectedEdge ?? (selected?.source && selected?.target ? selected : displayRelationships.find((edge) => edge.source === selected?.id || edge.target === selected?.id) ?? finding?.relationships?.[0] ?? null);
  useEffect(() => { setSelected(findingRelationships?.[0] ?? model.relationships[0] ?? null); setDrawerOpen(true); }, [finding?.id, findingRelationships, model.relationships]);
  function selectGraph(item) { setSelected(item); setDrawerOpen(true); }
  return <div className="investigation-workspace">
    <header className="investigation-mobile-header"><button type="button" onClick={onBack} aria-label="Back to investigations">←</button><div><span className="forensic-kicker">Investigation</span><strong>{finding?.title ?? "Evidence review"}</strong></div><ConfidenceTierChip tier={finding?.tier} /></header>
    <div className="investigation-layout">
      <aside className="investigation-context"><ReadOnlyIndicator /><div><span className="forensic-kicker">Investigation identity</span><code>{finding?.id}</code></div><section><h1>{finding?.title}</h1><p>{finding?.system}</p><ConfidenceTierChip tier={finding?.tier} showDefinition /></section><dl><div><dt>Baseline</dt><dd>{finding?.comparison.baseline}</dd></div><div><dt>Current window</dt><dd>{finding?.comparison.current}</dd></div><div><dt>Evidence run</dt><dd>{runId ?? "Not persisted"}</dd></div></dl><nav aria-label="Engineer investigation questions">{["What changed?", "Why does Neraium believe that?", "What supports it?", "What weakens or contradicts it?", "Where should I inspect first?", "What would confirm or rule it out?", "What was the outcome?"].map((question) => <a key={question} href={`#${question.toLowerCase().replace(/[^a-z]+/g, "-")}`}>{question}</a>)}</nav><section><h2>Investigation history</h2><p>{finding?.outcome ? "A verified human outcome is attached to this evidence." : "No verified outcome has been recorded."}</p></section></aside>
      <main className="investigation-analysis" id="investigation-analysis">
        <ObservationInterpretationBlock observation={finding?.observedChange} interpretation={finding?.whyItMatters} conclusion={finding?.title} limitations={[...(finding?.contradictions ?? []), ...(finding?.limitations ?? [])]} />
        <RelationshipGraph nodes={model.nodes} relationships={displayRelationships} selectedId={selected?.id} timeLabel={timeValue === 0 ? "Now vs learned baseline" : `${timeValue} hours before now`} onSelect={selectGraph} />
        <TimeShiftSlider frames={model.timelineFrames} gaps={model.gaps} value={timeValue} onChange={setTimeValue} />
        <section className="selected-relationship"><span className="forensic-kicker">Selected relationship</span><h2>{relationship?.label ?? "No mapped relationship"}</h2><dl><div><dt>Baseline behavior</dt><dd>{relationship?.baseline ?? "Not supplied"}</dd></div><div><dt>Current behavior</dt><dd>{relationship?.current ?? "Not supplied"}</dd></div><div><dt>Semantic state</dt><dd>{relationship?.state ?? "Insufficient evidence"}</dd></div><div><dt>Confidence</dt><dd>{relationship?.confidence || finding?.tier}</dd></div></dl></section>
        <section className="investigation-primary-action" id="where-should-i-inspect-first-"><div><span className="forensic-kicker">Where should I inspect first?</span><h2>{finding?.recommendationAllowed ? finding.firstPlaceToLook : "No specific recommendation is supported"}</h2><p>{finding?.recommendationAllowed ? finding.confirmationCriteria : finding?.limitations?.[0] || "Review the missing evidence before selecting an inspection target."}</p></div><button type="button" className="forensic-button" onClick={() => setDrawerOpen(true)}>Inspect supporting evidence</button></section>
        <InvestigationOutcome runId={runId} apiFetch={apiFetch} currentUser={currentUser} />
        <CmmsExportReview finding={finding} site={model.site} />
      </main>
      <div className="investigation-evidence-rail" aria-label="Evidence panel"><EvidenceDrawer open={drawerOpen} finding={finding} relationship={relationship} result={model.result} gaps={model.gaps} onClose={() => setDrawerOpen(false)} onTrace={onTrace} />{!drawerOpen ? <button type="button" className="forensic-button evidence-rail-open" onClick={() => setDrawerOpen(true)}>Open evidence drawer</button> : null}</div>
    </div>
  </div>;
}

function EvidenceWorkspace({ model, apiFetch, onTrace }) {
  const finding = model.selectedFinding;
  const runId = runIdentity(model, finding);
  return <div className="evidence-workspace"><header className="forensic-page-header"><div><span className="forensic-kicker">Evidence</span><h1>Reasoning lineage</h1><p>Measured, derived, inferred, configured, and human-entered values remain visibly distinct.</p></div><ConfidenceTierChip tier={finding?.tier ?? "Withheld"} /></header>{finding ? <div className="evidence-workspace__layout"><section><EvidenceLineage finding={finding} relationship={finding.relationships[0] ?? model.relationships[0]} result={model.result} /></section><aside><ObservationInterpretationBlock observation={finding.observedChange} interpretation={finding.whyItMatters} conclusion={finding.title} limitations={[...finding.contradictions, ...finding.limitations]} /><EvidencePackageExport runId={runId} apiFetch={apiFetch} /><button type="button" className="forensic-button" onClick={onTrace}>Open trace mode</button></aside></div> : <WorkspaceEmpty />}</div>;
}

function TraceWorkspace({ model, apiFetch, onInvestigation }) {
  const [selectedId, setSelectedId] = useState(model.trace[0]?.id ?? null);
  const [copyState, setCopyState] = useState("");
  const [auditState, setAuditState] = useState("");
  const finding = model.selectedFinding;
  const runId = runIdentity(model, finding);
  async function copyReference() { await navigator.clipboard?.writeText?.(runId || finding?.id || ""); setCopyState("Reference copied."); }
  async function tagForAudit() {
    if (!runId) return;
    setAuditState("Tagging evidence for audit…");
    try {
      const response = await apiFetch(`/api/evidence/runs/${encodeURIComponent(runId)}/audit-tag`, { method: "POST" });
      if (!response.ok) throw new Error("Evidence could not be tagged for audit.");
      setAuditState("Evidence tagged for audit.");
    } catch (error) { setAuditState(error?.message || "Evidence could not be tagged for audit."); }
  }
  return <div className="trace-workspace"><header className="forensic-page-header"><div><span className="forensic-kicker">Trace mode</span><h1>Reproducible conclusion lineage</h1><p>Observation → normalization → feature → relationship → drift → interpretation → finding → recommendation</p></div><ReadOnlyIndicator /></header><div className="trace-actions"><EvidencePackageExport runId={runId} apiFetch={apiFetch} /><button type="button" className="forensic-button forensic-button--secondary" onClick={tagForAudit} disabled={!runId}>Tag for audit</button><button type="button" className="forensic-button forensic-button--secondary" onClick={copyReference}>Copy reference</button><button type="button" className="forensic-button" onClick={() => onInvestigation(finding)}>Open related investigation</button><span role="status" aria-live="polite">{auditState || copyState}</span></div><TraceTimeline steps={model.trace} selectedId={selectedId} onSelect={(step) => setSelectedId(step.id)} /></div>;
}

export default function EngineeringReasoningWorkspace({ liveOps, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, domainDetection, apiFetch, onWorkspaceNavigate, onSignOut, signOutPending = false, currentUser }) {
  const [route, setRoute] = useState(routeFromLocation);
  const [selectedFindingId, setSelectedFindingId] = useState(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [evidenceSelection, setEvidenceSelection] = useState(null);
  const [selectedSiteId, setSelectedSiteId] = useState(null);
  const [portfolioRuns, setPortfolioRuns] = useState([]);
  const currentModel = useMemo(() => buildEngineeringReasoningModel({ liveOps, canonicalFinding, currentSession, result: effectiveLatestUploadResult, snapshot: effectiveLatestUploadSnapshot, domainDetection }), [liveOps, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, domainDetection]);
  const portfolioModels = useMemo(() => {
    const persisted = buildEngineeringReasoningModelsFromEvidenceRuns(portfolioRuns);
    const withoutCurrent = persisted.filter((item) => item.site.id !== currentModel.site.id);
    return [currentModel, ...withoutCurrent];
  }, [currentModel, portfolioRuns]);
  const model = portfolioModels.find((item) => item.site.id === selectedSiteId) ?? currentModel;
  const selectedFinding = model.findings.find((finding) => finding.id === selectedFindingId) ?? model.selectedFinding;
  useEffect(() => {
    let cancelled = false;
    Promise.resolve(apiFetch?.("/api/evidence/runs?limit=100"))
      .then((response) => response?.ok ? response.json() : null)
      .then((payload) => { if (!cancelled && Array.isArray(payload?.runs)) setPortfolioRuns(payload.runs); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [apiFetch]);
    useEffect(() => { const onPop = () => setRoute(routeFromLocation()); window.addEventListener("popstate", onPop); return () => window.removeEventListener("popstate", onPop); }, []);
  useEffect(() => { const keyHandler = (event) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); document.querySelector(".global-asset-search input")?.focus(); } }; window.addEventListener("keydown", keyHandler); return () => window.removeEventListener("keydown", keyHandler); }, []);
  function navigate(target) {
    if (target === "data-connections" || target === "governance-admin") { onWorkspaceNavigate?.(target); return; }
    const path = target === "investigations" && selectedFindingId ? `/investigations/${encodeURIComponent(selectedFindingId)}` : ROUTES[target];
    window.history.pushState({}, "", path); setRoute(target); setMobileNavOpen(false); document.getElementById("forensic-main")?.focus({ preventScroll: true });
  }
  function openFinding(finding) { if (!finding) return; setSelectedFindingId(finding.id); window.history.pushState({}, "", `/investigations/${encodeURIComponent(finding.id)}`); setRoute("investigations"); setEvidenceSelection(null); }
  function openEvidence(finding) { setSelectedFindingId(finding.id); setEvidenceSelection(finding); window.history.pushState({}, "", `/evidence/${encodeURIComponent(finding.id)}`); setRoute("evidence"); }
  function handleSearch(item) { if (item.findingId) setSelectedFindingId(item.findingId); if (item.target === "investigation") { const finding = model.findings.find((candidate) => candidate.id === item.findingId) ?? model.findings.find((candidate) => candidate.variables.includes(item.nodeId)) ?? selectedFinding; openFinding(finding); } else navigate(item.target); }
  const inOpenInvestigation = route === "investigations" && Boolean(selectedFindingId || window.location.pathname.split("/").filter(Boolean).length > 1);
  return <div className="forensic-shell" data-testid="engineering-reasoning-platform">
    <a className="skip-link" href="#forensic-main">Skip to main content</a>
    <aside className={`forensic-sidebar${mobileNavOpen ? " is-open" : ""}`} aria-label="Application sidebar"><div className="forensic-brand"><span className="forensic-brand__mark" aria-hidden="true">N</span><div><strong>Neraium</strong><small>SII engineering intelligence</small></div></div><nav aria-label="Primary navigation">{NAV_ITEMS.map(([id, label]) => <button key={id} type="button" className={route === id ? "is-active" : ""} aria-current={route === id ? "page" : undefined} onClick={() => navigate(id)}><span aria-hidden="true" className={`nav-glyph nav-glyph--${id}`} />{label}{id === "investigations" && model.findings.length ? <small>{model.findings.length}</small> : null}</button>)}</nav><div className="forensic-sidebar__boundary"><ReadOnlyIndicator compact /><p>{model.site.governanceStatement}</p></div><div className="forensic-sidebar__account"><span>{currentUser?.name || currentUser?.email || "Signed in"}</span><small>{currentUser?.role || "engineer"}</small>{currentUser?.role === "admin" ? <button type="button" onClick={() => navigate("governance-admin")}>Governance / Administration</button> : null}{onSignOut ? <button type="button" onClick={onSignOut} disabled={signOutPending}>{signOutPending ? "Signing out…" : "Sign out"}</button> : null}</div></aside>
    <div className="forensic-app"><header className="forensic-topbar"><button type="button" className="forensic-mobile-menu" aria-expanded={mobileNavOpen} aria-label="Toggle navigation" onClick={() => setMobileNavOpen((value) => !value)}>☰</button><GlobalAssetSearch items={model.searchItems} onSelect={handleSearch} /><div className="forensic-topbar__site"><span>{model.site.name}</span><ConfidenceTierChip tier={model.evidenceQuality} /></div></header>
      <main id="forensic-main" aria-label="Neraium platform workspace" tabIndex={-1}>{!model.hasAnalysis && route !== "portfolio" ? <WorkspaceEmpty onConnect={() => navigate("data-connections")} /> : route === "portfolio" ? <PortfolioWorkspace sites={portfolioModels.map((item) => item.site)} onSelectSite={(site) => { setSelectedSiteId(site.id); navigate("site"); }} /> : route === "site" ? <SiteOverview model={model} onInvestigate={openFinding} onEvidence={openEvidence} /> : route === "investigations" ? (inOpenInvestigation && selectedFinding ? <InvestigationWorkspace model={model} finding={selectedFinding} apiFetch={apiFetch} currentUser={currentUser} onTrace={() => navigate("trace")} onBack={() => { setSelectedFindingId(null); window.history.pushState({}, "", ROUTES.investigations); setRoute("investigations"); }} /> : <InvestigationList model={model} onOpen={openFinding} />) : route === "evidence" ? <EvidenceWorkspace model={{ ...model, selectedFinding: evidenceSelection ?? selectedFinding }} apiFetch={apiFetch} onTrace={() => navigate("trace")} /> : <TraceWorkspace model={{ ...model, selectedFinding }} apiFetch={apiFetch} onInvestigation={openFinding} />}</main>
    </div>
  </div>;
}
