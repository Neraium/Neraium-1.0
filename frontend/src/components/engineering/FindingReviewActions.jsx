import React, { useState } from "react";
import { KNOWN_CONDITIONS, reviewStateLabel } from "../../viewModels/findingReviewState";

export default function FindingReviewActions({ finding, reviewRecord, onAction, compact = false }) {
  const [explanationOpen, setExplanationOpen] = useState(false);
  const [reason, setReason] = useState(KNOWN_CONDITIONS[0].value);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState({ state: "idle", message: "" });
  const currentState = reviewRecord?.state ?? "new";

  async function apply(action) {
    setStatus({ state: "saving", message: "Saving review state." });
    try {
      const result = await onAction?.(finding, action);
      const suffix = result?.persisted === false && action.state !== "investigating"
        ? " Saved for this workspace; the evidence record was unavailable."
        : "";
      setStatus({ state: "complete", message: `${reviewStateLabel(action.state)}.${suffix}` });
      if (action.state === "explained") setExplanationOpen(false);
    } catch (error) {
      setStatus({ state: "error", message: error?.message || "The review state could not be saved." });
    }
  }

  function saveExplanation(event) {
    event.preventDefault();
    apply({ state: "explained", reason, note: reason === "other" ? note : "" });
  }

  return (
    <div className={`finding-review-actions${compact ? " finding-review-actions--compact" : ""}`}>
      <div className="finding-review-actions__buttons" aria-label={`Quick review actions for ${finding?.title ?? "finding"}`}>
        <button type="button" className="forensic-button forensic-button--secondary" aria-pressed={currentState === "investigating"} disabled={status.state === "saving"} onClick={() => apply({ state: "investigating" })}>I’m checking this</button>
        <button type="button" className="forensic-button forensic-button--secondary" aria-expanded={explanationOpen} aria-pressed={currentState === "explained"} disabled={status.state === "saving"} onClick={() => setExplanationOpen((value) => !value)}>Known or explained</button>
        <button type="button" className="forensic-button forensic-button--secondary" aria-pressed={currentState === "not_useful"} disabled={status.state === "saving"} onClick={() => apply({ state: "not_useful" })}>Not useful</button>
      </div>
      {explanationOpen ? (
        <form className="finding-review-actions__explanation" onSubmit={saveExplanation}>
          <label>Known condition
            <select value={reason} onChange={(event) => setReason(event.target.value)}>
              {KNOWN_CONDITIONS.map((condition) => <option key={condition.value} value={condition.value}>{condition.label}</option>)}
            </select>
          </label>
          {reason === "other" ? <label>Short reason<input value={note} maxLength={240} onChange={(event) => setNote(event.target.value)} placeholder="Describe the known condition" required /></label> : null}
          <div><button type="submit" className="forensic-button" disabled={status.state === "saving"}>Save explanation</button><button type="button" className="forensic-link-button" onClick={() => setExplanationOpen(false)}>Cancel</button></div>
        </form>
      ) : null}
      <span className="finding-review-actions__status" role="status" aria-live="polite">{status.message}</span>
    </div>
  );
}
