# Independent resource-binding certification

DECISION: RESOURCE_BINDING_BLOCKED_OWNERSHIP

## Scope and baseline

Branch `fix/deterministic-governed-output`; HEAD
`a922c496fa2baeac63b7c882a640d8e6b58caa90`. Read AGENTS.md and
`resource-binding-candidate.md`. Inspected the production diff, new resource
binding implementation, candidate fixtures/attacks, and changed comparison tests.
The index is empty. This certification changes no production or tests, performs
no fixes, and does not resume relationship-authority implementation. This report
is the only new certification artifact.

## Material defect — original-finding attachment bypasses source validation

**P1: Validate the destination finding before borrowing an original consequence
input.** In `backend/app/services/measurable_consequence.py:306–319`, attachment
compares tuple strings, window, and selected context/persistence fields, then
passes only `candidates[0]` to `build_measurable_consequence`. The destination
finding is never passed to the certified resolver. Its conflicting
`relationship_source_evidence` is consequently ignored.

An independently executed component-substitution diagnostic reproduced:

| Check | Result |
|---|---|
| Certified resolver on destination, temporal required | Rejected (`None`) |
| Direct consequence adapter on destination | `not_quantifiable` |
| Attachment using the same-ID original | **`quantified`** |
| Attached cumulative amount | **12839.999999999996** |

The destination retained A's exact tuple, ID, window, and qualification fields,
but carried the intact source payload from another relationship B. No tuple,
registry record, resource binding, or digest was changed or recomputed during
the attack. Original finding, resource evidence, catalog, and registry remained
unchanged. This is an attachment-boundary validation bypass, not a claim of an
external endpoint exploit or a break of the integrity hash.

The candidate's direct `raw_source` attack does reject the conflict. Its
attachment tests cover other-owner tuples, missing ownership, duplicate/missing
originals, and context/window/persistence changes, but omit this same-tuple,
conflicting-source case. Passing those tests therefore does not establish the
required rejection at both consumer paths.

Expected behavior: a destination rejected by the certified source/assessment
resolver must remain non-quantifiable when passed through attachment. A same-ID
original must not rescue it. This is material to the explicitly requested
conflicting-source and broad-original-borrowing rejection requirements.

## Reproduction

Executed as an inline diagnostic with
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python`:

```python
from copy import deepcopy
from math import isclose
from app.services.relationship_evidence_binding import SOURCE, REGISTRY, resolve
from app.services.resource_relationship_binding import ownership
from app.services.measurable_consequence import (
    build_measurable_consequence, attach_measurable_consequences,
)
from resource_binding_cases import assessment
from test_measurable_consequence import fixture

original, expected, catalog = fixture()
registry = assessment()[1]
donor = assessment(columns=('flow', 'other_load'))[0]
destination = deepcopy(original)
destination[SOURCE] = deepcopy(donor[SOURCE])
saved = deepcopy((original, expected, catalog, registry))
assert ownership(destination) == ownership(original)
assert resolve(destination, registry, authorized_scope=registry['scope'],
               require_temporal=True) is None
direct = build_measurable_consequence(
    destination, expected_behavior=expected, signal_catalog=catalog,
    relationship_registry=registry, authorized_scope=registry['scope'],
)
assert direct['status'] == 'not_quantifiable'
attach_measurable_consequences(
    {'conditions': [destination]},
    source={REGISTRY: registry, 'sii_result': {'expected_behavior': expected},
            'telemetry_signal_catalog': catalog},
    original_findings=[original],
)
attached = destination['measurable_consequence']
assert attached['status'] == 'quantified'  # Reproduced defect, not desired behavior.
assert isclose(attached['cumulative_amount'], 12840, rel_tol=1e-12)
assert saved == (original, expected, catalog, registry)
```

## Focused tests and freeze assessment

The following run was started before the independent diagnostic identified the
defect and was allowed to finish. No additional validation campaign was started
after the defect. Result: **128 passed**, two warnings, 61.06 seconds.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q tests/test_resource_relationship_binding.py tests/test_measurable_consequence.py tests/test_relationship_assessment_binding.py tests/test_relationship_binding_ownership.py tests/test_relationship_evidence_binding.py tests/test_telemetry_result_projection.py tests/test_sii_evidence_transport.py
```

This includes positive consequence equality with committed HEAD for eligible
fixtures and gate variants, resource attacks, same-source assessment substitution
regressions, fallback, historical reads, producer tests, upload transport, and
connector projection. Group/rank/primary/order invariance checks also passed.
The independent attachment diagnostic demonstrates a gap in that green coverage.

ANALYTICAL_MATH_CHANGED: NO

No numerical calculation change was found in the inspected diff. The certified
binding implementation, relationship change/recurrence reducers, relationship
graph, finding classifier, condition corroboration, runtime governance, and
telemetry analysis window have no diff against HEAD. Producer numerical equality
and consequence invariance tests passed. There are no changes to control,
presentation templates, telemetry admission, or production temporal continuation
in the candidate diff. Nevertheless, consequence ownership/gate preservation
cannot be certified because of the attachment bypass above.

Historical compatibility checks passed for their covered read paths; no historical
reconstruction, migration, reanalysis, or production record mutation was performed.
No broad regression, LBNL, wastewater, scale, performance, or browser campaign ran.

## Disposition

Stopped certification on the material defect. No production/test fix was attempted.
`git diff --check` passed; the new report also passed a no-index whitespace check.
No staging, commit, or push.

Commit allowlist: **not issued**.
Commit subject: **not issued**.

Next action: obtain a separately authorized correction of destination validation
at the attachment boundary and add the corresponding regression, then request
recertification. Do not commit this candidate as certified.
