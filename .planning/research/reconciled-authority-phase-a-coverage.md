# Reconciled Authority Phase A Coverage

Date: 2026-08-27

Binding source: reconciliation commit `837a4839972e5a1a34fca2436ffb489988e10f1d`, especially `.planning/research/reconciled-master-acceptance-plan.md`.

Phase A coverage below means a pure type, deterministic identity, serialization, or validator can express/reject the stated condition. It does not claim that scheduling, storage, publication, crash recovery, projection routing, frontend behavior, learning, parity, or cutover is implemented.

## P0.2 event-time A-Z

| Risk | Phase A invariant / test target | Later implementation evidence |
|---|---|---|
| ET-A | Chronology identity excludes arrival order; unordered semantic sets canonicalize before digest | Phase C shadow chronology; Phase F parity |
| ET-B | No ingestion/processing timestamp field exists in chronology equality; future state is explicit | Phase C readiness/quarantine; Phase H active routing |
| ET-C | Poll/page/run identifiers are absent from slot identity | Phase C manifest assembly; Phase F parity |
| ET-D | Canonical observation UUID is a typed existing wrapper and is absent from semantic slot identity | Phase C semantic-manifest comparison; P0.1 regressions |
| ET-E | Source run is retained only by native P0.1 identity and excluded from chronology slot | Phase C duplicate-learning guard; Phase H publication |
| ET-F | Slots carry half-open contribution/lookback bounds and generation, allowing an ascending bounded sequence | Phase C backfill planner; Phase G apply-once |
| ET-G | `historical_non_learning` and exact causal predecessor/reference are representable; missing reference fails closed | Phase C resolver; Phase H runtime enforcement |
| ET-H | Late-before-freeze disposition is representable without changing identity rules | Phase C late-data transition service |
| ET-I | Manifest/input digest is an execution-ID input, so mutation creates a different execution | Phase C claim invalidation; Phase H CAS |
| ET-J | Stale/prepublication-rejected disposition is representable; no stale-publication behavior is implemented | Phase H publication CAS/fault tests |
| ET-K | Postpublication-late-impact disposition is separate from immutable published identity | Phase C impact records; Phase H publication immutability |
| ET-L | Later-frontier historical/replay modes and non-active generation are representable | Phase C resolver; future authorized replay work |
| ET-M | Same slot/manifest/predecessor tuple yields the same execution ID (retry identity) | Phase G apply receipt; Phase H recovery |
| ET-N | Changed immutable manifest/predecessor/generation mutates execution ID; no automatic active generation exists | Phase C authorization; Phase H publication |
| ET-O | `analyzing` lifecycle can be carried without customer authority/finalization | Phase H recovery before publication |
| ET-P | Blocked/failed plan disposition is representable and cannot be called finalized | Phase G inert stage/apply fault tests |
| ET-Q | Staged-orphan/inert state can be described without active-learning semantics | Phase G orphan reconciliation |
| ET-R | Pending/finalized learning states are distinct while exact execution identity remains stable | Phase G receipts; Phase H finalization recovery |
| ET-S | Ordered identity sets preserve declared order; unordered sets sort; no arrival/UUID tie-break field exists | Phase C equal-time semantic conflict detection |
| ET-T | UTC-aware microsecond timestamps and explicit configuration identity are required; no timezone default exists | Phase C normalization/reference integration |
| ET-U | Invalid/missing timestamp disposition and ineligible outcome are representable; no processing fallback field exists | Phase C quarantine; Phase D authority adapter |
| ET-V | Future-quarantined state plus unresolved FutureSkewConfiguration fail closed | Phase C release policy; Phase H routing |
| ET-W | `stable_no_change` validates exactly zero findings | Phase D publisher; Phase H progress; Phase I/J projections |
| ET-X | `insufficient_evidence` is distinct, completed, and exactly zero findings without richer P0.4 meaning | Phase D adapter; Phase H progress; P0.4 separate |
| ET-Y | Native -> authority -> package typed chain and exact-scope projection envelope prevent identity aliasing | Phase E package; Phase I/J sticky routing |
| ET-Z | New modules have no Health Relevance imports/edits; changed-path and existing fixed-input regressions are gates | Every later phase; especially Phase F and final cutover |

Additional Phase A cadence checks validate only explicitly supplied configured fixtures: positive `C`, `C <= L`, exact divisibility, aware UTC origin, and configuration mutation sensitivity. No production cadence, origin, edge policy, overlap policy, lateness, or future-skew value is selected.

## P0.3 AT-R01–AT-R36

