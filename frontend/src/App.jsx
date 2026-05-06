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
  return (
    <section className="upload-layout">
      <div className="section-heading">
        <h2>Facility data ingestion</h2>
        <p>
          CSV ingestion will support historical facility data and sensor exports.
        </p>
      </div>

      <div className="upload-zone" aria-label="CSV ingestion placeholder">
        <strong>CSV upload area</strong>
        <span>
          Upload handling is not active yet. This space is reserved for facility
          exports, sensor readings, and controlled environment history.
        </span>
      </div>
    </section>
  );
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
