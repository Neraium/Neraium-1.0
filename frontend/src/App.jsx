import { useEffect, useState } from "react";
import { API_BASE_URL } from "./config";
import "./styles.css";

const NAV_ITEMS = [
  {
    label: "Overview",
    eyebrow: "Monitoring",
    description: "Facility telemetry, drift monitoring, and current operational context.",
  },
  {
    label: "Facility Systems",
    eyebrow: "Systems",
    description: "Environmental systems, room review surfaces, and control scope.",
  },
  {
    label: "Data Upload",
    eyebrow: "Ingest",
    description: "Operational batch intake, profiling, baseline review, and evidence output.",
  },
  {
    label: "Reports",
    eyebrow: "Findings",
    description: "Operator findings, evidence sources, and room-level review notes.",
  },
];

const FALLBACK_SYSTEMS = [
  {
    name: "HVAC",
    scope: "Temperature conditioning, equipment runtime behavior, and room balancing.",
  },
  {
    name: "Humidity control",
    scope: "Dehumidification, humidification, and room moisture balance.",
  },
  {
    name: "Airflow",
    scope: "Air movement patterns, circulation behavior, and room exchange signals.",
  },
  {
    name: "Irrigation",
    scope: "Irrigation events, timing windows, and environmental response context.",
  },
  {
    name: "Lighting",
    scope: "Lighting schedules, photoperiod windows, and fixture response context.",
  },
  {
    name: "Sensor network",
    scope: "Room sensors, gateway exports, and historical telemetry continuity.",
  },
];

const FACILITY_MAP_PLACEHOLDERS = [
  "North flower zone",
  "South flower zone",
  "Propagation zone",
  "Dry and cure support",
];

const REPORT_TEMPLATES = [
  "Environmental Drift Summary",
  "System Coupling Review",
  "Operator Action Report",
];

const TELEMETRY_CATEGORIES = [
  "temperature",
  "humidity",
  "CO2",
  "HVAC",
  "airflow",
  "irrigation",
  "lighting",
  "sensor network",
];

