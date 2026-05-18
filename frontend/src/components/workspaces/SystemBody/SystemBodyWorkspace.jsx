import React, { useRef, useState } from "react";
import SystemOrbPanel from "./SystemOrbPanel";
import PageContainer from "../../layout/PageContainer";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";

export default function SystemBodyWorkspace({
  systemState,
  uiState,
  coherence,
  stateLabel,
  subtitle,
  connectionStatus,
  connectionTone,
  primaryMessage,
  summaryTitle,
  narrativeItems,
  metrics,
  evidenceItems,
  timelineItems,
  lastUpdate,
  focusLabel,
  lifecycleRail = [],
  orbData = null,
  statusLight = "gray",
  governedOnly = false,
  governedDetail = null,
  apiFetch = null,
  accessCode = "",
  onWorkspaceNavigate = null,
  onUploadComplete = null,
  isLoading = false,
  isEmptyStructuralState = false,
}) {
  void isLoading;
  const [detailOpen, setDetailOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState("");
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsProgressPercent, setSettingsProgressPercent] = useState(null);
  const uploadInputRef = useRef(null);
  const hasAdmittedFinding = statusLight !== "gray";
  const heartbeat = heartbeatStatus(connectionTone, connectionStatus, lastUpdate);

  const operatorFocus =
    narrativeItems?.find((item) => item.label?.toLowerCase().includes("operator"))?.value
    || EMPTY_VALUE;

  const canUpload = typeof apiFetch === "function";

    async function triggerUploadPicker() {
      if (!canUpload || settingsBusy) return;
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
        uploadInputRef.current.click();
      }
    }

    async function handleUploadSelection(event) {
      const file = event.target.files?.[0] ?? null;
      if (!file) return;
      if (!String(file.name || "").toLowerCase().endsWith(".csv")) {
        setSettingsMessage("Only CSV files are accepted for governed historical upload.");
        return;
      }
      if (!canUpload) {
        setSettingsMessage("Upload is unavailable because API client is not configured.");
        return;
      }
      setSettingsBusy(true);
      setSettingsProgressPercent(0);
      setSettingsMessage("Uploading historical CSV to governed intake.");
      try {
        const formData = new FormData();
        formData.append("file", file);
        const uploadResponse = await apiFetch("/api/data/upload", {
          method: "POST",
          accessCode,
          body: formData,
        });
        const uploadPayload = await safeJson(uploadResponse);
        if (!uploadResponse.ok || !uploadPayload?.job_id) {
          throw new Error(readUploadError(uploadPayload, uploadResponse.status));
        }
        const completed = await pollUploadJob({
          apiFetch,
          accessCode,
          jobId: uploadPayload.job_id,
          onProgress: ({ message, percent }) => {
            setSettingsMessage(message);
            if (Number.isFinite(percent)) {
              setSettingsProgressPercent(percent);
            }
          },
        });
        setSettingsProgressPercent(100);
        setSettingsMessage(`Historical replay ready from admitted upload ${completed.job_id}.`);
        if (typeof onUploadComplete === "function") {
          await onUploadComplete(completed);
        }
      } catch (error) {
        setSettingsProgressPercent(null);
        setSettingsMessage(error?.message || "Governed upload failed.");
      } finally {
        setSettingsBusy(false);
      }
    }

    function openWorkspace(workspaceId) {
      if (settingsBusy) return;
      if (typeof onWorkspaceNavigate === "function") {
        onWorkspaceNavigate(workspaceId);
      }
    }

  return (
    <PageContainer className="system-body system-body--gate">
      <section className={`system-gate system-gate--${statusLight} ui-state-surface ui-state-surface--${uiState}`} aria-label="The Gate">
          <div className={`system-gate__heartbeat system-gate__heartbeat--${heartbeat.tone}`} aria-label={`Neraium platform status: ${heartbeat.label}`}>
            <span className="system-gate__heartbeat-dot" />
            <strong>{heartbeat.label}</strong>
          </div>
          <button type="button" className="system-gate__settings" aria-label="Open Gate settings" onClick={() => setSettingsOpen((v) => !v)}>
            SET
          </button>
          <div className="system-gate__center" role="button" tabIndex={0} onClick={() => hasAdmittedFinding && setDetailOpen(true)} onKeyDown={(event) => {
            if ((event.key === "Enter" || event.key === " ") && hasAdmittedFinding) {
              event.preventDefault();
              setDetailOpen(true);
            }
          }}>
            <SystemOrbPanel
              systemState={systemState}
              uiState={uiState}
              coherence={coherence}
              stateLabel={stateLabel}
              lastUpdate={lastUpdate}
              focusLabel={focusLabel}
              orbData={null}
              compactPreview
            />
            <p className="system-gate__state">{stateLabel || EMPTY_VALUE}</p>
            <p className="system-gate__timestamp">{lastUpdate || connectionStatus || EMPTY_VALUE}</p>
            {hasAdmittedFinding ? <p className="system-gate__inspect">Tap to Inspect</p> : null}
          </div>
          {settingsOpen ? (
            <aside className="system-gate__settings-panel" aria-label="Gate settings panel">
              <ul>
                <li><button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("onboarding")} disabled={settingsBusy}>Set up system</button></li>
                <li><button type="button" className="system-gate__settings-action" onClick={triggerUploadPicker} disabled={settingsBusy || !canUpload}>Upload historical CSV</button></li>
                <li><button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("data-connections")} disabled={settingsBusy}>Connect live telemetry source</button></li>
                <li><button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("historical-replay")} disabled={settingsBusy}>Replay controls</button></li>
                <li><button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("governance-admin")} disabled={settingsBusy}>Governance/admin access</button></li>
              </ul>
              <input ref={uploadInputRef} type="file" accept=".csv,text/csv" onChange={handleUploadSelection} className="system-gate__upload-input" />
              {settingsBusy && Number.isFinite(settingsProgressPercent) ? (
                <div className="system-gate__upload-progress-wrap">
                  <div
                    className="system-gate__upload-progress"
                    role="progressbar"
                    aria-label="Upload progress"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(settingsProgressPercent)}
                  >
                    <span style={{ width: `${settingsProgressPercent}%` }} />
                  </div>
                  <strong className="system-gate__upload-progress-label">{Math.round(settingsProgressPercent)}%</strong>
                </div>
              ) : null}
              {settingsMessage ? <p className="system-gate__settings-message">{settingsMessage}</p> : null}
            </aside>
          ) : null}
          {detailOpen && hasAdmittedFinding && governedDetail ? (
            <aside className="system-gate__detail" aria-label="Governed admitted detail view">
              <header>
                <strong>Gate State Detail</strong>
                <button type="button" className="btn btn--secondary" onClick={() => setDetailOpen(false)}>Close</button>
              </header>
              <ul>
                <li><span>Why</span><strong>{governedDetail.why || EMPTY_VALUE}</strong></li>
                <li><span>Primary Evidence Family</span><strong>{governedDetail.primaryEvidenceFamily || EMPTY_VALUE}</strong></li>
                <li><span>Corroborating Evidence Families</span><strong>{governedDetail.corroboratingEvidenceFamilies || EMPTY_VALUE}</strong></li>
                <li><span>Doctrine Rules Satisfied</span><strong>{governedDetail.doctrineRulesSatisfied || EMPTY_VALUE}</strong></li>
                <li><span>Where</span><strong>{governedDetail.affectedRelationshipPath || EMPTY_VALUE}</strong></li>
                <li><span>Operational Mapping</span><strong>{governedDetail.operationalMapping || EMPTY_VALUE}</strong></li>
                <li><span>How Long</span><strong>{governedDetail.elapsedOperationalDuration || EMPTY_VALUE}</strong></li>
                <li><span>Persistence Count</span><strong>{governedDetail.persistenceCount || EMPTY_VALUE}</strong></li>
                <li><span>First Admitted Window</span><strong>{governedDetail.firstAdmittedWindow || EMPTY_VALUE}</strong></li>
                <li><span>Trajectory</span><strong>{governedDetail.trajectory || EMPTY_VALUE}</strong></li>
                <li><span>Drift Velocity</span><strong>{governedDetail.driftVelocity || EMPTY_VALUE}</strong></li>
                <li><span>Transition Pressure</span><strong>{governedDetail.transitionPressure || EMPTY_VALUE}</strong></li>
                <li><span>Relational Stability Trend</span><strong>{governedDetail.relationalStabilityTrend || EMPTY_VALUE}</strong></li>
                <li><span>Structural Drift Trend</span><strong>{governedDetail.structuralDriftTrend || EMPTY_VALUE}</strong></li>
                <li><span>Recovery Window Status</span><strong>{governedDetail.recoveryWindowStatus || EMPTY_VALUE}</strong></li>
                <li><span>Intervention Sensitivity</span><strong>{governedDetail.interventionSensitivity || EMPTY_VALUE}</strong></li>
                <li><span>Subsystem Affected</span><strong>{governedDetail.affectedSubsystem || EMPTY_VALUE}</strong></li>
                <li><span>Structural Relationship Evidence</span><strong>{governedDetail.structuralRelationshipEvidence || EMPTY_VALUE}</strong></li>
                <li><span>Operator Focus</span><strong>{governedDetail.operatorFocus || EMPTY_VALUE}</strong></li>
                <li><span>EVP Reference</span><strong>{governedDetail.evpPreview || EMPTY_VALUE}</strong></li>
              </ul>
            </aside>
          ) : null}
      </section>
    </PageContainer>
  );
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function readUploadError(payload, statusCode) {
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail?.message === "string") return detail.message;
  if (typeof payload?.message === "string" && payload.message.trim()) return payload.message;
  return `Upload request failed (${statusCode}).`;
}

