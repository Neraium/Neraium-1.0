import { useState } from "react";

import { loginUser } from "../services/api/authApi";
import { PRODUCT_NAME } from "../content/productLanguage";

const LAST_EMAIL_KEY = "neraium.auth.last_email";

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
      <section className="auth-experience" aria-label="Neraium secure access">
        <section className="auth-panel">
          <div className="auth-identity" aria-label="Application identity">
            <div className="auth-brand">
              <span className="auth-brand__mark" aria-hidden="true"><span /></span>
              <span>{PRODUCT_NAME}</span>
            </div>
            <p>Systemic Infrastructure Intelligence</p>
          </div>

          <div className="auth-divider" aria-hidden="true" />
          <div className="auth-panel__header">
            <p className="auth-access-label"><span aria-hidden="true" /> Secure Operator Access</p>
            <h1 id="auth-title">Welcome back</h1>
            <p className="auth-copy">Sign in to continue.</p>
          </div>

          {notice ? <p className="auth-notice" role="status">{notice}</p> : null}
          <form className="auth-form" onSubmit={handleSubmit} aria-busy={busy}>
            <label htmlFor="auth-email">Email</label>
            <input id="auth-email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" placeholder="name@organization.com" disabled={busy} />
            <label htmlFor="auth-password">Password</label>
            <input id="auth-password" value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" placeholder="Enter your password" disabled={busy} />
            {error ? <p className="auth-error" role="alert">{error}</p> : null}
            <button type="submit" className="command-button auth-submit" disabled={busy} aria-label={busy ? "Signing in..." : "Sign in"}>
              <span>{busy ? "Signing in..." : "Sign in"}</span>
              <span aria-hidden="true">→</span>
            </button>
          </form>
          <div className="auth-security-note">
            <span aria-hidden="true">◇</span>
            <p><strong>Protected environment</strong><br />Encrypted session · Authorized personnel only</p>
          </div>
        </section>
      </section>
    </main>
  );
}