| Risk | Phase A invariant / test target | Later implementation evidence |
|---|---|---|
| AT-R01 | Terminal-outcome/finding cardinality validator owns count independently of native metadata | Phase D publisher; Phase F parity |
| AT-R02 | Finding IDs use one semantic occurrence tuple; duplicate IDs and ambiguous bindings are rejected | Phase D lossless adapter; Phase F disagreement fixtures |
| AT-R03 | Native result identity and authoritative finding-set digest are different typed members | Phase D adapter; Phase E package |
| AT-R04 | Projection envelope keeps authoritative total/set digest when returned page is partial | Phase I backend projections; Phase J frontend consumption |
| AT-R05 | Envelope names exactly one authority execution; no candidate-precedence contract exists | Phase I routing; Phase J removal of reconstruction |
| AT-R06 | Finding identity excludes presentation grouping and is immutable | Phase I grouping DTO; Phase J presentation-only behavior |
| AT-R07 | Stable requires zero findings; workflow counts cannot alter authoritative total | Phase D publisher; Phase I/J projections |
| AT-R08 | Canonical completeness rejects partial authority; omissions belong only to projection envelope | Phase E package; Phase I legacy projection; Phase M policy cleanup |
| AT-R09 | Exact finding IDs/count are bound independently of summary/export records | Phase D adapter; Phase I projections |
| AT-R10 | WorkflowCaseIdentity requires exact authority plus finding (or future approved series namespace) | Phase I workflow overlay; Phase K legacy handling |
| AT-R11 | Unavailable completeness is explicit and cannot contain returned analytical objects | Phase I transport mismatch handling; Phase J frontend |
| AT-R12 | Finding occurrence includes authority execution and cannot be mutable workflow identity | Phase D live publisher; Phase K retirement |
| AT-R13 | Only typed EvidenceFact plus EvidenceBinding can enter a finding evidence set | Phase D adapter; Phase E package |
| AT-R14 | Narrative text has no evidence qualification constructor or identity role | Phase I narrative projection; Phase J presentation |
| AT-R15 | Evidence fact identity is stored once per execution and bindings reference it | Phase E section builder; Phase L structural-copy retirement |
| AT-R16 | One independently derived complete AnalyticalReference is required | Phase C resolver; Phase D publisher; Phase F parity |
| AT-R17 | Native reference metadata cannot satisfy typed AnalyticalReference equality | Phase D adapter; Phase F mismatch fixtures |
| AT-R18 | Analytical reference participates in finding identity, so version/reference mutation changes occurrence | Phase D publisher; Phase K live retirement |
| AT-R19 | Digests carry algorithm+contract and versions are equality-bound; cross-kind substitution fails | Phase D/E validation; Phase F corruption fixtures |
| AT-R20 | Exactly one `deterministic_finding_classification_v3` binding is required per finding; value/trace are output-integrity-bound | Phase D single invocation; Phase F parity |
| AT-R21 | Exactly one lossless immutable structured `finding-confidence-v1` payload with output integrity; aggregate is explicitly undefined/P0.5-dependent | Phase D adapter; Phase I projection; P0.5 if aggregate required |
| AT-R22 | Exactly one structured, output-integrity-bound PersistenceAssessment or explicit non-lossless P0.5 dependency | Phase D lossless adapter; Phase F parity; P0.5 for disagreement |
| AT-R23 | Workflow identity/state is outside analytical equality and cardinality | Phase I workflow overlay; Phase J presentation |
| AT-R24 | Evidence binding validates same authority execution, exact finding, and exact scope/connection | Phase E package/index; Phase I Evidence Record |
| AT-R25 | VersionBundle is typed, unique, deterministic, and equality-bound | Phase D/E publisher/package; Phase I DTO |
| AT-R26 | Projection envelope validates exact authority/package/native identities and typed integrity inputs | Phase E package verification; Phase I transport selection |
| AT-R27 | CanonicalAuthorityPackage has a distinct namespace/version from both legacy package families | Phase E builder; Phase M terminology/deprecation |
| AT-R28 | Package/export association requires exact authority and optional exact finding | Phase E manifest; Phase I export projection |
| AT-R29 | NativeExecutionBinding requires an immutable terminal source identity and typed integrity | Phase D publisher; Phase H atomic publication |
| AT-R30 | Cursor/reference is an integrity-bound locator, never analytical identity or latest fallback | Phase I cursor/cache; Phase J browser history |
| AT-R31 | Analytical finding ID includes authority execution; legacy condition IDs cannot compare equal | Phase D adapter; Phase K legacy retirement |
| AT-R32 | Workflow case and analytical finding use distinct typed namespaces and exact refs | Phase I workflow; Phase J routes; Phase K legacy |
| AT-R33 | Authority status is distinct from completeness and workflow state | Phase I transport DTO; Phase J labels |
| AT-R34 | Frozen fact integrity/identity excludes read-time annotation state | Phase E package; Phase I reads |
| AT-R35 | Related-package/sidecar IDs have no evidence-binding role in Phase A contracts | Phase I related projection; Phase M cleanup |
| AT-R36 | Integrity equality requires exact algorithm and contract; historical digest aliases fail | Phase E verifier; Phase I legacy reads |

## P1.2 readiness boundary

Phase A supplies package metadata, ordered section descriptors, fully scoped object index descriptors, typed version bundles, package/section/object integrity, package completeness, and the common bounded projection envelope. Phase E remains responsible for deterministic package construction and any compression; Phase B remains responsible for storage; Phase I remains responsible for backend projections. Phase A performs none of those runtime actions.
