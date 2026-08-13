import React, { useEffect, useMemo, useState } from "react";
import { fetchRelatedEvidencePackages } from "../../services/api/evidenceCorrelationApi";
import { buildCorrelationPresentation } from "../../viewModels/evidenceCorrelation";

export default function RelatedEvidencePackages({ packageId, apiFetch }) {
  const normalizedPackageId = String(packageId ?? "").trim();
  const [state, setState] = useState({ payload: null, loading: Boolean(normalizedPackageId), error: "" });

  useEffect(() => {
    if (!normalizedPackageId || typeof apiFetch !== "function") {
      setState({ payload: null, loading: false, error: "" });
      return undefined;
    }
    const controller = new AbortController();
    setState({ payload: null, loading: true, error: "" });
    fetchRelatedEvidencePackages({ apiFetch, packageId: normalizedPackageId, signal: controller.signal })
      .then((payload) => setState({ payload, loading: false, error: "" }))
      .catch((error) => {
        if (error?.name !== "AbortError") setState({ payload: null, loading: false, error: error?.message || "Related findings could not be loaded." });
      });
    return () => controller.abort();
  }, [apiFetch, normalizedPackageId]);

  const presentation = useMemo(() => buildCorrelationPresentation(state.payload, {
    loading: state.loading,
    error: state.error,
    packageId: normalizedPackageId,
  }), [normalizedPackageId, state.error, state.loading, state.payload]);

  return (
    <section className={`related-evidence related-evidence--${presentation.tone}`} aria-labelledby="related-evidence-title" data-testid="related-evidence">
      <header className="related-evidence__header">
        <div><span className="forensic-kicker">Related evidence</span><h2 id="related-evidence-title">{presentation.title}</h2></div>
      </header>
      <p>{presentation.body}</p>
      {presentation.items.length ? (
        <div className="related-evidence__list" aria-label="Related evidence packages">
          {presentation.items.map((item) => (
            <article key={item.relationship_id} className="related-evidence__item">
              <h3>Related evidence package</h3>
              <p>{item.reason}</p>
              <ul className="related-evidence__dimensions" aria-label="Supported relationship dimensions">
                {item.relationshipLabels.map((label) => <li key={label}>{label}</li>)}
              </ul>
              <details><summary>Technical references</summary><ul className="related-evidence__refs"><li><code>{item.package_id}</code></li>{(item.evidence_refs ?? []).map((reference) => <li key={reference}><code>{reference}</code></li>)}</ul></details>
              {item.limitationLabels.length ? <ul className="related-evidence__limitations" aria-label="Relationship limitations">{item.limitationLabels.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul> : null}
            </article>
          ))}
        </div>
      ) : null}
      {presentation.limitations.length ? <ul className="related-evidence__limitations" aria-label="Correlation limitations">{presentation.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul> : null}
      <p className="related-evidence__non-claim">{presentation.nonClaim}</p>
      {normalizedPackageId ? <details className="related-evidence__trace"><summary>Correlation trace</summary><p>Selected evidence package <code>{normalizedPackageId}</code></p></details> : null}
    </section>
  );
}
