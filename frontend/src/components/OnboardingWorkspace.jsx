import { useEffect, useMemo, useRef, useState } from "react";

const STORAGE_KEY = "neraium.onboarding.v1";

const SYSTEM_TYPES = [
  "Cannabis Grow",
  "Data Center Cooling",
  "HVAC / Facilities",
  "Water / Utility",
  "Custom Infrastructure",
];

const DATA_SOURCES = [
  "CSV Upload",
  "API",
  "Historian",
  "BMS / BAS",
  "MQTT",
  "Modbus Gateway",
  "Demo Mode",
];

const SIGNAL_ROLES = [
  "temperature",
  "humidity",
  "vpd",
  "pressure",
  "airflow",
  "vibration",
  "energy_load",
  "equipment_state",
  "cooling_response",
  "dehumidifier_response",
  "custom",
];

const STEPS = [
  "System Type",
  "Data Source",
  "Connection Details",
  "Signal Mapping",
  "Connection Test",
  "Baseline Setup",
  "Go Online",
];

const MOCK_FIELDS = [
  "timestamp",
  "room",
  "temperature",
  "humidity",
  "vpd",
  "pressure",
  "airflow",
  "fan_speed",
  "equipment_state",
];

function defaultState() {
  return {
    step: 0,
    systemType: "",
    dataSource: "",
    csvFileName: "",
    detectedColumns: [],
    api: {
      baseUrl: "",
      token: "",
      pollingInterval: "30",
      siteName: "",
      systemName: "",
    },
    signalMapping: {},
    baselineMode: "live-learning-window",
    connectionTest: null,
    monitoringStarted: false,
  };
}

// Mocked test helper (isolated so production endpoint checks can replace it).
function runMockConnectionTest(flow) {
  const sourceReachable = Boolean(
    flow.dataSource
    && (
      flow.dataSource === "Demo Mode"
      || flow.dataSource === "CSV Upload"
      || (flow.api.baseUrl && flow.api.token)
    )
  );
  const telemetryReceived = flow.dataSource === "CSV Upload"
    ? Boolean(flow.csvFileName)
    : sourceReachable;
  const timestampDetected = flow.dataSource === "CSV Upload"
    ? flow.detectedColumns.includes("timestamp")
    : true;
  const mappedCount = Object.values(flow.signalMapping).filter(Boolean).length;
  const requiredSignalsMapped = mappedCount >= 3;
  const sampleRateAcceptable = flow.dataSource === "API"
    ? Number(flow.api.pollingInterval) > 0 && Number(flow.api.pollingInterval) <= 300
    : true;
  return {
    sourceReachable,
    telemetryReceived,
    timestampDetected,
    requiredSignalsMapped,
    sampleRateAcceptable,
  };
}

function loadSavedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState();
    const parsed = JSON.parse(raw);
    return { ...defaultState(), ...parsed, api: { ...defaultState().api, ...(parsed?.api || {}) } };
  } catch {
    return defaultState();
  }
}

