import { Component } from "react";

export default class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    console.error("Neraium UI recovered from render error", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="access-shell">
          <section className="access-panel" aria-labelledby="recovery-title">
            <div className="access-brand">
              <div className="brand-mark">N</div>
              <span>System recovery</span>
            </div>
            <div className="access-copy">
              <p className="eyebrow">Neraium</p>
              <h1 id="recovery-title">System view is recovering.</h1>
              <p>Backend processing is still available. Refresh the page to reload the latest stable state.</p>
            </div>
            <button className="command-button" type="button" onClick={() => window.location.reload()}>
              Refresh view
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}
