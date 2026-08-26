# SII authority boundaries

This document defines which repository capabilities may participate in customer-facing analytical authority. Code presence, serialization support, a test fixture, or a research document does not by itself make a capability a production result.

## Production

Production SII is evidence-qualified, read-only, system-level infrastructure intelligence. The normal path is:

```text
scoped telemetry
  -> authoritative SII analysis
  -> qualified evidence and explicit limitations
  -> finding/status classification
  -> Results -> Finding Review -> Investigation -> Evidence Record
```

Production output may describe observed behavioral displacement, relationship change, persistence, operating context, data quality, sensor health, temporal or multivariate support, expected-behavior residuals, and qualified structural paths. It preserves tenant, facility, system, asset, method/version, source-window, and evidence lineage where available.

Production does not establish root cause, predict failure or remaining useful life, control equipment, or infer fleet behavior from one upload. Review windows are operational scheduling aids, not predicted failure times. Relationship and path evidence is non-causal unless a separately approved causal evidence contract says otherwise.

The production upload replay is the telemetry-derived analysis trace used by Investigation and Evidence Record. It is distinct from structural-cognition research simulations. The compatibility `evidence_lineage` field remains available alongside the formal production traceability and evidence contracts; it does not make the surrounding research facade authoritative.

## Internal and experimental

The structural-cognition packages are retained for research and isolated component testing. This includes heuristic causality, counterfactual scenarios, structural archetypes and static memory matching, synthetic multi-facility/site construction, simulation, federation/exchange packages, training packages, structural search, alternate stability/cognition composites, and aggregate behavioral-twin packaging.

These packages do not participate in the default upload result, formal finding classification, or customer explanation. They must not be enabled by a normal customer query flag or reconstructed by the frontend. Their terminology describes research objects, not shipped production authority.

This boundary does not apply to the separately governed production behavioral-model architecture documented in [Unified SII Architecture](sii_architecture.md). Persisted behavioral models, expected-behavior evidence, and qualified behavioral graph comparisons remain production evidence when their identity, scope, lineage, and method contracts are satisfied.

## Static and reference

Standards, ontologies, certification/reference packs, language guides, architecture references, case studies, and curricula are repository reference material. They are not per-run evidence and are not embedded in normal upload results. Reference documents may describe proposed contracts or vocabulary, but must be read as static material unless a production contract explicitly adopts them.

## Future

Cross-system, cross-facility, fleet, federated, causal, counterfactual, independently validated digital-twin, and predictive-maintenance capabilities are not production-qualified merely because prototypes exist. Promotion requires a separately approved evidence contract, scoped real-world data, validation, uncertainty and limitation handling, method/version lineage, product integration, and regression coverage.

Until that promotion occurs, customer surfaces must render correctly without those fields and must not synthesize substitutes.

## Presentation boundary

- Results is triage only.
- Finding Review presents what changed, why it deserves attention, evidence strength, important limitations, whether cause is established, and concise engineering checks.
- Investigation presents qualified technical evidence, including baseline/current behavior, relationships, persistence, operating context, temporal and multivariate evidence, data quality, source signals, lineage, and legitimate replay/timing context.
- Evidence Record preserves deep production provenance and audit detail. It is not an outlet for experimental structural-cognition packages.

Customer explanations remain conservative and read-only: what changed, why it deserves review, what evidence supports it, what is unknown, and what engineering should investigate next.
