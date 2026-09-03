import { useEffect, useState } from "react";
import "../styles/auth-premium.css";

import { loginUser, registerEmployee } from "../services/api/authApi";
import { PRODUCT_NAME } from "../content/productLanguage";

const LAST_EMAIL_KEY = "neraium.auth.last_email";

function readInviteToken() {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.hash.replace(/^#/, "")).get("invite") || "";
}

function readLastEmail() {
  if (typeof window === "undefined") return "";
  try {
    return String(window.localStorage.getItem(LAST_EMAIL_KEY) ?? "");
  } catch {
    return "";
  }
}

function rememberLastEmail(email) {
  try {
    window.localStorage.setItem(LAST_EMAIL_KEY, email);
  } catch {
    // Remembering an email is optional and must not affect authentication.
  }
}

export default function AuthScreen({ notice = "", onAuthenticated }) {
  const [inviteToken] = useState(readInviteToken);
  const [mode, setMode] = useState(() => readInviteToken() ? "request" : "login");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState(readLastEmail);
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!inviteToken || typeof window === "undefined") return;
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  }, [inviteToken]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;
    if (mode === "request" && (!firstName.trim() || !lastName.trim())) {
      setError("Enter your first and last name.");
      return;
    }
    if (!email.trim() || !password) {
      setError(mode === "request" ? "Enter your email and password." : "Enter your email and password to continue.");
      return;
    }
    if (mode === "request" && password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (mode === "request" && password !== passwordConfirmation) {
      setError("Passwords do not match.");
      return;
    }
    if (mode === "request" && !inviteToken) {
      setError("Open the employee invitation link provided by your administrator.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (mode === "request") {
        const payload = await registerEmployee({ firstName, lastName, email, password, passwordConfirmation, inviteToken });
        setPassword("");
        setPasswordConfirmation("");
        rememberLastEmail(email.trim().toLowerCase());
        onAuthenticated?.(payload);
        return;
      }
      const payload = await loginUser({ email: email.trim(), password });
      setPassword("");
      rememberLastEmail(email.trim().toLowerCase());
      onAuthenticated?.(payload);
    } catch (submitError) {
      setError(String(submitError?.message ?? "Sign in failed. Check your credentials and try again."));
    } finally {
      setBusy(false);
    }
  }

  function switchMode(nextMode) {
    if (busy) return;
    setMode(nextMode);
    setError("");
    setPassword("");
    setPasswordConfirmation("");
    setShowPassword(false);
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
            <p className="auth-access-label"><span aria-hidden="true" /> Secure Employee Access</p>
            <h1 id="auth-title">{mode === "login" ? "Welcome back" : "Create your profile"}</h1>
            <p className="auth-copy">
              {mode === "login" && "Sign in to continue."}
              {mode === "request" && "Complete your profile using your company signup link."}
            </p>
          </div>

          {mode === "login" && notice ? <p className="auth-notice" role="status">{notice}</p> : null}
          <form className="auth-form" onSubmit={handleSubmit} aria-busy={busy}>
            {mode === "request" ? (
              <div className="auth-name-grid">
                <label htmlFor="auth-first-name">First name
                  <input id="auth-first-name" value={firstName} onChange={(event) => setFirstName(event.target.value)} type="text" autoComplete="given-name" disabled={busy} />
                </label>
                <label htmlFor="auth-last-name">Last name
                  <input id="auth-last-name" value={lastName} onChange={(event) => setLastName(event.target.value)} type="text" autoComplete="family-name" disabled={busy} />
                </label>
              </div>
            ) : null}
            <label htmlFor="auth-email">Email</label>
            <input id="auth-email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" placeholder="name@organization.com" disabled={busy} />
            <label htmlFor="auth-password">Password</label>
            <input id="auth-password" value={password} onChange={(event) => setPassword(event.target.value)} type={showPassword ? "text" : "password"} autoComplete={mode === "request" ? "new-password" : "current-password"} placeholder={mode === "request" ? "At least 8 characters" : "Enter your password"} disabled={busy} />
            {mode === "request" ? <>
              <label htmlFor="auth-password-confirmation">Confirm password</label>
              <input id="auth-password-confirmation" value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} type={showPassword ? "text" : "password"} autoComplete="new-password" disabled={busy} />
            </> : null}
            <label className="auth-password-toggle">
              <input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)} disabled={busy} />
              <span>Show password{mode === "request" ? "s" : ""}</span>
            </label>
            {error ? <p className="auth-error" role="alert">{error}</p> : null}
            <button type="submit" className="command-button auth-submit" disabled={busy} aria-label={busy ? (mode === "request" ? "Creating profile..." : "Signing in...") : (mode === "request" ? "Create profile" : "Sign in")}>
              <span>{busy ? (mode === "request" ? "Creating profile..." : "Signing in...") : (mode === "request" ? "Create profile" : "Sign in")}</span>
              <span aria-hidden="true">→</span>
            </button>
            <button type="button" className="auth-switch" disabled={busy} onClick={() => switchMode(mode === "login" ? "request" : "login")}>
              {mode === "login" ? "Create Profile" : "Back to login"}
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
