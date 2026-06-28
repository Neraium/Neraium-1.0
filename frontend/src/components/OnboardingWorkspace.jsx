import { useEffect, useMemo, useRef, useState } from "react";
import { buildApiUrl } from "../config";
import { uploadTelemetryFileWithProgress } from "../services/api/uploadApi";
import * as uploadStateView from "../viewModels/uploadState";

const STORAGE_KEY = "neraium.onboarding.v1";

const SYSTEM_TYPES = [
  "General Telemetry",
  "Process Telemetry",
  "Built Environment",
  "Mobile / Fleet",
  "Custom Stream",
];

const DATA_SOURCES = [
  "CSV Upload",
  "API",
  "Read-only Stream",
  "Control Platform",
  "MQTT",
  "Modbus Gateway",
  "Demo Mode",
];

const SIGNAL_ROLES = [
  "state_variable_a",
  "state_variable_b",
  "state_variable_c",
  "control_signal",
  "setpoint",
  "response_metric",
  "load_metric",
  "event_marker",
  "context_variable",
  "recovery_indicator",
  "custom_variable",
];

const STEPS = [
  "Telemetry Profile",
  "Data Source",
  "Connection Details",
  "Variable Mapping",
  "Connection Test",
  "Reference Setup",
  "Begin Monitoring",
];

const MOCK_FIELDS = [
  "timestamp",
  "segment",
  "variable_a",
  "variable_b",
  "variable_c",
  "control_signal",
  "setpoint",
  "load_metric",
  "response_metric",
  "event_marker",
];

const UPLOAD_STAGE_LABELS = {
  validating: "validating",
  uploading: "uploading",
  queued: "queued",
  processing: "processing",
  complete: "complete",
  failed: "failed",
};

function normalizeOnboardingUploadStage(value) {
  const normalized = String(value ?? "").toLowerCase();
  if (["uploading"].includes(normalized)) return "uploading";
  if (["validated", "upload_started"].includes(normalized)) return "validating";
  if (["pending", "queued", "accepted"].includes(normalized)) return "queued";
  if (["complete"].includes(normalized)) return "complete";
  if (["failed", "error", "not_found"].includes(normalized)) return "failed";
  return "processing";
}

async function readJsonSafely(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function defaultState() {
  return {
    step: 0,
    systemType: "",
    dataSource: "",
    csvFileName: "",
    detectedColumns: [],
    uploadJobId: "",
    uploadStatus: "",
    uploadMessage: "",
    uploadError: "",
    uploadCompleteSticky: false,
    api: {
      baseUrl: "",
      token: "",
      pollingInterval: "30",
      siteName: "",
      systemName: "",
    },
    signalMapping: {},
    baselineMode: "live-learning-window",
    baselineTrainingMode: "auto-detect-stable-window",
    baselineWindowStart: "",
    baselineWindowEnd: "",
    connectionTest: null,
    connectionTestState: "idle",
    connectionTestMessage: "",
    connectionTestError: "",
    monitoringStarted: false,
  };
}

function buildLocalConnectionAssessment(flow) {
  const mappedCount = Object.values(flow.signalMapping).filter(Boolean).length;
  const sourceReachable = Boolean(
    flow.dataSource
    && (
      flow.dataSource === "Demo Mode"
      || flow.dataSource === "CSV Upload"
      || Boolean(flow.api.baseUrl)
    )
  );
  const telemetryReceived = flow.dataSource === "CSV Upload"
    ? Boolean(flow.csvFileName)
    : sourceReachable;
  const timestampDetected = flow.dataSource === "CSV Upload"
    ? flow.detectedColumns.includes("timestamp")
    : true;
  return {
    sourceReachable,
    telemetryReceived,
    timestampDetected,
    requiredSignalsMapped: mappedCount >= 3,
    sampleRateAcceptable: flow.dataSource === "API"
      ? Number(flow.api.pollingInterval) > 0 && Number(flow.api.pollingInterval) <= 300
      : true,
  };
}

function loadSavedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState();
    const parsed = JSON.parse(raw);
    return {
      ...defaultState(),
      ...parsed,
      api: {
        ...defaultState().api,
        ...(parsed?.api || {}),
        token: "",
      },
    };
  } catch {
    return defaultState();
  }
}

function storageSafeFlow(flow) {
  return {
    ...flow,
    api: {
      ...(flow?.api || {}),
      token: "",
    },
  };
}

