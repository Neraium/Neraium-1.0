import { useEffect, useState } from "react";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

const NAV_ITEMS = [
  "Overview",
  "Facility Systems",
  "Data Upload",
  "Reports",
];

const OVERVIEW_CARDS = [
  {
    label: "Facility status",
    value: "Ready for facility data",
    detail: "Customer facility context will appear here as onboarding is configured.",
  },
  {
    label: "Environmental drift",
    value: "Baseline pending",
    detail: "Drift views will summarize changes across controlled environment data.",
  },
  {
    label: "Systems monitored",
    value: "6 focus areas",
    detail: "HVAC, humidity, airflow, irrigation, lighting, and sensor data.",
  },
  {
    label: "Latest report",
    value: "No reports yet",
    detail: "Reports will appear after facility data is connected and reviewed.",
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

const REPORTS = [
  "Environmental Drift Summary",
  "System Coupling Review",
  "Operator Action Report",
];

function App() {
  const [activePage, setActivePage] = useState("Overview");
  const [apiStatus, setApiStatus] = useState({
    state: "checking",
    label: "Checking API",
    detail: "Connecting to the Neraium API.",
  });
  const [systems, setSystems] = useState(FALLBACK_SYSTEMS);

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
            label: "API online",
            detail: `${payload.service} reported ${payload.status}.`,
          });
        }
      } catch {
        if (isActive) {
          setApiStatus({
            state: "offline",
            label: "API unavailable",
            detail: "Start the backend service to connect this app shell.",
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
        }
      } catch {
        if (isActive) {
          setSystems(FALLBACK_SYSTEMS);
        }
      }
    }

    loadFacilitySystems();

    return () => {
      isActive = false;
    };
  }, []);

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <span className="brand-mark">N</span>
          <div>
            <p className="brand-name">Neraium</p>
            <p className="brand-subtitle">Cultivation operations</p>
          </div>
        </div>

        <nav className="nav-list">
          {NAV_ITEMS.map((item) => (
            <button
              className={`nav-button ${activePage === item ? "nav-button--active" : ""}`}
              key={item}
              type="button"
              onClick={() => setActivePage(item)}
            >
              {item}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className={`status-dot status-dot--${apiStatus.state}`} />
          <div>
            <p>{apiStatus.label}</p>
            <span>Backend {API_BASE_URL.replace("http://", "")}</span>
          </div>
        </div>
      </aside>

      <section className="workspace" aria-labelledby="page-title">
        <PageHeader activePage={activePage} />
        {activePage === "Overview" && <OverviewPage apiStatus={apiStatus} />}
        {activePage === "Facility Systems" && <FacilitySystemsPage systems={systems} />}
        {activePage === "Data Upload" && <DataUploadPage />}
        {activePage === "Reports" && <ReportsPage />}
      </section>
    </main>
  );
}

function PageHeader({ activePage }) {
  return (
    <header className="page-header">
      <p className="eyebrow">Neraium</p>
      <h1 id="page-title">{activePage}</h1>
      <p>
        Environmental drift intelligence for cannabis grow facilities and
        controlled environment operations.
      </p>
    </header>
  );
}

function OverviewPage({ apiStatus }) {
  return (
    <div className="page-stack">
      <section className="intro-band">
        <div>
          <h2>Environmental drift before visible crop stress</h2>
          <p>
            Neraium helps cannabis cultivation teams detect and explain
            environmental drift before it becomes visible crop stress.
          </p>
        </div>
        <div className="api-status" aria-live="polite">
          <span className={`status-dot status-dot--${apiStatus.state}`} />
          <div>
            <strong>{apiStatus.label}</strong>
            <span>{apiStatus.detail}</span>
          </div>
        </div>
      </section>

      <section className="metric-grid" aria-label="Facility overview">
        {OVERVIEW_CARDS.map((card) => (
          <article className="metric-card" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <p>{card.detail}</p>
          </article>
        ))}
      </section>
    </div>
  );
}

function FacilitySystemsPage({ systems }) {
  return (
    <section className="list-panel">
      <div className="section-heading">
        <h2>Monitored systems</h2>
        <p>
          Placeholder cultivation systems are hardcoded until facility data
          contracts are defined.
        </p>
      </div>

      <div className="system-list">
        {systems.map((system) => (
          <article className="system-row" key={system.name}>
            <div>
              <h3>{system.name}</h3>
              <p>{system.scope}</p>
            </div>
            <span>Placeholder</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function DataUploadPage() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(null);

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
      setUploadState("complete");
    } catch (error) {
      setUploadError(error.message);
      setUploadState("error");
    }
  }

  return (
    <section className="upload-layout">
      <div className="section-heading">
        <h2>Facility data ingestion</h2>
        <p>
          Upload CSV exports from cultivation sensors or facility systems to
          validate structure, profile numeric readings, compare an initial
          baseline window, and preview the first rows. Files are parsed for this
          session and are not stored permanently.
        </p>
      </div>

      <form className="upload-zone" onSubmit={handleUpload}>
        <label htmlFor="csv-upload">
          <strong>CSV sensor export</strong>
          <span>
            CSV ingestion supports historical facility data and sensor exports
            for controlled environment review.
          </span>
        </label>
        <input
          accept=".csv,text/csv"
          id="csv-upload"
          type="file"
          onChange={(event) => {
            setSelectedFile(event.target.files?.[0] ?? null);
            setUploadError("");
          }}
        />
        <button type="submit" disabled={uploadState === "uploading"}>
          {uploadState === "uploading" ? "Uploading" : "Validate CSV"}
        </button>
        {selectedFile && <p className="selected-file">{selectedFile.name}</p>}
        {uploadError && <p className="form-error">{uploadError}</p>}
      </form>

      {uploadResult && <UploadResult result={uploadResult} />}
    </section>
  );
}

function UploadResult({ result }) {
  const quality = result.data_quality;
  const timestampProfile = result.timestamp_profile;
  const baselineAnalysis = result.baseline_analysis;

  return (
    <section className="upload-result" aria-label="CSV upload result">
      {quality && (
        <div className={`readiness-banner readiness-banner--${quality.readiness}`}>
          <span>Readiness</span>
          <strong>{formatReadiness(quality.readiness)}</strong>
          <p>
            Lightweight data profiling checks whether this cultivation sensor
            export has usable rows, numeric readings, and timestamp context.
          </p>
        </div>
      )}

      <div className="result-summary">
        <div>
          <span>File</span>
          <strong>{result.filename}</strong>
        </div>
        <div>
          <span>Rows</span>
          <strong>{result.row_count}</strong>
        </div>
        <div>
          <span>Columns</span>
          <strong>{result.column_count}</strong>
        </div>
        <div>
          <span>Timestamp</span>
          <strong>{result.detected_timestamp_column ?? "Not detected"}</strong>
        </div>
        <div>
          <span>Numeric columns</span>
          <strong>{quality?.numeric_column_count ?? result.numeric_profiles?.length ?? 0}</strong>
        </div>
      </div>

      {quality && (
        <div className="result-section">
          <h3>Data Quality Summary</h3>
          <div className="quality-grid">
            <div>
              <span>Rows</span>
              <strong>{quality.row_count}</strong>
            </div>
            <div>
              <span>Columns</span>
              <strong>{quality.column_count}</strong>
            </div>
            <div>
              <span>Numeric columns</span>
              <strong>{quality.numeric_column_count}</strong>
            </div>
            <div>
              <span>Timestamp detected</span>
              <strong>{quality.timestamp_detected ? "Yes" : "No"}</strong>
            </div>
          </div>
        </div>
      )}

      {timestampProfile && (
        <div className="result-section">
          <h3>Time range</h3>
          <div className="time-grid">
            <div>
              <span>First timestamp</span>
              <strong>{timestampProfile.first_timestamp ?? "Not available"}</strong>
            </div>
            <div>
              <span>Last timestamp</span>
              <strong>{timestampProfile.last_timestamp ?? "Not available"}</strong>
            </div>
            <div>
              <span>Estimated sample interval</span>
              <strong>{timestampProfile.estimated_sample_interval ?? "Not available"}</strong>
            </div>
          </div>
        </div>
      )}

      {result.numeric_profiles?.length > 0 && (
        <div className="result-section">
          <h3>Numeric column profile</h3>
          <div className="profile-table-wrap">
            <table className="profile-table">
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
                      <span className={`flag flag--${profile.variability}`}>
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
        <div className="result-section">
          <h3>Baseline Comparison</h3>
          <div className={`assessment-banner assessment-banner--${baselineAnalysis.overall_assessment}`}>
            <span>Overall assessment</span>
            <strong>{formatAssessment(baselineAnalysis.overall_assessment)}</strong>
            <p>
              Uses the first 20% of rows as a simple baseline window and the
              last 20% as the recent window for descriptive comparison.
            </p>
          </div>

          <div className="quality-grid">
            <div>
              <span>Baseline rows</span>
              <strong>{baselineAnalysis.baseline_window_rows}</strong>
            </div>
            <div>
              <span>Recent rows</span>
              <strong>{baselineAnalysis.recent_window_rows}</strong>
            </div>
            <div>
              <span>Columns analyzed</span>
              <strong>{baselineAnalysis.columns_analyzed}</strong>
            </div>
          </div>

          {baselineAnalysis.column_drift.length > 0 && (
            <div className="profile-table-wrap">
              <table className="profile-table">
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Baseline avg</th>
                    <th>Recent avg</th>
                    <th>Change</th>
                    <th>Percent</th>
                    <th>Direction</th>
                    <th>Flag</th>
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
                        <span className={`flag flag--${drift.drift_flag}`}>
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
            <ul className="warning-list">
              {baselineAnalysis.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="result-section">
        <h3>Columns</h3>
        <div className="column-list">
          {result.columns.map((column) => (
            <span key={column}>{column || "Unnamed column"}</span>
          ))}
        </div>
      </div>

      <div className="result-section">
        <h3>Preview rows</h3>
        {result.preview_rows.length > 0 ? (
          <div className="preview-table-wrap">
            <table className="preview-table">
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
          <p className="empty-note">No preview rows were found in this CSV.</p>
        )}
      </div>

      {result.warnings.length > 0 && (
        <div className="result-section">
          <h3>Warnings</h3>
          <ul className="warning-list">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
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

function ReportsPage() {
  return (
    <section className="list-panel">
      <div className="section-heading">
        <h2>Reports</h2>
        <p>
          Report generation is not active yet. These report types define the
          first customer-facing review structure.
        </p>
      </div>

      <div className="report-list">
        {REPORTS.map((report) => (
          <article className="report-row" key={report}>
            <div>
              <h3>{report}</h3>
              <p>Report template placeholder</p>
            </div>
            <button type="button" disabled>
              Pending
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}

export default App;
