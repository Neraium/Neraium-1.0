export async function fetchCanonicalCognitionState({ apiFetch, accessCode }) {
  const emptyCanonicalState = {
    cognition_state: "Monitoring",
    structural_stability: "WATCH",
    active_archetypes: [],
    propagation_pathways: [],
    evidence_lineage: {},
    structural_memory_matches: [],
    continuation_windows: {
      window: "Monitoring",
      structural_pathways: [],
      uncertainty_range: [],
    },
    replay_summary: {
      frame_count: 0,
      canonical_flow: [],
      active_frame: {},
    },
    recovery_convergence: {},
    operator_explanation: "No structural cognition payload is available yet. Upload or connect telemetry to initialize operator workflow context.",
    source_mode: "live",
  };

  const latestUploadSnapshot = await readLatestUploadSnapshot({ apiFetch, accessCode });

  const response = await apiFetch(
    "/api/facility/cognition-state",
    { accessCode },
  );
  if (response.ok) {
    const state = await response.json();
    return mergeUploadBackedCognitionState(state, latestUploadSnapshot);
  }

  // Backward compatibility for deployments that have /facility/systems
  // but have not yet rolled out /facility/cognition-state.
  if (response.status === 404 || response.status >= 500) {
    const fallback = await apiFetch("/api/facility/systems", { accessCode });
    if (!fallback.ok) {
      // If both endpoints are unavailable on this deployment revision,
      // return a safe upload-backed state when an upload is active instead of
      // leaving the mission-control orb stuck in an empty state.
      return mergeUploadBackedCognitionState(emptyCanonicalState, latestUploadSnapshot);
    }
    const payload = await fallback.json();
    const intelligence = payload?.intelligence ?? {};
    const archetypes = Array.isArray(intelligence?.active_archetypes)
      ? intelligence.active_archetypes
      : [];
    const archetypeNames = archetypes.map((item) => (typeof item === "string" ? item : item?.name)).filter(Boolean);
    const propagationPaths = intelligence?.causality_graph?.dominant_pathways ?? [];
    const continuation = intelligence?.counterfactuals?.progression_scenarios?.[0] ?? {};
    const replay = intelligence?.replay_timeline ?? {};

    return mergeUploadBackedCognitionState({
      cognition_state: intelligence?.facility_state ?? "Monitoring",
      structural_stability: intelligence?.structural_stability_index?.state ?? "WATCH",
      active_archetypes: archetypeNames,
      propagation_pathways: propagationPaths,
      evidence_lineage: intelligence?.evidence_lineage ?? {},
      structural_memory_matches: intelligence?.structural_memory?.matches ?? [],
      continuation_windows: {
        window: continuation?.window ?? "Monitoring",
        structural_pathways: intelligence?.counterfactuals?.structural_continuation_pathways ?? [],
        uncertainty_range: intelligence?.counterfactuals?.progression_scenarios ?? [],
      },
      replay_summary: {
        frame_count: replay?.meta?.frame_count ?? (replay?.timeline?.length ?? 0),
        canonical_flow: replay?.meta?.canonical_flow ?? [],
        active_frame: replay?.timeline?.[replay?.timeline?.length - 1] ?? {},
      },
      recovery_convergence: intelligence?.recovery_convergence ?? {},
      operator_explanation:
        intelligence?.operator_explanation_v2?.narrative
        ?? intelligence?.operator_explanation_v2?.summary
        ?? "Evidence-backed structural cognition is available for operator review.",
      source_mode: "live",
    }, latestUploadSnapshot);
  }

  return mergeUploadBackedCognitionState(emptyCanonicalState, latestUploadSnapshot);
}

async function readLatestUploadSnapshot({ apiFetch, accessCode }) {
  try {
    const response = await apiFetch("/api/data/latest-upload", { accessCode });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

function mergeUploadBackedCognitionState(state, latestUploadSnapshot) {
  if (!hasActiveUpload(latestUploadSnapshot)) {
    return state;
  }

  const activeArchetypes = Array.isArray(state?.active_archetypes) ? state.active_archetypes.filter(Boolean) : [];
  const propagationPathways = Array.isArray(state?.propagation_pathways) ? state.propagation_pathways.filter(Boolean) : [];
  const hasSignals = activeArchetypes.length > 0 || propagationPathways.length > 0;

  if (hasSignals) {
    return state;
  }

  const filename = latestUploadSnapshot?.last_filename ?? "uploaded telemetry";
  const rows = latestUploadSnapshot?.rows_processed ?? 0;
  const columns = latestUploadSnapshot?.columns_detected ?? 0;
  const modelLabel = filename ? `${filename} active` : "Latest upload active";

  return {
    ...state,
    cognition_state: state?.cognition_state && state.cognition_state !== "Monitoring"
      ? state.cognition_state
      : "Active Session",
    structural_stability: state?.structural_stability && state.structural_stability !== "UNKNOWN"
      ? state.structural_stability
      : "WATCH",
    active_archetypes: ["TELEMETRY_ACTIVE"],
    propagation_pathways: propagationPathways,
    evidence_lineage: {
      ...(state?.evidence_lineage ?? {}),
      evidence_sources: {
        ...(state?.evidence_lineage?.evidence_sources ?? {}),
        topology_evidence: [
          `Uploaded telemetry is active: ${modelLabel}.`,
          rows > 0 || columns > 0
            ? `${rows} rows and ${columns} columns are available for structural review.`
            : "Telemetry import is available for structural review.",
        ],
      },
    },
    continuation_windows: {
      ...(state?.continuation_windows ?? {}),
      window: state?.continuation_windows?.window && state.continuation_windows.window !== "Monitoring"
        ? state.continuation_windows.window
        : "Monitoring active upload",
    },
    recovery_convergence: {
      ...(state?.recovery_convergence ?? {}),
      convergence_quality: state?.recovery_convergence?.convergence_quality ?? "monitoring",
    },
    operator_explanation:
      state?.operator_explanation && !String(state.operator_explanation).toLowerCase().includes("no structural cognition payload")
        ? state.operator_explanation
        : "Uploaded telemetry is active. Neraium is holding the facility in operator review while structural evidence and replay context are assembled.",
    source_mode: "uploaded",
  };
}

function hasActiveUpload(snapshot) {
  const status = String(snapshot?.status ?? "").toLowerCase();
  return Boolean(
    status === "active"
    || status === "baseline_active"
    || snapshot?.latest_result
    || snapshot?.state_available
    || snapshot?.last_filename
    || (snapshot?.rows_processed ?? 0) > 0
    || (snapshot?.columns_detected ?? 0) > 0
  );
}

