import React, { useState } from "react";

function filenameFromHeader(response, fallback) {
  const disposition = response.headers?.get?.("content-disposition") ?? "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] ?? fallback;
}

export default function EvidencePackageExport({ runId, apiFetch, disabled = false }) {
  const [state, setState] = useState({ status: "idle", message: "" });
  async function exportPackage(format) {
    if (!runId || disabled || state.status === "loading") return;
    setState({ status: "loading", message: `Preparing ${format.toUpperCase()} evidence package…` });
    try {
      const response = await apiFetch(`/api/evidence/package/${encodeURIComponent(runId)}?format=${format}`);
      if (!response.ok) throw new Error("Evidence package could not be prepared.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filenameFromHeader(response, `neraium-evidence-${runId}.${format}`);
      anchor.click();
      URL.revokeObjectURL(url);
      setState({ status: "complete", message: `${format.toUpperCase()} evidence package exported.` });
    } catch (error) {
      setState({ status: "error", message: error?.message || "Evidence package export failed." });
    }
  }
  return (
    <div className="evidence-package-export">
      <span className="forensic-kicker">Export evidence package</span>
      <div role="group" aria-label="Evidence package formats"><button type="button" className="forensic-button forensic-button--secondary" onClick={() => exportPackage("pdf")} disabled={disabled || state.status === "loading"}>PDF</button><button type="button" className="forensic-button forensic-button--secondary" onClick={() => exportPackage("json")} disabled={disabled || state.status === "loading"}>JSON</button></div>
      <span role="status" aria-live="polite">{state.message || (disabled ? "A persisted evidence identity is required before export." : "Governance policy is applied before export.")}</span>
    </div>
  );
}
