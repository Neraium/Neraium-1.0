import React, { useState } from "react";

const INITIAL_REPORT = { inspected: "", found: "", actionTaken: "", note: "", problemFound: "uncertain", needsEscalation: false, investigationComplete: false };

export default function FieldReportForm({ disabled = false, onSubmit }) {
  const [report, setReport] = useState(INITIAL_REPORT);
  const [state, setState] = useState({ pending: false, message: "", error: false });

  async function submit(event) {
    event.preventDefault();
    setState({ pending: true, message: "", error: false });
    try {
      await onSubmit?.(report);
      setReport(INITIAL_REPORT);
      setState({ pending: false, message: report.investigationComplete ? "Investigation sent for review." : "Field update saved.", error: false });
    } catch (error) {
      setState({ pending: false, message: error?.message || "Field update could not be saved.", error: true });
    }
  }

  return (
    <section className="field-report" aria-labelledby="field-report-title">
      <header><span className="work-eyebrow">Field update</span><h2 id="field-report-title">Report what you found</h2><p>Keep it short. Record enough for the lead to review the investigation.</p></header>
      <form onSubmit={submit}>
        <label>What did you inspect?<textarea required value={report.inspected} onChange={(event) => setReport((current) => ({ ...current, inspected: event.target.value }))} /></label>
        <label>What did you find?<textarea required value={report.found} onChange={(event) => setReport((current) => ({ ...current, found: event.target.value }))} /></label>
        <label>Action taken, if any<input value={report.actionTaken} onChange={(event) => setReport((current) => ({ ...current, actionTaken: event.target.value }))} /></label>
        <fieldset><legend>Was a physical problem found?</legend><div className="work-choice-row">{[["yes", "Yes"], ["no", "No obvious problem"], ["uncertain", "Uncertain"]].map(([value, label]) => <label key={value}><input type="radio" name="problem-found" value={value} checked={report.problemFound === value} onChange={(event) => setReport((current) => ({ ...current, problemFound: event.target.value }))} />{label}</label>)}</div></fieldset>
        <label>Additional note<textarea value={report.note} onChange={(event) => setReport((current) => ({ ...current, note: event.target.value }))} /></label>
        <div className="work-check-row">
          <label><input type="checkbox" checked={report.needsEscalation} onChange={(event) => setReport((current) => ({ ...current, needsEscalation: event.target.checked }))} />I need help or engineering escalation</label>
          <label><input type="checkbox" checked={report.investigationComplete} onChange={(event) => setReport((current) => ({ ...current, investigationComplete: event.target.checked }))} />My investigation is complete</label>
        </div>
        <button type="submit" className="work-primary-action" disabled={disabled || state.pending}>{state.pending ? "Saving…" : report.investigationComplete ? "Send for review" : "Save field update"}</button>
        <p className={`work-form-status${state.error ? " is-error" : ""}`} role="status" aria-live="polite">{state.message}</p>
      </form>
    </section>
  );
}
