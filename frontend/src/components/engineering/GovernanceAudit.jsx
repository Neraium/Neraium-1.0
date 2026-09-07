import React from "react";

export default function GovernanceAudit({ governance }) {
  return <>
    <p>Recorded {governance.evaluated_at || "time unavailable"} · Source run {governance.source_run_id || "unavailable"}</p>
    <h3>Maturity reasons</h3><ul>{(governance.maturity?.reasons || []).map(reason => <li key={reason}>{reason.replaceAll("_", " ")}</li>)}</ul>
    <h3>Limitations</h3><ul>{(governance.limitations || []).map(reason => <li key={reason}>{reason}</li>)}</ul>
    <h3>Evidence families</h3><ul>{[...new Set((governance.graph?.evidence || []).map(item => item.evidence_family))].map(family => <li key={family}>{family.replaceAll("_", " ")}</li>)}</ul>
    <h3>Policy and decision</h3><p>{governance.authority_decision ? `${governance.authority_decision.policy_id} · version ${governance.authority_decision.policy_version} · ${governance.authority_decision.decision_outcome}` : "Authority decision unavailable"}</p>
    <details><summary>Frozen evidence, context, consequence, and replay record</summary><pre className="evidence-record-json" tabIndex={0}>{JSON.stringify(governance, null, 2)}</pre></details>
  </>;
}
