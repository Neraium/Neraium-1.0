import { useEffect, useMemo, useRef, useState } from "react";
import {
  createTelemetryConnection,
  discoverTelemetrySignals,
  getFacilityContext,
  listCanonicalSignalConcepts,
  listTelemetryConnections,
  listTelemetryProviders,
  listTelemetryErrors,
  listTelemetryRuns,
  listTelemetrySignals,
  mapTelemetrySignal,
  putTelemetryCredentials,
  putFacilityContext,
  retryTelemetryRun,
  setTelemetryConnectionEnabled,
  startTelemetryBackfill,
  validateTelemetryConnection,
} from "../services/api/telemetryConnectionsApi";

const EMPTY_CONNECTION = Object.freeze({
  name: "",
  connectorType: "https_telemetry",
  baseUrl: "",
  requestPath: "/telemetry",
  authenticationScheme: "bearer",
  recordsPath: "records",
  timestampField: "timestamp",
  valueField: "value",
  externalTagIdField: "tag_id",
  externalTagNameField: "tag_name",
  unitField: "unit",
  qualityField: "quality",
  timezone: "UTC",
  pollingIntervalSeconds: "300",
  templateId: "",
  networkProfileId: "",
});

const EMPTY_MAPPING = Object.freeze({
  signalId: "",
  systemId: "",
  assetId: "",
  canonicalSignalId: "",
  sourceUnit: "",
  sourceTimezone: "UTC",
  expectedCadenceSeconds: "300",
});

const HEALTH_FACETS = Object.freeze([
  ["credentials_state", "Credentials valid"],
  ["endpoint_state", "Endpoint reachable"],
  ["telemetry_state", "Telemetry arriving"],
  ["mapping_state", "Mappings complete"],
  ["freshness_state", "Data current"],
  ["quality_state", "Data quality acceptable"],
]);

function roleCapabilities(currentUser) {
  const role = String(currentUser?.role ?? "viewer").toLowerCase();
  return {
    canConfigure: role === "admin",
    canOperate: role === "admin" || role === "operator",
  };
}

function formatState(value) {
  const normalized = String(value ?? "unknown").replaceAll("_", " ").trim();
  return normalized ? normalized[0].toUpperCase() + normalized.slice(1) : "Unknown";
}

function formatTimestamp(value, timezone = "UTC") {
  const timestamp = Date.parse(String(value ?? ""));
  if (!Number.isFinite(timestamp)) return "Not yet received";
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: timezone || "UTC",
      timeZoneName: "short",
    }).format(new Date(timestamp));
  } catch {
    return new Date(timestamp).toISOString();
  }
}

function countSignals(signals, predicate) {
  return signals.reduce((count, signal) => count + (predicate(signal) ? 1 : 0), 0);
}

function connectionScopeKey(datasetScopeKey, connections) {
  const scopes = [...new Set(connections.map((connection) => String(connection?.resource_scope_id ?? "").trim()).filter(Boolean))];
  if (scopes.length > 1) throw new Error("Telemetry authority could not be established for this facility.");
  return `${String(datasetScopeKey || "anonymous")}:${scopes[0] || "empty"}`;
}

function connectionConfiguration(form) {
  if (form.connectorType === "historian_template") {
    return {
      template_id: form.templateId.trim(),
      network_profile_id: form.networkProfileId.trim(),
      parameters: {},
    };
  }
  return {
    base_url: form.baseUrl.trim(),
    request_path: form.requestPath.trim(),
    authentication_scheme: form.authenticationScheme,
    records_path: form.recordsPath.trim(),
    timestamp_field: form.timestampField.trim(),
    value_field: form.valueField.trim(),
    external_tag_id_field: form.externalTagIdField.trim(),
    external_tag_name_field: form.externalTagNameField.trim(),
    unit_field: form.unitField.trim(),
    quality_field: form.qualityField.trim(),
  };
}

function HealthFacet({ health, facet, label }) {
  const state = health?.[facet] ?? "unknown";
  const good = ["valid", "reachable", "arriving", "complete", "current", "acceptable", "healthy"].includes(String(state));
  return (
    <li className="telemetry-health-facet">
      <span className={`telemetry-health-dot telemetry-health-dot--${good ? "good" : String(state)}`} aria-hidden="true" />
      <span>{label}</span>
      <strong>{formatState(state)}</strong>
    </li>
  );
}

