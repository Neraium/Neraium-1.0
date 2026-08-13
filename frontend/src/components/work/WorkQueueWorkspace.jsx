import React, { useEffect, useMemo, useState } from "react";
import { fetchFinding, fetchFindingActivity, fetchFindingMembers, fetchFindings, isFindingApiUnavailable, patchFindingWorkflow, postFindingFieldReport, resolveFinding } from "../../services/api/findingsApi";
import { emptyStateForQueue, normalizeWorkFinding, queryForWorkQueue, workCardAction, workFiltersForMode, workStatusLabel } from "../../viewModels/workQueue";
import OperationalFindingBrief from "./OperationalFindingBrief";
import WorkFindingCard from "./WorkFindingCard";
import "../../styles/work-workflow.css";

const PAGE_SIZE = 30;

function clean(value) {
  return String(value ?? "").trim();
}

export default function WorkQueueWorkspace({ apiFetch, currentUser, currentWorkspace = null, findingId = "", onRouteFinding, onOpenInvestigation, onOpenEvidence, technicalFindingFor }) {
  const [mode, setMode] = useState("mine");
  const [filter, setFilter] = useState("active");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [controls, setControls] = useState({ assignee: "", priority: "", status: "", system: "" });
  const [offset, setOffset] = useState(0);
  const [queue, setQueue] = useState({ items: [], loading: true, error: "", hasMore: false });
  const [selectedId, setSelectedId] = useState(clean(findingId));
  const [selectedItem, setSelectedItem] = useState(null);
  const [membersState, setMembersState] = useState({ items: [], loading: true, error: "" });
  const [detailState, setDetailState] = useState({ loading: false, error: "" });
  const [activity, setActivity] = useState({ items: [], loading: false, error: "" });
  const [mutation, setMutation] = useState({ pending: false, message: "", error: false });
  const [reloadKey, setReloadKey] = useState(0);
  const members = membersState.items;
  const workspaceName = clean(currentWorkspace?.display_name ?? currentWorkspace?.displayName) || "Personal workspace";
  const visibleFilters = workFiltersForMode(mode);
  const activeControlCount = mode === "team" ? Object.values(controls).filter((value) => clean(value)).length : 0;

  useEffect(() => {
    setSelectedId(clean(findingId));
  }, [findingId]);

  useEffect(() => {
    let cancelled = false;
    setMembersState({ items: [], loading: true, error: "" });
    fetchFindingMembers({ apiFetch })
      .then((items) => { if (!cancelled) setMembersState({ items, loading: false, error: "" }); })
      .catch(() => { if (!cancelled) setMembersState({ items: [], loading: false, error: "Team members could not be loaded for this facility workspace." }); });
    return () => { cancelled = true; };
  }, [apiFetch]);

  useEffect(() => {
    let cancelled = false;
    setQueue((current) => ({ ...current, loading: true, error: "" }));
    const query = queryForWorkQueue({ mode, filter, ...controls, limit: PAGE_SIZE, offset });
    fetchFindings({ apiFetch, ...query })
      .then((payload) => {
        if (cancelled) return;
        const items = payload.findings.map((item) => normalizeWorkFinding(item));
        setQueue({ items, loading: false, error: "", hasMore: Boolean(payload.has_more) });
        if (selectedId) {
          const selected = items.find((item) => item.findingId === selectedId);
          if (selected) setSelectedItem(selected);
        }
      })
      .catch((error) => { if (!cancelled) setQueue({ items: [], loading: false, error: error?.message || "Work could not be loaded.", hasMore: false }); });
    return () => { cancelled = true; };
  }, [apiFetch, controls, filter, mode, offset, reloadKey, selectedId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedId) {
      setSelectedItem(null);
      setDetailState({ loading: false, error: "" });
      return undefined;
    }
    const queued = queue.items.find((item) => item.findingId === selectedId);
    if (queued) {
      setSelectedItem(queued);
      setDetailState({ loading: false, error: "" });
      return undefined;
    }
    setSelectedItem(null);
    setDetailState({ loading: true, error: "" });
    fetchFinding({ apiFetch, findingId: selectedId })
      .then((result) => {
        if (cancelled) return;
        setSelectedItem(normalizeWorkFinding({ finding: result.payload, workflow: result.workflow }));
        setDetailState({ loading: false, error: "" });
      })
      .catch((error) => {
        if (cancelled) return;
        setDetailState({
          loading: false,
          error: isFindingApiUnavailable(error)
            ? "This finding is unavailable in the current facility workspace."
            : "This work item could not be loaded. Try again.",
        });
      });
    return () => { cancelled = true; };
  }, [apiFetch, queue.items, selectedId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedItem?.findingId) {
      setActivity({ items: [], loading: false, error: "" });
      return undefined;
    }
    setActivity({ items: [], loading: true, error: "" });
    fetchFindingActivity({ apiFetch, findingId: selectedItem.findingId })
      .then((items) => { if (!cancelled) setActivity({ items, loading: false, error: "" }); })
      .catch((error) => { if (!cancelled) setActivity({ items: [], loading: false, error: error?.message || "Activity could not be loaded." }); });
    return () => { cancelled = true; };
  }, [apiFetch, selectedItem?.findingId, selectedItem?.version]);

  const empty = emptyStateForQueue({ mode, filter, filtered: activeControlCount > 0 });
  const selectedFilterLabel = visibleFilters.find((item) => item.id === filter)?.label ?? "Current view";
  const technicalFinding = useMemo(() => selectedItem ? technicalFindingFor?.(selectedItem) ?? null : null, [selectedItem, technicalFindingFor]);

  function changeMode(nextMode) {
    setMode(nextMode);
    if (nextMode === "mine" && filter === "needs-assignment") setFilter("active");
    if (nextMode === "mine") setFiltersOpen(false);
    setOffset(0);
  }

  function clearControls() {
    setControls({ assignee: "", priority: "", status: "", system: "" });
    setOffset(0);
  }

  function changeFilter(nextFilter) {
    setFilter(nextFilter);
    setOffset(0);
  }

  function updateControl(name, value) {
    setControls((current) => ({ ...current, [name]: value }));
    setOffset(0);
  }

  function openFinding(finding) {
    setSelectedId(finding.findingId);
    setSelectedItem(finding);
    setDetailState({ loading: false, error: "" });
    onRouteFinding?.(finding.findingId);
  }

  function closeFinding() {
    setSelectedId("");
    setSelectedItem(null);
    setDetailState({ loading: false, error: "" });
    onRouteFinding?.("");
  }

  function applyResult(result, message) {
    setSelectedItem(normalizeWorkFinding({ finding: result.payload, workflow: result.workflow }));
    setMutation({ pending: false, message, error: false });
    setReloadKey((value) => value + 1);
  }

  async function mutateWorkflow(changes, successMessage = "Work updated.") {
    if (!selectedItem) return;
    setMutation({ pending: true, message: "", error: false });
    try {
      const result = await patchFindingWorkflow({ apiFetch, findingId: selectedItem.findingId, expectedVersion: selectedItem.version, changes });
      applyResult(result, successMessage);
    } catch (error) {
      setMutation({ pending: false, message: error?.message || "Work could not be updated.", error: true });
      throw error;
    }
  }

  async function submitFieldReport(report) {
    if (!selectedItem) return;
    setMutation({ pending: true, message: "", error: false });
    try {
      const result = await postFindingFieldReport({ apiFetch, findingId: selectedItem.findingId, expectedVersion: selectedItem.version, ...report });
      applyResult(result, report.investigationComplete ? "Investigation sent for review." : "Field update saved.");
    } catch (error) {
      setMutation({ pending: false, message: error?.message || "Field update could not be saved.", error: true });
      throw error;
    }
  }

  async function resolve(outcome, note) {
    if (!selectedItem) return;
    setMutation({ pending: true, message: "", error: false });
    try {
      const result = await resolveFinding({ apiFetch, findingId: selectedItem.findingId, expectedVersion: selectedItem.version, outcome, note });
      applyResult(result, "Review outcome recorded.");
    } catch (error) {
      setMutation({ pending: false, message: error?.message || "Review outcome could not be saved.", error: true });
    }
  }

  return (
    <div className={`work-workspace${selectedId ? " has-selection" : ""}`} data-testid="work-queue-workspace">
      <section className="work-queue" aria-labelledby="work-queue-title">
        <header className="work-queue__header"><div><span className="work-eyebrow">Facility workspace · {workspaceName}</span><h1 id="work-queue-title">Work</h1><p>Shared findings and human action for this maintenance team.</p></div></header>
        <div className="work-mode-switch" role="group" aria-label="Work view"><button type="button" aria-pressed={mode === "mine"} onClick={() => changeMode("mine")}>My Work</button><button type="button" aria-pressed={mode === "team"} onClick={() => changeMode("team")}>Team Findings</button></div>
        <div className="work-filter-list" aria-label={`${mode === "mine" ? "My Work" : "Team Findings"} filters`}>{visibleFilters.map((item) => <button type="button" key={item.id} aria-pressed={filter === item.id} onClick={() => changeFilter(item.id)}>{item.label}</button>)}</div>
        {mode === "team" ? <>
          <div className="work-filter-tools">
            <button type="button" className="work-filter-toggle" aria-expanded={filtersOpen} aria-controls="work-queue-controls" onClick={() => setFiltersOpen((value) => !value)}>More filters{activeControlCount ? ` · ${activeControlCount} active` : ""}</button>
            {activeControlCount ? <button type="button" className="work-filter-clear" onClick={clearControls}>Clear filters</button> : null}
          </div>
          <div id="work-queue-controls" className="work-queue-controls" aria-label="Additional team filters" hidden={!filtersOpen}>
            <label>Assignee<select value={controls.assignee} disabled={membersState.loading || Boolean(membersState.error)} onChange={(event) => updateControl("assignee", event.target.value)}><option value="">Anyone</option>{members.map((member) => <option key={member.memberId} value={member.memberId}>{member.displayName}</option>)}</select></label>
            <label>Priority<select value={controls.priority} onChange={(event) => updateControl("priority", event.target.value)}><option value="">Any priority</option>{["low", "medium", "high", "critical"].map((item) => <option key={item} value={item}>{item[0].toUpperCase() + item.slice(1)}</option>)}</select></label>
            <label>Status<select value={controls.status} onChange={(event) => updateControl("status", event.target.value)}><option value="">Any status</option>{["open", "acknowledged", "investigating", "waiting", "escalated", "awaiting_review", "monitoring", "resolved", "dismissed"].map((item) => <option key={item} value={item}>{workStatusLabel(item)}</option>)}</select></label>
            <label>System<input value={controls.system} onChange={(event) => updateControl("system", event.target.value)} placeholder="System name" /></label>
          </div>
          {membersState.error && filtersOpen ? <p className="work-member-error" role="alert">{membersState.error}</p> : null}
        </> : null}

        {queue.loading ? <div className="work-queue-state work-queue-state--loading" role="status"><span className="work-loading-mark" aria-hidden="true" /><h2>Loading {mode === "mine" ? "My Work" : "Team Findings"}</h2><p>Fetching the latest work for {workspaceName}.</p></div>
          : queue.error ? <div className="work-queue-state" role="alert"><h2>Work is unavailable</h2><p>{queue.error}</p><button type="button" onClick={() => setReloadKey((value) => value + 1)}>Try again</button></div>
            : queue.items.length ? <div className="work-card-list">{queue.items.map((finding) => <WorkFindingCard key={finding.findingId} finding={finding} mode={mode} actionLabel={workCardAction(finding, { mode })} selected={finding.findingId === selectedId} onOpen={openFinding} />)}</div>
              : <div className={`work-queue-state${mode === "team" ? " work-queue-state--operational" : ""}`}>
                {mode === "team" ? <div className="work-queue-state__summary" aria-label={`${selectedFilterLabel}: 0 matching findings`}><span>{selectedFilterLabel}</span><strong>0 matching</strong></div> : null}
                <h2>{empty.title}</h2><p>{empty.body}</p>
                {activeControlCount ? <button type="button" onClick={clearControls}>Clear filters</button>
                  : mode === "team" && filter !== "active" ? <button type="button" onClick={() => changeFilter("active")}>Review active findings</button> : null}
              </div>}
        {!queue.loading && !queue.error && queue.items.length ? <nav className="work-pagination" aria-label="Work pages"><button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button><span>Page {Math.floor(offset / PAGE_SIZE) + 1}</span><button type="button" disabled={!queue.hasMore} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button></nav> : null}
      </section>

      {detailState.loading ? <section className="work-detail-state" aria-live="polite"><span className="work-eyebrow">Facility workspace</span><h2>Loading finding…</h2><p>Checking this work item against your current workspace access.</p></section> : null}
      {!detailState.loading && detailState.error ? <section className="work-detail-state" role="alert"><span className="work-eyebrow">Authorized access required</span><h2>Finding unavailable</h2><p>{detailState.error}</p><button type="button" onClick={closeFinding}>Back to work list</button></section> : null}
      {selectedItem ? <OperationalFindingBrief finding={selectedItem} currentUser={currentUser} members={members} membersLoading={membersState.loading} membersError={membersState.error} activity={activity.items} activityLoading={activity.loading} activityError={activity.error} pending={mutation.pending} mutationMessage={mutation.message} mutationError={mutation.error} onBack={closeFinding} onWorkflow={mutateWorkflow} onFieldReport={submitFieldReport} onResolve={resolve} technicalFinding={technicalFinding} onInvestigation={onOpenInvestigation} onEvidence={onOpenEvidence} /> : null}
    </div>
  );
}