function App() {
  const [activePage, setActivePage] = useState("Overview");
  const [apiStatus, setApiStatus] = useState({
    state: "checking",
    label: "Checking backend",
    detail: "Establishing API telemetry link.",
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
            detail: "Start the backend service to activate monitoring surfaces.",
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
  const roomContext = deriveRoomContext(latestUploadResult);
  const timeCoverage = deriveTimeCoverage(latestUploadResult);
  const findingsCount = buildFindingsFeed(latestUploadResult).length;

  return (
    <main className="mission-app">
      <aside className="mission-sidebar" aria-label="Primary navigation">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            N
          </div>
          <div>
            <p className="brand-name">Neraium</p>
            <p className="brand-subtitle">Cultivation infrastructure intelligence</p>
          </div>
        </div>

        <div className="sidebar-block">
          <p className="sidebar-label">Workspace</p>
          <nav className="nav-stack">
            {NAV_ITEMS.map((item) => (
              <button
                className={`nav-tile ${activePage === item.label ? "nav-tile--active" : ""}`}
                key={item.label}
                type="button"
                onClick={() => setActivePage(item.label)}
              >
                <span className="nav-tile-label">{item.label}</span>
                <span className="nav-tile-detail">{item.description}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-block sidebar-block--terminal">
          <p className="sidebar-label">Persistent telemetry</p>
          <TelemetryLine label="API target" value={formatEndpoint(API_BASE_URL)} />
          <TelemetryLine label="Room context" value={roomContext.primary} />
          <TelemetryLine label="Time coverage" value={timeCoverage.summary} />
          <TelemetryLine
            label="Findings in queue"
            value={findingsCount > 0 ? `${findingsCount} active` : "Awaiting batch"}
          />
        </div>

        <div className="sidebar-footer">
          <div className={`system-dot system-dot--${apiStatus.state}`} />
          <div>
            <p>{apiStatus.label}</p>
            <span>{apiStatus.detail}</span>
          </div>
        </div>
      </aside>

      <div className="mission-main">
        <TopTelemetryBar
          activeItem={activeItem}
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          timeCoverage={timeCoverage}
        />

        <section className="mission-workspace" aria-labelledby="page-title">
          {activePage === "Overview" && (
            <OverviewPage
              apiStatus={apiStatus}
              latestUploadResult={latestUploadResult}
              systems={systems}
              systemsState={systemsState}
              roomContext={roomContext}
            />
          )}
          {activePage === "Facility Systems" && (
            <FacilitySystemsPage
              systems={systems}
              systemsState={systemsState}
              latestUploadResult={latestUploadResult}
              roomContext={roomContext}
            />
          )}
          {activePage === "Data Upload" && (
            <DataUploadPage
              latestUploadResult={latestUploadResult}
              onUploadComplete={setLatestUploadResult}
              roomContext={roomContext}
            />
          )}
          {activePage === "Reports" && (
            <ReportsPage
              latestUploadResult={latestUploadResult}
              roomContext={roomContext}
            />
          )}
        </section>
      </div>
    </main>
  );
}

function TopTelemetryBar({
  activeItem,
  apiStatus,
  latestUploadResult,
  roomContext,
  timeCoverage,
}) {
  const readiness = latestUploadResult?.data_quality?.readiness;
  const analysisResult = latestUploadResult?.engine_result?.overall_result;

  return (
    <header className="top-telemetry">
      <div className="top-telemetry__title">
        <p className="eyebrow">{activeItem.eyebrow}</p>
        <h1 id="page-title">{activeItem.label}</h1>
        <p>{activeItem.description}</p>
      </div>

      <div className="telemetry-strip">
        <TelemetryBadge label="Backend" value={apiStatus.label} tone={apiStatus.state} />
        <TelemetryBadge label="Room or zone" value={roomContext.primary} tone="muted" />
        <TelemetryBadge
          label="Upload batch"
          value={latestUploadResult?.filename ?? "Awaiting ingest"}
          tone={latestUploadResult ? "online" : "muted"}
        />
        <TelemetryBadge
          label="Readiness"
          value={readiness ? formatReadiness(readiness) : "No active batch"}
          tone={readiness ?? "muted"}
        />
        <TelemetryBadge
          label="Time coverage"
          value={timeCoverage.summary}
          tone={timeCoverage.hasCoverage ? "online" : "muted"}
        />
        <TelemetryBadge
          label="Operational result"
          value={analysisResult ? formatEngineResult(analysisResult) : "Not generated"}
          tone={analysisResult ?? "muted"}
        />
      </div>
    </header>
  );
}

function OverviewPage({ apiStatus, latestUploadResult, systems, systemsState, roomContext }) {
  const telemetryCards = buildTelemetryCards(latestUploadResult);
  const findingsFeed = buildFindingsFeed(latestUploadResult);
  const alerts = buildAlertItems(latestUploadResult, apiStatus);
  const driftRows = latestUploadResult?.baseline_analysis?.column_drift ?? [];
  const relationshipRows = buildRelationshipRows(latestUploadResult);
  const timeline = buildOperationalTimeline(latestUploadResult, apiStatus, roomContext);
  const facilityMapZones = buildFacilityMapZones(roomContext);
  const evidenceConsole = buildEvidenceConsole(latestUploadResult);

  return (
    <div className="workspace-grid workspace-grid--overview">
      <Panel
        title="Operational timeline"
        subtitle="Timestamped facility and ingest events for the current session."
        className="span-7"
      >
        <TimelineFeed items={timeline} />
      </Panel>

      <Panel
        title="Active findings feed"
        subtitle="Signals, observations, and review items extracted from the latest batch."
        className="span-5"
      >
        <FindingsFeed items={findingsFeed} emptyText="Awaiting uploaded telemetry batch." />
      </Panel>

      <Panel
        title="Facility map placeholder"
        subtitle="Room and zone review surface grounded in current upload context."
        className="span-4"
      >
        <FacilityMapPlaceholder zones={facilityMapZones} />
      </Panel>

      <Panel
        title="Room and zone state"
        subtitle="Operational placeholders for room-level review context."
        className="span-4"
      >
        <RoomStateGrid roomContext={roomContext} />
      </Panel>

      <Panel
        title="Environmental telemetry"
        subtitle="Current telemetry channels mapped from uploaded cultivation data."
        className="span-4"
      >
        <TelemetryCardGrid cards={telemetryCards} />
      </Panel>

      <Panel
        title="Drift monitoring"
        subtitle="Baseline versus recent movement across environmental channels."
        className="span-6"
      >
        <DriftMonitor rows={driftRows} />
      </Panel>

      <Panel
        title="Relational stability"
        subtitle="Paired signal behavior and coupling shifts across the active batch."
        className="span-3"
      >
        <RelationshipMonitor rows={relationshipRows} />
      </Panel>

      <Panel
        title="Operator alerts"
        subtitle="Warnings, limitations, and operational checks requiring review."
        className="span-3"
      >
        <AlertList alerts={alerts} />
      </Panel>

      <Panel
        title="Ingest activity"
        subtitle="Batch intake, readiness state, and source coverage progression."
        className="span-6"
      >
        <IngestConsole result={latestUploadResult} roomContext={roomContext} />
      </Panel>

      <Panel
        title="Evidence console"
        subtitle="Evidence-first record of sources, audit trace, and review columns."
        className="span-6"
      >
        <EvidenceConsole lines={evidenceConsole} />
      </Panel>

      <Panel
        title="Facility systems"
        subtitle="Current environmental systems and backend source state."
        className="span-12"
      >
        <SystemsMatrix
          systems={systems}
          systemsState={systemsState}
          roomContext={roomContext}
        />
      </Panel>
    </div>
  );
}

function FacilitySystemsPage({ systems, systemsState, latestUploadResult, roomContext }) {
  const telemetryCards = buildTelemetryCards(latestUploadResult);

  return (
    <div className="workspace-grid workspace-grid--systems">
      <Panel
        title="Systems matrix"
        subtitle="Operational scope across environmental control surfaces and review lanes."
        className="span-8"
      >
        <SystemsMatrix
          systems={systems}
          systemsState={systemsState}
          roomContext={roomContext}
        />
      </Panel>

      <Panel
        title="Telemetry coverage"
        subtitle="Mapped channel coverage across facility systems."
        className="span-4"
      >
        <TelemetryCardGrid cards={telemetryCards} />
      </Panel>

      <Panel
        title="Zone review context"
        subtitle="Room-level operational placeholders for premium cultivation facilities."
        className="span-12"
      >
        <ZoneContextTable roomContext={roomContext} />
      </Panel>
    </div>
  );
}

function DataUploadPage({ latestUploadResult, onUploadComplete, roomContext }) {
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

  const telemetryCards = buildTelemetryCards(uploadResult);
  const batchTimeline = buildOperationalTimeline(uploadResult, null, roomContext);

  return (
    <div className="workspace-grid workspace-grid--ingest">
      <Panel
        title="Operational batch intake"
        subtitle="CSV ingestion for room telemetry, facility controls, irrigation review, and evidence generation."
        className="span-7"
      >
        <form className="ingest-form" onSubmit={handleUpload}>
          <div className="ingest-copy">
            <span className="section-token">Batch source</span>
            <strong>Cultivation telemetry export</strong>
            <p>
              Upload historical room, zone, irrigation, HVAC, or sensor-network exports
              for deterministic profiling, baseline review, and operator findings.
            </p>
          </div>

          <div className="ingest-actions">
            <input
              accept=".csv,text/csv"
              id="csv-upload"
              type="file"
              onChange={(event) => {
                setSelectedFile(event.target.files?.[0] ?? null);
                setUploadError("");
              }}
            />
            <button className="command-button" type="submit" disabled={uploadState === "uploading"}>
              {uploadState === "uploading" ? "Validating batch" : "Validate batch"}
            </button>
          </div>

          <div className="ingest-status-row">
            <span>{selectedFile ? selectedFile.name : "No file selected"}</span>
            <span>{uploadStateMessage(uploadState)}</span>
          </div>

          {uploadError && <p className="form-error">{uploadError}</p>}
        </form>
      </Panel>

      <Panel
        title="Ingest activity"
        subtitle="Live batch progression, room context, and readiness steps."
        className="span-5"
      >
        <TimelineFeed items={batchTimeline} />
      </Panel>

      <Panel
        title="Environmental telemetry"
        subtitle="Channel coverage available from the active or latest batch."
        className="span-4"
      >
        <TelemetryCardGrid cards={telemetryCards} />
      </Panel>

      <Panel
        title="Expected source structure"
        subtitle="Current ingest assumptions for cultivation infrastructure exports."
        className="span-4"
      >
        <CompactList
          items={[
            "Timestamped room or zone telemetry rows.",
            "Environmental and equipment channels with numeric values.",
            "Consistent export labels across HVAC, irrigation, and sensor systems.",
            "Enough recent rows to compare baseline and active windows.",
          ]}
          emptyText="No source structure guidance available."
        />
      </Panel>

      <Panel
        title="Session batch state"
        subtitle="Current browser-session ingest context."
        className="span-4"
      >
        <SessionStatePanel result={uploadResult} roomContext={roomContext} />
      </Panel>

      {!uploadResult && uploadState !== "uploading" && !uploadError && (
        <Panel
          title="Awaiting operational batch"
          subtitle="The ingest workspace will populate after the first validated upload."
          className="span-12"
        >
          <EmptyState
            title="No active cultivation batch"
            body="Validate a CSV export to populate telemetry coverage, baseline drift, room context, operator findings, and evidence consoles."
          />
        </Panel>
      )}

      {uploadState === "uploading" && (
        <Panel
          title="Validation in progress"
          subtitle="Profiling telemetry structure, baseline windows, and operator evidence."
          className="span-12"
        >
          <EmptyState
            title="Processing uploaded telemetry"
            body="Neraium is preparing the batch for deterministic review across environmental channels and room-level findings."
          />
        </Panel>
      )}

      {uploadResult && (
        <UploadResult result={uploadResult} />
      )}
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
    <>
      <Panel
        title="Batch readiness"
        subtitle="Current usability state for the uploaded operational batch."
        className="span-12"
      >
        <StatusBanner
          title={formatReadiness(quality.readiness)}
          subtitle="Timestamp continuity, sensor coverage, and baseline-comparison readiness for the current cultivation export."
          tone={quality.readiness}
        />
        <MetricRow
          metrics={[
            { label: "Batch", value: result.filename },
            { label: "Rows", value: result.row_count },
            { label: "Columns", value: result.column_count },
            { label: "Timestamp column", value: result.detected_timestamp_column ?? "Not detected" },
            {
              label: "Sensor channels",
              value: quality?.numeric_column_count ?? result.numeric_profiles?.length ?? 0,
            },
          ]}
        />
      </Panel>

      <Panel
        title="Data quality"
        subtitle="Usability summary for row count, column coverage, and timestamp context."
        className="span-4"
      >
        <MetricGrid
          metrics={[
            { label: "Rows", value: quality.row_count },
            { label: "Columns", value: quality.column_count },
            { label: "Numeric columns", value: quality.numeric_column_count },
            { label: "Timestamp detected", value: quality.timestamp_detected ? "Yes" : "No" },
          ]}
        />
      </Panel>

      <Panel
        title="Time coverage"
        subtitle="Detected time range and estimated sample interval."
        className="span-4"
      >
        <MetricGrid
          metrics={[
            { label: "First timestamp", value: timestampProfile.first_timestamp ?? "Not available" },
            { label: "Last timestamp", value: timestampProfile.last_timestamp ?? "Not available" },
            {
              label: "Sample interval",
              value: timestampProfile.estimated_sample_interval ?? "Not available",
            },
          ]}
        />
      </Panel>

      <Panel
        title="Cultivation mapping"
        subtitle="Mapped systems and sensor coverage from uploaded columns."
        className="span-4"
      >
        <MetricGrid
          metrics={[
            { label: "Mapped columns", value: cultivationMapping.mapped_column_count },
            { label: "Unknown columns", value: cultivationMapping.unknown_column_count },
            { label: "Coverage", value: `${cultivationMapping.coverage_percent}%` },
          ]}
        />
      </Panel>

      <Panel
        title="Numeric profiles"
        subtitle="Per-channel ranges, averages, missing values, and variability."
        className="span-6"
      >
        <DataTable
          columns={["Column", "Min", "Max", "Average", "Missing", "Variability"]}
          rows={result.numeric_profiles.map((profile) => [
            profile.column,
            profile.min,
            profile.max,
            profile.average,
            `${profile.missing_count} (${profile.missing_percent}%)`,
            <span className={`status-chip status-chip--${profile.variability}`} key={profile.column}>
              {profile.variability}
            </span>,
          ])}
        />
      </Panel>

      <Panel
        title="Baseline drift"
        subtitle="First-window versus recent-window movement across telemetry channels."
        className="span-6"
      >
        <StatusBanner
          title={formatAssessment(baselineAnalysis.overall_assessment)}
          subtitle="The first 20% of rows define the baseline window and the last 20% define the active comparison window."
          tone={baselineAnalysis.overall_assessment}
        />
        <DriftMonitor rows={baselineAnalysis.column_drift} />
      </Panel>

      <Panel
        title="Mapped system categories"
        subtitle="Grouped cultivation categories and uploaded channel assignments."
        className="span-4"
      >
        <MappingGrid mapping={cultivationMapping} />
      </Panel>

      {engineResult && (
        <Panel
          title="Engine result"
          subtitle="Deterministic system behavior evidence for the uploaded batch."
          className="span-8"
        >
          <EngineResultPanel result={engineResult} />
        </Panel>
      )}

      {result.operator_report && (
        <Panel
          title="Operator findings report"
          subtitle="Plain-language findings, checks, limitations, and evidence sections."
          className="span-8"
        >
          <OperatorReportPanel report={result.operator_report} />
        </Panel>
      )}

      <Panel
        title="Preview rows"
        subtitle="First parsed rows from the current operational batch."
        className="span-4"
      >
        {result.preview_rows.length > 0 ? (
          <PreviewTable columns={result.columns} rows={result.preview_rows} />
        ) : (
          <EmptyState
            title="No preview rows available"
            body="The file headers were read, but no data rows were available for preview."
          />
        )}
      </Panel>

      <Panel
        title="Evidence console"
        subtitle="Warnings, audit trace, and batch review notes."
        className="span-12"
      >
        <EvidenceConsole lines={buildEvidenceConsole(result)} />
      </Panel>
    </>
  );
}

function ReportsPage({ latestUploadResult, roomContext }) {
  const latestReport = latestUploadResult?.operator_report;
  const findingsFeed = buildFindingsFeed(latestUploadResult);
  const evidenceConsole = buildEvidenceConsole(latestUploadResult);

  return (
    <div className="workspace-grid workspace-grid--reports">
      <Panel
        title="Operational findings"
        subtitle="Session-driven findings report for growers, environmental operators, and infrastructure teams."
        className="span-8"
      >
        {latestReport ? (
          <OperatorReportPanel report={latestReport} />
        ) : (
          <EmptyState
            title="No findings report in session"
            body="Validate a cultivation CSV batch in the ingest workspace to generate the latest operator report."
          />
        )}
      </Panel>

      <Panel
        title="Findings feed"
        subtitle="Signals, observations, and evidence summaries from the latest batch."
        className="span-4"
      >
        <FindingsFeed items={findingsFeed} emptyText="Awaiting first batch findings." />
      </Panel>

      <Panel
        title="Report catalog"
        subtitle="Current report types surfaced in the workspace."
        className="span-4"
      >
        <CompactList
          items={REPORT_TEMPLATES}
          emptyText="No report templates listed."
        />
      </Panel>

      <Panel
        title="Room review context"
        subtitle="Current room, zone, and grow-cycle placeholders for the active batch."
        className="span-4"
      >
        <RoomStateGrid roomContext={roomContext} />
      </Panel>

      <Panel
        title="Evidence console"
        subtitle="Evidence sources, audit trace lines, and columns requiring review."
        className="span-4"
      >
        <EvidenceConsole lines={evidenceConsole} />
      </Panel>
    </div>
  );
}

function Panel({ title, subtitle, className = "", children }) {
  return (
    <section className={`ops-panel ${className}`.trim()}>
      <div className="ops-panel__header">
        <div>
          <p className="section-token">{title}</p>
          <h2>{subtitle}</h2>
        </div>
      </div>
      <div className="ops-panel__body">{children}</div>
    </section>
  );
}

function TimelineFeed({ items }) {
  return (
    <div className="timeline-feed">
      {items.map((item) => (
        <div className="timeline-row" key={`${item.time}-${item.title}-${item.detail}`}>
          <div className={`timeline-dot timeline-dot--${item.tone}`} />
          <div className="timeline-time">{item.time}</div>
          <div className="timeline-copy">
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function FindingsFeed({ items, emptyText }) {
  if (items.length === 0) {
    return <EmptyState title="No active findings" body={emptyText} compact />;
  }

  return (
    <div className="findings-feed">
      {items.map((item) => (
        <div className="finding-row" key={`${item.title}-${item.detail}`}>
          <div className={`system-dot system-dot--${item.tone}`} />
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function FacilityMapPlaceholder({ zones }) {
  return (
    <div className="facility-map">
      {zones.map((zone) => (
        <div className={`facility-zone facility-zone--${zone.tone}`} key={zone.label}>
          <span>{zone.label}</span>
          <strong>{zone.value}</strong>
          <p>{zone.detail}</p>
        </div>
      ))}
    </div>
  );
}

function RoomStateGrid({ roomContext }) {
  const cards = [
    {
      label: "Primary room",
      value: roomContext.primary,
      detail: "Current room or zone inferred from the active batch when available.",
    },
    {
      label: "Secondary review lane",
      value: roomContext.secondary,
      detail: "Placeholder lane for multi-zone review and operator cross-checks.",
    },
    {
      label: "Grow cycle",
      value: roomContext.cycle,
      detail: "Cycle context remains placeholder until facility-specific metadata is connected.",
    },
    {
      label: "Irrigation review",
      value: roomContext.irrigation,
      detail: "Irrigation review context reflects uploaded channel coverage when present.",
    },
  ];

  return (
    <div className="state-grid">
      {cards.map((card) => (
        <div className="state-card" key={card.label}>
          <span>{card.label}</span>
          <strong>{card.value}</strong>
          <p>{card.detail}</p>
        </div>
      ))}
    </div>
  );
}

function TelemetryCardGrid({ cards }) {
  return (
    <div className="telemetry-grid">
      {cards.map((card) => (
        <div className="telemetry-card" key={card.label}>
          <div className="telemetry-card__header">
            <span>{card.label}</span>
            <div className={`system-dot system-dot--${card.tone}`} />
          </div>
          <strong>{card.primary}</strong>
          <p>{card.secondary}</p>
          <MiniBars values={card.series} />
        </div>
      ))}
    </div>
  );
}

function MiniBars({ values }) {
  if (!values || values.length === 0) {
    return <div className="mini-bars mini-bars--empty">No live series</div>;
  }

  const maxValue = Math.max(...values, 1);

  return (
    <div className="mini-bars">
      {values.map((value, index) => (
        <span
          className="mini-bars__bar"
          key={`${value}-${index}`}
          style={{ height: `${Math.max((value / maxValue) * 100, 18)}%` }}
        />
      ))}
    </div>
  );
}

function DriftMonitor({ rows }) {
  if (!rows || rows.length === 0) {
    return (
      <EmptyState
        title="No drift monitor data"
        body="Upload telemetry with enough usable rows to compare baseline and active windows."
        compact
      />
    );
  }

  const maxMagnitude = Math.max(
    ...rows.map((row) => Math.abs(row.percent_change ?? row.absolute_change ?? 0)),
    1,
  );

  return (
    <div className="drift-monitor">
      {rows.map((row) => {
        const magnitude = Math.abs(row.percent_change ?? row.absolute_change ?? 0);
        const width = Math.max((magnitude / maxMagnitude) * 100, 4);

        return (
          <div className="drift-row" key={row.column}>
            <div className="drift-row__label">
              <span>{row.column}</span>
              <strong>
                {row.percent_change === null ? row.absolute_change : `${row.percent_change}%`}
              </strong>
            </div>
            <div className="drift-row__bar">
              <span
                className={`drift-row__fill drift-row__fill--${row.drift_flag}`}
                style={{ width: `${width}%` }}
              />
            </div>
            <div className="drift-row__meta">
              <span>{row.direction}</span>
              <span>{row.drift_flag}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RelationshipMonitor({ rows }) {
  if (rows.length === 0) {
    return (
      <EmptyState
        title="No relational evidence"
        body="Relationship monitoring will populate when paired numeric channels are available."
        compact
      />
    );
  }

  return (
    <div className="relationship-list">
      {rows.map((row) => (
        <div className="relationship-row" key={`${row.columns.join("-")}-${row.change}`}>
          <div>
            <span>{row.columns.join(" x ")}</span>
            <strong>{row.change}</strong>
          </div>
          <p>
            Baseline {row.baseline_correlation} to active {row.recent_correlation}
          </p>
        </div>
      ))}
    </div>
  );
}

function AlertList({ alerts }) {
  return (
    <div className="alert-list">
      {alerts.map((alert) => (
        <div className="alert-row" key={`${alert.title}-${alert.detail}`}>
          <div className={`system-dot system-dot--${alert.tone}`} />
          <div>
            <strong>{alert.title}</strong>
            <p>{alert.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function IngestConsole({ result, roomContext }) {
  const lines = [
    `batch.source=${result?.filename ?? "pending"}`,
    `room.context=${roomContext.primary}`,
    `rows=${result?.row_count ?? "pending"}`,
    `columns=${result?.column_count ?? "pending"}`,
    `readiness=${result?.data_quality?.readiness ?? "pending"}`,
    `mapped_columns=${result?.cultivation_mapping?.mapped_column_count ?? "pending"}`,
    `engine_result=${result?.engine_result?.overall_result ?? "pending"}`,
  ];

  return (
    <div className="console-lines">
      {lines.map((line) => (
        <div className="console-line" key={line}>
          <span>{line}</span>
        </div>
      ))}
    </div>
  );
}

function EvidenceConsole({ lines }) {
  return (
    <div className="console-lines console-lines--scroll">
      {lines.map((line) => (
        <div className="console-line" key={line}>
          <span>{line}</span>
        </div>
      ))}
    </div>
  );
}

function SystemsMatrix({ systems, systemsState, roomContext }) {
  return (
    <DataTable
      columns={["System", "Operational review scope", "Room or zone context", "Source state"]}
      rows={systems.map((system) => [
        system.name,
        system.scope,
        systemRoomContext(system.name, roomContext),
        systemsState === "ready" ? "Backend placeholder endpoint" : "Local fallback surface",
      ])}
    />
  );
}

function ZoneContextTable({ roomContext }) {
  const rows = [
    ["Primary room", roomContext.primary, "Active review placeholder"],
    ["Secondary lane", roomContext.secondary, "Cross-room comparison placeholder"],
    ["Irrigation zone", roomContext.irrigation, "Irrigation review placeholder"],
    ["Grow cycle", roomContext.cycle, "Cycle-stage placeholder"],
  ];

  return (
    <DataTable
      columns={["Context lane", "Current value", "Operational role"]}
      rows={rows}
    />
  );
}

function SessionStatePanel({ result, roomContext }) {
  const items = [
    ["Room or zone", roomContext.primary],
    ["Latest batch", result?.filename ?? "No active batch"],
    ["Readiness", result ? formatReadiness(result.data_quality.readiness) : "Pending"],
    [
      "Findings state",
      result?.engine_result ? formatEngineResult(result.engine_result.overall_result) : "Pending",
    ],
  ];

  return (
    <div className="metric-grid metric-grid--single">
      {items.map(([label, value]) => (
        <MetricCell key={label} label={label} value={value} />
      ))}
    </div>
  );
}

function MappingGrid({ mapping }) {
  return (
    <div className="mapping-grid">
      {Object.entries(mapping.categories).map(([category, columns]) => (
        <div className="mapping-card" key={category}>
          <span>{category}</span>
          <strong>{columns.length > 0 ? columns.join(", ") : "No mapped columns"}</strong>
        </div>
      ))}
    </div>
  );
}

function EngineResultPanel({ result }) {
  const relationshipRows = buildRelationshipRows({ engine_result: result });
  const findings = result.signals.map((signal) => signal.message);
  const checks = result.recommended_checks;

  return (
    <div className="panel-stack">
      <StatusBanner
        title={formatEngineResult(result.overall_result)}
        subtitle={result.summary}
        tone={result.overall_result}
      />
      <MetricGrid
        metrics={[
          { label: "Corroboration", value: formatShortLabel(result.system_evidence?.corroboration_level ?? "limited") },
          {
            label: "Changed categories",
            value: result.system_evidence?.categories_showing_meaningful_change ?? 0,
          },
          {
            label: "Changed signals",
            value: result.system_evidence?.numeric_signals_showing_meaningful_change ?? 0,
          },
          {
            label: "Persistence",
            value: formatShortLabel(result.persistence_assessment?.status ?? "limited"),
          },
        ]}
      />
      <div className="dual-column">
        <CompactList items={findings} emptyText="No engine findings were recorded." title="Findings" />
        <CompactList items={checks} emptyText="No operator checks were generated." title="Checks" />
      </div>
      <div className="dual-column">
        <CompactList
          items={result.limitations}
          emptyText="No additional limitations were recorded."
          title="Limitations"
        />
        <CompactList
          items={relationshipRows.map((row) => `${row.columns.join(" x ")}: ${row.change}`)}
          emptyText="No relational stability changes were recorded."
          title="Relational stability"
        />
      </div>
    </div>
  );
}

function OperatorReportPanel({ report }) {
  return (
    <div className="panel-stack">
      <StatusBanner
        title={report.title}
        subtitle={report.summary}
        tone={report.data_readiness}
      />
      <MetricGrid
        metrics={[
          { label: "Readiness", value: formatReadiness(report.data_readiness) },
          {
            label: "Timestamp column",
            value: report.time_coverage.detected_timestamp_column ?? "Not detected",
          },
          {
            label: "Sample interval",
            value: report.time_coverage.estimated_sample_interval ?? "Not available",
          },
          {
            label: "Evidence sources",
            value: report.source_sections_used.length,
          },
        ]}
      />
      <div className="dual-column">
        <CompactList
          items={report.key_observations}
          emptyText="No observations were generated."
          title="Observations"
        />
        <CompactList
          items={report.recommended_operator_checks}
          emptyText="No operator checks were generated."
          title="Operator checks"
        />
      </div>
      <div className="dual-column">
        <CompactList
          items={formatColumnsRequiringReview(report.columns_requiring_review)}
          emptyText="No columns were marked for review."
          title="Columns requiring review"
        />
        <CompactList
          items={report.limitations}
          emptyText="No additional limitations were recorded."
          title="Limitations"
        />
      </div>
    </div>
  );
}

function PreviewTable({ columns, rows }) {
  return (
    <DataTable
      columns={columns}
      rows={rows.map((row) => columns.map((column) => row[column]))}
      compact
    />
  );
}

function DataTable({ columns, rows, compact = false }) {
  return (
    <div className={`table-shell ${compact ? "table-shell--compact" : ""}`}>
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${rowIndex}-${columns[0]}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CompactList({ items, emptyText, title }) {
  return (
    <div className="list-block">
      {title && <p className="list-block__title">{title}</p>}
      {items.length > 0 ? (
        <ul className="compact-list">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="empty-copy">{emptyText}</p>
      )}
    </div>
  );
}

function MetricRow({ metrics }) {
  return (
    <div className="metric-row">
      {metrics.map((metric) => (
        <MetricCell key={metric.label} label={metric.label} value={metric.value} />
      ))}
    </div>
  );
}

function MetricGrid({ metrics }) {
  return (
    <div className="metric-grid">
      {metrics.map((metric) => (
        <MetricCell key={metric.label} label={metric.label} value={metric.value} />
      ))}
    </div>
  );
}

function MetricCell({ label, value }) {
  return (
    <div className="metric-cell">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TelemetryBadge({ label, value, tone }) {
  return (
    <div className={`telemetry-badge telemetry-badge--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TelemetryLine({ label, value }) {
  return (
    <div className="telemetry-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusBanner({ title, subtitle, tone }) {
  return (
    <div className={`status-banner status-banner--${tone}`}>
      <div className={`system-dot system-dot--${tone}`} />
      <div>
        <strong>{title}</strong>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}

function EmptyState({ title, body, compact = false }) {
  return (
    <div className={`empty-state ${compact ? "empty-state--compact" : ""}`}>
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function buildTelemetryCards(result) {
  if (!result) {
    return TELEMETRY_CATEGORIES.map((category) => ({
      label: formatCategory(category),
      primary: "Awaiting channel coverage",
      secondary: "No active telemetry batch.",
      series: [],
      tone: "muted",
    }));
  }

  const mapping = result.cultivation_mapping?.categories ?? {};
  const profilesByColumn = new Map(
    (result.numeric_profiles ?? []).map((profile) => [profile.column, profile]),
  );
  const driftByColumn = new Map(
    (result.baseline_analysis?.column_drift ?? []).map((row) => [row.column, row]),
  );

  return TELEMETRY_CATEGORIES.map((category) => {
    const mappedColumns = mapping[category] ?? [];
    const matchingProfile = mappedColumns.map((column) => profilesByColumn.get(column)).find(Boolean);
    const matchingDrift = mappedColumns.map((column) => driftByColumn.get(column)).find(Boolean);
    const series = buildSeriesFromProfile(matchingProfile, matchingDrift);

    if (!matchingProfile) {
      return {
        label: formatCategory(category),
        primary: mappedColumns.length > 0 ? "Mapped without numeric profile" : "Awaiting channel",
        secondary:
          mappedColumns.length > 0
            ? mappedColumns.join(", ")
            : "No uploaded channel mapped to this system category.",
        series,
        tone: "muted",
      };
    }

    const coverage = matchingProfile.missing_percent === 0
      ? "full coverage"
      : `${matchingProfile.missing_percent}% missing`;

    return {
      label: formatCategory(category),
      primary: `${matchingProfile.average} avg`,
      secondary: `${matchingProfile.column} | ${coverage}`,
      series,
      tone: matchingDrift?.drift_flag ?? matchingProfile.variability ?? "normal",
    };
  });
}

function buildSeriesFromProfile(profile, drift) {
  if (!profile) {
    return [];
  }

  const values = [profile.min, profile.average, profile.max]
    .filter((value) => typeof value === "number")
    .map((value) => Math.abs(value));

  if (drift && typeof drift.absolute_change === "number") {
    values.push(Math.abs(drift.absolute_change));
  }

  return values.length > 0 ? values : [];
}

function buildOperationalTimeline(result, apiStatus, roomContext) {
  const items = [];

  if (apiStatus) {
    items.push({
      time: "Session",
      title: apiStatus.label,
      detail: apiStatus.detail,
      tone: apiStatus.state,
    });
  }

  if (!result) {
    items.push({
      time: "Awaiting batch",
      title: "No operational ingest",
      detail: `Room context placeholder: ${roomContext.primary}.`,
      tone: "muted",
    });
    items.push({
      time: "Awaiting batch",
      title: "Baseline review pending",
      detail: "Upload a cultivation telemetry export to populate monitoring surfaces.",
      tone: "muted",
    });
    return items;
  }

  const timeCoverage = deriveTimeCoverage(result);
  items.push({
    time: timeCoverage.first ?? "Start",
    title: "Time coverage opened",
    detail: `Detected ${result.detected_timestamp_column ?? "row-order"} context for the uploaded batch.`,
    tone: "online",
  });
  items.push({
    time: "Batch",
    title: "Ingest validated",
    detail: `${result.row_count} rows and ${result.column_count} columns were parsed in memory.`,
    tone: "online",
  });
  items.push({
    time: "Batch",
    title: "Room context resolved",
    detail: roomContext.primary,
    tone: "muted",
  });
  items.push({
    time: "Review",
    title: "Readiness assessed",
    detail: formatReadiness(result.data_quality.readiness),
    tone: result.data_quality.readiness,
  });
  items.push({
    time: "Review",
    title: "Mapping coverage",
    detail: `${result.cultivation_mapping.mapped_column_count} mapped columns across cultivation systems.`,
    tone: result.cultivation_mapping.mapped_column_count > 0 ? "online" : "muted",
  });
  if (result.engine_result) {
    items.push({
      time: timeCoverage.last ?? "Review",
      title: "Operational findings generated",
      detail: formatEngineResult(result.engine_result.overall_result),
      tone: result.engine_result.overall_result,
    });
  }
  return items;
}

function buildFindingsFeed(result) {
  if (!result) {
    return [];
  }

  const items = [];
  const signals = result.engine_result?.signals ?? [];
  const observations = result.operator_report?.key_observations ?? [];
  const reviewColumns = result.operator_report?.columns_requiring_review ?? [];

  signals.slice(0, 4).forEach((signal) => {
    items.push({
      title: "Engine signal",
      detail: signal.message,
      tone: signal.level ?? result.engine_result?.overall_result ?? "muted",
    });
  });

  observations.slice(0, 3).forEach((observation) => {
    items.push({
      title: "Observation",
      detail: observation,
      tone: "muted",
    });
  });

  reviewColumns.slice(0, 3).forEach((item) => {
    items.push({
      title: "Column review",
      detail: `${item.column}: ${item.reasons.join(" ")}`,
      tone: "needs_review",
    });
  });

  return items;
}

function buildAlertItems(result, apiStatus) {
  const alerts = [];

  if (apiStatus.state !== "online") {
    alerts.push({
      title: "Backend link unavailable",
      detail: apiStatus.detail,
      tone: "offline",
    });
  }

  if (!result) {
    alerts.push({
      title: "Awaiting operational ingest",
      detail: "No telemetry batch is active in this session.",
      tone: "muted",
    });
    return alerts;
  }

  const warnings = result.warnings ?? [];
  const limitations = result.engine_result?.limitations ?? [];
  const checks = result.operator_report?.recommended_operator_checks ?? [];

  warnings.slice(0, 2).forEach((warning) => {
    alerts.push({
      title: "Batch warning",
      detail: warning,
      tone: "needs_review",
    });
  });

  limitations.slice(0, 2).forEach((limitation) => {
    alerts.push({
      title: "Review limitation",
      detail: limitation,
      tone: "muted",
    });
  });

  checks.slice(0, 2).forEach((check) => {
    alerts.push({
      title: "Operator check",
      detail: check,
      tone: "online",
    });
  });

  return alerts.length > 0
    ? alerts
    : [
        {
          title: "No active operator alerts",
          detail: "Current batch did not surface additional review alerts.",
          tone: "online",
        },
      ];
}

function buildEvidenceConsole(result) {
  if (!result) {
    return [
      "evidence.console=awaiting_batch",
      "engine.audit=not_available",
      "operator.report=not_generated",
    ];
  }

  const lines = [
    `batch.file=${result.filename}`,
    `data.readiness=${result.data_quality.readiness}`,
    `batch.rows=${result.row_count}`,
    `batch.columns=${result.column_count}`,
    `mapping.coverage=${result.cultivation_mapping.coverage_percent}%`,
  ];

  (result.operator_report?.source_sections_used ?? []).forEach((section) => {
    lines.push(`report.source=${section}`);
  });

  (result.operator_report?.columns_requiring_review ?? []).slice(0, 4).forEach((item) => {
    lines.push(`review.column=${item.column}`);
  });

  (result.engine_result?.audit_trace ?? []).slice(0, 12).forEach((entry) => {
    lines.push(`engine.audit=${entry}`);
  });

  return lines;
}

function buildRelationshipRows(result) {
  const evidence = result?.engine_result?.evidence ?? [];
  return evidence.filter((item) => item.type === "relationship_change");
}

function buildFacilityMapZones(roomContext) {
  return FACILITY_MAP_PLACEHOLDERS.map((label, index) => {
    const current = index === 0 ? roomContext.primary : index === 1 ? roomContext.secondary : "Context placeholder";
    return {
      label,
      value: current,
      detail:
        index === 2
          ? "Propagation and transition review lane placeholder."
          : index === 3
            ? "Support environment review placeholder."
            : "Operational room context placeholder.",
      tone: index === 0 ? "online" : "muted",
    };
  });
}

function deriveRoomContext(result) {
  if (!result) {
    return {
      primary: "Room context pending",
      secondary: "Secondary lane pending",
      cycle: "Cycle placeholder",
      irrigation: "Irrigation context pending",
    };
  }

  const roomColumn = result.columns.find((column) => {
    const normalized = column.toLowerCase();
    return normalized.includes("room") || normalized.includes("zone");
  });
  const cycleColumn = result.columns.find((column) => {
    const normalized = column.toLowerCase();
    return normalized.includes("cycle") || normalized.includes("stage") || normalized.includes("phase");
  });

  const roomValues = roomColumn
    ? result.preview_rows.map((row) => row[roomColumn]).filter(Boolean)
    : [];
  const cycleValues = cycleColumn
    ? result.preview_rows.map((row) => row[cycleColumn]).filter(Boolean)
    : [];
  const irrigationMapped = result.cultivation_mapping?.categories?.irrigation?.length ?? 0;

  return {
    primary: roomValues[0] ?? "Room context not present in upload",
    secondary: roomValues[1] ?? "Secondary room context pending",
    cycle: cycleValues[0] ?? "Grow cycle placeholder",
    irrigation: irrigationMapped > 0 ? "Irrigation channels mapped" : "Irrigation context pending",
  };
}

function deriveTimeCoverage(result) {
  if (!result?.timestamp_profile) {
    return {
      hasCoverage: false,
      first: null,
      last: null,
      summary: "Awaiting timestamps",
    };
  }

  const first = result.timestamp_profile.first_timestamp;
  const last = result.timestamp_profile.last_timestamp;

  return {
    hasCoverage: Boolean(first || last),
    first,
    last,
    summary:
      first && last
        ? `${first} to ${last}`
        : result.timestamp_profile.estimated_sample_interval ?? "Timestamp range unavailable",
  };
}

function systemRoomContext(systemName, roomContext) {
  const normalized = systemName.toLowerCase();
  if (normalized.includes("irrigation")) {
    return roomContext.irrigation;
  }
  if (normalized.includes("sensor")) {
    return roomContext.primary;
  }
  return roomContext.secondary;
}

function formatCategory(category) {
  if (category === "CO2") {
    return category;
  }
  return category
    .split(" ")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function uploadStateMessage(uploadState) {
  if (uploadState === "uploading") {
    return "Validation in progress";
  }
  if (uploadState === "complete") {
    return "Batch validation complete";
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

function formatColumnsRequiringReview(columnsRequiringReview) {
  return columnsRequiringReview.map((item) => `${item.column}: ${item.reasons.join(" ")}`);
}

export default App;
