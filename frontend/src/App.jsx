import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "./config";
import "./styles.css";

const WORKSPACES = [
  {
    id: "overview",
    label: "Overview",
    eyebrow: "Summary",
    description: "Facility-wide operational awareness, alerts, ingest activity, and top findings.",
  },
  {
    id: "facility-systems",
    label: "Facility Systems",
    eyebrow: "Systems",
    description: "Environmental systems review, room telemetry, drift, and sensor relationships.",
  },
  {
    id: "data-intake",
    label: "Data Intake",
    eyebrow: "Intake",
    description: "Procedural CSV intake, validation, schema review, baseline comparison, and evidence state.",
  },
  {
    id: "evidence-reports",
    label: "Evidence & Reports",
    eyebrow: "Evidence",
    description: "Findings review, evidence analysis, timeline playback, room observations, and report output.",
  },
  {
    id: "intelligence-console",
    label: "Intelligence Console",
    eyebrow: "Console",
    description: "Live monitoring, drift feed, relationship changes, event stream, and evidence terminal.",
  },
];

const FALLBACK_SYSTEMS = [
  {
    name: "HVAC",
    scope: "Temperature conditioning, runtime behavior, and room balancing.",
  },
  {
    name: "Humidity control",
    scope: "Dehumidification, humidification, and moisture stability.",
  },
  {
    name: "Airflow",
    scope: "Circulation, pressure movement, and room exchange behavior.",
  },
  {
    name: "Irrigation",
    scope: "Irrigation timing, cycle review, and environmental response context.",
  },
  {
    name: "Lighting",
    scope: "Photoperiod windows, fixture response, and environmental coupling.",
  },
  {
    name: "Sensor network",
    scope: "Room sensors, gateway exports, and telemetry continuity.",
  },
];

const TELEMETRY_CHANNELS = [
  "temperature",
  "humidity",
  "CO2",
  "HVAC",
  "airflow",
  "irrigation",
  "lighting",
  "sensor network",
];

const INTAKE_STAGES = [
  "Batch receipt",
  "Header and schema detection",
  "Timestamp and room context review",
  "Baseline and evidence extraction",
];

const REPORT_TEMPLATES = [
  "Environmental Drift Summary",
  "System Coupling Review",
  "Operator Action Report",
];