export default function OnboardingWorkspace({ onBackToGate, onStartMonitoring, onUploadComplete, accessCode = "", apiFetch = null }) {
  const [flow, setFlow] = useState(loadSavedState);
  const csvInputRef = useRef(null);
  const uploadPollAbortRef = useRef(false);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(storageSafeFlow(flow)));
  }, [flow]);

  useEffect(() => () => {
    uploadPollAbortRef.current = true;
  }, []);

  const mappedCount = useMemo(
    () => Object.values(flow.signalMapping).filter(Boolean).length,
    [flow.signalMapping],
  );

  const canContinue = useMemo(() => {
    if (flow.step === 0) return Boolean(flow.systemType);
    if (flow.step === 1) return Boolean(flow.dataSource);
    if (flow.step === 2) {
      if (flow.dataSource === "API") {
        return Boolean(flow.api.baseUrl && flow.api.token && flow.api.siteName && flow.api.systemName && Number(flow.api.pollingInterval) > 0);
      }
      if (flow.dataSource === "CSV Upload") return Boolean(flow.csvFileName);
      if (flow.dataSource === "Demo Mode") return true;
      return true;
    }
    if (flow.step === 3) return mappedCount > 0;
    if (flow.step === 4) return flow.connectionTestState === "passed";
    if (flow.step === 5) return Boolean(flow.baselineMode);
    return true;
  }, [flow, mappedCount]);

  function buildConnectionTestReset() {
    return {
      connectionTest: null,
      connectionTestState: "idle",
      connectionTestMessage: "",
      connectionTestError: "",
    };
  }

  function updateFlow(patch) {
    setFlow((current) => ({ ...current, ...patch }));
  }

  function setApiField(field, value) {
    setFlow((current) => ({
      ...current,
      ...buildConnectionTestReset(),
      api: { ...current.api, [field]: value },
    }));
  }

  function prevStep() {
    updateFlow({ step: Math.max(flow.step - 1, 0) });
  }

  function resetWizard() {
    const clean = defaultState();
    setFlow(clean);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(storageSafeFlow(clean)));
  }

  function handleMockCsvSelect() {
    const detectedColumns = MOCK_FIELDS;
    setFlow((current) => ({
      ...current,
      csvFileName: "sample_telemetry_export.csv",
      detectedColumns,
      signalMapping: {
        ...current.signalMapping,
        state_variable_a: current.signalMapping.state_variable_a || "variable_a",
        state_variable_b: current.signalMapping.state_variable_b || "variable_b",
        state_variable_c: current.signalMapping.state_variable_c || "variable_c",
      },
      ...buildConnectionTestReset(),
      step: 3,
      uploadStatus: "complete",
      uploadMessage: "Demo telemetry loaded.",
      uploadError: "",
      uploadCompleteSticky: true,
    }));
  }

  async function onboardingFetch(path, options = {}) {
    if (typeof apiFetch === "function") {
      return apiFetch(path, { accessCode, ...options });
    }
    return fetch(buildApiUrl(path), {
      credentials: "include",
      ...options,
      headers: {
        ...(options.headers || {}),
        ...(accessCode ? { "X-Neraium-Access-Code": accessCode } : {}),
      },
    });
  }

  async function pollUploadUntilTerminal(jobId) {
    let attempts = 0;
    while (attempts < 240 && !uploadPollAbortRef.current) {
      attempts += 1;
      const response = await onboardingFetch(`/api/data/upload-status/${encodeURIComponent(jobId)}`);
      const payload = await readJsonSafely(response);
      const stage = normalizeOnboardingUploadStage(payload?.status ?? payload?.processing_state);

      if (flow.uploadCompleteSticky && stage === "failed") {
        return payload;
      }

      if (!response.ok && stage === "failed") {
        throw new Error(String(payload?.message || payload?.error || "Upload processing failed."));
      }

      setFlow((current) => {
        if (current.uploadCompleteSticky && stage !== "complete") {
          return current;
        }
        return {
          ...current,
          uploadStatus: stage,
          uploadMessage: String(payload?.progress_label || payload?.message || current.uploadMessage || ""),
          uploadError: stage === "failed" ? String(payload?.error || payload?.message || "Upload failed.") : "",
          uploadCompleteSticky: current.uploadCompleteSticky || stage === "complete",
        };
      });

      if (stage === "complete") return payload;
      if (stage === "failed") throw new Error(String(payload?.message || payload?.error || "Upload processing failed."));

      await new Promise((resolve) => window.setTimeout(resolve, 1200));
    }
    throw new Error("Upload status polling timed out.");
  }

  async function refreshLatestUploadAndPropagate(expectedJobId, fallbackPayload = null) {
    const latestResponse = await onboardingFetch("/api/data/latest-upload?include_persisted=1");
    const latestPayload = await readJsonSafely(latestResponse);
    if (!latestResponse.ok) {
      throw new Error(String(latestPayload?.detail || latestPayload?.message || "Unable to confirm the latest upload state."));
    }
    const finalPayload = uploadStateView.resolveCurrentUploadResult(latestPayload) ?? null;
    const resolvedJobId = String(
      finalPayload?.job_id
      || uploadStateView.resolveCurrentUploadJobId(latestPayload)
      || fallbackPayload?.job_id
      || ""
    ).trim();
    if (!finalPayload || (expectedJobId && resolvedJobId !== String(expectedJobId).trim())) {
      throw new Error("Upload completed, but the latest session state is not ready yet. Retry in a moment.");
    }
    if (typeof onUploadComplete === "function") {
      await onUploadComplete(finalPayload);
    }
    return finalPayload;
  }

  async function handleCsvFileSelection(event) {
    const file = event.target.files?.[0] ?? null;
    if (!file) return;

    uploadPollAbortRef.current = false;
    setFlow((current) => ({
      ...current,
      csvFileName: file.name,
      uploadStatus: "validating",
      uploadMessage: "Validating file and detecting columns...",
      uploadError: "",
      uploadCompleteSticky: current.uploadCompleteSticky,
    }));

    let detectedColumns = [];
    try {
      const text = await file.text();
      const headerLine = String(text || "").split(/\r?\n/, 1)[0] ?? "";
      detectedColumns = headerLine
        .split(",")
        .map((column) => column.replace(/^"|"$/g, "").trim())
        .filter(Boolean);
    } catch {
      detectedColumns = [];
    }

    setFlow((current) => ({
      ...current,
      detectedColumns,
      signalMapping: {
        ...current.signalMapping,
        state_variable_a: current.signalMapping.state_variable_a || (detectedColumns.includes("variable_a") ? "variable_a" : ""),
        state_variable_b: current.signalMapping.state_variable_b || (detectedColumns.includes("variable_b") ? "variable_b" : ""),
        state_variable_c: current.signalMapping.state_variable_c || (detectedColumns.includes("variable_c") ? "variable_c" : ""),
      },
      ...buildConnectionTestReset(),
      step: 3,
    }));

    try {
      const { ok, payload } = await uploadTelemetryFileWithProgress({
        file,
        accessCode,
        onProgress: (progress) => {
          const stage = normalizeOnboardingUploadStage(progress?.stage);
          setFlow((current) => ({
            ...current,
            uploadStatus: stage,
            uploadMessage: String(progress?.message || current.uploadMessage || ""),
            uploadError: "",
          }));
        },
      });

      if (!ok) {
        throw new Error(String(payload?.message || "Upload request failed."));
      }

      const jobId = String(payload?.job_id ?? payload?.jobId ?? payload?.id ?? "").trim();
      if (!jobId) {
        throw new Error("Upload accepted but no job_id returned.");
      }

      setFlow((current) => ({
        ...current,
        uploadJobId: jobId,
        uploadStatus: "queued",
        uploadMessage: String(payload?.message || "Upload accepted. Processing queued."),
        uploadError: "",
      }));

      const completionPayload = await pollUploadUntilTerminal(jobId);
      setFlow((current) => ({
        ...current,
        uploadStatus: "processing",
        uploadMessage: "Finalizing the active session state...",
        uploadError: "",
      }));
      await refreshLatestUploadAndPropagate(jobId, completionPayload);
      setFlow((current) => ({
        ...current,
        uploadStatus: "complete",
        uploadMessage: String(completionPayload?.message || "Telemetry processing complete."),
        uploadError: "",
        uploadCompleteSticky: true,
      }));
    } catch (error) {
      setFlow((current) => {
        if (current.uploadCompleteSticky) return current;
        return {
          ...current,
          uploadStatus: "failed",
          uploadError: String(error?.message || "Upload failed."),
          uploadMessage: "Upload failed.",
        };
      });
    }
  }

  async function runConnectionTest() {
    if (flow.dataSource === "API") {
      updateFlow({
        ...buildConnectionTestReset(),
        connectionTestState: "running",
        connectionTestMessage: "Verifying read-only API access and telemetry structure...",
      });

      try {
        const response = await onboardingFetch("/api/connectors/rest/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            endpoint: flow.api.baseUrl,
            token: flow.api.token,
            source_id: flow.api.siteName || "customer-rest",
            system_id: flow.api.systemName || "facility-rest",
          }),
        });
        const payload = await readJsonSafely(response);
        if (!response.ok) {
          throw new Error(String(payload?.detail || payload?.message || "API verification failed."));
        }
        const readiness = buildLocalConnectionAssessment(flow);
        updateFlow({
          connectionTest: {
            ...readiness,
            sourceReachable: payload.connection_status !== "offline" && payload.connection_status !== "not_configured",
            telemetryReceived: Number(payload.records_ingested) > 0 || Number(payload.sensors_detected) > 0,
            backendValidated: true,
            connectionStatus: payload.connection_status,
            sensorsDetected: Number(payload.sensors_detected ?? 0),
            recordsIngested: Number(payload.records_ingested ?? 0),
            warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
          },
          connectionTestState: "passed",
          connectionTestMessage: String(payload?.message || "Read-only verification passed."),
          connectionTestError: "",
          step: 5,
        });
        return;
      } catch (error) {
        updateFlow({
          ...buildConnectionTestReset(),
          connectionTestState: "failed",
          connectionTestError: String(error?.message || "API verification failed."),
        });
        return;
      }
    }

    const results = buildLocalConnectionAssessment(flow);
    updateFlow({
      connectionTest: results,
      connectionTestState: "passed",
      connectionTestMessage: flow.dataSource === "CSV Upload"
        ? "Uploaded telemetry is ready for mapping review."
        : "Readiness checks passed for the selected data source.",
      connectionTestError: "",
      step: 5,
    });
  }

  function setMappedField(role, value) {
    setFlow((current) => ({
      ...current,
      ...buildConnectionTestReset(),
      signalMapping: { ...current.signalMapping, [role]: value || "" },
    }));
  }

  function startMonitoring() {
    updateFlow({ monitoringStarted: true });
    if (typeof onStartMonitoring === "function") onStartMonitoring();
  }

  function advanceStep() {
    if (!canContinue) return;
    updateFlow({ step: Math.min(flow.step + 1, STEPS.length - 1) });
  }

  return (
    <section className="onboarding-shell" aria-label="Neraium setup wizard">
      <header className="onboarding-header">
        <div>
          <p className="section-token">Neraium Setup</p>
          <h1>Set Up Telemetry Intake</h1>
          <p>Guided onboarding from first connection to structural monitoring.</p>
        </div>
        <div className="onboarding-actions">
          <button type="button" className="secondary-command-button" onClick={onBackToGate}>Back to Gate</button>
          <button type="button" className="secondary-command-button" onClick={resetWizard}>Reset</button>
        </div>
      </header>

      <ol className="onboarding-stepper" aria-label="Onboarding steps">
        {STEPS.map((label, index) => (
          <li key={label} className={index === flow.step ? "is-active" : index < flow.step ? "is-complete" : ""}>
            <span>{index + 1}</span>
            <strong>{label}</strong>
          </li>
        ))}
      </ol>

      <div className="onboarding-card">
        {flow.step === 0 && (
          <div className="onboarding-section">
            <h2>Telemetry Profile</h2>
            <div className="onboarding-choice-grid">
              {SYSTEM_TYPES.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={`onboarding-choice ${flow.systemType === option ? "is-selected" : ""}`}
                  onClick={() => updateFlow({ systemType: option, ...buildConnectionTestReset(), step: 1 })}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        )}

        {flow.step === 1 && (
          <div className="onboarding-section">
            <h2>Data Source</h2>
            <div className="onboarding-choice-grid">
              {DATA_SOURCES.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={`onboarding-choice ${flow.dataSource === option ? "is-selected" : ""}`}
                  onClick={() => updateFlow({
                    dataSource: option,
                    ...buildConnectionTestReset(),
                    step: 2,
                  })}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        )}

        {flow.step === 2 && (
          <div className="onboarding-section">
            <h2>Connection Details</h2>
            {flow.dataSource === "API" && (
              <div className="onboarding-form-grid">
                <label className="onboarding-field">
                  <span>API base URL</span>
                  <input
                    aria-label="API base URL"
                    value={flow.api.baseUrl}
                    onChange={(event) => setApiField("baseUrl", event.target.value)}
                    placeholder="https://example.test/telemetry"
                    autoComplete="url"
                  />
                </label>
                <label className="onboarding-field">
                  <span>API key or token</span>
                  <input
                    aria-label="API key or token"
                    type="password"
                    value={flow.api.token}
                    onChange={(event) => setApiField("token", event.target.value)}
                    placeholder="Enter read-only token"
                    autoComplete="current-password"
                  />
                </label>
                <label className="onboarding-field">
                  <span>Polling interval (seconds)</span>
                  <input
                    aria-label="Polling interval (seconds)"
                    value={flow.api.pollingInterval}
                    onChange={(event) => setApiField("pollingInterval", event.target.value)}
                    placeholder="30"
                    inputMode="numeric"
                  />
                </label>
                <label className="onboarding-field">
                  <span>Deployment label</span>
                  <input
                    aria-label="Deployment label"
                    value={flow.api.siteName}
                    onChange={(event) => setApiField("siteName", event.target.value)}
                    placeholder="Production greenhouse"
                  />
                </label>
                <label className="onboarding-field">
                  <span>Telemetry stream label</span>
                  <input
                    aria-label="Telemetry stream label"
                    value={flow.api.systemName}
                    onChange={(event) => setApiField("systemName", event.target.value)}
                    placeholder="Main telemetry stream"
                  />
                </label>
              </div>
            )}
            {flow.dataSource === "CSV Upload" && (
              <div className="onboarding-inline">
                <input
                  ref={csvInputRef}
                  type="file"
                  accept=".csv,.json,text/csv,application/json"
                  style={{ display: "none" }}
                  onChange={handleCsvFileSelection}
                />
                <button
                  type="button"
                  className="command-button"
                  onClick={() => csvInputRef.current?.click()}
                >
                  Upload and Detect Variables
                </button>
                <button type="button" className="secondary-command-button" onClick={handleMockCsvSelect}>Use Demo CSV</button>
                <span>
                  {flow.csvFileName ? `${flow.csvFileName} (${flow.detectedColumns.length} columns detected)` : "No file selected yet."}
                  {flow.uploadStatus ? ` | ${UPLOAD_STAGE_LABELS[flow.uploadStatus] || flow.uploadStatus}` : ""}
                  {flow.uploadJobId ? ` | job ${flow.uploadJobId}` : ""}
                </span>
                {flow.uploadMessage ? <span>{flow.uploadMessage}</span> : null}
                {flow.uploadError ? <span>{flow.uploadError}</span> : null}
              </div>
            )}
            {flow.dataSource === "Demo Mode" && (
              <div className="onboarding-inline">
                <span>Demo telemetry package will be used for setup and baseline learning.</span>
              </div>
            )}
            {!["API", "CSV Upload", "Demo Mode"].includes(flow.dataSource) && (
              <div className="onboarding-inline">
                <span>Connector UI scaffolded. Production connector details can be wired to backend endpoints later.</span>
              </div>
            )}
          </div>
        )}

        {flow.step === 3 && (
          <div className="onboarding-section">
            <h2>Variable Mapping</h2>
            <div className="onboarding-form-grid">
              {SIGNAL_ROLES.map((role) => (
                <label key={role} className="onboarding-map-row">
                  <span>{role}</span>
                  <input
                    value={flow.signalMapping[role] || ""}
                    onChange={(event) => setMappedField(role, event.target.value)}
                    placeholder={flow.detectedColumns[0] || "source field"}
                    list="detected-column-options"
                  />
                </label>
              ))}
            </div>
            <datalist id="detected-column-options">
              {flow.detectedColumns.map((col) => <option key={col} value={col} />)}
            </datalist>
          </div>
        )}

        {flow.step === 4 && (
          <div className="onboarding-section">
            <h2>Connection Test</h2>
            <div className="onboarding-inline">
              <button
                type="button"
                className="command-button"
                onClick={() => {
                  void runConnectionTest();
                }}
                disabled={flow.connectionTestState === "running"}
              >
                {flow.connectionTestState === "running" ? "Testing Connection..." : "Run Connection Test"}
              </button>
            </div>
            {flow.connectionTestMessage ? <p className="narrative-text">{flow.connectionTestMessage}</p> : null}
            {flow.connectionTestError ? <p className="narrative-text">{flow.connectionTestError}</p> : null}
            {flow.connectionTest && (
              <ul className="onboarding-checklist">
                <li className={flow.connectionTest.sourceReachable ? "ok" : "warn"}>Data source reachable</li>
                <li className={flow.connectionTest.telemetryReceived ? "ok" : "warn"}>Telemetry received</li>
                <li className={flow.connectionTest.timestampDetected ? "ok" : "warn"}>Timestamp detected</li>
                <li className={flow.connectionTest.requiredSignalsMapped ? "ok" : "warn"}>Required variables mapped</li>
                <li className={flow.connectionTest.sampleRateAcceptable ? "ok" : "warn"}>Sample rate acceptable</li>
              </ul>
            )}
            {Array.isArray(flow.connectionTest?.warnings) && flow.connectionTest.warnings.length > 0 ? (
              <ul className="compact-list">
                {flow.connectionTest.warnings.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            ) : null}
          </div>
        )}

        {flow.step === 5 && (
          <div className="onboarding-section">
            <h2>Reference Setup</h2>
            <div className="onboarding-form-grid" style={{ marginBottom: 16 }}>
              <label className="onboarding-map-row">
                <span>Training mode</span>
                <select
                  value={flow.baselineTrainingMode}
                  onChange={(event) => updateFlow({ baselineTrainingMode: event.target.value })}
                >
                  <option value="auto-detect-stable-window">Auto-detect stable window</option>
                  <option value="operator-marked-window">Operator-marked stable window</option>
                </select>
              </label>
              <label className="onboarding-map-row">
                <span>Stable window start</span>
                <input
                  type="datetime-local"
                  value={flow.baselineWindowStart}
                  onChange={(event) => updateFlow({ baselineWindowStart: event.target.value })}
                />
              </label>
              <label className="onboarding-map-row">
                <span>Stable window end</span>
                <input
                  type="datetime-local"
                  value={flow.baselineWindowEnd}
                  onChange={(event) => updateFlow({ baselineWindowEnd: event.target.value })}
                />
              </label>
            </div>
            <p className="narrative-text">
              Connect to data source, verify telemetry, choose a stable training period or accept auto-detection, and let the reference behavior finish learning before findings go live.
            </p>
            <div className="onboarding-choice-grid">
              {[
                { id: "historical-upload", label: "Upload Historical Reference" },
                { id: "live-learning-window", label: "Use First Live Learning Window" },
                { id: "demo-baseline", label: "Use Demo Reference" },
              ].map((mode) => (
                <button
                  key={mode.id}
                  type="button"
                  className={`onboarding-choice ${flow.baselineMode === mode.id ? "is-selected" : ""}`}
                  onClick={() => updateFlow({ baselineMode: mode.id, step: 6 })}
                >
                  {mode.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {flow.step === 6 && (
          <div className="onboarding-section">
            <h2>Begin Monitoring</h2>
            <ul className="onboarding-summary">
              <li><span>Profile</span><strong>{flow.api.systemName || flow.systemType || "Unspecified telemetry profile"}</strong></li>
              <li><span>Data source</span><strong>{flow.dataSource || "Not selected"}</strong></li>
              <li><span>Mapped variables</span><strong>{mappedCount}</strong></li>
              <li><span>Baseline</span><strong>{flow.baselineMode}</strong></li>
              <li><span>Training mode</span><strong>{flow.baselineTrainingMode}</strong></li>
            </ul>
            <button type="button" className="command-button onboarding-start" onClick={startMonitoring}>Start Monitoring</button>
            {flow.monitoringStarted && (
              <p className="onboarding-started">Monitoring started. Returning operators to the Gate now uses this setup context.</p>
            )}
          </div>
        )}
      </div>

      <footer className="onboarding-footer">
        <button type="button" className="secondary-command-button" onClick={prevStep} disabled={flow.step === 0}>Back</button>
        {(flow.step === 2 || flow.step === 3) ? (
          <button type="button" className="command-button" onClick={advanceStep} disabled={!canContinue}>Continue</button>
        ) : null}
      </footer>
    </section>
  );
}
