import { useEffect, useState } from "react";
import { API_BASE_URL } from "./config";
import "./styles.css";

const NAV_ITEMS = [
  {
    label: "Overview",
    eyebrow: "Facility",
    description: "Workspace status and current operating context.",
  },
  {
    label: "Facility Systems",
    eyebrow: "Systems",
    description: "Environmental and control systems in review scope.",
  },
  {
    label: "Data Upload",
    eyebrow: "Ingestion",
    description: "CSV intake, profiling, baseline review, and engine results.",
  },
  {
    label: "Reports",
    eyebrow: "Findings",
    description: "Session report output for growers and operators.",
  },
];

const FOCUS_AREAS = [
  {
    name: "HVAC",
    detail: "Temperature conditioning, runtime shifts, and room balancing.",
  },
  {
    name: "Humidity",
    detail: "Moisture control, dehumidification cycles, and room drift.",
  },
  {
    name: "Airflow",
    detail: "Circulation behavior, fan interaction, and movement continuity.",
  },
  {
    name: "Irrigation",
    detail: "Water events, timing windows, and environmental response context.",
  },
  {
    name: "Lighting",
    detail: "Photoperiod changes, response windows, and fixture-driven patterns.",
  },
  {
    name: "Sensor Network",
    detail: "Export quality, timestamp continuity, and channel coverage.",
  },
];

const FALLBACK_SYSTEMS = [
  {
    name: "HVAC",
    scope: "Temperature conditioning and equipment runtime behavior",
  },
  {
    name: "Humidity control",
    scope: "Dehumidification, humidification, and room moisture balance",
  },
  {
    name: "Airflow",
    scope: "Air movement patterns, circulation, and room exchange signals",
  },
  {
    name: "Irrigation",
    scope: "Irrigation events, timing, and environmental response context",
  },
  {
    name: "Lighting",
    scope: "Lighting schedules and environmental response windows",
  },
  {
    name: "Sensor network",
    scope: "Room sensors, facility exports, and historical readings",
  },
];

const REPORT_TEMPLATES = [
  {
    name: "Environmental Drift Summary",
    detail: "Session-level change review across uploaded environmental channels.",
  },
  {
    name: "System Coupling Review",
    detail: "Relationship shifts between paired facility signals and operating windows.",
  },
  {
    name: "Operator Action Report",
    detail: "Plain-language checks that can be matched against room and shift logs.",
  },
];

