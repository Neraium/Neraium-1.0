import { useState } from "react";

import { loginUser } from "../services/api/authApi";
import { PRODUCT_NAME } from "../content/productLanguage";

const LAST_EMAIL_KEY = "neraium.auth.last_email";

const PLATFORM_SIGNALS = [
  { value: "24/7", label: "Facility observation" },
  { value: "Read-only", label: "Infrastructure access" },
  { value: "Evidence", label: "Behind every insight" },
];

export default function AuthScreen({ notice = "", onAuthenticated }) {
  const [email, setEmail] = useState(() => typeof window === "undefined" ? "" : String(window.localStorage.getItem(LAST_EMAIL_KEY) ?? ""));
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;
    if (!email.trim() || !password) {
      setError("Enter your email and password to continue.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload = await loginUser({ email: email.trim(), password });
      window.localStorage.setItem(LAST_EMAIL_KEY, email.trim().toLowerCase());
      setPassword("");
      onAuthenticated?.(payload.user);
    } catch (submitError) {
      setError(String(submitError?.message ?? "Sign in failed. Check your credentials and try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell auth-shell--premium" aria-labelledby="auth-title" data-testid="auth-screen">
      <div className="auth-ambient auth-ambient--one" aria-hidden="true" />
      <div className="auth-ambient auth-ambient--two" aria-hidden="true" />

      <section className="auth-experience" aria-label="Neraium secure access">
        <aside className="auth-story" aria-label="Platform overview">
          <div className="auth-brand">
            <span className="auth-brand__mark" aria-hidden="true"><span /></span>
            <span>{PRODUCT_NAME}</span>
          </div>

          <div className="auth-story__content">
            <p className="auth-kicker">Systemic Infrastructure Intelligence</p>
            <h2>See the behavior<br />behind the system.</h2>
            <p className="auth-story__lede">
              A decision environment for teams responsible for complex, critical facilities.
            </p>
          </div>

          <div className="auth-signal-grid" role="list" aria-label="Platform principles">
            {PLATFORM_SIGNALS.map((signal) => (
              <div className="auth-signal" role="listitem" key={signal.label}>
                <strong>{signal.value}</strong>
                <span>{signal.label}</span>
              </div>
            ))}
          </div>

          <div className="auth-orbit" aria-hidden="true">
            <span className="auth-orbit__ring auth-orbit__ring--outer" />
            <span className="auth-orbit__ring auth-orbit__ring--inner" />
            <span className="auth-orbit__core" />
          </div>
        </aside>

        <section className="auth-panel">
          <div className="auth-panel__header">
            <p className="auth-access-label"><span aria-hidden="true" /> Secure operator access</p>
            <h1 id="auth-title">Welcome back</h1>
            <p className="auth-copy">Sign in to enter your facility command center.</p>
          </div>

          {notice ? <p className="auth-notice" role="status">{notice}</p> : null}
          <form className="auth-form" onSubmit={handleSubmit} aria-busy={busy}>
            <label htmlFor="auth-email">Email</label>
            <input id="auth-email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" placeholder="name@organization.com" disabled={busy} />
            <label htmlFor="auth-password">Password</label>
            <input id="auth-password" value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" placeholder="Enter your password" disabled={busy} />
            {error ? <p className="auth-error" role="alert">{error}</p> : null}
            <button type="submit" className="command-button auth-submit" disabled={busy} aria-label={busy ? "Signing in..." : "Sign in"}>
              <span>{busy ? "Signing in..." : "Enter command center"}</span>
              <span aria-hidden="true">→</span>
            </button>
          </form>
          <div className="auth-security-note">
            <span aria-hidden="true">◇</span>
            <p><strong>Protected environment</strong><br />Encrypted session · Authorized personnel only</p>
          </div>
          <p className="auth-help">Need access? Contact your Neraium administrator.</p>
        </section>
      </section>
      <p className="auth-legal">Neraium operational intelligence · All activity is securely logged</p>
    </main>
  );
}
