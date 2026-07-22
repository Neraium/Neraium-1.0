import React, { useState } from "react";

const OUTCOMES = [
  "Root cause confirmed", "Operating condition explained", "Instrumentation issue", "Maintenance performed",
  "No issue found", "Escalated", "Deferred", "Other",
];
const CATEGORY_BY_OUTCOME = {
  "Root cause confirmed": "confirmed_issue",
  "Operating condition explained": "known_operational_change",
  "Instrumentation issue": "sensor_or_data_problem",
  "Maintenance performed": "maintenance_event",
  "No issue found": "nothing_meaningful",
  Escalated: "useful_warning",
  Deferred: "ignore",
  Other: "useful_warning",
};

export default function InvestigationOutcome({ runId, apiFetch, currentUser, onSaved }) {
  const [expanded, setExpanded] = useState(false);
  const [form, setForm] = useState({ outcome: OUTCOMES[0], note: "", workOrder: "", followup: "" });
  const [state, setState] = useState({ status: "idle", message: "" });
  async function submit(event) {
    event.preventDefault();
    if (!runId) return;
    setState({ status: "saving", message: "Recording outcome…" });
    try {
      const response = await apiFetch(`/api/evidence/runs/${encodeURIComponent(runId)}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: CATEGORY_BY_OUTCOME[form.outcome],
          outcome: form.outcome,
          note: form.note || null,
          action_taken: form.workOrder ? `Related work-order reference: ${form.workOrder}` : null,
          followup_at: form.followup ? new Date(form.followup).toISOString() : null,
        }),
      });
      if (!response.ok) throw new Error("Outcome could not be persisted.");
      const payload = await response.json();
      setState({ status: "complete", message: `Outcome recorded and verified by ${currentUser?.name || currentUser?.email || "signed-in engineer"}.` });
      onSaved?.(payload);
    } catch (error) {
      setState({ status: "error", message: error?.message || "Outcome could not be recorded." });
    }
  }
  if (!expanded) return <section className="investigation-outcome investigation-outcome--collapsed"><div><span className="forensic-kicker">Operational memory</span><h2>What was the outcome?</h2><p>Verified outcomes remain governed human evidence; they do not become universal engineering rules.</p></div><button type="button" className="forensic-button forensic-button--secondary" onClick={() => setExpanded(true)}>Record outcome</button></section>;
  return (
    <section className="investigation-outcome"><header><div><span className="forensic-kicker">Operational memory</span><h2>Record investigation outcome</h2></div><button type="button" className="forensic-icon-button" aria-label="Close outcome form" onClick={() => setExpanded(false)}>×</button></header>
      <form onSubmit={submit}>
        <label>Outcome<select value={form.outcome} onChange={(event) => setForm((current) => ({ ...current, outcome: event.target.value }))}>{OUTCOMES.map((outcome) => <option key={outcome}>{outcome}</option>)}</select></label>
        <label>Engineer notes<textarea rows="4" value={form.note} onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))} placeholder="Record observed result and verification context." /></label>
        <div className="investigation-outcome__row"><label>Related work-order reference<input value={form.workOrder} onChange={(event) => setForm((current) => ({ ...current, workOrder: event.target.value }))} /></label><label>Follow-up date<input type="datetime-local" value={form.followup} onChange={(event) => setForm((current) => ({ ...current, followup: event.target.value }))} /></label></div>
        <dl><div><dt>Verified by</dt><dd>{currentUser?.name || currentUser?.email || "Signed-in engineer"}</dd></div><div><dt>Verification time</dt><dd>Recorded by the evidence service at submission</dd></div></dl>
        <button type="submit" className="forensic-button" disabled={!runId || state.status === "saving"}>Record verified outcome</button>
        <span role="status" aria-live="polite">{state.message || (!runId ? "A persisted evidence identity is required before an outcome can be recorded." : "")}</span>
      </form>
    </section>
  );
}
