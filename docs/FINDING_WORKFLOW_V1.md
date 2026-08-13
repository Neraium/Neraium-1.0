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
- status: `open`, `acknowledged`, `investigating`, `waiting`, `escalated`,
  `awaiting_review`, `monitoring`, `resolved`, or `dismissed`;
- recommended, user-selected, and effective priority;
- optional person or team assignment with a display label and external reference;
- assigner and append-only assignment/reassignment history;
- due date and manager note;
- optional work-order and external integration references;
- latest feedback;
- latest and historical structured technician field reports;
- validation outcome and note;
- resolution outcome, note, actor, and time.

Controlled resolution outcomes are `issue_found`, `no_issue_found`, `operational_change`, `sensor_issue`, and `maintenance_performed`. They are retained on the finding for future validation; they do not retroactively change the evidence or its confidence.

Person assignments with an `external_ref` use the existing auth account email/subject as
their stable member ID. New directory-backed person assignments must resolve to an active
account and project its canonical display name. `GET /api/findings/members` exposes only
the safe active-member projection (`member_id`, `display_name`, existing generic `role`,
and `is_active`). Label-only person assignments and team/reference assignments remain
readable and writable for historical compatibility; they are not treated as validated
identities. No team, organization, or enterprise identity model is implied. Work-order
fields remain integration hooks, not CMMS records.

Structured field reports record a concise note, what was inspected, what was found,
action taken, the `yes`/`no`/`uncertain` physical-problem result, escalation need, and
investigation completion. Each report is one immutable workflow event. An escalation
request projects the finding to `escalated`; a completed investigation without escalation
projects it to `awaiting_review`. Terminal `resolved` and `dismissed` findings reject new
field reports so a late direct API write cannot silently reopen completed work.

## API and concurrency

The API exposes:

- `GET /api/findings` with source/status, priority, system, assigned-to-me, assignee,
  unassigned, overdue, in-progress, awaiting-review, active, recently-resolved, and
  pagination filters. Workflow filters are applied before pagination;
- `GET /api/findings/members` for the authenticated active-member assignment picker;
- `GET /api/findings/{finding_id}`;
- `GET /api/findings/{finding_id}/activity`;
- `PATCH /api/findings/{finding_id}/workflow`;
- `POST /api/findings/{finding_id}/feedback`;
- `POST /api/findings/{finding_id}/field-reports`;
- `POST /api/findings/{finding_id}/resolution`.

Every mutation requires `expected_version`. A stale edit returns HTTP 409 with the current
version, allowing clients to reload instead of overwriting another operator's work.
Optional idempotency keys make retries replay-safe. Raw append-only events remain in the
activity response for audit consumers; the additive `activity` projection provides plain
human labels and includes the original detection event.

Production authorization uses the existing roles rather than introducing maintenance
RBAC. `operator` and `admin` retain lead/engineer workflow capability. A `viewer` can act
only when the current assignment is a validated active person assignment whose member ID
exactly matches the authenticated subject. That viewer may acknowledge, investigate,
wait, escalate, submit field reports, and complete to awaiting review; they cannot assign,
reprioritize, set dates/guidance, dismiss, resolve, or use engineering feedback mutations.
These checks are server-side. Existing non-production compatibility behavior and the
general `require_api_access` deployment assumptions remain unchanged.

Assignment never grants evidence or dataset access. Finding reads and writes continue to
use the persisted dataset/workspace scope. Cross-user shared operational visibility is
therefore intentionally deferred until an explicit shared workspace boundary exists;
per-user isolation is not weakened by this workflow.

## Legacy compatibility

Existing run-level lifecycle and feedback endpoints remain supported. Compatibility writes are centralized:

- an unambiguous one-finding evidence run records one canonical finding event and projects it into legacy reads;
- repeating the same compatibility request does not create duplicate events;
- an ambiguous historical run with multiple findings remains run-level and is never copied onto every finding;
- new finding-level endpoints do not also write legacy lifecycle rows;
- source provenance, package identity, replay, and audit history remain unchanged.

New evidence records include an immutable identity snapshot for every source finding so a multi-finding run can be materialized without guessing. Older records remain readable. Finding cases are scoped using the persisted dataset/workspace scope where it exists. Legacy live records without such scope retain their historical visibility behavior rather than letting the first reader claim new provenance.