function App() {
  const [activeWorkspace, setActiveWorkspace] = useState("overview");
  const [apiStatus, setApiStatus] = useState({
    state: "checking",
    label: "Checking backend",
    detail: "Establishing API telemetry link.",
  });
  const [systems, setSystems] = useState(FALLBACK_SYSTEMS);
  const [systemsState, setSystemsState] = useState("loading");
  const [latestUploadResult, setLatestUploadResult] = useState(null);
  const workspaceRef = useRef(null);

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

  const activeConfig = WORKSPACES.find((workspace) => workspace.id === activeWorkspace) ?? WORKSPACES[0];
  const roomContext = deriveRoomContext(latestUploadResult);
  const timeCoverage = deriveTimeCoverage(latestUploadResult);

  useEffect(() => {
    if (workspaceRef.current) {
      workspaceRef.current.scrollTo({ top: 0, behavior: "auto" });
    }
  }, [activeWorkspace]);

  function renderActiveWorkspace() {
    if (activeWorkspace === "overview") {
      return (
        <OverviewWorkspace
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
          systems={systems}
          systemsState={systemsState}
          roomContext={roomContext}
        />
      );
    }

    if (activeWorkspace === "facility-systems") {
      return (
        <FacilitySystemsWorkspace
          systems={systems}
          systemsState={systemsState}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
        />
      );
    }

    if (activeWorkspace === "data-intake") {
      return (
        <DataIntakeWorkspace
          latestUploadResult={latestUploadResult}
          onUploadComplete={setLatestUploadResult}
          roomContext={roomContext}
        />
      );
    }

    if (activeWorkspace === "evidence-reports") {
      return (
        <EvidenceReportsWorkspace
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          setActiveWorkspace={setActiveWorkspace}
        />
      );
    }

    return (
      <IntelligenceConsoleWorkspace
        latestUploadResult={latestUploadResult}
        apiStatus={apiStatus}
        roomContext={roomContext}
      />
    );
  }

  return (
    <main className="platform-shell">
      <aside className="platform-sidebar" aria-label="Workspace navigation">
        <div className="sidebar-brand">
          <div className="brand-mark">N</div>
          <div>
            <p className="brand-name">Neraium</p>
            <p className="brand-subtitle">Cultivation infrastructure intelligence</p>
          </div>
        </div>

        <div className="sidebar-section">
          <p className="sidebar-kicker">Workspaces</p>
          <nav className="workspace-nav">
            {WORKSPACES.map((workspace) => (
              <button
                className={`workspace-nav__item ${activeWorkspace === workspace.id ? "workspace-nav__item--active" : ""}`}
                key={workspace.id}
                type="button"
                aria-current={activeWorkspace === workspace.id ? "page" : undefined}
                onClick={() => setActiveWorkspace(workspace.id)}
              >
                <span className="workspace-nav__label">{workspace.label}</span>
                <span className="workspace-nav__detail">{workspace.description}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-section sidebar-section--terminal">
          <p className="sidebar-kicker">Persistent telemetry</p>
          <SidebarTelemetry label="API target" value={formatEndpoint(API_BASE_URL)} />
          <SidebarTelemetry label="Primary room" value={roomContext.primary} />
          <SidebarTelemetry label="Time coverage" value={timeCoverage.summary} />
          <SidebarTelemetry
            label="Findings"
            value={latestUploadResult?.engine_result ? `${latestUploadResult.engine_result.signals.length} active` : "Awaiting batch"}
          />
        </div>

        <div className="sidebar-footer">
          <StatusDot tone={apiStatus.state} />
          <div>
            <p>{apiStatus.label}</p>
            <span>{apiStatus.detail}</span>
          </div>
        </div>
      </aside>

      <div className="platform-main">
        <TopStatusBar
          activeConfig={activeConfig}
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          timeCoverage={timeCoverage}
        />

        <section
          key={activeWorkspace}
          ref={workspaceRef}
          className="platform-workspace"
          aria-labelledby="page-title"
        >
          {renderActiveWorkspace()}
        </section>
      </div>
    </main>
  );
}

function TopStatusBar({ activeConfig, apiStatus, latestUploadResult, roomContext, timeCoverage }) {
  return (
    <header className="top-status">
      <div className="top-status__title">
        <p className="eyebrow">{activeConfig.eyebrow}</p>
        <h1 id="page-title">{activeConfig.label}</h1>
        <p>{activeConfig.description}</p>
      </div>

      <div className="status-rack">
        <StatusChip label="Backend" value={apiStatus.label} tone={apiStatus.state} />
        <StatusChip label="Room or zone" value={roomContext.primary} tone="muted" />
        <StatusChip
          label="Upload batch"
          value={latestUploadResult?.filename ?? "Awaiting ingest"}
          tone={latestUploadResult ? "online" : "muted"}
        />
        <StatusChip
          label="Readiness"
          value={latestUploadResult ? formatReadiness(latestUploadResult.data_quality.readiness) : "No active batch"}
          tone={latestUploadResult?.data_quality?.readiness ?? "muted"}
        />
        <StatusChip
          label="Time coverage"
          value={timeCoverage.summary}
          tone={timeCoverage.hasCoverage ? "online" : "muted"}
        />
        <StatusChip
          label="Operational result"
          value={latestUploadResult?.engine_result ? formatEngineResult(latestUploadResult.engine_result.overall_result) : "Not generated"}
          tone={latestUploadResult?.engine_result?.overall_result ?? "muted"}
        />
      </div>
    </header>
  );
}

function OverviewWorkspace({ apiStatus, latestUploadResult, systems, systemsState, roomContext }) {
  const alerts = buildAlertItems(latestUploadResult, apiStatus).slice(0, 4);
  const findings = buildFindingsFeed(latestUploadResult).slice(0, 3);
  const timeline = buildOperationalTimeline(latestUploadResult, apiStatus, roomContext).slice(0, 4);
  const metrics = buildOverviewMetrics(latestUploadResult, apiStatus, systems, systemsState);
  const summaryTelemetry = buildTelemetryCards(latestUploadResult).slice(0, 4);

  return (
    <div className="workspace-grid workspace-grid--overview">
      <Panel
        title="Operational summary"
        subtitle="Current facility status for operations leadership and executive-operational review."
        className="span-6"
      >
        <MetricGrid metrics={metrics} />
      </Panel>

      <Panel
        title="Active alerts summary"
        subtitle="Current warnings, checks, and attention items."
        className="span-3"
      >
        <AlertList alerts={alerts} />
      </Panel>

      <Panel
        title="Latest ingestion activity"
        subtitle="Recent timestamped activity for the active or latest batch."
        className="span-3"
      >
        <TimelineFeed items={timeline} />
      </Panel>

      <Panel
        title="Top findings"
        subtitle="Highest-priority findings from the current session."
        className="span-4"
      >
        <FeedList items={findings} emptyText="Awaiting uploaded telemetry batch." />
      </Panel>

      <Panel
        title="High-level telemetry"
        subtitle="Primary environmental channels and current operational coverage."
        className="span-4"
      >
        <TelemetryCardGrid cards={summaryTelemetry} compact />
      </Panel>

      <Panel
        title="Room and zone summary"
        subtitle="Current room context and placeholder review lanes."
        className="span-4"
      >
        <ZoneSummaryGrid items={buildZoneSummary(roomContext)} />
      </Panel>
    </div>
  );
}

function FacilitySystemsWorkspace({ systems, systemsState, latestUploadResult, roomContext }) {
  const telemetryCards = buildTelemetryCards(latestUploadResult);
  const driftRows = latestUploadResult?.baseline_analysis?.column_drift ?? [];
  const relationshipRows = buildRelationshipRows(latestUploadResult);
  const roomTransitions = buildRoomTransitions(latestUploadResult, roomContext);
  const irrigationPanel = telemetryCards.find((card) => card.label === "Irrigation") ?? null;

  return (
    <div className="workspace-grid workspace-grid--systems">
      <Panel
        title="HVAC and environmental telemetry"
        subtitle="Current telemetry strips and time-series placeholders across monitored environmental channels."
        className="span-8"
      >
        <TelemetryCardGrid cards={telemetryCards.slice(0, 6)} />
      </Panel>

      <Panel
        title="Irrigation review"
        subtitle="Current irrigation context and batch-derived review surface."
        className="span-4"
      >
        <TelemetryCardGrid cards={irrigationPanel ? [irrigationPanel] : []} compact />
        <CompactList
          items={[
            `Irrigation context: ${roomContext.irrigation}.`,
            "Cycle and event interpretation remain placeholder-driven until facility metadata is connected.",
          ]}
          emptyText="Awaiting irrigation context."
        />
      </Panel>

      <Panel
        title="Room and zone telemetry"
        subtitle="Current room-level context and transition surface."
        className="span-3"
      >
        <TimelineFeed items={roomTransitions} />
      </Panel>

      <Panel
        title="Operational drift"
        subtitle="Baseline versus active-window movement across room telemetry."
        className="span-6"
      >
        <DriftMonitor rows={driftRows} />
      </Panel>

      <Panel
        title="Sensor relationships"
        subtitle="Paired signal changes and relational stability review."
        className="span-3"
      >
        <RelationshipMonitor rows={relationshipRows} />
      </Panel>

      <Panel
        title="Systems table"
        subtitle="Operational systems, room context, and source-state coverage."
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

function DataIntakeWorkspace({ latestUploadResult, onUploadComplete, roomContext }) {
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

  const intakeStages = buildIntakeStages(uploadResult, uploadState, roomContext);

  return (
    <div className="workspace-grid workspace-grid--intake">
      <Panel
        title="CSV intake workflow"
        subtitle="Procedural intake for telemetry exports, parsing, validation, and evidence extraction."
        className="span-7"
      >
        <form className="intake-flow" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <p className="section-token">Batch source</p>
            <h3>Cultivation telemetry export</h3>
            <p>
              Upload room, irrigation, HVAC, or sensor-network CSV batches for deterministic parsing,
              baseline review, and operational evidence extraction.
            </p>
          </div>

          <div className="intake-flow__controls">
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

          <div className="intake-flow__status">
            <span>{selectedFile ? selectedFile.name : "No file selected"}</span>
            <span>{uploadStateMessage(uploadState)}</span>
          </div>

          {uploadError && <p className="form-error">{uploadError}</p>}
        </form>
      </Panel>

      <Panel
        title="Validation stages"
        subtitle="Traceable intake stages for schema, parsing, and evidence readiness."
        className="span-5"
      >
        <WorkflowStages items={intakeStages} />
      </Panel>

      <Panel
        title="Schema detection and room mapping"
        subtitle="Detected room context, mapped columns, and schema output from the active batch."
        className="span-4"
      >
        <SchemaMappingPanel result={uploadResult} roomContext={roomContext} />
      </Panel>

      <Panel
        title="Validation checks"
        subtitle="Current batch verification summary and procedural checkpoints."
        className="span-4"
      >
        <VerificationPanel result={uploadResult} />
      </Panel>

      <Panel
        title="Evidence extraction state"
        subtitle="Current extraction status for baseline evidence, findings, and report generation."
        className="span-4"
      >
        <EvidenceExtractionPanel result={uploadResult} />
      </Panel>

      <Panel
        title="Baseline comparison"
        subtitle="Current baseline review and operational drift extraction from the active batch."
        className="span-12"
      >
        {uploadResult ? (
          <DriftMonitor rows={uploadResult.baseline_analysis.column_drift} detailed />
        ) : (
          <EmptyState
            title="No baseline comparison available"
            body="Validate a telemetry batch to populate baseline movement and operational drift review."
          />
        )}
      </Panel>
    </div>
  );
}

function EvidenceReportsWorkspace({ latestUploadResult, roomContext, setActiveWorkspace }) {
  const latestReport = latestUploadResult?.operator_report;
  const findings = buildFindingsFeed(latestUploadResult);
  const timeline = buildOperationalTimeline(latestUploadResult, null, roomContext);
  const evidenceLines = buildEvidenceConsole(latestUploadResult);
  const observations = buildRoomObservations(latestUploadResult, roomContext);

  return (
    <div className="workspace-grid workspace-grid--evidence">
      <Panel
        title="Findings report"
        subtitle="Analytical review surface for findings, checks, and evidence-backed observations."
        className="span-7"
      >
        {latestReport ? (
          <OperatorReportPanel report={latestReport} />
        ) : (
          <EmptyState
            title="No findings report in session"
            body="Validate a cultivation batch in Data Intake to generate the latest operator report."
          />
        )}
      </Panel>

      <Panel
        title="Evidence review"
        subtitle="Audit-ready evidence references, source sections, and extraction traces."
        className="span-5"
      >
        <EvidenceConsole lines={evidenceLines} />
      </Panel>

      <Panel
        title="Timeline playback"
        subtitle="Timestamp-heavy playback for ingest, readiness, and findings progression."
        className="span-4"
      >
        <TimelineFeed items={timeline} />
      </Panel>

      <Panel
        title="Room observations"
        subtitle="Current room and zone observations grounded in the active batch."
        className="span-4"
      >
        <CompactList items={observations} emptyText="No room observations available." />
      </Panel>

      <Panel
        title="Limitations and exported reports"
        subtitle="Current limitations and exported report surface for the active session."
        className="span-4"
      >
        {latestReport ? (
          <CompactList items={[...latestReport.limitations, ...REPORT_TEMPLATES]} emptyText="No report output available." />
        ) : (
          <CompactList items={REPORT_TEMPLATES} emptyText="No report output available." />
        )}
      </Panel>

      <Panel
        title="Operational notes"
        subtitle="Current findings and navigation back to intake review."
        className="span-12"
      >
        <div className="evidence-action-row">
          <CompactList items={findings.slice(0, 6)} emptyText="Awaiting evidence-linked findings." inline />
          <button className="command-button command-button--secondary" type="button" onClick={() => setActiveWorkspace("data-intake")}>
            Open Data Intake
          </button>
        </div>
      </Panel>
    </div>
  );
}

function IntelligenceConsoleWorkspace({ latestUploadResult, apiStatus, roomContext }) {
  const telemetryCards = buildTelemetryCards(latestUploadResult);
  const driftRows = latestUploadResult?.baseline_analysis?.column_drift ?? [];
  const relationshipRows = buildRelationshipRows(latestUploadResult);
  const timeline = buildOperationalTimeline(latestUploadResult, apiStatus, roomContext);
  const findings = buildFindingsFeed(latestUploadResult);
  const consoleEvents = buildConsoleEvents(latestUploadResult, apiStatus, roomContext);

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel
        title="Live telemetry"
        subtitle="Current channel strips and environmental monitoring surface."
        className="span-6"
      >
        <TelemetryCardGrid cards={telemetryCards} />
      </Panel>

      <Panel
        title="Drift feed"
        subtitle="Current drift transitions and baseline movement across telemetry channels."
        className="span-2"
      >
        <DriftFeed rows={driftRows} />
      </Panel>

      <Panel
        title="Relationship changes"
        subtitle="Current paired-sensor changes and relational events."
        className="span-2"
      >
        <RelationshipMonitor rows={relationshipRows} />
      </Panel>

      <Panel
        title="Operational notices"
        subtitle="Current findings and monitoring notices."
        className="span-2"
      >
        <FeedList items={findings.slice(0, 6)} emptyText="Awaiting telemetry findings." />
      </Panel>

      <Panel
        title="Live event stream"
        subtitle="Session-wide operational events, ingest progression, and room transitions."
        className="span-4"
      >
        <TimelineFeed items={timeline} />
      </Panel>

      <Panel
        title="Evidence terminal"
        subtitle="Streaming evidence and operational terminal output."
        className="span-5"
      >
        <EvidenceConsole lines={consoleEvents} animated />
      </Panel>

      <Panel
        title="Future assistant placement"
        subtitle="Reserved workspace for future guided operational intelligence."
        className="span-3"
      >
        <EmptyState
          title="Future assistant surface reserved"
          body="This console intentionally leaves room for future guided operational assistance without changing the current monitoring workflow."
          compact
        />
      </Panel>
    </div>
  );
}

function WorkflowStages({ items }) {
  return (
    <div className="workflow-list">
      {items.map((item) => (
        <div className="workflow-step" key={item.title}>
          <StatusDot tone={item.tone} />
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
          <span>{item.state}</span>
        </div>
      ))}
    </div>
  );
}

function SchemaMappingPanel({ result, roomContext }) {
  return (
    <MetricGrid
      metrics={[
        { label: "Primary room", value: roomContext.primary },
        { label: "Secondary lane", value: roomContext.secondary },
        {
          label: "Mapped columns",
          value: result ? result.cultivation_mapping.mapped_column_count : "Awaiting batch",
        },
        {
          label: "Unknown columns",
          value: result ? result.cultivation_mapping.unknown_column_count : "Awaiting batch",
        },
      ]}
      compact
    />
  );
}

function VerificationPanel({ result }) {
  return (
    <MetricGrid
      metrics={[
        {
          label: "Readiness",
          value: result ? formatReadiness(result.data_quality.readiness) : "Awaiting batch",
        },
        { label: "Rows parsed", value: result ? result.row_count : "Pending" },
        { label: "Timestamp context", value: result?.detected_timestamp_column ?? "Pending" },
        { label: "Numeric channels", value: result ? result.data_quality.numeric_column_count : "Pending" },
      ]}
      compact
    />
  );
}

function EvidenceExtractionPanel({ result }) {
  return (
    <FeedList
      items={[
        {
          title: "Baseline evidence",
          detail: result ? `${result.baseline_analysis.columns_analyzed} columns analyzed.` : "Awaiting batch.",
          tone: result ? "online" : "muted",
        },
        {
          title: "Engine evidence",
          detail: result?.engine_result ? `${result.engine_result.evidence.length} evidence items.` : "Awaiting batch.",
          tone: result?.engine_result ? "online" : "muted",
        },
        {
          title: "Operator report",
          detail: result?.operator_report ? "Current findings report available." : "Awaiting batch.",
          tone: result?.operator_report ? "online" : "muted",
        },
      ]}
      emptyText="Awaiting evidence extraction."
    />
  );
}

function MetricGrid({ metrics, compact = false }) {
  return (
    <div className={`metric-grid ${compact ? "metric-grid--compact" : ""}`}>
      {metrics.map((metric) => (
        <div className="metric-cell" key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </div>
      ))}
    </div>
  );
}

function FeedList({ items, emptyText, inline = false }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No active items" body={emptyText} compact />;
  }

  return (
    <div className={`feed-list ${inline ? "feed-list--inline" : ""}`}>
      {items.map((item, index) => (
        <div className="feed-item" key={`${item.title ?? item}-${index}`}>
          <StatusDot tone={item.tone ?? "muted"} />
          <div>
            <strong>{item.title ?? item}</strong>
            {item.detail && <p>{item.detail}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

function TimelineFeed({ items }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No timeline events" body="Awaiting timestamped operational activity." compact />;
  }

  return (
    <div className="timeline-list">
      {items.map((item, index) => (
        <div className="timeline-item" key={`${item.time}-${item.title}-${index}`}>
          <StatusDot tone={item.tone} />
          <span className="timeline-item__time">{item.time}</span>
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function TelemetryCardGrid({ cards, compact = false }) {
  if (!cards || cards.length === 0) {
    return <EmptyState title="No telemetry available" body="Awaiting uploaded telemetry coverage." compact />;
  }

  return (
    <div className={`telemetry-grid ${compact ? "telemetry-grid--compact" : ""}`}>
      {cards.map((card) => (
        <div className="telemetry-card" key={card.label}>
          <div className="telemetry-card__header">
            <span>{card.label}</span>
            <StatusDot tone={card.tone} />
          </div>
          <strong>{card.primary}</strong>
          <p>{card.secondary}</p>
          <MiniSeries values={card.series} tone={card.tone} />
        </div>
      ))}
    </div>
  );
}

function MiniSeries({ values, tone }) {
  if (!values || values.length === 0) {
    return <div className="mini-series mini-series--empty">No series</div>;
  }

  const maxValue = Math.max(...values, 1);

  return (
    <div className="mini-series">
      {values.map((value, index) => (
        <span
          className={`mini-series__bar mini-series__bar--${tone}`}
          key={`${value}-${index}`}
          style={{ height: `${Math.max((value / maxValue) * 100, 16)}%` }}
        />
      ))}
    </div>
  );
}

function DriftMonitor({ rows, detailed = false }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title="No drift review available" body="Awaiting telemetry with enough usable rows." compact />;
  }

  const maxMagnitude = Math.max(
    ...rows.map((row) => Math.abs(row.percent_change ?? row.absolute_change ?? 0)),
    1,
  );

  return (
    <div className="drift-list">
      {rows.map((row) => {
        const magnitude = Math.abs(row.percent_change ?? row.absolute_change ?? 0);
        const width = Math.max((magnitude / maxMagnitude) * 100, 6);

        return (
          <div className="drift-row" key={row.column}>
            <div className="drift-row__meta">
              <span>{row.column}</span>
              <strong>
                {row.percent_change === null ? row.absolute_change : `${row.percent_change}%`}
              </strong>
            </div>
            <div className="drift-row__track">
              <span
                className={`drift-row__fill drift-row__fill--${row.drift_flag}`}
                style={{ width: `${width}%` }}
              />
            </div>
            <div className="drift-row__status">
              <span>{row.direction}</span>
              <span>{row.drift_flag}</span>
            </div>
            {detailed && row.warnings?.length > 0 && (
              <p className="drift-row__detail">{row.warnings.join(" ")}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function DriftFeed({ rows }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title="No drift feed" body="Awaiting baseline comparison output." compact />;
  }

  return (
    <FeedList
      items={rows.map((row) => ({
        title: row.column,
        detail: `${row.direction} movement with ${row.percent_change === null ? row.absolute_change : `${row.percent_change}%`} change.`,
        tone: row.drift_flag,
      }))}
      emptyText="Awaiting drift output."
    />
  );
}

function RelationshipMonitor({ rows }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title="No relationship changes" body="Awaiting paired telemetry evidence." compact />;
  }

  return (
    <div className="relationship-list">
      {rows.map((row, index) => (
        <div className="relationship-row" key={`${row.columns.join("-")}-${index}`}>
          <span>{row.columns.join(" x ")}</span>
          <strong>{row.change}</strong>
          <p>
            baseline {row.baseline_correlation} to active {row.recent_correlation}
          </p>
        </div>
      ))}
    </div>
  );
}

function AlertList({ alerts }) {
  if (!alerts || alerts.length === 0) {
    return <EmptyState title="No active alerts" body="Current session does not contain additional alerts." compact />;
  }

  return <FeedList items={alerts} emptyText="No active alerts." />;
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

function ZoneSummaryGrid({ items }) {
  return (
    <div className="zone-summary-grid">
      {items.map((item) => (
        <div className="zone-summary-card" key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          <p>{item.detail}</p>
        </div>
      ))}
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
        compact
      />

      <div className="two-column-block">
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
    </div>
  );
}

function CompactList({ items, emptyText, title, inline = false }) {
  return (
    <div className={`compact-list-block ${inline ? "compact-list-block--inline" : ""}`}>
      {title && <p className="section-token">{title}</p>}
      {items && items.length > 0 ? (
        <ul className={`compact-list ${inline ? "compact-list--inline" : ""}`}>
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

function EvidenceConsole({ lines, animated = false }) {
  return (
    <div className={`evidence-console ${animated ? "evidence-console--animated" : ""}`}>
      {lines.map((line, index) => (
        <div className="evidence-console__line" key={`${line}-${index}`}>
          <span>{line}</span>
        </div>
      ))}
    </div>
  );
}

function DataTable({ columns, rows }) {
  return (
    <div className="table-shell">
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

function EmptyState({ title, body, compact = false }) {
  return (
    <div className={`empty-state ${compact ? "empty-state--compact" : ""}`}>
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function StatusBanner({ title, subtitle, tone }) {
  return (
    <div className={`status-banner status-banner--${tone}`}>
      <StatusDot tone={tone} />
      <div>
        <strong>{title}</strong>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}

function StatusChip({ label, value, tone }) {
  return (
    <div className={`status-chip status-chip--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SidebarTelemetry({ label, value }) {
  return (
    <div className="sidebar-telemetry">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusDot({ tone }) {
  return <span className={`status-dot status-dot--${tone}`} />;
}

function buildTelemetryCards(result) {
  if (!result) {
    return TELEMETRY_CHANNELS.map((channel) => ({
      label: formatCategory(channel),
      primary: "Awaiting channel",
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

  return TELEMETRY_CHANNELS.map((channel) => {
    const mappedColumns = mapping[channel] ?? [];
    const profile = mappedColumns.map((column) => profilesByColumn.get(column)).find(Boolean);
    const drift = mappedColumns.map((column) => driftByColumn.get(column)).find(Boolean);

    if (!profile) {
      return {
        label: formatCategory(channel),
        primary: mappedColumns.length > 0 ? "Mapped without numeric profile" : "Awaiting channel",
        secondary:
          mappedColumns.length > 0
            ? mappedColumns.join(", ")
            : "No uploaded channel mapped to this system category.",
        series: [],
        tone: "muted",
      };
    }

    return {
      label: formatCategory(channel),
      primary: `${profile.average} avg`,
      secondary: `${profile.column} | ${profile.missing_percent}% missing`,
      series: buildSeries(profile, drift),
      tone: drift?.drift_flag ?? profile.variability ?? "normal",
    };
  });
}

function buildSeries(profile, drift) {
  const values = [profile.min, profile.average, profile.max]
    .filter((value) => typeof value === "number")
    .map((value) => Math.abs(value));

  if (drift && typeof drift.absolute_change === "number") {
    values.push(Math.abs(drift.absolute_change));
  }

  return values;
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
      title: "No active ingest",
      detail: `Room placeholder: ${roomContext.primary}.`,
      tone: "muted",
    });
    items.push({
      time: "Awaiting batch",
      title: "Baseline review pending",
      detail: "Upload telemetry to populate facility-wide timeline playback.",
      tone: "muted",
    });
    return items;
  }

  const timeCoverage = deriveTimeCoverage(result);
  items.push({
    time: timeCoverage.first ?? "Batch start",
    title: "Time coverage opened",
    detail: `Detected ${result.detected_timestamp_column ?? "row-order"} timeline context.`,
    tone: "online",
  });
  items.push({
    time: "Batch",
    title: "Ingest validated",
    detail: `${result.row_count} rows and ${result.column_count} columns parsed in memory.`,
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
      time: timeCoverage.last ?? "Findings",
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

  (result.warnings ?? []).slice(0, 2).forEach((warning) => {
    alerts.push({
      title: "Batch warning",
      detail: warning,
      tone: "needs_review",
    });
  });

  (result.engine_result?.limitations ?? []).slice(0, 2).forEach((limitation) => {
    alerts.push({
      title: "Review limitation",
      detail: limitation,
      tone: "muted",
    });
  });

  (result.operator_report?.recommended_operator_checks ?? []).slice(0, 2).forEach((check) => {
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

function buildOverviewMetrics(result, apiStatus, systems, systemsState) {
  return [
    {
      label: "Facility stability",
      value: result?.engine_result ? deriveFacilityStability(result) : "Awaiting review",
    },
    {
      label: "Active alerts",
      value: buildAlertItems(result, apiStatus).length,
    },
    {
      label: "Ingestion state",
      value: result ? formatReadiness(result.data_quality.readiness) : "No active batch",
    },
    {
      label: "Systems in scope",
      value: systemsState === "ready" ? `${systems.length} live` : `${systems.length} placeholder`,
    },
  ];
}

function buildZoneSummary(roomContext) {
  return [
    {
      label: "Primary room",
      value: roomContext.primary,
      detail: "Current room or zone inferred from active upload context.",
    },
    {
      label: "Secondary lane",
      value: roomContext.secondary,
      detail: "Cross-room review placeholder for facility operations.",
    },
    {
      label: "Grow cycle",
      value: roomContext.cycle,
      detail: "Cycle context remains placeholder until facility metadata is connected.",
    },
    {
      label: "Irrigation review",
      value: roomContext.irrigation,
      detail: "Irrigation context reflects mapped channels when present.",
    },
  ];
}

function buildRoomTransitions(result, roomContext) {
  const items = [
    {
      time: "Transition",
      title: "Primary room context",
      detail: roomContext.primary,
      tone: "online",
    },
    {
      time: "Transition",
      title: "Secondary review lane",
      detail: roomContext.secondary,
      tone: "muted",
    },
    {
      time: "Transition",
      title: "Irrigation context",
      detail: roomContext.irrigation,
      tone: "needs_review",
    },
  ];

  if (result?.timestamp_profile?.estimated_sample_interval) {
    items.push({
      time: "Timing",
      title: "Sample interval",
      detail: result.timestamp_profile.estimated_sample_interval,
      tone: "online",
    });
  }

  return items;
}

function buildEvidenceConsole(result) {
  if (!result) {
    return [
      "evidence.console=awaiting_batch",
      "schema.mapping=not_available",
      "operator.report=not_generated",
    ];
  }

  const lines = [
    `batch.file=${result.filename}`,
    `data.readiness=${result.data_quality.readiness}`,
    `rows=${result.row_count}`,
    `columns=${result.column_count}`,
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

function buildConsoleEvents(result, apiStatus, roomContext) {
  const lines = [
    `console.link=${apiStatus.label}`,
    `console.room=${roomContext.primary}`,
    `console.secondary=${roomContext.secondary}`,
    `console.irrigation=${roomContext.irrigation}`,
  ];

  if (result) {
    lines.push(`console.batch=${result.filename}`);
    lines.push(`console.readiness=${result.data_quality.readiness}`);
    (result.engine_result?.signals ?? []).slice(0, 6).forEach((signal) => {
      lines.push(`signal.event=${signal.message}`);
    });
  } else {
    lines.push("console.batch=awaiting_ingest");
  }

  return [...lines, ...buildEvidenceConsole(result).slice(0, 10)];
}

function buildRelationshipRows(result) {
  const evidence = result?.engine_result?.evidence ?? [];
  return evidence.filter((item) => item.type === "relationship_change");
}

function buildRoomObservations(result, roomContext) {
  const observations = [
    `Primary room or zone context: ${roomContext.primary}.`,
    `Secondary review lane: ${roomContext.secondary}.`,
    `Grow cycle placeholder: ${roomContext.cycle}.`,
    `Irrigation context: ${roomContext.irrigation}.`,
  ];

  if (result?.operator_report?.time_coverage?.first_timestamp && result?.operator_report?.time_coverage?.last_timestamp) {
    observations.push(
      `Observed time coverage runs from ${result.operator_report.time_coverage.first_timestamp} to ${result.operator_report.time_coverage.last_timestamp}.`,
    );
  }

  return observations;
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
      summary: "Awaiting timestamps",
    };
  }

  const first = result.timestamp_profile.first_timestamp;
  const last = result.timestamp_profile.last_timestamp;

  return {
    hasCoverage: Boolean(first || last),
    summary:
      first && last
        ? `${first} to ${last}`
        : result.timestamp_profile.estimated_sample_interval ?? "Timestamp range unavailable",
  };
}

function deriveFacilityStability(result) {
  const overallResult = result.engine_result?.overall_result;
  if (overallResult === "normal") {
    return "No elevated drift found";
  }
  if (overallResult === "elevated") {
    return "Meaningful change requires review";
  }
  if (overallResult === "needs_review") {
    return "More review context needed";
  }
  return "Awaiting operational review";
}

function buildIntakeStages(result, uploadState, roomContext) {
  return INTAKE_STAGES.map((stage, index) => {
    if (uploadState === "uploading") {
      return {
        title: stage,
        detail: index === 0 ? "Batch is being validated." : "Pending upstream stage completion.",
        state: index === 0 ? "active" : "queued",
        tone: index === 0 ? "checking" : "muted",
      };
    }

    if (!result) {
      return {
        title: stage,
        detail: index === 2 ? `Room placeholder: ${roomContext.primary}.` : "Awaiting uploaded telemetry batch.",
        state: "pending",
        tone: "muted",
      };
    }

    const details = [
      `${result.filename} received for in-memory parsing.`,
      `${result.columns.length} headers detected across the uploaded batch.`,
      `Room context resolved as ${roomContext.primary}.`,
      `${result.engine_result ? "Evidence extracted and findings generated." : "Evidence generation pending."}`,
    ];

    return {
      title: stage,
      detail: details[index],
      state: "complete",
      tone: index === 3 && !result.engine_result ? "needs_review" : "online",
    };
  });
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

function formatEngineResult(result) {
  if (result === "elevated") {
    return "Elevated";
  }
  if (result === "needs_review") {
    return "Needs review";
  }
  return "Normal";
}

function formatEndpoint(endpoint) {
  return endpoint.replace("http://", "").replace("https://", "");
}

function formatColumnsRequiringReview(columnsRequiringReview) {
  return columnsRequiringReview.map((item) => `${item.column}: ${item.reasons.join(" ")}`);
}

export default App;
