import React from "react";
import { EmptyState, Panel } from "./workspacePrimitives";

const CHUNK_RELOAD_KEY_PREFIX = "neraium.chunk-reload:";

const WORKSPACE_RECOVERY_COPY = {
  title: "Workspace temporarily unavailable",
  message: "We couldn’t load the latest workspace state. Your connected data and existing analysis are still available. Retry the latest telemetry or continue with the last available state.",
  primaryAction: "Retry latest telemetry",
  secondaryAction: "Use last available state",
};

const CHUNK_RECOVERY_COPY = {
  title: "The workspace was updated",
  bodyTitle: "Reload required",
  message: "Reload the workspace to fetch the current application bundle. Your connected data and existing analysis are still available.",
  primaryAction: "Reload Workspace",
  secondaryAction: "Use last available state",
};

export function isChunkLoadError(error) {
  const message = String(error?.message ?? error ?? "");
  return /(?:failed to fetch dynamically imported module|error loading dynamically imported module|loading chunk \d+ failed|chunkloaderror|importing a module script failed)/i.test(message);
}

function reloadPage() {
  if (typeof window !== "undefined") window.location.reload();
}

function makeReferenceId(seed) {
  const source = String(seed ?? Date.now());
  let hash = 0;
  for (let index = 0; index < source.length; index += 1) {
    hash = ((hash << 5) - hash + source.charCodeAt(index)) | 0;
  }
  return `NRA-${Math.abs(hash).toString(36).slice(0, 7).toUpperCase()}`;
}

export default class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, referenceId: null };
    this.handleRetry = this.handleRetry.bind(this);
    this.handleUseLastAvailable = this.handleUseLastAvailable.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { error, referenceId: makeReferenceId(error?.message) };
  }

  componentDidCatch(error, info) {
    const context = this.props.errorContext ?? {};
    console.error("[neraium] render fallback activated", {
      message: error?.message ?? "Render failure",
      workspaceId: context.workspaceId ?? this.props.workspaceId ?? "workspace",
      failingComponent: context.failingComponent ?? "AppErrorBoundary",
      telemetryTimestamp: context.telemetryTimestamp ?? null,
      schemaVersion: context.schemaVersion ?? null,
      requestCorrelationId: context.requestCorrelationId ?? null,
      referenceId: this.state.referenceId,
      componentStack: info?.componentStack ?? "",
    });

    // A rejected lazy import stays rejected in the current document, so resetting
    // React state cannot recover after a deployment replaces hashed bundles. Reload
    // once per failed asset to fetch the current application document and manifest.
    if (isChunkLoadError(error) && typeof window !== "undefined") {
      const reloadKey = `${CHUNK_RELOAD_KEY_PREFIX}${String(error?.message ?? "unknown")}`;
      if (window.sessionStorage.getItem(reloadKey) !== "1") {
        window.sessionStorage.setItem(reloadKey, "1");
        (this.props.reloadPage ?? reloadPage)();
      }
    }
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null, referenceId: null });
    }
  }

  handleRetry() {
    if (isChunkLoadError(this.state.error)) {
      (this.props.reloadPage ?? reloadPage)();
      return;
    }

    this.setState({ error: null, referenceId: null });
    if (typeof this.props.onRetry === "function") {
      this.props.onRetry();
      return;
    }
    reloadPage();
  }

  handleUseLastAvailable() {
    this.setState({ error: null, referenceId: null });
    if (typeof this.props.onUseLastAvailableState === "function") {
      this.props.onUseLastAvailableState();
    }
  }

  render() {
    if (this.state.error) {
      const recoveryCopy = isChunkLoadError(this.state.error) ? CHUNK_RECOVERY_COPY : WORKSPACE_RECOVERY_COPY;
      return (
        <div data-testid="app-render-fallback">
          <div className="workspace-grid workspace-recovery-shell">
            <Panel title={recoveryCopy.title} className="span-12 workspace-recovery-panel">
              <EmptyState
                title={recoveryCopy.bodyTitle ?? recoveryCopy.title}
                body={recoveryCopy.message}
              />
              <p className="workspace-recovery-reference">Reference {this.state.referenceId ?? "NRA-WORKSPACE"}</p>
              <div className="panel-actions workspace-recovery-actions">
                <button
                  type="button"
                  className="command-button"
                  onClick={this.handleRetry}
                >
                  {recoveryCopy.primaryAction}
                </button>
                <button
                  type="button"
                  className="secondary-command-button"
                  onClick={this.handleUseLastAvailable}
                >
                  {recoveryCopy.secondaryAction}
                </button>
              </div>
            </Panel>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