function normalizeUploadStatus(status) {
  const value = String(status ?? "").toLowerCase();
  if (["completed", "complete", "ready", "done", "success"].includes(value)) return "complete";
  if (["failed", "error", "cancelled"].includes(value)) return "failed";
  return "running";
}

function deriveProgressPercent(payload) {
  const directCandidates = [payload?.percent, payload?.progress, payload?.progress_percent, payload?.percentage];
  const direct = directCandidates
    .map((value) => Number(value))
    .find((value) => Number.isFinite(value));
  if (Number.isFinite(direct)) {
    return Math.max(0, Math.min(100, direct));
  }

  const status = String(payload?.status ?? "").toLowerCase();
  const stagedPercent = {
    uploading: 12,
    accepted: 18,
    pending: 28,
    queued: 28,
    validating_schema: 36,
    parsing: 48,
    baseline_modeling: 62,
    structural_scoring: 74,
    running_sii: 82,
    cognition_ready: 90,
    generating_replay: 94,
    writing_state: 97,
    completed: 100,
    complete: 100,
    ready: 100,
    done: 100,
    success: 100,
    failed: 100,
    error: 100,
    cancelled: 100,
  };
  return stagedPercent[status] ?? null;
}

async function pollUploadJob({ apiFetch, accessCode, jobId, onProgress }) {
  const maxChecks = 180;
  let failureCount = 0;
  let highestPercent = 0;
  for (let check = 0; check < maxChecks; check += 1) {
    try {
      const response = await apiFetch(`/api/data/upload-status/${encodeURIComponent(jobId)}`, { accessCode });
      const payload = await safeJson(response);
      if (!response.ok) {
        throw new Error(readUploadError(payload, response.status));
      }
      failureCount = 0;
      const status = normalizeUploadStatus(payload?.status);
      if (status === "complete") {
        return payload;
      }
      if (status === "failed") {
        throw new Error(readUploadError(payload, 500));
      }
      const derivedPercent = deriveProgressPercent(payload);
      const percent = Number.isFinite(derivedPercent)
        ? Math.max(highestPercent, Math.max(0, Math.min(99, derivedPercent)))
        : highestPercent;
      highestPercent = percent;
      const label = payload?.progress_label || payload?.message || "Processing governed telemetry intake.";
      onProgress?.({
        message: `${label} (${Math.round(percent)}%)`,
        percent: Math.round(percent),
      });
      await wait(nextUploadPollDelay({ payload, failureCount }));
    } catch (error) {
      failureCount += 1;
      if (failureCount >= 20) {
        throw error;
      }
      await wait(nextUploadPollDelay({ payload: null, failureCount, failedAttempt: true }));
    }
  }
  throw new Error("Upload polling timed out before governed processing completed.");
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nextUploadPollDelay({ payload, failureCount = 0, failedAttempt = false }) {
  const hintedRetry = Number(payload?.retry_after_ms);
  if (Number.isFinite(hintedRetry) && hintedRetry >= 1000) {
    return Math.min(Math.max(hintedRetry, 1000), 30000);
  }

  const percent = Number(payload?.percent);
  const progress = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : null;
  let baseDelay = 2000;

  if (failedAttempt) {
    baseDelay = Math.min(2000 + failureCount * 1500, 15000);
  } else if (progress != null) {
    if (progress < 20) baseDelay = 1400;
    else if (progress < 70) baseDelay = 2200;
    else if (progress < 95) baseDelay = 3200;
    else baseDelay = 4200;
  } else {
    baseDelay = 2600;
  }

  const hiddenMultiplier = typeof document !== "undefined" && document.visibilityState === "hidden" ? 1.75 : 1;
  return Math.round(baseDelay * hiddenMultiplier);
}

function statusLightLabel(light) {
  if (light === "yellow") return "Watch";
  if (light === "red") return "Alert";
  return "Stable";
}

function heartbeatStatus(connectionTone, connectionStatus, lastUpdate) {
  const text = `${connectionTone ?? ""} ${connectionStatus ?? ""} ${lastUpdate ?? ""}`.toLowerCase();
  if (text.includes("offline") || text.includes("disconnected")) {
    return { label: "Offline", tone: "offline" };
  }
  if (text.includes("replay")) {
    return { label: "Replay running", tone: "syncing" };
  }
  if (text.includes("sync")) {
    return { label: "Data stream active", tone: "syncing" };
  }
  if (text.includes("degraded") || text.includes("limited") || text.includes("elevated")) {
    return { label: "Connection degraded", tone: "degraded" };
  }
  return { label: "Neraium online", tone: "online" };
}
