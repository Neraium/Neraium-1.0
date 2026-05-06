import { useEffect, useState } from "react";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

function App() {
  const [apiStatus, setApiStatus] = useState({
    state: "checking",
    label: "Checking API",
    detail: "Connecting to the Neraium API.",
  });

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

  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <div className="hero__content">
          <p className="eyebrow">Neraium</p>
          <h1 id="page-title">Neraium</h1>
          <p className="subtitle">
            Environmental drift intelligence for cannabis grow facilities
          </p>
          <p className="intro">
            Neraium helps cultivation teams detect and explain environmental drift
            before it becomes crop stress.
          </p>
        </div>

        <div className="status-panel" aria-live="polite">
          <span className={`status-dot status-dot--${apiStatus.state}`} />
          <div>
            <p className="status-label">{apiStatus.label}</p>
            <p className="status-detail">{apiStatus.detail}</p>
          </div>
        </div>
      </section>
    </main>
  );
}

export default App;
