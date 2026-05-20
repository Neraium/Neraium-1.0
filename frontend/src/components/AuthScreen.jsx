import { useState } from "react";
import { loginUser, signupUser } from "../services/api/authApi";

export default function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError("Email and password are required.");
      return;
    }
    if (mode === "signup" && password.trim().length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload = mode === "signup"
        ? await signupUser({ name: name.trim(), email: email.trim(), password })
        : await loginUser({ email: email.trim(), password });
      if (typeof onAuthenticated === "function") {
        onAuthenticated(payload?.user ?? null);
      }
    } catch (submitError) {
      setError(String(submitError?.message ?? "Authentication failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-panel">
        <p className="auth-kicker">Neraium Access</p>
        <h1>{mode === "signup" ? "Create Your Account" : "Sign In"}</h1>
        <p className="auth-copy">
          {mode === "signup"
            ? "Create an operator account to access telemetry upload and analysis."
            : "Sign in to continue to your facility control and intelligence workspace."}
        </p>
        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "signup" ? (
            <label>
              Name
              <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Operator name" autoComplete="name" />
            </label>
          ) : null}
          <label>
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@facility.com" autoComplete="email" />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" autoComplete={mode === "signup" ? "new-password" : "current-password"} />
          </label>
          {error ? <p className="auth-error">{error}</p> : null}
          <button type="submit" className="command-button auth-submit" disabled={busy}>
            {busy ? "Working..." : (mode === "signup" ? "Create Account" : "Sign In")}
          </button>
        </form>
        <button
          type="button"
          className="auth-switch"
          onClick={() => {
            setMode((current) => (current === "login" ? "signup" : "login"));
            setError("");
          }}
          disabled={busy}
        >
          {mode === "login" ? "Need an account? Create one" : "Already have an account? Sign in"}
        </button>
      </div>
    </div>
  );
}

