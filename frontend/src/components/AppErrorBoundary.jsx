import React from "react";
import { EmptyState, Panel } from "./workspacePrimitives";

export default class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
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
            </Panel>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
