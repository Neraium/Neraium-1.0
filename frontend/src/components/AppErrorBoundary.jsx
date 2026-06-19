import React from "react";
import { EmptyState, Panel } from "./workspacePrimitives";

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
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  handleRetry() {
    this.setState({ error: null });
    if (typeof this.props.onRetry === "function") {
      this.props.onRetry();
      return;
    }
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div data-testid="app-render-fallback">
          <div className="workspace-grid">
            <Panel title="Workspace Recovery" className="span-12">
              <EmptyState
                title="We hit a workspace error"
                body="The latest telemetry state could not be rendered safely. Refresh the workspace or reopen the upload view."
              />
              <div className="panel-actions">
                <button
                  type="button"
                  className="command-button"
                  onClick={this.handleRetry}
                >
                  Retry Workspace
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