export default function OnboardingWorkspace({ onBackToGate, onStartMonitoring }) {
  const [flow, setFlow] = useState(loadSavedState);
  const csvInputRef = useRef(null);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(flow));
  }, [flow]);

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
    if (flow.step === 4) return Boolean(flow.connectionTest);
    if (flow.step === 5) return Boolean(flow.baselineMode);
    return true;
  }, [flow, mappedCount]);

  function updateFlow(patch) {
    setFlow((current) => ({ ...current, ...patch }));
  }

  function setApiField(field, value) {
    setFlow((current) => ({ ...current, api: { ...current.api, [field]: value } }));
  }

  function prevStep() {
    updateFlow({ step: Math.max(flow.step - 1, 0) });
  }

  function resetWizard() {
    const clean = defaultState();
    setFlow(clean);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(clean));
  }

  function handleMockCsvSelect() {
    const detectedColumns = MOCK_FIELDS;
    setFlow((current) => ({
      ...current,
      csvFileName: "sample_telemetry_export.csv",
      detectedColumns,
      signalMapping: {
        ...current.signalMapping,
        temperature: current.signalMapping.temperature || "temperature",
        humidity: current.signalMapping.humidity || "humidity",
        vpd: current.signalMapping.vpd || "vpd",
      },
      step: 3,
    }));
  }

  async function handleCsvFileSelection(event) {
    const file = event.target.files?.[0] ?? null;
    if (!file) return;
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
      csvFileName: file.name,
      detectedColumns,
      signalMapping: {
        ...current.signalMapping,
        temperature: current.signalMapping.temperature || (detectedColumns.includes("temperature") ? "temperature" : ""),
        humidity: current.signalMapping.humidity || (detectedColumns.includes("humidity") ? "humidity" : ""),
        vpd: current.signalMapping.vpd || (detectedColumns.includes("vpd") ? "vpd" : ""),
      },
    }));
    setFlow((current) => ({ ...current, step: 3 }));
  }

  function runConnectionTest() {
    const results = runMockConnectionTest(flow);
    updateFlow({ connectionTest: results });
  }

  function setMappedField(role, value) {
    setFlow((current) => ({
      ...current,
      signalMapping: { ...current.signalMapping, [role]: value || "" },
    }));
  }

  function startMonitoring() {
    updateFlow({ monitoringStarted: true });
    if (typeof onStartMonitoring === "function") onStartMonitoring();
  }

  useEffect(() => {
    if (flow.step === 2 && canContinue && flow.dataSource === "API") {
      const timer = window.setTimeout(() => {
        setFlow((current) => (
          current.step === 2
            ? { ...current, step: Math.min(current.step + 1, STEPS.length - 1) }
            : current
        ));
      }, 180);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [canContinue, flow.step, flow.dataSource]);

  return (
    <section className="onboarding-shell" aria-label="Neraium setup wizard">
      <header className="onboarding-header">
        <div>
          <p className="section-token">Neraium Setup</p>
          <h1>Set Up System</h1>
          <p>Guided onboarding from first configuration to live monitoring.</p>
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
            <h2>System Type</h2>
            <div className="onboarding-choice-grid">
              {SYSTEM_TYPES.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={`onboarding-choice ${flow.systemType === option ? "is-selected" : ""}`}
                  onClick={() => updateFlow({ systemType: option, step: 1 })}
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
                  onClick={() => updateFlow({ dataSource: option, step: 2 })}
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
                <input value={flow.api.baseUrl} onChange={(event) => setApiField("baseUrl", event.target.value)} placeholder="API base URL" />
                <input value={flow.api.token} onChange={(event) => setApiField("token", event.target.value)} placeholder="API key / token" />
                <input value={flow.api.pollingInterval} onChange={(event) => setApiField("pollingInterval", event.target.value)} placeholder="Polling interval (seconds)" />
                <input value={flow.api.siteName} onChange={(event) => setApiField("siteName", event.target.value)} placeholder="Site name" />
                <input value={flow.api.systemName} onChange={(event) => setApiField("systemName", event.target.value)} placeholder="System name" />
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
                  Upload and Detect Columns
                </button>
                <button type="button" className="secondary-command-button" onClick={handleMockCsvSelect}>Use Demo CSV</button>
                <span>{flow.csvFileName ? `${flow.csvFileName} (${flow.detectedColumns.length} columns detected)` : "No file selected yet."}</span>
              </div>
            )}
            {flow.dataSource === "Demo Mode" && (
              <div className="onboarding-inline">
                <span>Demo telemetry package will be used for setup and baseline.</span>
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
            <h2>Signal Mapping</h2>
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
              <button type="button" className="command-button" onClick={() => {
                runConnectionTest();
                updateFlow({ step: 5 });
              }}>Run Connection Test</button>
            </div>
            {flow.connectionTest && (
              <ul className="onboarding-checklist">
                <li className={flow.connectionTest.sourceReachable ? "ok" : "warn"}>Data source reachable</li>
                <li className={flow.connectionTest.telemetryReceived ? "ok" : "warn"}>Telemetry received</li>
                <li className={flow.connectionTest.timestampDetected ? "ok" : "warn"}>Timestamp detected</li>
                <li className={flow.connectionTest.requiredSignalsMapped ? "ok" : "warn"}>Required signals mapped</li>
                <li className={flow.connectionTest.sampleRateAcceptable ? "ok" : "warn"}>Sample rate acceptable</li>
              </ul>
            )}
          </div>
        )}

        {flow.step === 5 && (
          <div className="onboarding-section">
            <h2>Baseline Setup</h2>
            <div className="onboarding-choice-grid">
              {[
                { id: "historical-upload", label: "Upload Historical Baseline" },
                { id: "live-learning-window", label: "Use First Live Learning Window" },
                { id: "demo-baseline", label: "Use Demo Baseline" },
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
            <h2>Go Online</h2>
            <ul className="onboarding-summary">
              <li><span>System</span><strong>{flow.api.systemName || flow.systemType || "Unspecified system"}</strong></li>
              <li><span>Data source</span><strong>{flow.dataSource || "Not selected"}</strong></li>
              <li><span>Mapped signals</span><strong>{mappedCount}</strong></li>
              <li><span>Baseline</span><strong>{flow.baselineMode}</strong></li>
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
      </footer>
    </section>
  );
}
