import React, { useMemo, useState } from "react";

export default function CmmsExportReview({ finding, site }) {
  const [open, setOpen] = useState(false);
  const payload = useMemo(() => ({
    status: "draft_for_human_review",
    site: site?.name,
    finding_reference: finding?.id,
    summary: finding?.title,
    observed_change: finding?.observedChange,
    inspection_target: finding?.recommendationAllowed ? finding?.firstPlaceToLook : null,
    confidence_tier: finding?.tier,
    limitations: finding?.limitations,
    dispatch_authorized: false,
  }), [finding, site]);
  function download() {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `neraium-cmms-review-${finding?.id || "finding"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return <div className="cmms-review"><button type="button" className="forensic-button forensic-button--secondary" onClick={() => setOpen((value) => !value)}>Review CMMS payload</button>{open ? <section><span className="forensic-kicker">Human review required</span><h3>Draft work-order payload</h3><p>This payload is not dispatched and cannot execute a work order.</p><dl>{Object.entries(payload).map(([key, value]) => <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd>{Array.isArray(value) ? value.join("; ") || "None" : value === null ? "Withheld" : String(value)}</dd></div>)}</dl><button type="button" className="forensic-button" onClick={download}>Download reviewed payload</button></section> : null}</div>;
}
