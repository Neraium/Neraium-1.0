import React, { useEffect, useMemo, useState } from "react";
import { fetchFinding, fetchFindingActivity, fetchFindingMembers, fetchFindings, patchFindingWorkflow, postFindingFieldReport, resolveFinding } from "../../services/api/findingsApi";
import { canLeadWorkflow, emptyStateForQueue, normalizeWorkFinding, queryForWorkQueue, WORK_FILTERS } from "../../viewModels/workQueue";
import OperationalFindingBrief from "./OperationalFindingBrief";
import WorkFindingCard from "./WorkFindingCard";
import "../../styles/work-workflow.css";

const PAGE_SIZE = 30;

function clean(value) {
  return String(value ?? "").trim();
}

export default function WorkQueueWorkspace({ apiFetch, currentUser, findingId = "", onRouteFinding, onOpenInvestigation, onOpenEvidence, technicalFindingFor }) {
  const [mode, setMode] = useState("mine");
  const [filter, setFilter] = useState("active");
  const [controls, setControls] = useState({ assignee: "", priority: "", status: "", system: "" });
  const [offset, setOffset] = useState(0);
  const [queue, setQueue] = useState({ items: [], loading: true, error: "", hasMore: false });
  const [selectedId, setSelectedId] = useState(clean(findingId));
  const [selectedItem, setSelectedItem] = useState(null);
  const [members, setMembers] = useState([]);
  const [activity, setActivity] = useState({ items: [], loading: false, error: "" });
  const [mutation, setMutation] = useState({ pending: false, message: "", error: false });
  const [reloadKey, setReloadKey] = useState(0);
  const lead = canLeadWorkflow(currentUser?.role);

  useEffect(() => {
    setSelectedId(clean(findingId));
  }, [findingId]);

  useEffect(() => {
    let cancelled = false;
    if (!lead) {
      setMembers([]);
      return undefined;
    }
    fetchFindingMembers({ apiFetch }).then((items) => { if (!cancelled) setMembers(items); }).catch(() => { if (!cancelled) setMembers([]); });
    return () => { cancelled = true; };
  }, [apiFetch, lead]);

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
      return undefined;
    }
    const queued = queue.items.find((item) => item.findingId === selectedId);
    if (queued) {
      setSelectedItem(queued);
      return undefined;
    }
    fetchFinding({ apiFetch, findingId: selectedId })
      .then((result) => { if (!cancelled) setSelectedItem(normalizeWorkFinding({ finding: result.payload, workflow: result.workflow })); })
      .catch((error) => { if (!cancelled) setMutation({ pending: false, message: error?.message || "This work item could not be loaded.", error: true }); });
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

  const empty = emptyStateForQueue({ mode, filter });
  const technicalFinding = useMemo(() => selectedItem ? technicalFindingFor?.(selectedItem) ?? null : null, [selectedItem, technicalFindingFor]);

  function changeMode(nextMode) {
    setMode(nextMode);
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
    onRouteFinding?.(finding.findingId);
  }

  function closeFinding() {
    setSelectedId("");
    setSelectedItem(null);
    onRouteFinding?.("");
  }

  function applyResult(result, message) {
    setSelectedItem(normalizeWorkFinding({ finding: result.payload, workflow: result.workflow }));
    setMutation({ pending: false, message, error: false });
    setReloadKey((value) => value + 1);
  }

  async function mutateWorkflow(changes) {
    if (!selectedItem) return;
    setMutation({ pending: true, message: "", error: false });
    try {
      const result = await patchFindingWorkflow({ apiFetch, findingId: selectedItem.findingId, expectedVersion: selectedItem.version, changes });
      applyResult(result, "Work updated.");
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
    <div className={`work-workspace${selectedItem ? " has-selection" : ""}`} data-testid="work-queue-workspace">
      <section className="work-queue" aria-labelledby="work-queue-title">
        <header className="work-queue__header"><div><span className="work-eyebrow">Maintenance workflow</span><h1 id="work-queue-title">Work</h1><p>Turn persistent changes into clearly owned human action.</p></div></header>
        <div className="work-mode-switch" role="group" aria-label="Work view"><button type="button" aria-pressed={mode === "mine"} onClick={() => changeMode("mine")}>My Work</button><button type="button" aria-pressed={mode === "team"} onClick={() => changeMode("team")}>Team Findings</button></div>
        <div className="work-filter-list" aria-label="Work filters">{WORK_FILTERS.map((item) => <button type="button" key={item.id} aria-pressed={filter === item.id} onClick={() => changeFilter(item.id)}>{item.label}</button>)}</div>
        {mode === "team" ? <div className="work-queue-controls" aria-label="Queue controls"><label>Assignee<select value={controls.assignee} onChange={(event) => updateControl("assignee", event.target.value)}><option value="">Anyone</option>{members.map((member) => <option key={member.memberId} value={member.memberId}>{member.displayName}</option>)}</select></label><label>Priority<select value={controls.priority} onChange={(event) => updateControl("priority", event.target.value)}><option value="">Any priority</option>{["low", "medium", "high", "critical"].map((item) => <option key={item} value={item}>{item}</option>)}</select></label><label>Status<select value={controls.status} onChange={(event) => updateControl("status", event.target.value)}><option value="">Any status</option>{["open", "acknowledged", "investigating", "waiting", "escalated", "awaiting_review", "monitoring", "resolved", "dismissed"].map((item) => <option key={item} value={item}>{item.replace(/_/g, " ")}</option>)}</select></label><label>System<input value={controls.system} onChange={(event) => updateControl("system", event.target.value)} placeholder="System name" /></label></div> : null}

        {queue.loading ? <p className="work-queue-state" role="status">Loading work…</p>
          : queue.error ? <div className="work-queue-state" role="alert"><h2>Work is unavailable</h2><p>{queue.error}</p><button type="button" onClick={() => setReloadKey((value) => value + 1)}>Try again</button></div>
            : queue.items.length ? <div className="work-card-list">{queue.items.map((finding) => <WorkFindingCard key={finding.findingId} finding={finding} selected={finding.findingId === selectedId} onOpen={openFinding} />)}</div>
              : <div className="work-queue-state"><h2>{empty.title}</h2><p>{empty.body}</p></div>}
        {!queue.loading && !queue.error && queue.items.length ? <nav className="work-pagination" aria-label="Work pages"><button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button><span>Page {Math.floor(offset / PAGE_SIZE) + 1}</span><button type="button" disabled={!queue.hasMore} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button></nav> : null}
      </section>

      {selectedItem ? <OperationalFindingBrief finding={selectedItem} currentUser={currentUser} members={members} activity={activity.items} activityLoading={activity.loading} activityError={activity.error} pending={mutation.pending} mutationMessage={mutation.message} mutationError={mutation.error} onBack={closeFinding} onWorkflow={mutateWorkflow} onFieldReport={submitFieldReport} onResolve={resolve} technicalFinding={technicalFinding} onInvestigation={onOpenInvestigation} onEvidence={onOpenEvidence} /> : null}
    </div>
  );
}
