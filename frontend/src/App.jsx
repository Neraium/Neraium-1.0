import { lazy, Suspense, useCallback, useEffect, useState } from "react";

import WorkspaceLoadingState from "./components/WorkspaceLoadingState";
import { fetchCurrentUser } from "./services/api/authApi";
import { clearDatasetSessionCache } from "./services/datasetSessionCache";

const AuthScreen = lazy(() => import("./components/AuthScreen"));
const AuthenticatedApp = lazy(() => import("./AuthenticatedApp"));

function App() {
  const [authState, setAuthState] = useState({
    status: "checking",
    user: null,
    notice: "",
    errorKind: null,
  });
  const [authCheckAttempt, setAuthCheckAttempt] = useState(0);

  const resetSignedOutSession = useCallback(() => {
    clearDatasetSessionCache();
  }, []);

  const handleAuthenticated = useCallback((user) => {
    setAuthState({ status: "authenticated", user, notice: "", errorKind: null });
  }, []);

  const handleSignedOut = useCallback((notice = "Sign in to continue.") => {
    resetSignedOutSession();
    setAuthState({ status: "signed-out", user: null, notice, errorKind: null });
  }, [resetSignedOutSession]);

  const handleRetrySession = useCallback(() => {
    setAuthState({ status: "checking", user: null, notice: "", errorKind: null });
    setAuthCheckAttempt((current) => current + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    fetchCurrentUser({ signal: controller.signal })
      .then((payload) => {
        if (cancelled) return;
        if (payload?.authenticated && payload?.user) {
          handleAuthenticated(payload.user);
          return;
        }
        handleSignedOut("Sign in to continue.");
      })
      .catch((error) => {
        if (cancelled || error?.name === "AbortError") return;
        const errorKind = ["backend-unavailable", "malformed-response", "timeout"].includes(error?.kind)
          ? error.kind
          : "backend-unavailable";
        setAuthState({
          status: "error",
          user: null,
          notice: String(error?.message ?? "Unable to verify your session. Retry session verification."),
          errorKind,
        });
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [authCheckAttempt, handleAuthenticated, handleSignedOut]);

  if (authState.status === "checking") {
    return <WorkspaceLoadingState label="Opening Neraium" detail="Checking your secure session." fullScreen />;
  }

  if (authState.status === "error") {
    const errorLabel = authState.errorKind === "timeout"
      ? "Session verification timed out"
      : authState.errorKind === "malformed-response"
        ? "Session response unavailable"
        : "Session service unavailable";
    return (
      <WorkspaceLoadingState
        label={errorLabel}
        detail={authState.notice}
        fullScreen
        variant="error"
        actionLabel="Retry"
        onAction={handleRetrySession}
      />
    );
  }

  if (authState.status !== "authenticated" || !authState.user) {
    return (
      <Suspense fallback={<WorkspaceLoadingState label="Opening secure access" detail="Loading sign-in." fullScreen />}>
        <AuthScreen notice={authState.notice} onAuthenticated={handleAuthenticated} />
      </Suspense>
    );
  }

  const userKey = String(authState.user.email ?? authState.user.id ?? "authenticated");
  return (
    <Suspense fallback={<WorkspaceLoadingState label="Opening workspace" detail="Loading the application runtime." fullScreen />}>
      <AuthenticatedApp key={userKey} currentUser={authState.user} onSignedOut={handleSignedOut} />
    </Suspense>
  );
}

export default App;
