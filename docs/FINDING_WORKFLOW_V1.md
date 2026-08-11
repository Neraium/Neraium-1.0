# Finding Workflow v1

Finding Workflow v1 is a lightweight operational sidecar for assigning, inspecting, and validating a Neraium finding. It does not modify analytical evidence, replace a CMMS, create work orders, or infer organizational authority that is not already represented by Neraium's API authorization model.

## Identity and immutability

Each workflow case points to one immutable source finding:

- evidence findings use a deterministic `evidence-finding-*` identity derived from the evidence run and its source finding key;
- live findings retain their existing `live-finding-*` identity;
- `source` records the source kind, source id, and original finding key;
- `evidence` is the immutable source snapshot used when the case was materialized.

Operational state is stored separately in `finding_cases` and append-only `finding_workflow_events`. Database constraints preserve the source identity and evidence snapshot, prevent deleting a case, and prevent updating or deleting workflow events. The current workflow view is a projection of those events.

## Workflow fields

The workflow projection includes:

- monotonically increasing `version`;
- status: `open`, `acknowledged`, `investigating`, `monitoring`, `resolved`, or `dismissed`;
- recommended, user-selected, and effective priority;
- optional person or team assignment with a display label and external reference;
- due date and manager note;
- optional work-order and external integration references;
- latest feedback;
- validation outcome and note;
- resolution outcome, note, actor, and time.

Controlled resolution outcomes are `issue_found`, `no_issue_found`, `operational_change`, `sensor_issue`, and `maintenance_performed`. They are retained on the finding for future validation; they do not retroactively change the evidence or its confidence.

Assignment labels are lightweight references, not a Neraium user directory. Work-order fields are integration hooks, not CMMS records.

## API and concurrency

The API exposes:

- `GET /api/findings` with source, status, and pagination filters;
- `GET /api/findings/{finding_id}`;
- `GET /api/findings/{finding_id}/activity`;
- `PATCH /api/findings/{finding_id}/workflow`;
- `POST /api/findings/{finding_id}/feedback`;
- `POST /api/findings/{finding_id}/resolution`.

Every mutation requires `expected_version`. A stale edit returns HTTP 409 with the current version, allowing clients to reload instead of overwriting another operator's work. Optional idempotency keys make retries replay-safe. Reads use the existing API-access boundary; mutations use the existing operator-role boundary and audit logging. No manager- or engineer-specific authorization role is introduced.

## Legacy compatibility

Existing run-level lifecycle and feedback endpoints remain supported. Compatibility writes are centralized:

- an unambiguous one-finding evidence run records one canonical finding event and projects it into legacy reads;
- repeating the same compatibility request does not create duplicate events;
- an ambiguous historical run with multiple findings remains run-level and is never copied onto every finding;
- new finding-level endpoints do not also write legacy lifecycle rows;
- source provenance, package identity, replay, and audit history remain unchanged.

New evidence records include an immutable identity snapshot for every source finding so a multi-finding run can be materialized without guessing. Older records remain readable. Finding cases are scoped using the persisted dataset/workspace scope where it exists. Legacy live records without such scope retain their historical visibility behavior rather than letting the first reader claim new provenance.
