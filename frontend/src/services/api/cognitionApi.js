export async function fetchCanonicalCognitionState({ apiFetch, accessCode, mode = "live" }) {
  const response = await apiFetch(
    `/api/facility/cognition-state?mode=${encodeURIComponent(mode)}`,
    { accessCode },
  );
  if (response.ok) {
    return response.json();
  }

  // Backward compatibility for deployments that have /facility/systems
  // but have not yet rolled out /facility/cognition-state.
  if (response.status === 404) {
    const fallback = await apiFetch("/api/facility/systems", { accessCode });
    if (!fallback.ok) {
      throw new Error(`Unexpected response: ${fallback.status}`);
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
      source_mode: mode,
    };
  }

  throw new Error(`Unexpected response: ${response.status}`);
}
