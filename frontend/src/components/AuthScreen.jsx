import { useState } from "react";

import { loginUser } from "../services/api/authApi";

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
    <main className="auth-shell" aria-labelledby="auth-title" data-testid="auth-screen">
      <section className="auth-panel">
        <p className="auth-kicker">Neraium Operational Intelligence</p>
        <h1 id="auth-title">Sign in</h1>
        <p className="auth-copy">Use the operator or administrator account provided by your facility administrator.</p>
        {notice ? <p className="auth-notice" role="status">{notice}</p> : null}
        <form className="auth-form" onSubmit={handleSubmit} aria-busy={busy}>
          <label htmlFor="auth-email">Email</label>
          <input id="auth-email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" disabled={busy} />
          <label htmlFor="auth-password">Password</label>
          <input id="auth-password" value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" disabled={busy} />
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          <button type="submit" className="command-button auth-submit" disabled={busy}>
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p className="auth-help">Cannot sign in? Ask an administrator to activate your account or reset your session.</p>
      </section>
    </main>
  );
}