function App() {
  const [activePage, setActivePage] = useState("Overview");
  const [apiStatus, setApiStatus] = useState({
    state: "checking",
    label: "Checking API",
    detail: "Connecting to the Neraium API.",
  });
  const [systems, setSystems] = useState(FALLBACK_SYSTEMS);
  const [systemsState, setSystemsState] = useState("loading");
  const [latestUploadResult, setLatestUploadResult] = useState(null);

  useEffect(() => {
    let isActive = true;

    async function checkApiHealth() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/health`);
        if (!response.ok) {
          throw new Error(`Unexpected response: ${response.status}`);
        }

        const payload = await response.json();
        if (isActive) {
          setApiStatus({
            state: "online",
            label: "Backend online",
            detail: `${payload.service} reported ${payload.status}.`,
          });
        }
      } catch {
        if (isActive) {
          setApiStatus({
            state: "offline",
            label: "Backend unavailable",
            detail: "Start the backend service to activate the workspace.",
          });
        }
      }
    }

    checkApiHealth();

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    let isActive = true;

    async function loadFacilitySystems() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/facility/systems`);
        if (!response.ok) {
          throw new Error(`Unexpected response: ${response.status}`);
        }

        const payload = await response.json();
        if (isActive && Array.isArray(payload.systems)) {
          setSystems(payload.systems);
          setSystemsState("ready");
        }
      } catch {
        if (isActive) {
          setSystems(FALLBACK_SYSTEMS);
          setSystemsState("fallback");
        }
      }
    }

    loadFacilitySystems();

    return () => {
      isActive = false;
    };
  }, []);

  const activeItem = NAV_ITEMS.find((item) => item.label === activePage) ?? NAV_ITEMS[0];

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="sidebar-header">
          <div className="brand-mark" aria-hidden="true">
            N
          </div>
          <div className="brand-copy">
            <p className="brand-name">Neraium</p>
            <p className="brand-subtitle">Cultivation operations console</p>
          </div>
        </div>

        <div className="sidebar-section">
          <p className="sidebar-label">Workspace</p>
          <nav className="nav-list">
            {NAV_ITEMS.map((item) => (
              <button
                className={`nav-button ${activePage === item.label ? "nav-button--active" : ""}`}
                key={item.label}
                type="button"
                onClick={() => setActivePage(item.label)}
              >
                <span className="nav-button-label">{item.label}</span>
                <span className="nav-button-detail">{item.description}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-panel">
          <p className="sidebar-label">Current deployment path</p>
          <strong>Amplify frontend + ECS backend</strong>
          <span>Frontend API target is controlled by VITE_API_BASE_URL.</span>
        </div>

        <div className="sidebar-footer">
          <div className={`status-indicator status-indicator--${apiStatus.state}`} />
          <div>
            <p>{apiStatus.label}</p>
            <span>{formatEndpoint(API_BASE_URL)}</span>
          </div>
        </div>
      </aside>

      <div className="workspace-shell">
        <TopBar
          activeItem={activeItem}
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
        />

        <section className="workspace" aria-labelledby="page-title">
          {activePage === "Overview" && (
            <OverviewPage
              apiStatus={apiStatus}
              latestUploadResult={latestUploadResult}
              systems={systems}
              systemsState={systemsState}
            />
          )}
          {activePage === "Facility Systems" && (
            <FacilitySystemsPage systems={systems} systemsState={systemsState} />
          )}
          {activePage === "Data Upload" && (
            <DataUploadPage
              latestUploadResult={latestUploadResult}
              onUploadComplete={setLatestUploadResult}
            />
          )}
          {activePage === "Reports" && (
            <ReportsPage latestUploadResult={latestUploadResult} />
          )}
        </section>
      </div>
    </main>
  );
}

function TopBar({ activeItem, apiStatus, latestUploadResult }) {
  const readiness = latestUploadResult?.data_quality?.readiness;
  const analysisAvailable = Boolean(latestUploadResult?.engine_result);

  return (
    <header className="topbar">
      <div className="topbar-title">
        <p className="eyebrow">{activeItem.eyebrow}</p>
        <h1 id="page-title">{activeItem.label}</h1>
        <p>{activeItem.description}</p>
      </div>

      <div className="topbar-meta">
        <StatusPill label="Backend" value={apiStatus.label} tone={apiStatus.state} />
        <StatusPill
          label="Upload readiness"
          value={readiness ? formatReadiness(readiness) : "Awaiting data"}
          tone={readiness ?? "muted"}
        />
        <StatusPill
          label="Session analysis"
          value={analysisAvailable ? "Available" : "Not generated"}
          tone={analysisAvailable ? "online" : "muted"}
        />
      </div>
    </header>
  );
}

function OverviewPage({ apiStatus, latestUploadResult, systems, systemsState }) {
  const readiness = latestUploadResult?.data_quality?.readiness;
  const latestReport = latestUploadResult?.operator_report;
  const engineResult = latestUploadResult?.engine_result;
  const focusMetrics = [
    {
      label: "Backend connection",
      value: apiStatus.label,
      detail: apiStatus.detail,
      tone: apiStatus.state,
    },
    {
      label: "Upload readiness",
      value: readiness ? formatReadiness(readiness) : "Awaiting first upload",
      detail: readiness
        ? "Latest session dataset has been profiled for usability."
        : "No cultivation dataset has been reviewed in this session.",
      tone: readiness ?? "muted",
    },
    {
      label: "Latest analysis",
      value: engineResult ? formatEngineResult(engineResult.overall_result) : "No analysis yet",
      detail: engineResult
        ? "Engine output is available in the Data Upload and Reports sections."
        : "Analysis surfaces will populate after the first CSV validation pass.",
      tone: engineResult?.overall_result ?? "muted",
    },
    {
      label: "Operational coverage",
      value: `${systems.length} systems`,
      detail:
        systemsState === "ready"
          ? "Facility scope is loaded from the backend placeholder endpoint."
          : "Using current scaffold system coverage for workspace orientation.",
      tone: "muted",
    },
  ];

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">Operations console</p>
          <h2>Environmental drift review for controlled cultivation facilities</h2>
          <p>
            Neraium gives growers and facility operators a clear working surface for
            reviewing uploaded sensor exports, comparing baseline behavior, and
            turning raw facility data into practical operating checks.
          </p>
        </div>

        <div className="hero-side">
          <div className="hero-status">
            <span className={`inline-dot inline-dot--${apiStatus.state}`} />
            <div>
              <strong>{apiStatus.label}</strong>
              <p>{apiStatus.detail}</p>
            </div>
          </div>

          <div className="hero-note">
            <span>Session source</span>
            <strong>{latestUploadResult?.filename ?? "No active upload"}</strong>
            <p>
              {latestReport
                ? "The latest session report is available in the Reports workspace."
                : "Upload a cultivation sensor export to populate session findings."}
            </p>
          </div>
        </div>
      </section>

      <section className="metrics-grid" aria-label="Overview metrics">
        {focusMetrics.map((metric) => (
          <article className="metric-panel" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <p>{metric.detail}</p>
            <div className={`metric-tone metric-tone--${metric.tone}`} />
          </article>
        ))}
      </section>

      <section className="overview-layout">
        <div className="surface-panel">
          <SectionHeading
            title="Operational focus areas"
            description="Primary systems and datasets currently framed for cultivation review."
          />
          <div className="focus-list">
            {FOCUS_AREAS.map((area) => (
              <article className="focus-row" key={area.name}>
                <div>
                  <h3>{area.name}</h3>
                  <p>{area.detail}</p>
                </div>
                <span>In scope</span>
              </article>
            ))}
          </div>
        </div>

        <div className="stack-column">
          <div className="surface-panel">
            <SectionHeading
              title="Latest session snapshot"
              description="Immediate context from the most recent upload in this browser session."
            />
            {latestUploadResult ? (
              <div className="snapshot-list">
                <SnapshotItem label="File" value={latestUploadResult.filename} />
                <SnapshotItem
                  label="Time coverage"
                  value={
                    latestUploadResult.timestamp_profile?.first_timestamp &&
                    latestUploadResult.timestamp_profile?.last_timestamp
                      ? `${latestUploadResult.timestamp_profile.first_timestamp} to ${latestUploadResult.timestamp_profile.last_timestamp}`
                      : "Timestamp range not available"
                  }
                />
                <SnapshotItem
                  label="Readiness"
                  value={formatReadiness(latestUploadResult.data_quality.readiness)}
                />
                <SnapshotItem
                  label="Mapped columns"
                  value={`${latestUploadResult.cultivation_mapping.mapped_column_count} columns`}
                />
              </div>
            ) : (
              <EmptyPanel
                title="No session dataset"
                body="The command surface will summarize file coverage, readiness, and mapped cultivation categories after the first CSV validation pass."
              />
            )}
          </div>

          <div className="surface-panel">
            <SectionHeading
              title="Readiness checkpoints"
              description="What this workspace expects before a session becomes useful to operators."
            />
            <ul className="plain-list">
              <li>Consistent timestamps across historical cultivation exports.</li>
              <li>Numeric environmental channels such as temperature, humidity, or CO2.</li>
              <li>Clear column labels that map to facility systems and sensor sources.</li>
              <li>Enough rows to compare baseline and recent operating windows.</li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}

function FacilitySystemsPage({ systems, systemsState }) {
  return (
    <div className="page-stack">
      <section className="surface-panel">
        <SectionHeading
          title="Monitored facility systems"
          description="Current cultivation categories exposed to the frontend workspace. These remain placeholder records until facility-specific contracts are connected."
        />

        <div className="systems-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>System</th>
                <th>Current review scope</th>
                <th>Workspace source</th>
              </tr>
            </thead>
            <tbody>
              {systems.map((system) => (
                <tr key={system.name}>
                  <td>{system.name}</td>
                  <td>{system.scope}</td>
                  <td>
                    {systemsState === "ready"
                      ? "Backend placeholder endpoint"
                      : "Local fallback surface"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function DataUploadPage({ latestUploadResult, onUploadComplete }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);

  async function handleUpload(event) {
    event.preventDefault();
    if (!selectedFile) {
      setUploadError("Choose a CSV file exported from facility or sensor systems.");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    setUploadState("uploading");
    setUploadError("");
    setUploadResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/data/upload`, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.detail ?? "CSV upload could not be validated.");
      }

      setUploadResult(payload);
      onUploadComplete(payload);
      setUploadState("complete");
    } catch (error) {
      setUploadError(error.message);
      setUploadState("error");
    }
  }

  return (
    <div className="page-stack">
      <section className="upload-console">
        <div className="surface-panel surface-panel--accent">
          <SectionHeading
            title="Facility data ingestion"
            description="Upload CSV exports from cultivation sensors or facility systems to validate structure, profile numeric readings, compare an initial baseline window, and prepare a session report."
          />

          <form className="upload-form" onSubmit={handleUpload}>
            <label className="upload-field" htmlFor="csv-upload">
              <span className="upload-field-label">CSV sensor export</span>
              <span className="upload-field-text">
                Historical room exports, control system extracts, and sensor data can be reviewed here without permanent storage.
              </span>
            </label>

            <div className="upload-actions">
              <input
                accept=".csv,text/csv"
                id="csv-upload"
                type="file"
                onChange={(event) => {
                  setSelectedFile(event.target.files?.[0] ?? null);
                  setUploadError("");
                }}
              />
              <button
                className="primary-button"
                type="submit"
                disabled={uploadState === "uploading"}
              >
                {uploadState === "uploading" ? "Validating dataset" : "Validate CSV"}
              </button>
            </div>

            <div className="upload-meta">
              <p className="selected-file">
                {selectedFile ? selectedFile.name : "No file selected"}
              </p>
              <p className={`upload-state upload-state--${uploadState}`}>
                {uploadStateMessage(uploadState)}
              </p>
            </div>

            {uploadError && <p className="form-error">{uploadError}</p>}
          </form>
        </div>

        <div className="stack-column">
          <div className="surface-panel">
            <SectionHeading
              title="Expected source data"
              description="The current ingestion flow is tuned for structured cultivation exports."
            />
            <ul className="plain-list">
              <li>Timestamped historical sensor rows.</li>
              <li>Numeric channels for environment and equipment behavior.</li>
              <li>Consistent column naming across room or facility exports.</li>
              <li>Enough recent rows to compare baseline and current windows.</li>
            </ul>
          </div>

          <div className="surface-panel">
            <SectionHeading
              title="Current session state"
              description="The frontend keeps only the latest validated upload in browser state."
            />
            {uploadResult ? (
              <div className="snapshot-list">
                <SnapshotItem label="Latest file" value={uploadResult.filename} />
                <SnapshotItem
                  label="Rows processed"
                  value={`${uploadResult.row_count} rows`}
                />
                <SnapshotItem
                  label="Readiness"
                  value={formatReadiness(uploadResult.data_quality.readiness)}
                />
              </div>
            ) : (
              <EmptyPanel
                title="No validated upload"
                body="After a successful CSV validation pass, this area will summarize the active dataset for the current session."
              />
            )}
          </div>
        </div>
      </section>

      {uploadState === "uploading" && (
        <div className="surface-panel surface-panel--muted">
          <SectionHeading
            title="Processing upload"
            description="Neraium is validating the file structure, profiling numeric columns, and preparing review sections for this session."
          />
        </div>
      )}

      {!uploadResult && uploadState !== "uploading" && !uploadError && (
        <EmptyPanel
          title="Upload review workspace is empty"
          body="Validate a cultivation CSV export to populate data quality, baseline comparison, cultivation mapping, engine output, and the latest operator report."
        />
      )}

      {uploadResult && <UploadResult result={uploadResult} />}
    </div>
  );
}

function UploadResult({ result }) {
  const quality = result.data_quality;
  const timestampProfile = result.timestamp_profile;
  const baselineAnalysis = result.baseline_analysis;
  const cultivationMapping = result.cultivation_mapping;
  const engineResult = result.engine_result;

  return (
    <section className="upload-result" aria-label="CSV upload result">
      {quality && (
        <div className={`status-banner status-banner--${quality.readiness}`}>
          <div>
            <span>Upload readiness</span>
            <strong>{formatReadiness(quality.readiness)}</strong>
          </div>
          <p>
            This review checks timestamp continuity, numeric channel coverage, and
            baseline comparison readiness for the uploaded cultivation export.
          </p>
        </div>
      )}

      <div className="result-summary">
        <SummaryMetric label="File" value={result.filename} />
        <SummaryMetric label="Rows" value={result.row_count} />
        <SummaryMetric label="Columns" value={result.column_count} />
        <SummaryMetric
          label="Timestamp column"
          value={result.detected_timestamp_column ?? "Not detected"}
        />
        <SummaryMetric
          label="Numeric channels"
          value={quality?.numeric_column_count ?? result.numeric_profiles?.length ?? 0}
        />
      </div>

      <div className="overview-layout">
        <div className="surface-panel">
          <SectionHeading
            title="Data quality summary"
            description="Usability checks for row coverage, numeric channels, and time context."
          />
          <div className="stats-grid stats-grid--compact">
            <SummaryMetric label="Rows" value={quality.row_count} />
            <SummaryMetric label="Columns" value={quality.column_count} />
            <SummaryMetric label="Numeric columns" value={quality.numeric_column_count} />
            <SummaryMetric
              label="Timestamp detected"
              value={quality.timestamp_detected ? "Yes" : "No"}
            />
          </div>
        </div>

        {timestampProfile && (
          <div className="surface-panel">
            <SectionHeading
              title="Time coverage"
              description="Detected timestamp range and approximate sampling interval."
            />
            <div className="stats-grid stats-grid--compact">
              <SummaryMetric
                label="First timestamp"
                value={timestampProfile.first_timestamp ?? "Not available"}
              />
              <SummaryMetric
                label="Last timestamp"
                value={timestampProfile.last_timestamp ?? "Not available"}
              />
              <SummaryMetric
                label="Sample interval"
                value={timestampProfile.estimated_sample_interval ?? "Not available"}
              />
            </div>
          </div>
        )}
      </div>

      {result.numeric_profiles?.length > 0 && (
        <div className="surface-panel">
          <SectionHeading
            title="Numeric profiles"
            description="Per-column scan of value ranges, missing coverage, and variability."
          />
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Min</th>
                  <th>Max</th>
                  <th>Average</th>
                  <th>Missing</th>
                  <th>Variability</th>
                </tr>
              </thead>
              <tbody>
                {result.numeric_profiles.map((profile) => (
                  <tr key={profile.column}>
                    <td>{profile.column}</td>
                    <td>{profile.min}</td>
                    <td>{profile.max}</td>
                    <td>{profile.average}</td>
                    <td>
                      {profile.missing_count} ({profile.missing_percent}%)
                    </td>
                    <td>
                      <span className={`tone-pill tone-pill--${profile.variability}`}>
                        {profile.variability}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {baselineAnalysis && (
        <div className="surface-panel">
          <SectionHeading
            title="Baseline comparison"
            description="Descriptive comparison between the first and most recent operating windows in the uploaded file."
          />

          <div className={`status-banner status-banner--${baselineAnalysis.overall_assessment}`}>
            <div>
              <span>Overall assessment</span>
              <strong>{formatAssessment(baselineAnalysis.overall_assessment)}</strong>
            </div>
            <p>
              The current baseline review uses the first 20% of rows as a baseline
              window and the last 20% as the recent comparison window.
            </p>
          </div>

          <div className="stats-grid stats-grid--compact">
            <SummaryMetric label="Baseline rows" value={baselineAnalysis.baseline_window_rows} />
            <SummaryMetric label="Recent rows" value={baselineAnalysis.recent_window_rows} />
            <SummaryMetric label="Columns analyzed" value={baselineAnalysis.columns_analyzed} />
          </div>

          {baselineAnalysis.column_drift.length > 0 && (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Baseline avg</th>
                    <th>Recent avg</th>
                    <th>Change</th>
                    <th>Percent</th>
                    <th>Direction</th>
                    <th>Review flag</th>
                  </tr>
                </thead>
                <tbody>
                  {baselineAnalysis.column_drift.map((drift) => (
                    <tr key={drift.column}>
                      <td>{drift.column}</td>
                      <td>{drift.baseline_average}</td>
                      <td>{drift.recent_average}</td>
                      <td>{drift.absolute_change}</td>
                      <td>
                        {drift.percent_change === null
                          ? "Not available"
                          : `${drift.percent_change}%`}
                      </td>
                      <td>{drift.direction}</td>
                      <td>
                        <span className={`tone-pill tone-pill--${drift.drift_flag}`}>
                          {drift.drift_flag}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {baselineAnalysis.warnings.length > 0 && (
            <MessageList title="Baseline notes" items={baselineAnalysis.warnings} />
          )}
        </div>
      )}

      {cultivationMapping && <CultivationMapping mapping={cultivationMapping} />}
      {engineResult && <EngineResult result={engineResult} />}
      {result.operator_report && <OperatorReport report={result.operator_report} />}

      <div className="overview-layout">
        <div className="surface-panel">
          <SectionHeading
            title="Columns detected"
            description="Uploaded CSV headers available to the current session."
          />
          <div className="chip-list">
            {result.columns.map((column) => (
              <span key={column}>{column || "Unnamed column"}</span>
            ))}
          </div>
        </div>

        <div className="surface-panel">
          <SectionHeading
            title="Preview rows"
            description="First parsed rows from the uploaded dataset."
          />
          {result.preview_rows.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    {result.columns.map((column) => (
                      <th key={column}>{column || "Unnamed"}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.preview_rows.map((row, rowIndex) => (
                    <tr key={`${result.filename}-${rowIndex}`}>
                      {result.columns.map((column) => (
                        <td key={`${column}-${rowIndex}`}>{row[column]}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyPanel
              title="No preview rows available"
              body="The file headers were read, but no data rows were available for preview."
            />
          )}
        </div>
      </div>

      {result.warnings.length > 0 && (
        <MessageList title="Upload warnings" items={result.warnings} />
      )}
    </section>
  );
}

function EngineResult({ result }) {
  const systemEvidence = result.system_evidence;
  const persistenceAssessment = result.persistence_assessment;
  const changedCategories = systemEvidence?.categories_showing_meaningful_change ?? 0;
  const changedSignals = systemEvidence?.numeric_signals_showing_meaningful_change ?? 0;
  const corroborationLevel = systemEvidence?.corroboration_level ?? "limited";

  return (
    <section className="surface-panel surface-panel--report" aria-label="Engine result">
      <SectionHeading
        title="Neraium SII v1"
        description="Deterministic system behavior review for the currently uploaded cultivation dataset."
      />

      <div className={`status-banner status-banner--${result.overall_result}`}>
        <div>
          <span>Engine result</span>
          <strong>{formatEngineResult(result.overall_result)}</strong>
        </div>
        <p>{result.summary}</p>
      </div>

      <div className="stats-grid">
        <SummaryMetric label="Engine version" value={result.engine_version} />
        <SummaryMetric label="Signals" value={result.signals.length} />
        <SummaryMetric label="Evidence items" value={result.evidence.length} />
        <SummaryMetric label="Corroboration" value={formatShortLabel(corroborationLevel)} />
        <SummaryMetric label="Changed categories" value={changedCategories} />
        <SummaryMetric label="Changed signals" value={changedSignals} />
        <SummaryMetric
          label="Persistence"
          value={formatShortLabel(persistenceAssessment?.status ?? "limited")}
        />
        <SummaryMetric label="Audit entries" value={result.audit_trace.length} />
      </div>

      {systemEvidence && <SystemEvidence evidence={systemEvidence} />}
      {persistenceAssessment && <PersistenceAssessment assessment={persistenceAssessment} />}
      <SplitMessageGrid
        leftTitle="Signals"
        leftItems={result.signals.map((signal) => signal.message)}
        leftEmpty="No engine signals were recorded for this dataset."
        rightTitle="Recommended checks"
        rightItems={result.recommended_checks}
        rightEmpty="No additional operator checks were added for this pass."
      />
      <SplitMessageGrid
        leftTitle="Limitations"
        leftItems={result.limitations}
        leftEmpty="No additional limitations were recorded."
        rightTitle="Audit trace"
        rightItems={result.audit_trace}
        rightEmpty="No audit entries were recorded."
      />
    </section>
  );
}

function SystemEvidence({ evidence }) {
  const categoriesWithEvidence = Object.entries(evidence.categories).filter(
    ([, category]) => category.signals.length > 0 || category.evidence.length > 0,
  );

  return (
    <div className="result-section">
      <SectionHeading
        title="System evidence"
        description="Grouped evidence by cultivation category for this uploaded dataset."
      />
      {categoriesWithEvidence.length > 0 ? (
        <div className="mapping-grid">
          {categoriesWithEvidence.map(([category, categoryEvidence]) => (
            <article className="mapping-card" key={category}>
              <h4>{category}</h4>
              {categoryEvidence.columns.length > 0 && (
                <div className="chip-list">
                  {categoryEvidence.columns.map((column) => (
                    <span key={`${category}-${column}`}>{column}</span>
                  ))}
                </div>
              )}
              {categoryEvidence.signals.length > 0 && (
                <ul className="plain-list plain-list--compact">
                  {categoryEvidence.signals.map((signal) => (
                    <li key={`${category}-${signal.type}-${signal.message}`}>
                      {signal.message}
                    </li>
                  ))}
                </ul>
              )}
              {categoryEvidence.signals.length === 0 && categoryEvidence.evidence.length > 0 && (
                <ul className="plain-list plain-list--compact">
                  {categoryEvidence.evidence.map((item) => (
                    <li key={`${category}-${formatEvidenceKey(item)}`}>
                      {formatEvidenceItem(item)}
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      ) : (
        <EmptyPanel
          title="No grouped system evidence"
          body="No cultivation categories showed meaningful change in this uploaded review."
        />
      )}
    </div>
  );
}

function PersistenceAssessment({ assessment }) {
  return (
    <div className="result-section">
      <SectionHeading
        title="Persistence assessment"
        description="Review of whether recent-window movement remains consistent across the recent rows."
      />

      <div className="stats-grid stats-grid--compact">
        <SummaryMetric label="Status" value={formatShortLabel(assessment.status)} />
        <SummaryMetric label="Columns assessed" value={assessment.columns_assessed} />
        <SummaryMetric label="Persistent columns" value={assessment.persistent_columns.length} />
      </div>

      {assessment.details.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Column</th>
                <th>Direction</th>
                <th>Recent rows checked</th>
                <th>Supporting rows</th>
                <th>Support</th>
                <th>Persistent</th>
              </tr>
            </thead>
            <tbody>
              {assessment.details.map((detail) => (
                <tr key={detail.column}>
                  <td>{detail.column}</td>
                  <td>{detail.direction}</td>
                  <td>{detail.recent_values_checked}</td>
                  <td>{detail.supporting_recent_rows}</td>
                  <td>{detail.support_percent}%</td>
                  <td>{detail.persistent ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {assessment.limitations.length > 0 && (
        <MessageList title="Persistence notes" items={assessment.limitations} />
      )}
    </div>
  );
}

function CultivationMapping({ mapping }) {
  const categoryEntries = Object.entries(mapping.categories);

  return (
    <section className="surface-panel">
      <SectionHeading
        title="Cultivation mapping"
        description="Deterministic keyword mapping of uploaded columns into facility system categories."
      />

      <div className="stats-grid stats-grid--compact">
        <SummaryMetric label="Mapped columns" value={mapping.mapped_column_count} />
        <SummaryMetric label="Unknown columns" value={mapping.unknown_column_count} />
        <SummaryMetric label="Coverage" value={`${mapping.coverage_percent}%`} />
      </div>

      <div className="mapping-grid">
        {categoryEntries.map(([category, columns]) => (
          <article className="mapping-card" key={category}>
            <h4>{category}</h4>
            {columns.length > 0 ? (
              <div className="chip-list">
                {columns.map((column) => (
                  <span key={`${category}-${column}`}>{column}</span>
                ))}
              </div>
            ) : (
              <p className="empty-note">No mapped columns.</p>
            )}
          </article>
        ))}
      </div>

      {mapping.warnings.length > 0 && (
        <MessageList title="Mapping notes" items={mapping.warnings} />
      )}
    </section>
  );
}

function OperatorReport({ report }) {
  return (
    <section className="surface-panel surface-panel--report" aria-label="Operator report">
      <div className="report-summary">
        <div>
          <p className="eyebrow">Latest operator report</p>
          <h2>{report.title}</h2>
          <p>{report.summary}</p>
        </div>
        <div className="report-meta">
          <SummaryMetric label="Readiness" value={formatReadiness(report.data_readiness)} />
          <SummaryMetric
            label="Timestamp column"
            value={report.time_coverage.detected_timestamp_column ?? "Not detected"}
          />
          <SummaryMetric
            label="Sample interval"
            value={report.time_coverage.estimated_sample_interval ?? "Not available"}
          />
        </div>
      </div>

      <div className="report-columns">
        <ReportSection
          title="Observations"
          items={report.key_observations}
          emptyText="No observations were generated for this upload."
        />
        <ReportSection
          title="Operator checks"
          items={report.recommended_operator_checks}
          emptyText="No additional operator checks were generated."
        />
      </div>

      <div className="report-columns">
        <ReportSection
          title="Columns requiring review"
          items={formatColumnsRequiringReview(report.columns_requiring_review)}
          emptyText="No columns were marked for review."
        />
        <ReportSection
          title="Limitations"
          items={report.limitations}
          emptyText="No additional report limitations were recorded."
        />
      </div>

      <div className="report-columns">
        <ReportSection
          title="Evidence sources"
          items={report.source_sections_used}
          emptyText="No evidence sources were listed."
        />
        <ReportSection
          title="Time coverage"
          items={formatTimeCoverage(report.time_coverage)}
          emptyText="No time coverage details were available."
        />
      </div>

      {report.warnings?.length > 0 && (
        <MessageList title="Report warnings" items={report.warnings} />
      )}
    </section>
  );
}

function ReportsPage({ latestUploadResult }) {
  const latestReport = latestUploadResult?.operator_report;

  return (
    <div className="page-stack">
      {latestReport ? (
        <OperatorReport report={latestReport} />
      ) : (
        <EmptyPanel
          title="No operator report in session"
          body="The Reports workspace will present the latest upload findings after a cultivation CSV file is validated in the Data Upload section."
        />
      )}

      <section className="surface-panel">
        <SectionHeading
          title="Report workspace"
          description="Session-driven outputs currently available to growers and facility operators."
        />
        <div className="report-template-list">
          {REPORT_TEMPLATES.map((report) => (
            <article className="report-template-row" key={report.name}>
              <div>
                <h3>{report.name}</h3>
                <p>{report.detail}</p>
              </div>
              <span>{latestReport ? "Available in session" : "Awaiting upload"}</span>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function SectionHeading({ title, description }) {
  return (
    <div className="section-heading">
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

function SummaryMetric({ label, value }) {
  return (
    <div className="summary-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ label, value, tone }) {
  return (
    <div className={`status-pill status-pill--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SnapshotItem({ label, value }) {
  return (
    <div className="snapshot-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyPanel({ title, body }) {
  return (
    <section className="empty-panel">
      <h3>{title}</h3>
      <p>{body}</p>
    </section>
  );
}

function MessageList({ title, items }) {
  return (
    <section className="surface-panel surface-panel--muted">
      <h3>{title}</h3>
      <ul className="plain-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function SplitMessageGrid({
  leftTitle,
  leftItems,
  leftEmpty,
  rightTitle,
  rightItems,
  rightEmpty,
}) {
  return (
    <div className="report-columns">
      <ReportSection title={leftTitle} items={leftItems} emptyText={leftEmpty} />
      <ReportSection title={rightTitle} items={rightItems} emptyText={rightEmpty} />
    </div>
  );
}

function ReportSection({ title, items, emptyText }) {
  return (
    <div className="report-section">
      <h3>{title}</h3>
      {items.length > 0 ? (
        <ul className="plain-list">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="empty-note">{emptyText}</p>
      )}
    </div>
  );
}

function uploadStateMessage(uploadState) {
  if (uploadState === "uploading") {
    return "Validation in progress";
  }
  if (uploadState === "complete") {
    return "Latest validation complete";
  }
  if (uploadState === "error") {
    return "Validation needs attention";
  }
  return "Awaiting file selection";
}

function formatReadiness(readiness) {
  if (readiness === "ready") {
    return "Ready";
  }
  if (readiness === "needs_review") {
    return "Needs review";
  }
  return "Not ready";
}

function formatAssessment(assessment) {
  return assessment === "normal" ? "Normal" : "Needs review";
}

function formatEngineResult(result) {
  if (result === "elevated") {
    return "Elevated";
  }
  if (result === "needs_review") {
    return "Needs review";
  }
  return "Normal";
}

function formatShortLabel(value) {
  return value.replaceAll("_", " ").replace(/^\w/, (character) => character.toUpperCase());
}

function formatEndpoint(endpoint) {
  return endpoint.replace("http://", "").replace("https://", "");
}

function formatEvidenceKey(item) {
  if (item.type === "column_drift") {
    return `${item.type}-${item.column}-${item.direction}-${item.drift_flag}`;
  }
  if (item.type === "relationship_change") {
    return `${item.type}-${item.columns.join("-")}-${item.change}`;
  }
  return JSON.stringify(item);
}

function formatEvidenceItem(item) {
  if (item.type === "column_drift") {
    return `${item.column} moved ${item.direction} from ${item.baseline_average} to ${item.recent_average} with a ${item.drift_flag} review flag.`;
  }
  if (item.type === "relationship_change") {
    return `${item.columns.join(" and ")} changed paired behavior by ${item.change}.`;
  }
  return "Evidence item recorded for this category.";
}

function formatColumnsRequiringReview(columnsRequiringReview) {
  return columnsRequiringReview.map(
    (item) => `${item.column}: ${item.reasons.join(" ")}`,
  );
}

function formatTimeCoverage(timeCoverage) {
  return [
    `Timestamp column: ${timeCoverage.detected_timestamp_column ?? "Not detected"}`,
    `First timestamp: ${timeCoverage.first_timestamp ?? "Not available"}`,
    `Last timestamp: ${timeCoverage.last_timestamp ?? "Not available"}`,
    `Estimated sample interval: ${timeCoverage.estimated_sample_interval ?? "Not available"}`,
  ];
}

export default App;
