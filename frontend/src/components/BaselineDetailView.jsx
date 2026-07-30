import { Panel } from "./workspacePrimitives";
import "../styles/baseline-detail.css";

function display(value, fallback = "Not reported") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value).replaceAll("_", " ");
}

function formatTimestamp(value) {
  if (!value) return "Not reported";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return display(value);
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function percentage(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not reported";
  return `${Math.round(Math.abs(number) <= 1 ? number * 100 : number)}%`;
}

export default function BaselineDetailView({ routeIdentity, detailState, onRetry, onImportComparison }) {
  const baselineId = String(routeIdentity?.baselineId ?? "").trim();
  const portfolioId = String(routeIdentity?.portfolioId ?? "").trim();
  const ready = detailState.status === "ready" && detailState.result?.candidate_model;
  const candidate = detailState.result?.candidate_model ?? {};
  const source = candidate?.source ?? detailState.result?.source ?? {};
  const schema = candidate?.telemetry_schema ?? {};
  const signals = Array.isArray(schema?.numeric_columns)
    ? schema.numeric_columns
    : Array.isArray(schema?.signal_catalog)
      ? schema.signal_catalog
      : [];
  const relationships = Array.isArray(candidate?.relationship_graph?.edges) ? candidate.relationship_graph.edges : [];
  const operatingModes = Array.isArray(candidate?.operating_modes) ? candidate.operating_modes : [];
  const expectedModels = Array.isArray(candidate?.expected_behavior_models) ? candidate.expected_behavior_models : [];
  const quality = candidate?.data_quality ?? {};
  const timestamp = candidate?.timestamp_quality ?? {};
  const analysisState = detailState.result?.analysis_state ?? { status: "empty", count: 0, analyses: [] };
  const hasLinkedAnalysis = analysisState.status !== "empty" && Number(analysisState.count) > 0;
  const activationState = String(
    detailState.result?.activation?.state ?? candidate?.activation?.state ?? candidate?.status ?? "stored",
  ).replaceAll("_", " ");
  const notFound = detailState.status === "error" && detailState.notFound === true;
  const summary = ready ? [
    { label: "Dataset", value: detailState.result?.filename ?? source?.filename ?? "Not reported" },
    { label: "Rows learned", value: source?.row_count ?? quality?.row_count ?? "Not reported" },
    { label: "Signals analyzed", value: signals.length || "Not reported" },
    { label: "Relationships learned", value: relationships.length || "Not reported" },
    { label: "Operating modes", value: operatingModes.length || "Not available" },
    { label: "Expected-behavior models", value: expectedModels.length || "Not available" },
  ] : [];

  return (
    <div className="data-connections-workspace baseline-detail-route" data-testid="baseline-detail-route">
      <Panel title="Baseline Details" subtitle="Loaded from the portfolio and baseline identifiers in this URL." className="span-7 baseline-detail-panel">
        {detailState.status === "error" ? (
          <section className="baseline-detail-error" role="alert" aria-live="assertive">
            <p className="baseline-detail-error__eyebrow">Baseline unavailable</p>
            <h3>{notFound ? "Baseline Not Found" : "Baseline Could Not Be Opened"}</h3>
            <p>{detailState.message}</p>
            <dl className="baseline-detail-error__diagnostics" aria-label="Request diagnostics">
              <div><dt>Error type</dt><dd>{display(detailState.errorType, "baseline request failed")}</dd></div>
              <div><dt>HTTP status</dt><dd>{detailState.httpStatus ?? "No response"}</dd></div>
              <div><dt>Request ID</dt><dd>{detailState.requestId ?? "Not returned"}</dd></div>
            </dl>
            <button type="button" className="command-button" onClick={onRetry}>Retry Baseline</button>
          </section>
        ) : null}
        {!ready && detailState.status !== "error" ? (
          <section className="baseline-detail-loading" role="status" aria-live="polite" aria-busy="true">
            <span className="baseline-detail-loading__spinner" aria-hidden="true" />
            <div>
              <h3>Opening Baseline</h3>
              <p>Loading {baselineId} from portfolio {portfolioId}. This request stops after 15 seconds if the service does not respond.</p>
            </div>
          </section>
        ) : null}
        {ready ? (
          <article className="baseline-detail" aria-labelledby="baseline-detail-heading">
            <header className="baseline-detail__header">
              <div>
                <p className="baseline-detail__eyebrow">Baseline established</p>
                <h3 id="baseline-detail-heading">Baseline established</h3>
                <p className="baseline-detail__lede">
                  {hasLinkedAnalysis
                    ? "Neraium has learned the system’s initial operating model. Comparison results remain separate from this baseline record."
                    : "Neraium has learned the system’s initial operating model. No comparison dataset or live telemetry has been evaluated yet."}
                </p>
              </div>
              <span className="baseline-detail__status">{activationState}</span>
            </header>

            <section className="baseline-detail__comparison" aria-labelledby="comparison-state-heading">
              <div>
                <p className="baseline-detail__eyebrow">Comparison state</p>
                <h4 id="comparison-state-heading">{!hasLinkedAnalysis ? "No comparison analysis" : `${analysisState.count} linked comparison ${analysisState.count === 1 ? "analysis" : "analyses"}`}</h4>
                <p>{!hasLinkedAnalysis
                  ? "Operational comparison content remains empty until a comparison dataset or live telemetry is evaluated against this baseline."
                  : "This baseline page shows only the learned model. Open a linked analysis route to review comparison results."}</p>
              </div>
              <button type="button" className="command-button" onClick={onImportComparison}>Import Comparison Dataset</button>
            </section>

            <dl className="baseline-detail__identity" aria-label="Baseline identity">
              <div><dt>Baseline ID</dt><dd>{baselineId}</dd></div>
              <div><dt>Portfolio ID</dt><dd>{portfolioId}</dd></div>
              <div><dt>System ID</dt><dd>{display(detailState.result?.system_id ?? source?.system_id)}</dd></div>
              <div><dt>Model version</dt><dd>{display(candidate?.version)}</dd></div>
            </dl>

            <dl className="baseline-success__summary" aria-label="Baseline summary">
              {summary.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}
            </dl>

            <div className="baseline-detail__grid">
              <section className="baseline-detail__section" aria-labelledby="baseline-window-heading">
                <p className="baseline-detail__eyebrow">Learned operating model</p>
                <h4 id="baseline-window-heading">Training window</h4>
                <dl className="baseline-detail__facts">
                  <div><dt>Start</dt><dd>{formatTimestamp(timestamp?.first_timestamp)}</dd></div>
                  <div><dt>End</dt><dd>{formatTimestamp(timestamp?.last_timestamp)}</dd></div>
                  <div><dt>Sample interval</dt><dd>{display(timestamp?.estimated_sample_interval)}</dd></div>
                  <div><dt>Readiness</dt><dd>{display(quality?.readiness)}</dd></div>
                </dl>
              </section>

              <section className="baseline-detail__section" aria-labelledby="baseline-quality-heading">
                <p className="baseline-detail__eyebrow">Data quality</p>
                <h4 id="baseline-quality-heading">Learning confidence</h4>
                <dl className="baseline-detail__facts">
                  <div><dt>Reliability</dt><dd>{display(quality?.reliability_rating)}</dd></div>
                  <div><dt>Reliability score</dt><dd>{percentage(quality?.reliability_score)}</dd></div>
                  <div><dt>Imputed cells</dt><dd>{quality?.imputation_report?.imputed_cells ?? 0}</dd></div>
                  <div><dt>Timestamp detected</dt><dd>{quality?.timestamp_detected === true ? "Yes" : "No"}</dd></div>
                </dl>
                {Array.isArray(quality?.warnings) && quality.warnings.length ? (
                  <ul className="baseline-detail__notes">{quality.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
                ) : <p className="baseline-detail__muted">No data-quality warnings were reported.</p>}
              </section>
            </div>

            <section className="baseline-detail__section" aria-labelledby="signal-inventory-heading">
              <p className="baseline-detail__eyebrow">Signal inventory</p>
              <h4 id="signal-inventory-heading">{signals.length} learned signals</h4>
              <div className="baseline-detail__chips">{signals.map((signal) => <span key={signal}>{signal}</span>)}</div>
            </section>

            <section className="baseline-detail__section" aria-labelledby="relationships-heading">
              <p className="baseline-detail__eyebrow">Relationships learned</p>
              <h4 id="relationships-heading">Strongest baseline relationships</h4>
              {relationships.length ? (
                <ul className="baseline-detail__relationship-list">
                  {relationships.slice(0, 8).map((relationship) => (
                    <li key={relationship.edge_id ?? `${relationship.source}-${relationship.target}`}>
                      <span>{display(relationship.source)} ↔ {display(relationship.target)}</span>
                      <small>{display(relationship.mode_id)} · strength {Number(relationship.strength ?? 0).toFixed(2)} · {relationship.sample_count ?? "Not reported"} samples</small>
                    </li>
                  ))}
                </ul>
              ) : <p className="baseline-detail__muted">No stable relationships were available to report.</p>}
            </section>

            {operatingModes.length ? (
              <section className="baseline-detail__section" aria-labelledby="operating-modes-heading">
                <p className="baseline-detail__eyebrow">Operating modes</p>
                <h4 id="operating-modes-heading">Learned operating contexts</h4>
                <ul className="baseline-detail__mode-list">
                  {operatingModes.slice(0, 8).map((mode) => (
                    <li key={mode.mode_id}><strong>{display(mode.label ?? mode.mode_id)}</strong><span>{mode.sample_count ?? 0} samples · {percentage(mode.sample_fraction)}</span></li>
                  ))}
                </ul>
              </section>
            ) : null}
          </article>
        ) : null}
      </Panel>
    </div>
  );
}
