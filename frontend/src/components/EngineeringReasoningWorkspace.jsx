import React, { useEffect, useMemo, useState } from "react";
import { buildEngineeringReasoningModel, buildEngineeringReasoningModelsFromEvidenceRuns } from "../viewModels/engineeringReasoning";
import { normalizeFindingPresentation } from "../viewModels/operatorFinding";
import ConfidenceTierChip from "./engineering/ConfidenceTierChip";
import EvidenceLineage from "./engineering/EvidenceLineage";
import EvidencePackageExport from "./engineering/EvidencePackageExport";
import FindingSummary from "./engineering/FindingSummary";
import FindingClassificationSummary from "./operational/FindingClassificationSummary";
import GlobalAssetSearch from "./engineering/GlobalAssetSearch";
import PortfolioWorkspace from "./engineering/PortfolioWorkspace";
import TraceTimeline from "./engineering/TraceTimeline";
import "../styles/engineering-reasoning.css";

const ROUTES = {
  portfolio: "/portfolio",
  site: "/sites/current",
  evidence: "/evidence",
  trace: "/trace",
};

function routeFromLocation() {
  if (typeof window === "undefined") return "portfolio";
  const path = window.location.pathname;
  if (path.startsWith("/systems/")) return "system";
  if (path.startsWith("/sites/")) return "site";
  if (path.startsWith("/evidence") || path.startsWith("/investigations")) return "evidence";
  if (path.startsWith("/trace")) return "trace";
  return "portfolio";
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

function EmptyAnalysis({ onConnect }) {
  return (
    <section className="operational-empty">
      <span className="operational-label">Status</span>
      <strong className="operational-status operational-status--evidence-insufficient">Evidence insufficient</strong>
      <h1>No analyzed dataset is available</h1>
      <p>Analyze a dataset to establish a baseline and compare current behavior.</p>
      <button type="button" className="forensic-button" onClick={onConnect}>Review Data Requirements</button>
    </section>
  );
}

function TechnicalSummary({ model }) {
  const warnings = model.selectedFinding?.technicalLimitations ?? [];
  return (
    <details className="operational-technical">
      <summary>Technical Details</summary>
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

function SiteOverview({ model, onEvidence }) {
  return (
    <div className="site-overview operational-overview">
      <OverviewHeader eyebrow={model.site.assigned ? "Site overview" : "Analysis overview"} name={model.site.name} status={model.status} confidence={model.evidenceQuality} summary={findingCountSummary(model.findings, model.status)} />
      {model.findings.length ? (
        <section className="active-findings" aria-label="Active findings">
          <div>{model.findings.map((finding) => <FindingSummary key={finding.id} finding={finding} onEvidence={onEvidence} />)}</div>
        </section>
      ) : (
        <section className="normal-summary">
          <span>What</span>
          <h2>{model.status === "Normal" ? "No active findings" : "No reliable finding can be shown"}</h2>
          <p>{model.status === "Normal" ? "Measured relationships remain within the learned baseline." : "The available evidence does not support a reliable comparison."}</p>
          <button type="button" className="forensic-button" onClick={() => onEvidence(null)}>Open Evidence</button>
        </section>
      )}
      <TechnicalSummary model={model} />
    </div>
  );
}

function SystemOverview({ model, system, onEvidence }) {
  if (!system) return <SiteOverview model={model} onEvidence={onEvidence} />;
  return (
    <div className="system-overview operational-overview">
      <OverviewHeader eyebrow="System overview" name={system.name} status={system.status} confidence={system.evidenceTier} location={system.location.join(" / ")} summary={findingCountSummary(system.findings, system.status)} />
      {system.findings.length ? (
        <section className="active-findings" aria-label="Active findings">
          <div>{system.findings.map((finding) => <FindingSummary key={finding.id} finding={finding} onEvidence={onEvidence} />)}</div>
        </section>
      ) : (
        <section className="normal-summary">
          <span>What</span>
          <h2>{system.status === "Normal" ? "No active findings" : "Evidence is insufficient for this system"}</h2>
          <p>{system.status === "Normal" ? "Mapped relationships remain within the learned baseline." : "A reliable system comparison is not available."}</p>
          <button type="button" className="forensic-button" onClick={() => onEvidence(null)}>Open Evidence</button>
        </section>
      )}
      <TechnicalSummary model={model} />
    </div>
  );
}

function LocationHierarchy({ items }) {
  return <ol className="location-hierarchy">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ol>;
}

function findingTimelineLabel(event) {
  if (event.periodLabel) return event.periodLabel;
  if (event.time) return event.time;
  if (event.start && event.end) return `${event.start} to ${event.end}`;
  if (event.start) return `From ${event.start}`;
  if (event.end) return `Through ${event.end}`;
  return "";
}

function displayLabel(value) {
  return String(value || "Unavailable").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function uniqueText(values) {
  return [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];
}

function EvidenceWorkspace({ model, finding, apiFetch, onTrace, onBack }) {
  const runId = runIdentity(model, finding);
  if (!finding) {
    return (
      <div className="evidence-workspace operational-evidence">
        <button type="button" className="evidence-back" onClick={onBack}>Back to overview</button>
        <OverviewHeader eyebrow="Evidence" name={model.status === "Normal" ? "No active findings" : "Evidence requirements not met"} status={model.status} confidence={model.evidenceQuality} />
        <section className="evidence-section"><span>Where</span><LocationHierarchy items={[model.site.locationLabel]} /></section>
        <section className="evidence-section"><span>Baseline vs current</span><p>{model.status === "Normal" ? "Mapped relationships remain within their learned behavior." : "A reliable baseline comparison is not available."}</p></section>
        <TechnicalSummary model={model} />
      </div>
    );
  }
  const limiting = [...finding.contradictions, ...finding.limitations];
  const relationship = finding.relationships[0] ?? model.relationships[0] ?? null;
  const presentation = finding.classificationPresentation ?? normalizeFindingPresentation(finding);
  const dataLimitations = uniqueText([...presentation.dataLimitations, ...limiting, presentation.certaintyLimit]);
  return (
    <div className="evidence-workspace operational-evidence">
      <button type="button" className="evidence-back" onClick={onBack}>Back to overview</button>
      <OverviewHeader eyebrow="Evidence" name={finding.title} status={finding.status} confidence={finding.tier} />
      <FindingClassificationSummary finding={finding} />
      {finding.confidenceReason ? <p className="evidence-confidence-reason">{finding.confidenceReason}</p> : null}
      <div className="operational-evidence__sections operational-evidence__sections--classification">
        <section className="evidence-section evidence-section--what">
          <h2>What changed</h2>
          <p>{finding.observedChange}</p>
          <p><strong>Engineering relevance:</strong> {finding.whyItMatters}</p>
          <h3>Where</h3>
          <LocationHierarchy items={finding.location.hierarchy} />
        </section>
        <section className="evidence-section">
          <h2>Why Neraium classified it this way</h2>
          <p>{presentation.meaning}</p>
          <ul>{presentation.reasons.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
        <section className="evidence-section">
          <h2>Data confidence and sensor-health context</h2>
          <dl className="classification-detail-grid">
            <div><dt>Data confidence</dt><dd>{presentation.dataConfidence.rating}</dd></div>
            <div><dt>Summary</dt><dd>{presentation.dataConfidence.summary}</dd></div>
          </dl>
          {presentation.sensorHealth.length ? <ul className="classification-sensor-list">{presentation.sensorHealth.map((sensor) => <li key={sensor.signal}><strong>{displayLabel(sensor.signal)} · {displayLabel(sensor.health)}</strong>{sensor.conditions.length ? <ul>{sensor.conditions.map((condition, index) => <li key={`${condition.type}-${index}`}>{displayLabel(condition.type)}: {condition.evidence || "No supporting condition detail was recorded."}</li>)}</ul> : null}</li>)}</ul> : <p>Sensor-health conditions were not recorded for this finding.</p>}
        </section>
        <section className="evidence-section">
          <h2>Operating-mode comparison</h2>
          <dl className="classification-detail-grid classification-detail-grid--mode">
            <div><dt>Baseline mode</dt><dd>{presentation.operatingMode.baseline}</dd></div>
            <div><dt>Recent mode</dt><dd>{presentation.operatingMode.recent}</dd></div>
            <div><dt>Mode match</dt><dd>{presentation.operatingMode.match}</dd></div>
            <div><dt>Comparison confidence</dt><dd>{presentation.operatingMode.confidence}</dd></div>
          </dl>
          {presentation.operatingMode.differences.length ? <ul>{presentation.operatingMode.differences.map((item, index) => <li key={`${item.feature}-${index}`}><strong>{displayLabel(item.feature)}:</strong> {item.reason || "A recorded operating-mode difference was present."}</li>)}</ul> : null}
          {presentation.operatingMode.reasons.length ? <ul>{presentation.operatingMode.reasons.map((item) => <li key={item}>{item}</li>)}</ul> : null}
        </section>
        <section className="evidence-section">
          <h2>Relationship timeline</h2>
          {presentation.timeline.length ? <ol className="classification-timeline">{presentation.timeline.map((event, index) => <li key={`${event.eventType}-${index}`}><time>{findingTimelineLabel(event)}</time><strong>{event.title}</strong>{event.detail ? <p>{event.detail}</p> : null}</li>)}</ol> : <p>No source-bounded timeline milestones were recorded for this finding.</p>}
        </section>
        <section className="evidence-section">
          <h2>Supporting evidence</h2>
          <p>{finding.comparisonSummary}</p>
          {finding.supporting.length ? <ul>{finding.supporting.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No supporting observation was supplied.</p>}
        </section>
        <section className="evidence-section">
          <h2>Highest-value next checks</h2>
          {presentation.investigationGuidance.length ? <ol className="classification-guidance">{presentation.investigationGuidance.map((item) => <li key={`${item.rank}-${item.check}`}><span>{item.rank}</span><div><small>{displayLabel(item.category)}</small><strong>{item.check}</strong><p>{item.reason}</p></div></li>)}</ol> : <p>No evidence-linked next check was recorded for this finding.</p>}
        </section>
        <section className="evidence-section">
          <h2>Alternative explanations</h2>
          {presentation.alternativeExplanations.length ? <ul>{presentation.alternativeExplanations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No alternative-explanation list was recorded for this finding.</p>}
        </section>
        <section className="evidence-section">
          <h2>Data limitations</h2>
          {dataLimitations.length ? <ul>{dataLimitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No additional data limitations were recorded.</p>}
        </section>
      </div>
      <details className="operational-technical evidence-technical">
        <summary>Technical Details</summary>
        <div className="operational-technical__content">
          <dl>
            <div><dt>Baseline window</dt><dd>{finding.comparison.baseline}</dd></div>
            <div><dt>Current window</dt><dd>{finding.comparison.current}</dd></div>
            <div><dt>Baseline relationship value</dt><dd>{finding.comparison.baselineValue ?? "Not supplied"}</dd></div>
            <div><dt>Current relationship value</dt><dd>{finding.comparison.currentValue ?? "Not supplied"}</dd></div>
            <div><dt>Relationship delta</dt><dd>{finding.comparison.delta ?? "Not supplied"}</dd></div>
            <div><dt>Evidence run</dt><dd>{runId ?? "Not persisted"}</dd></div>
          </dl>
          {finding.technicalLimitations.length ? <section><h3>All processing notes</h3><ul>{finding.technicalLimitations.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
          <EvidenceLineage finding={finding} relationship={relationship} result={model.result} />
          <div className="technical-actions">
            <EvidencePackageExport runId={runId} apiFetch={apiFetch} />
            <button type="button" className="forensic-button forensic-button--secondary" onClick={onTrace}>Open Trace Mode</button>
          </div>
        </div>
      </details>
    </div>
  );
}

function TraceWorkspace({ model, finding, apiFetch, onBack }) {
  const [selectedId, setSelectedId] = useState(model.trace[0]?.id ?? null);
  const runId = runIdentity(model, finding);
  return (
    <div className="trace-workspace">
      <button type="button" className="evidence-back" onClick={onBack}>Back to evidence</button>
      <header className="forensic-page-header"><div><span className="forensic-kicker">Technical Details</span><h1>Trace Mode</h1><p>Computational lineage for the selected evidence record.</p></div></header>
      <div className="trace-actions"><EvidencePackageExport runId={runId} apiFetch={apiFetch} /></div>
      <TraceTimeline steps={model.trace} selectedId={selectedId} onSelect={(step) => setSelectedId(step.id)} />
    </div>
  );
}

export default function EngineeringReasoningWorkspace({ liveOps, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, domainDetection, apiFetch, onWorkspaceNavigate, onSignOut, signOutPending = false, currentUser }) {
  const [route, setRoute] = useState(routeFromLocation);
  const [selectedFindingId, setSelectedFindingId] = useState(() => pathIdentity(["evidence", "investigations"]));
  const [selectedSystemName, setSelectedSystemName] = useState(() => pathIdentity(["systems"]));
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [selectedSiteId, setSelectedSiteId] = useState(() => pathIdentity(["sites"]) || null);
  const [portfolioRuns, setPortfolioRuns] = useState([]);
  const currentModel = useMemo(() => buildEngineeringReasoningModel({ liveOps, canonicalFinding, currentSession, result: effectiveLatestUploadResult, snapshot: effectiveLatestUploadSnapshot, domainDetection }), [liveOps, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, domainDetection]);
  const portfolioModels = useMemo(() => {
    const persisted = buildEngineeringReasoningModelsFromEvidenceRuns(portfolioRuns);
    const currentName = currentModel.site.name.trim().toLowerCase();
    const withoutCurrent = persisted.filter((item) => item.site.id !== currentModel.site.id && item.site.name.trim().toLowerCase() !== currentName);
    if (currentModel.hasAnalysis) return [currentModel, ...withoutCurrent];
    return persisted.length ? persisted : [currentModel];
  }, [currentModel, portfolioRuns]);
  const model = portfolioModels.find((item) => item.site.id === selectedSiteId) ?? currentModel;
  const selectedFinding = selectedFindingId === "__overview__" ? null : model.findings.find((finding) => finding.id === selectedFindingId) ?? model.selectedFinding;
  const selectedSystem = model.subsystems.find((system) => system.name === selectedSystemName) ?? null;
  const effectiveRoute = route === "portfolio" && portfolioModels.length <= 1 ? "site" : route;
  const navItems = portfolioModels.length > 1 ? [["portfolio", "Portfolio"], ["site", "Site Overview"], ["data-connections", "Data Connections"]] : [["site", "Site Overview"], ["data-connections", "Data Connections"]];

  useEffect(() => {
    let cancelled = false;
    Promise.resolve(apiFetch?.("/api/evidence/runs?limit=100"))
      .then((response) => response?.ok ? response.json() : null)
      .then((payload) => { if (!cancelled && Array.isArray(payload?.runs)) setPortfolioRuns(payload.runs); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [apiFetch]);

  useEffect(() => {
    const onPop = () => {
      setRoute(routeFromLocation());
      setSelectedFindingId(pathIdentity(["evidence", "investigations"]));
      setSelectedSystemName(pathIdentity(["systems"]));
      setSelectedSiteId(pathIdentity(["sites"]) || null);
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

  function navigate(target) {
    if (target === "data-connections" || target === "governance-admin") {
      onWorkspaceNavigate?.(target);
      return;
    }
    const path = target === "site" ? `/sites/${encodeURIComponent(model.site.id)}` : ROUTES[target];
    window.history.pushState({}, "", path);
    setRoute(target);
    setMobileNavOpen(false);
  }

  function openEvidence(finding) {
    setSelectedFindingId(finding?.id || "__overview__");
    const evidencePath = finding ? `/evidence/${encodeURIComponent(finding.id)}` : "/evidence";
    window.history.pushState({}, "", evidencePath);
    setRoute("evidence");
  }

  function openSystem(name) {
    setSelectedSystemName(name);
    window.history.pushState({}, "", `/systems/${encodeURIComponent(name)}`);
    setRoute("system");
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

  return (
    <div className="forensic-shell" data-testid="engineering-reasoning-platform">
      <a className="skip-link" href="#forensic-main">Skip to main content</a>
      <aside className={`forensic-sidebar${mobileNavOpen ? " is-open" : ""}`} aria-label="Application sidebar">
        <div className="forensic-brand"><span className="forensic-brand__mark" aria-hidden="true">N</span><div><strong>Neraium</strong><small>Operational evidence</small></div></div>
        <nav aria-label="Primary navigation">
          {navItems.map(([id, label]) => <button key={id} type="button" className={effectiveRoute === id ? "is-active" : ""} aria-current={effectiveRoute === id ? "page" : undefined} onClick={() => navigate(id)}><span aria-hidden="true" className={`nav-glyph nav-glyph--${id}`} />{label}</button>)}
        </nav>
        <div className="forensic-sidebar__account">
          <span>{currentUser?.name || currentUser?.email || "Signed in"}</span><small>{currentUser?.role || "engineer"}</small>
          {currentUser?.role === "admin" ? <button type="button" onClick={() => navigate("governance-admin")}>Administration</button> : null}
          {onSignOut ? <button type="button" onClick={onSignOut} disabled={signOutPending}>{signOutPending ? "Signing out..." : "Sign out"}</button> : null}
        </div>
      </aside>
      <div className="forensic-app">
        <header className="forensic-topbar">
          <button type="button" className="forensic-mobile-menu" aria-expanded={mobileNavOpen} aria-label="Toggle navigation" onClick={() => setMobileNavOpen((value) => !value)}>Menu</button>
          <GlobalAssetSearch items={model.searchItems} onSelect={handleSearch} />
          <div className="forensic-topbar__site"><span>{model.site.name}</span><ConfidenceTierChip tier={model.evidenceQuality} /></div>
        </header>
        <main id="forensic-main" aria-label="Neraium operational workspace" tabIndex={-1}>
          {!model.hasAnalysis ? <EmptyAnalysis onConnect={() => navigate("data-connections")} />
            : effectiveRoute === "portfolio" ? <PortfolioWorkspace sites={portfolioModels.map((item) => item.site)} onSelectSite={(site) => { setSelectedSiteId(site.id); window.history.pushState({}, "", "/sites/" + encodeURIComponent(site.id)); setRoute("site"); setMobileNavOpen(false); }} />
              : effectiveRoute === "site" ? <SiteOverview model={model} onEvidence={openEvidence} />
                : effectiveRoute === "system" ? <SystemOverview model={model} system={selectedSystem} onEvidence={openEvidence} />
                  : effectiveRoute === "evidence" ? <EvidenceWorkspace model={model} finding={selectedFinding} apiFetch={apiFetch} onTrace={() => navigate("trace")} onBack={() => navigate("site")} />
                    : <TraceWorkspace model={model} finding={selectedFinding} apiFetch={apiFetch} onBack={() => openEvidence(selectedFinding)} />}
        </main>
      </div>
    </div>
  );
}
