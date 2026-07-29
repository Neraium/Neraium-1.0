import { Panel } from "./workspacePrimitives";
import "../styles/baseline-detail.css";

export default function BaselineDetailView({ routeIdentity, detailState, onRetry }) {
  const baselineId = String(routeIdentity?.baselineId ?? "").trim();
  const portfolioId = String(routeIdentity?.portfolioId ?? "").trim();
  const ready = detailState.status === "ready" && detailState.result?.candidate_model;
  const candidate = detailState.result?.candidate_model ?? {};
  const source = candidate?.source ?? detailState.result?.source ?? {};
  const signalCount = candidate?.signal_memory?.signal_count
    ?? candidate?.telemetry_schema?.numeric_columns?.length
    ?? candidate?.telemetry_schema?.signal_catalog?.length
    ?? null;
  const relationshipCount = candidate?.relationship_memory?.relationship_count
    ?? candidate?.relationship_graph?.edges?.length
    ?? null;
  const summary = ready ? [
    { label: "Dataset", value: detailState.result?.filename ?? source?.filename ?? "Not reported" },
    { label: "Model version", value: candidate?.version ?? "Not reported" },
    { label: "Signals analyzed", value: signalCount ?? "Not reported" },
    { label: "Relationships learned", value: relationshipCount ?? "Not reported" },
  ] : [];
  const activationState = String(
    detailState.result?.activation?.state ?? candidate?.activation?.state ?? candidate?.status ?? "stored",
  ).replaceAll("_", " ");
  const notFound = detailState.status === "error" && detailState.notFound === true;

  return (
    <div className="data-connections-workspace baseline-detail-route" data-testid="baseline-detail-route">
      <Panel title="Baseline Details" subtitle="Loaded independently from the baseline ID in this URL." className="span-7 baseline-detail-panel">
        {detailState.status === "error" ? (
          <section className="baseline-detail-error" role="alert" aria-live="assertive">
            <p className="baseline-detail-error__eyebrow">Baseline unavailable</p>
            <h3>{notFound ? "Baseline Not Found" : "Baseline Could Not Be Opened"}</h3>
            <p>{detailState.message}</p>
            <button type="button" className="command-button" onClick={onRetry}>Retry Baseline</button>
          </section>
        ) : null}
        {!ready && detailState.status !== "error" ? (
          <section className="baseline-detail-loading" role="status" aria-live="polite" aria-busy="true">
            <span className="baseline-detail-loading__spinner" aria-hidden="true" />
            <div>
              <h3>Opening Baseline</h3>
              <p>Loading {baselineId} from portfolio {portfolioId}.</p>
            </div>
          </section>
        ) : null}
        {ready ? (
          <article className="baseline-detail" aria-labelledby="baseline-detail-heading">
            <header className="baseline-detail__header">
              <div>
                <p className="baseline-detail__eyebrow">Selected behavioral baseline</p>
                <h3 id="baseline-detail-heading">{baselineId}</h3>
              </div>
              <span className="baseline-detail__status">{activationState}</span>
            </header>
            <dl className="baseline-detail__identity" aria-label="Baseline identity">
              <div><dt>Baseline ID</dt><dd>{baselineId}</dd></div>
              <div><dt>Portfolio ID</dt><dd>{portfolioId}</dd></div>
              <div><dt>State source</dt><dd>{String(detailState.identity?.stateSource ?? "hydration").replaceAll("_", " ")}</dd></div>
            </dl>
            <dl className="baseline-success__summary" aria-label="Baseline summary">
              {summary.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}
            </dl>
          </article>
        ) : null}
      </Panel>
    </div>
  );
}