function ConnectionCard({ connection, selected, onSelect }) {
  const health = connection.health ?? {};
  const aggregate = health.aggregate_status ?? (connection.enabled ? "unknown" : "disabled");
  return (
    <button
      type="button"
      className={`telemetry-connection-card${selected ? " telemetry-connection-card--selected" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="telemetry-connection-card__heading">
        <strong>{connection.name}</strong>
        <span className={`telemetry-state telemetry-state--${aggregate}`}>{formatState(aggregate)}</span>
      </span>
      <span>{connection.connector_type === "https_telemetry" ? "Read-only HTTPS API" : "Managed historian provider"}</span>
      <small>Last telemetry · {formatTimestamp(connection.last_telemetry_at, connection.timezone)}</small>
      <small>{health.mapped_signal_count ?? 0} mapped · {health.stale_signal_count ?? 0} stale</small>
    </button>
  );
}

export default function TelemetryConnectionsWorkspace({
  apiFetch,
  accessCode = "",
  currentUser = null,
  currentWorkspace = null,
  datasetScopeKey = "anonymous",
}) {
  const { canConfigure, canOperate } = roleCapabilities(currentUser);
  const [connections, setConnections] = useState([]);
  const [providers, setProviders] = useState([]);
  const [concepts, setConcepts] = useState([]);
  const [facilityContext, setFacilityContext] = useState(null);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [signals, setSignals] = useState([]);
  const [runs, setRuns] = useState([]);
  const [errors, setErrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);
  const [connectionForm, setConnectionForm] = useState({ ...EMPTY_CONNECTION });
  const [credentialValue, setCredentialValue] = useState("");
  const [mapping, setMapping] = useState({ ...EMPTY_MAPPING });
  const [signalFilter, setSignalFilter] = useState("all");
  const [discoveryIncomplete, setDiscoveryIncomplete] = useState(false);
  const [backfill, setBackfill] = useState({ start: "", end: "" });
  const [systemDraft, setSystemDraft] = useState({ systemId: "", name: "", systemType: "", equipmentId: "", equipmentName: "", equipmentType: "" });
  const authorityKeyRef = useRef(`${datasetScopeKey}:pending`);
  const actionControllerRef = useRef(null);

  const selectedConnection = useMemo(
    () => connections.find((connection) => String(connection.connection_id) === selectedConnectionId) ?? null,
    [connections, selectedConnectionId],
  );
  const visibleSignals = useMemo(
    () => signals.filter((signal) => signalFilter === "all" || signal.mapping_status === signalFilter),
    [signalFilter, signals],
  );
  const mappedCount = countSignals(signals, (signal) => signal.mapping_status === "mapped");
  const unmappedCount = countSignals(signals, (signal) => signal.mapping_status !== "mapped");
  const staleCount = countSignals(signals, (signal) => signal.quality_state === "stale");
  const selectedProvider = providers.find((provider) => provider.connector_type === connectionForm.connectorType) ?? null;

  useEffect(() => {
    const controller = new AbortController();
    actionControllerRef.current?.abort();
    authorityKeyRef.current = `${datasetScopeKey}:pending`;
    setConnections([]);
    setProviders([]);
    setSelectedConnectionId("");
    setSignals([]);
    setRuns([]);
    setErrors([]);
    setFacilityContext(null);
    setMapping({ ...EMPTY_MAPPING });
    setCredentialValue("");
    setNotice("");
    setError("");
    setLoading(true);

    if (typeof apiFetch !== "function") {
      setLoading(false);
      setError("Telemetry connections are unavailable in this session.");
      return () => controller.abort();
    }

    Promise.all([
      listTelemetryConnections({ apiFetch, accessCode, signal: controller.signal }),
      listTelemetryProviders({ apiFetch, accessCode, signal: controller.signal }),
      listCanonicalSignalConcepts({ apiFetch, accessCode, signal: controller.signal }),
      getFacilityContext({ apiFetch, accessCode, signal: controller.signal }),
    ]).then(([connectionPayload, providerPayload, conceptPayload, contextPayload]) => {
      const nextConnections = Array.isArray(connectionPayload?.connections) ? connectionPayload.connections : [];
      const nextAuthorityKey = connectionScopeKey(datasetScopeKey, nextConnections);
      authorityKeyRef.current = nextAuthorityKey;
      setConnections(nextConnections);
      setProviders(Array.isArray(providerPayload?.providers) ? providerPayload.providers : []);
      setConcepts(Array.isArray(conceptPayload?.concepts) ? conceptPayload.concepts : []);
      setFacilityContext(contextPayload && typeof contextPayload === "object" ? contextPayload : null);
      setSelectedConnectionId((current) => nextConnections.some((item) => String(item.connection_id) === current)
        ? current
        : String(nextConnections[0]?.connection_id ?? ""));
    }).catch((requestError) => {
      if (requestError?.name !== "AbortError") setError(requestError?.message || "Telemetry connections could not be loaded.");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });

    return () => controller.abort();
  }, [accessCode, apiFetch, datasetScopeKey]);

  useEffect(() => {
    if (!selectedConnection || typeof apiFetch !== "function") return undefined;
    const expectedAuthority = authorityKeyRef.current;
    const selectedAuthority = `${String(datasetScopeKey || "anonymous")}:${String(selectedConnection.resource_scope_id || "empty")}`;
    if (selectedAuthority !== expectedAuthority) {
      setSelectedConnectionId("");
      setSignals([]);
      setError("This connection is not available in the current facility.");
      return undefined;
    }
    const controller = new AbortController();
    Promise.all([
      listTelemetrySignals({ apiFetch, accessCode, connectionId: selectedConnection.connection_id, signal: controller.signal }),
      listTelemetryRuns({ apiFetch, accessCode, connectionId: selectedConnection.connection_id, signal: controller.signal }),
      listTelemetryErrors({ apiFetch, accessCode, connectionId: selectedConnection.connection_id, signal: controller.signal }),
    ]).then(([signalPayload, runPayload, errorPayload]) => {
      if (authorityKeyRef.current !== expectedAuthority) return;
      setSignals(Array.isArray(signalPayload?.signals) ? signalPayload.signals : []);
      setRuns(Array.isArray(runPayload?.runs) ? runPayload.runs : []);
      setErrors(Array.isArray(errorPayload?.errors) ? errorPayload.errors : []);
    }).catch((requestError) => {
      if (requestError?.name !== "AbortError") setError(requestError?.message || "Connection detail could not be loaded.");
    });
    return () => controller.abort();
  }, [accessCode, apiFetch, datasetScopeKey, selectedConnection]);

  function beginAction(label) {
    actionControllerRef.current?.abort();
    const controller = new AbortController();
    actionControllerRef.current = controller;
    setBusy(label);
    setError("");
    setNotice("");
    return controller;
  }

  function toggleNewConnectionSetup() {
    if (showWizard) {
      setShowWizard(false);
      return;
    }
    setSelectedConnectionId("");
    setConnectionForm({ ...EMPTY_CONNECTION });
    setCredentialValue("");
    setWizardStep(1);
    setShowWizard(true);
  }

  function finishAction(controller) {
    if (actionControllerRef.current === controller) {
      actionControllerRef.current = null;
      setBusy("");
    }
  }

  function updateConnection(connection) {
    if (!connection) return;
    const expectedAuthority = authorityKeyRef.current;
    const returnedAuthority = `${String(datasetScopeKey || "anonymous")}:${String(connection.resource_scope_id || "empty")}`;
    if (!expectedAuthority.endsWith(":empty") && returnedAuthority !== expectedAuthority) {
      throw new Error("Telemetry authority changed while the request was active.");
    }
    authorityKeyRef.current = returnedAuthority;
    setConnections((current) => {
      const exists = current.some((candidate) => String(candidate.connection_id) === String(connection.connection_id));
      return exists
        ? current.map((candidate) => String(candidate.connection_id) === String(connection.connection_id) ? connection : candidate)
        : [connection, ...current];
    });
    setSelectedConnectionId(String(connection.connection_id));
  }

  async function handleCreate(event) {
    event.preventDefault();
    if (!canConfigure) return;
    const controller = beginAction("create");
    try {
      const payload = await createTelemetryConnection({
        apiFetch,
        accessCode,
        signal: controller.signal,
        connection: {
          name: connectionForm.name,
          connector_type: connectionForm.connectorType,
          configuration: connectionConfiguration(connectionForm),
          timezone: connectionForm.timezone,
          polling_interval_seconds: Number(connectionForm.pollingIntervalSeconds),
        },
      });
      updateConnection(payload.connection);
      setWizardStep(selectedProvider?.configuration_mode === "server_owned_template" || connectionForm.authenticationScheme === "none" ? 3 : 2);
      setNotice("Connection metadata saved. Credentials, when required, are submitted one way and are never shown again.");
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setError(requestError?.message);
    } finally {
      finishAction(controller);
    }
  }

  async function handleCredentials(event) {
    event.preventDefault();
    if (!selectedConnection || !credentialValue || !canConfigure) return;
    const controller = beginAction("credentials");
    try {
      const fieldName = connectionForm.authenticationScheme === "api_key" ? "api_key" : "bearer_token";
      await putTelemetryCredentials({
        apiFetch,
        accessCode,
        connectionId: selectedConnection.connection_id,
        values: { [fieldName]: credentialValue },
        signal: controller.signal,
      });
      setCredentialValue("");
      setConnections((current) => current.map((connection) => String(connection.connection_id) === selectedConnectionId
        ? { ...connection, credentials_configured: true }
        : connection));
      setWizardStep(3);
      setNotice("Credential saved securely. Its value cannot be retrieved from this workspace.");
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setError(requestError?.message);
    } finally {
      finishAction(controller);
    }
  }

  async function handleValidate() {
    if (!selectedConnection || !canOperate) return;
    const controller = beginAction("validate");
    try {
      const payload = await validateTelemetryConnection({ apiFetch, accessCode, connectionId: selectedConnection.connection_id, signal: controller.signal });
      updateConnection(payload.connection);
      setWizardStep(4);
      setNotice(payload.valid
        ? `Validation complete: endpoint reachable, authentication ${payload.authenticated ? "valid" : "not required"}, ${payload.observations_sampled} observations sampled.`
        : "Validation completed with a connection issue. Review the separate health checks before continuing.");
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setError(requestError?.message);
    } finally {
      finishAction(controller);
    }
  }

  async function handleDiscover() {
    if (!selectedConnection || !canOperate) return;
    const controller = beginAction("discover");
    try {
      const payload = await discoverTelemetrySignals({
        apiFetch,
        accessCode,
        connectionId: selectedConnection.connection_id,
        checkpoint: null,
        signal: controller.signal,
      });
      const listed = await listTelemetrySignals({ apiFetch, accessCode, connectionId: selectedConnection.connection_id, signal: controller.signal });
      setSignals(Array.isArray(listed?.signals) ? listed.signals : []);
      setDiscoveryIncomplete(payload.has_more === true);
      setWizardStep(5);
      setNotice(`${payload.registered_count} telemetry signals registered. Unmapped signals remain ineligible for analysis.`);
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setError(requestError?.message);
    } finally {
      finishAction(controller);
    }
  }

  async function handleDefineSystem(event) {
    event.preventDefault();
    if (!canOperate || !facilityContext || !systemDraft.systemId || !systemDraft.name || !systemDraft.systemType) return;
    const controller = beginAction("define-system");
    try {
      const equipment = systemDraft.equipmentId ? [{
        equipment_id: systemDraft.equipmentId,
        name: systemDraft.equipmentName || systemDraft.equipmentId,
        system_id: systemDraft.systemId,
        equipment_type: systemDraft.equipmentType || null,
      }] : [];
      const nextContext = {
        site_id: facilityContext.site_id || currentWorkspace?.workspace_id || "facility",
        site_name: facilityContext.site_name || currentWorkspace?.display_name || "Facility",
        timezone: facilityContext.timezone || selectedConnection?.timezone || "UTC",
        systems: [...(facilityContext.systems || []), {
          system_id: systemDraft.systemId,
          name: systemDraft.name,
          system_type: systemDraft.systemType,
          equipment_ids: equipment.map((item) => item.equipment_id),
        }],
        equipment: [...(facilityContext.equipment || []), ...equipment],
        signal_mappings: facilityContext.signal_mappings || [],
      };
      const saved = await putFacilityContext({ apiFetch, accessCode, context: nextContext, signal: controller.signal });
      setFacilityContext(saved);
      setMapping((current) => ({ ...current, systemId: systemDraft.systemId, assetId: systemDraft.equipmentId }));
      setSystemDraft({ systemId: "", name: "", systemType: "", equipmentId: "", equipmentName: "", equipmentType: "" });
      setWizardStep(6);
      setNotice("Physical system definition saved to the facility authority.");
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setError(requestError?.message);
    } finally {
      finishAction(controller);
    }
  }

  function chooseSignal(signal) {
    setMapping({
      ...EMPTY_MAPPING,
      signalId: String(signal.signal_id),
      sourceUnit: signal.source_unit || "",
      sourceTimezone: selectedConnection?.timezone || "UTC",
      expectedCadenceSeconds: String(signal.sample_cadence_seconds || selectedConnection?.polling_interval_seconds || 300),
      systemId: signal.system_id || "",
      assetId: signal.asset_id || "",
      canonicalSignalId: signal.canonical_signal_id || "",
    });
  }

  async function handleMapping(event) {
    event.preventDefault();
    if (!selectedConnection || !mapping.signalId || !canOperate) return;
    const controller = beginAction("mapping");
    try {
      const payload = await mapTelemetrySignal({
        apiFetch,
        accessCode,
        connectionId: selectedConnection.connection_id,
        signalId: mapping.signalId,
        signal: controller.signal,
        mapping: {
          system_id: mapping.systemId,
          asset_id: mapping.assetId || null,
          canonical_signal_id: mapping.canonicalSignalId,
          source_unit: mapping.sourceUnit,
          source_timezone: mapping.sourceTimezone,
          expected_cadence_seconds: Number(mapping.expectedCadenceSeconds),
          provenance: "manual",
          reason: "Approved during production system setup.",
        },
      });
      setSignals((current) => current.map((signal) => String(signal.signal_id) === mapping.signalId ? payload.signal : signal));
      setMapping({ ...EMPTY_MAPPING });
      setWizardStep(6);
      setNotice("Signal accepted into the defined system with explicit unit and time policy.");
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setError(requestError?.message);
    } finally {
      finishAction(controller);
    }
  }

  async function handleEnabled(enabled) {
    if (!selectedConnection || !canConfigure) return;
    const controller = beginAction(enabled ? "enable" : "disable");
    try {
      const payload = await setTelemetryConnectionEnabled({ apiFetch, accessCode, connectionId: selectedConnection.connection_id, enabled, signal: controller.signal });
      updateConnection(payload.connection);
      setWizardStep(enabled ? 9 : 8);
      setNotice(enabled ? "Continued read-only ingestion and system-level analysis enabled." : "Ingestion disabled safely. Existing evidence remains available.");
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setError(requestError?.message);
    } finally {
      finishAction(controller);
    }
  }

  async function handleBackfill(event) {
    event.preventDefault();
    if (!selectedConnection || !canOperate) return;
    const controller = beginAction("backfill");
    try {
      const payload = await startTelemetryBackfill({
        apiFetch,
        accessCode,
        connectionId: selectedConnection.connection_id,
        startAt: new Date(backfill.start).toISOString(),
        endAt: new Date(backfill.end).toISOString(),
        signal: controller.signal,
      });
      setRuns((current) => [payload.run, ...current]);
      setWizardStep(8);
      setNotice("Bounded historical backfill scheduled through the canonical telemetry pipeline.");
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setError(requestError?.message);
    } finally {
      finishAction(controller);
    }
  }

  async function handleRetry(run) {
    if (!selectedConnection || !canOperate) return;
    const controller = beginAction(`retry:${run.run_id}`);
    try {
      const payload = await retryTelemetryRun({ apiFetch, accessCode, connectionId: selectedConnection.connection_id, runId: run.run_id, signal: controller.signal });
      setRuns((current) => [payload.run, ...current]);
      setNotice("Bounded retry scheduled from the stored checkpoint.");
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setError(requestError?.message);
    } finally {
      finishAction(controller);
    }
  }

  return (
    <div className="telemetry-connections" data-testid="telemetry-connections-workspace">
      <header className="telemetry-connections__hero">
        <div>
          <p className="section-token">Production telemetry · {currentWorkspace?.display_name || currentWorkspace?.name || "Current facility"}</p>
          <h1>Connect a physical system</h1>
          <p>Neraium learns how the signals within a defined system behave together over time, preserves that behavioral memory, and surfaces qualified evidence when the system materially departs from what it has learned.</p>
        </div>
        {canConfigure ? <button type="button" className="command-button" onClick={toggleNewConnectionSetup}>{showWizard ? "Close setup" : "Add data source"}</button> : null}
      </header>

      <ol className="telemetry-setup-path" aria-label="System setup progress" tabIndex="0">
        {["Add data source", "Secure credentials", "Validate connection", "Discover telemetry", "Define system", "Map assets and signals", "Validate coverage", "Prepare reference", "Enable analysis"].map((label, index) => (
          <li key={label} className={wizardStep > index ? "is-current" : ""}><span>{index + 1}</span>{label}</li>
        ))}
      </ol>

      {error ? <div className="telemetry-banner telemetry-banner--error" role="alert"><strong>Action needed</strong><span>{error}</span></div> : null}
      {notice ? <div className="telemetry-banner" role="status"><strong>Update</strong><span>{notice}</span></div> : null}

      {showWizard ? (
        <section className="telemetry-panel telemetry-setup" aria-labelledby="telemetry-setup-heading">
          <div className="telemetry-panel__heading"><div><p className="section-token">Step {wizardStep} of 9</p><h2 id="telemetry-setup-heading">Add a read-only data source</h2></div><span className="telemetry-safety-chip">Retrieval only</span></div>
          {!selectedConnection || wizardStep === 1 ? (
            <form className="telemetry-form" onSubmit={handleCreate}>
              <fieldset><legend>Connector type</legend>{providers.map((provider) => <label key={provider.connector_type} className={`telemetry-choice${provider.available ? "" : " telemetry-choice--disabled"}`}><input type="radio" name="connector-type" value={provider.connector_type} checked={connectionForm.connectorType === provider.connector_type} disabled={!provider.available} onChange={(event) => setConnectionForm({ ...connectionForm, connectorType: event.target.value })} /><span><strong>{provider.display_name}</strong><small>{provider.description}</small><small>{provider.configuration_mode === "server_owned_template" ? provider.available ? "Requires approved server-owned template and network profile identifiers." : "Unavailable until an administrator configures an approved server-owned template and network profile." : "Safe HTTPS metadata only. Retrieval methods and egress policy remain server controlled."}</small></span></label>)}</fieldset>
              <div className="telemetry-form-grid">
                <label><span>Connection name</span><input required value={connectionForm.name} onChange={(event) => setConnectionForm({ ...connectionForm, name: event.target.value })} placeholder="Central plant historian API" /></label>
                {connectionForm.connectorType === "https_telemetry" ? <><label><span>HTTPS origin</span><input required type="url" pattern="https://.*" value={connectionForm.baseUrl} onChange={(event) => setConnectionForm({ ...connectionForm, baseUrl: event.target.value })} placeholder="https://telemetry.customer.example" /></label><label><span>Retrieval path</span><input required value={connectionForm.requestPath} onChange={(event) => setConnectionForm({ ...connectionForm, requestPath: event.target.value })} /></label><label><span>Authentication</span><select value={connectionForm.authenticationScheme} onChange={(event) => setConnectionForm({ ...connectionForm, authenticationScheme: event.target.value })}><option value="bearer">Bearer token</option><option value="api_key">API key</option><option value="none">No credential</option></select></label></> : <><label><span>Approved template ID</span><input required value={connectionForm.templateId} onChange={(event) => setConnectionForm({ ...connectionForm, templateId: event.target.value })} /></label><label><span>Approved network profile ID</span><input required value={connectionForm.networkProfileId} onChange={(event) => setConnectionForm({ ...connectionForm, networkProfileId: event.target.value })} /></label></>}
                <label><span>Facility/source timezone</span><input required value={connectionForm.timezone} onChange={(event) => setConnectionForm({ ...connectionForm, timezone: event.target.value })} /></label>
                <label><span>Expected retrieval cadence (seconds)</span><input required type="number" min="30" max="86400" value={connectionForm.pollingIntervalSeconds} onChange={(event) => setConnectionForm({ ...connectionForm, pollingIntervalSeconds: event.target.value })} /></label>
              </div>
              {connectionForm.connectorType === "https_telemetry" ? <details><summary>Advanced response field mapping</summary><div className="telemetry-form-grid telemetry-form-grid--advanced">
                {[["Records path", "recordsPath"], ["Timestamp field", "timestampField"], ["Value field", "valueField"], ["External tag ID field", "externalTagIdField"], ["Tag name field", "externalTagNameField"], ["Unit field", "unitField"], ["Quality field", "qualityField"]].map(([label, key]) => <label key={key}><span>{label}</span><input required value={connectionForm[key]} onChange={(event) => setConnectionForm({ ...connectionForm, [key]: event.target.value })} /></label>)}
              </div></details> : null}
              <div className="telemetry-actions"><button className="command-button" disabled={Boolean(busy) || !selectedProvider?.available} type="submit">Save connection metadata</button><small>Neraium accepts no browser-supplied SQL, DSN, file path, HTTP method, or command.</small></div>
            </form>
          ) : null}

          {selectedConnection && wizardStep === 2 ? (
            <form className="telemetry-form" onSubmit={handleCredentials}>
              <h3>Attach credential securely</h3><p>Enter the credential once. Neraium sends it directly to the server-side secret store and never returns the value or secret reference.</p>
              <label><span>{connectionForm.authenticationScheme === "api_key" ? "API key" : "Bearer token"}</span><input required type="password" autoComplete="new-password" value={credentialValue} onChange={(event) => setCredentialValue(event.target.value)} /></label>
              <div className="telemetry-actions"><button className="command-button" disabled={Boolean(busy)} type="submit">Store credential securely</button></div>
            </form>
          ) : null}

          {selectedConnection && wizardStep >= 3 ? (
            <div className="telemetry-setup-actions">
              <article><span>3</span><div><h3>Validate connection</h3><p>Reachability and authentication are evaluated separately.</p></div><button type="button" onClick={handleValidate} disabled={!canOperate || Boolean(busy)}>Validate</button></article>
              <article><span>4</span><div><h3>Discover telemetry</h3><p>Register a bounded source page without assuming semantic meaning.</p></div><button type="button" onClick={handleDiscover} disabled={!canOperate || wizardStep < 4 || Boolean(busy)}>Discover</button></article>
              <article><span>9</span><div><h3>Enable continued analysis</h3><p>Only intentionally mapped signals become analysis eligible.</p></div><button type="button" className="command-button" onClick={() => handleEnabled(true)} disabled={!canConfigure || wizardStep < 6 || mappedCount === 0 || Boolean(busy)}>Enable analysis</button></article>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="telemetry-panel" aria-labelledby="connection-registry-heading">
        <div className="telemetry-panel__heading"><div><p className="section-token">Facility-scoped registry</p><h2 id="connection-registry-heading">Data connections</h2></div><span>{connections.length} configured</span></div>
        {loading ? <p role="status">Loading facility connections…</p> : connections.length ? <div className="telemetry-connection-grid">{connections.map((connection) => <ConnectionCard key={connection.connection_id} connection={connection} selected={String(connection.connection_id) === selectedConnectionId} onSelect={() => setSelectedConnectionId(String(connection.connection_id))} />)}</div> : <div className="telemetry-empty"><h3>No telemetry source connected</h3><p>Add a read-only data source, define the physical system, and intentionally map its evidence signals before Neraium begins learning system behavior.</p>{canConfigure ? <button type="button" onClick={() => setShowWizard(true)}>Add data source</button> : <small>An administrator can add the first data source for this facility.</small>}</div>}
      </section>

      {selectedConnection ? (
        <>
          <section className="telemetry-panel" aria-labelledby="connection-health-heading">
            <div className="telemetry-panel__heading"><div><p className="section-token">Connection health</p><h2 id="connection-health-heading">{selectedConnection.name}</h2></div><span className={`telemetry-state telemetry-state--${selectedConnection.health?.aggregate_status || "unknown"}`}>{formatState(selectedConnection.health?.aggregate_status)}</span></div>
            <ul className="telemetry-health-grid">{HEALTH_FACETS.map(([facet, label]) => <HealthFacet key={facet} health={selectedConnection.health} facet={facet} label={label} />)}</ul>
            <dl className="telemetry-metrics"><div><dt>Last telemetry</dt><dd>{formatTimestamp(selectedConnection.last_telemetry_at, selectedConnection.timezone)}</dd></div><div><dt>Last successful ingestion</dt><dd>{formatTimestamp(selectedConnection.last_success_at, selectedConnection.timezone)}</dd></div><div><dt>Mapped signals</dt><dd>{mappedCount}</dd></div><div><dt>Stale signals</dt><dd>{staleCount}</dd></div></dl>
            <div className="telemetry-actions"><button type="button" onClick={() => handleEnabled(!selectedConnection.enabled)} disabled={!canConfigure || Boolean(busy)}>{selectedConnection.enabled ? "Disable safely" : "Re-enable ingestion"}</button><small>{selectedConnection.enabled ? "Disabling stops new retrieval; existing behavioral memory and evidence remain." : "A validation and at least one explicit mapping are required before enablement."}</small></div>
          </section>

          <section className="telemetry-panel" aria-labelledby="signal-mapping-heading">
            <div className="telemetry-panel__heading"><div><p className="section-token">System definition</p><h2 id="signal-mapping-heading">Map assets and signals</h2></div><span>{mappedCount} mapped · {unmappedCount} unmapped</span></div>
            <p>Signals are evidence inputs to the defined physical system. Unmapped signals are retained for review but excluded from analysis.</p>
            {discoveryIncomplete ? <div className="telemetry-banner" role="status"><strong>Discovery page complete</strong><span>The source reported additional tags. This production API currently registers one bounded page per discovery request; refresh discovery after the server-side continuation contract is enabled.</span></div> : null}
            <details className="telemetry-system-definition">
              <summary>Define another physical system</summary>
              <form className="telemetry-form" onSubmit={handleDefineSystem}>
                <p>System and equipment identity is saved through the facility context authority before signals can reference it.</p>
                <div className="telemetry-form-grid"><label><span>System ID</span><input required value={systemDraft.systemId} onChange={(event) => setSystemDraft({ ...systemDraft, systemId: event.target.value })} /></label><label><span>System name</span><input required value={systemDraft.name} onChange={(event) => setSystemDraft({ ...systemDraft, name: event.target.value })} /></label><label><span>System type</span><input required value={systemDraft.systemType} onChange={(event) => setSystemDraft({ ...systemDraft, systemType: event.target.value })} /></label><label><span>Equipment ID (optional)</span><input value={systemDraft.equipmentId} onChange={(event) => setSystemDraft({ ...systemDraft, equipmentId: event.target.value })} /></label><label><span>Equipment name</span><input value={systemDraft.equipmentName} onChange={(event) => setSystemDraft({ ...systemDraft, equipmentName: event.target.value })} /></label><label><span>Equipment type</span><input value={systemDraft.equipmentType} onChange={(event) => setSystemDraft({ ...systemDraft, equipmentType: event.target.value })} /></label></div>
                <div className="telemetry-actions"><button type="submit" disabled={!canOperate || Boolean(busy)}>Save system definition</button></div>
              </form>
            </details>
            <div className="telemetry-filter" role="group" aria-label="Filter discovered signals">{["all", "unmapped", "mapped", "invalid"].map((filter) => <button type="button" key={filter} aria-pressed={signalFilter === filter} onClick={() => setSignalFilter(filter)}>{formatState(filter)}</button>)}</div>
            <div className="telemetry-table-wrap"><table className="telemetry-table"><thead><tr><th>Source tag</th><th>Original unit</th><th>Mapping</th><th>Quality</th><th><span className="sr-only">Action</span></th></tr></thead><tbody>{visibleSignals.length ? visibleSignals.map((signal) => <tr key={signal.signal_id}><td><strong>{signal.display_label || signal.external_tag_name}</strong><small>{signal.external_tag_id}</small></td><td>{signal.source_unit || "Not supplied"}</td><td>{signal.mapping_status === "mapped" ? `${signal.system_id} / ${signal.asset_id || "system"} / ${signal.canonical_signal_name}` : "Unmapped · not analyzed"}</td><td>{formatState(signal.quality_state)}</td><td><button type="button" onClick={() => chooseSignal(signal)} disabled={!canOperate}>{signal.mapping_status === "mapped" ? "Review mapping" : "Map signal"}</button></td></tr>) : <tr><td colSpan="5">No discovered telemetry in this view.</td></tr>}</tbody></table></div>
            {mapping.signalId ? <form className="telemetry-form telemetry-mapping-form" onSubmit={handleMapping}><h3>Approve signal meaning</h3><p>Confirm the source tag’s place in the Tenant → Facility → System → Asset → Signal hierarchy. Neraium does not infer meaning from the tag name.</p><div className="telemetry-form-grid"><label><span>Defined system</span><select required value={mapping.systemId} onChange={(event) => setMapping({ ...mapping, systemId: event.target.value, assetId: "" })}><option value="">Select a facility system</option>{(facilityContext?.systems || []).map((system) => <option key={system.system_id} value={system.system_id}>{system.name}</option>)}</select></label><label><span>Asset / equipment</span><select value={mapping.assetId} onChange={(event) => setMapping({ ...mapping, assetId: event.target.value })}><option value="">System-level signal</option>{(facilityContext?.equipment || []).filter((item) => item.system_id === mapping.systemId).map((item) => <option key={item.equipment_id} value={item.equipment_id}>{item.name}</option>)}</select></label><label><span>Canonical signal concept</span><select required value={mapping.canonicalSignalId} onChange={(event) => setMapping({ ...mapping, canonicalSignalId: event.target.value })}><option value="">Select without guessing</option>{concepts.map((concept) => <option key={concept.canonical_signal_id} value={concept.canonical_signal_id}>{concept.display_name} · {concept.canonical_unit}</option>)}</select></label><label><span>Original engineering unit</span><input required value={mapping.sourceUnit} onChange={(event) => setMapping({ ...mapping, sourceUnit: event.target.value })} /></label><label><span>Source timezone</span><input required value={mapping.sourceTimezone} onChange={(event) => setMapping({ ...mapping, sourceTimezone: event.target.value })} /></label><label><span>Expected cadence (seconds)</span><input required type="number" min="1" max="86400" value={mapping.expectedCadenceSeconds} onChange={(event) => setMapping({ ...mapping, expectedCadenceSeconds: event.target.value })} /></label></div><div className="telemetry-actions"><button className="command-button" type="submit" disabled={Boolean(busy)}>Approve mapping</button><button type="button" onClick={() => setMapping({ ...EMPTY_MAPPING })}>Cancel</button></div></form> : null}
          </section>

          <section className="telemetry-panel telemetry-operations" aria-labelledby="ingestion-operations-heading">
            <div className="telemetry-panel__heading"><div><p className="section-token">Reference preparation and operations</p><h2 id="ingestion-operations-heading">Ingestion activity</h2></div><span>{errors.length} current problems</span></div>
            <form className="telemetry-backfill" onSubmit={handleBackfill}><div><h3>Prepare behavioral reference</h3><p>Schedule a bounded, resumable UTC backfill through the same canonical pipeline used for continued telemetry.</p></div><label><span>Start (UTC)</span><input required type="datetime-local" value={backfill.start} onChange={(event) => setBackfill({ ...backfill, start: event.target.value })} /></label><label><span>End (UTC)</span><input required type="datetime-local" value={backfill.end} onChange={(event) => setBackfill({ ...backfill, end: event.target.value })} /></label><button type="submit" disabled={!canOperate || Boolean(busy)}>Start backfill</button></form>
            <div className="telemetry-ops-grid"><div><h3>Recent runs</h3>{runs.length ? <ul className="telemetry-record-list">{runs.map((run) => <li key={run.run_id}><div><strong>{formatState(run.mode)} · {formatState(run.status)}</strong><small>{run.observations_accepted ?? 0} accepted · {run.observations_rejected ?? 0} rejected · {run.observations_duplicate ?? 0} duplicate</small></div>{["failed", "partial"].includes(run.status) ? <button type="button" onClick={() => handleRetry(run)} disabled={!canOperate || Boolean(busy)}>Retry</button> : null}</li>)}</ul> : <p>No ingestion runs yet.</p>}</div><div><h3>Ingestion errors</h3>{errors.length ? <ul className="telemetry-record-list">{errors.map((item) => <li key={item.error_id}><div><strong>{formatState(item.reason_code)}</strong><small>{item.external_tag_id || "Batch-level"} · {formatState(item.disposition)} · last seen {formatTimestamp(item.last_seen_at, selectedConnection.timezone)}</small></div><span>{item.occurrence_count}×</span></li>)}</ul> : <p>No sanitized ingestion errors reported.</p>}</div></div>
          </section>
        </>
      ) : null}
    </div>
  );
}
