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

  const response = await apiFetch(
    "/api/facility/cognition-state",
    { accessCode },
  );
  if (response.ok) {
    return response.json();
  }

  // Backward compatibility for deployments that have /facility/systems
  // but have not yet rolled out /facility/cognition-state.
  if (response.status === 404 || response.status >= 500) {
    const fallback = await apiFetch("/api/facility/systems", { accessCode });
    if (!fallback.ok) {
      // If both endpoints are unavailable on this deployment revision,
      // return a safe empty canonical state instead of breaking workflow UI.
      return emptyCanonicalState;
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

    return {
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
    };
  }

  return emptyCanonicalState;
}
