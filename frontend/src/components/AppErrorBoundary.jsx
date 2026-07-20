import React from "react";
import { EmptyState, Panel } from "./workspacePrimitives";

const CHUNK_RELOAD_KEY_PREFIX = "neraium.chunk-reload:";

export function isChunkLoadError(error) {
  const message = String(error?.message ?? error ?? "");
  return /(?:failed to fetch dynamically imported module|error loading dynamically imported module|loading chunk \d+ failed|chunkloaderror|importing a module script failed)/i.test(message);
}

function reloadPage() {
  if (typeof window !== "undefined") window.location.reload();
}

export default class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
    this.handleRetry = this.handleRetry.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("[neraium] render fallback activated", {
      message: error?.message ?? "Render failure",
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
      this.setState({ error: null });
    }
  }

  handleRetry() {
    if (isChunkLoadError(this.state.error)) {
      (this.props.reloadPage ?? reloadPage)();
      return;
    }

    this.setState({ error: null });
    if (typeof this.props.onRetry === "function") {
      this.props.onRetry();
      return;
    }
    reloadPage();
  }

  render() {
    if (this.state.error) {
      const chunkFailure = isChunkLoadError(this.state.error);
      return (
        <div data-testid="app-render-fallback">
          <div className="workspace-grid">
            <Panel title="Workspace Recovery" className="span-12">
              <EmptyState
                title={chunkFailure ? "The workspace was updated" : "We hit a workspace error"}
                body={chunkFailure
                  ? "Reload the workspace to open the latest version."
                  : "The latest telemetry state could not be rendered safely. Refresh the workspace or reopen the upload view."}
              />
              <div className="panel-actions">
                <button
                  type="button"
                  className="command-button"
                  onClick={this.handleRetry}
                >
                  {chunkFailure ? "Reload Workspace" : "Retry Workspace"}
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
