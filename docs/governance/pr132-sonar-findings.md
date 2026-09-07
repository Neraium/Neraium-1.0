# PR #132 SonarCloud findings

Reviewed source: `48d77027726547322b3b25414933762fdc957dd6` on `evidence-governance-phase2`.

Sources: [Sonar analysis](https://sonarcloud.io/dashboard?id=Neraium_Neraium-1.0&pullRequest=132),
[issue API](https://sonarcloud.io/api/issues/search?componentKeys=Neraium_Neraium-1.0&pullRequest=132&resolved=false&ps=100),
[quality gate API](https://sonarcloud.io/api/qualitygates/project_status?projectKey=Neraium_Neraium-1.0&pullRequest=132).

The failed condition was `new_reliability_rating`: actual `3` (C), maximum `1` (A).
The only BUG was `python:S1244`, an exact comparison of the method's fixed significance
threshold against `0.05`. This is category C: exact equality is intentional for this
method contract, and approximate equality would allow a different parameter.
The fix compares canonical JSON representations, consistent with the retained-statistics
comparison in the same validator. Adjacent floating-point values remain rejected.
No suppression or quality-gate configuration change is used.

The other 41 findings are category B. Small helper extractions preserve validation
order, outcome precedence, statistical arithmetic, and serialized records. Test
refactors move setup outside expected-exception blocks and split composite assertions.
There are no category A findings. The gate failure itself is category D, caused by the
category C issue above; it is not a coverage failure. The other reported gate conditions
passed: security A, maintainability A, duplication 0.0%, hotspots reviewed 100.0%.

Severity below is Sonar's reported `severity`, not the adversarial review severity.
Each row is one issue; file lines refer to the reviewed source before refactoring.

| Rule ID | Severity | File | Line | Exact complaint | Category |
| --- | --- | --- | ---: | --- | --- |
| `python:S3776` | CRITICAL | `backend/app/governance/authority_store.py` | 340 | Refactor this function to reduce its Cognitive Complexity from 20 to the 15 allowed. | B: maintainability/code quality |
| `python:S3776` | CRITICAL | `backend/app/governance/context.py` | 139 | Refactor this function to reduce its Cognitive Complexity from 20 to the 15 allowed. | B: maintainability/code quality |
| `python:S3776` | CRITICAL | `backend/app/governance/maturity.py` | 112 | Refactor this function to reduce its Cognitive Complexity from 26 to the 15 allowed. | B: maintainability/code quality |
| `python:S7498` | MINOR | `backend/app/governance/maturity.py` | 162 | Replace this constructor call with a literal. | B: maintainability/code quality |
| `python:S3776` | CRITICAL | `backend/app/governance/policy.py` | 112 | Refactor this function to reduce its Cognitive Complexity from 35 to the 15 allowed. | B: maintainability/code quality |
| `python:S7496` | MINOR | `backend/app/governance/policy.py` | 194 | Replace this set constructor call by a set literal. | B: maintainability/code quality |
| `python:S3776` | CRITICAL | `backend/app/governance/tiers.py` | 57 | Refactor this function to reduce its Cognitive Complexity from 16 to the 15 allowed. | B: maintainability/code quality |
| `python:S3776` | CRITICAL | `backend/app/governance/tiers.py` | 76 | Refactor this function to reduce its Cognitive Complexity from 34 to the 15 allowed. | B: maintainability/code quality |
| `python:S3358` | MAJOR | `backend/app/governance/tiers.py` | 111 | Extract this nested conditional expression into an independent statement. | B: maintainability/code quality |
| `python:S3776` | CRITICAL | `backend/app/governance/trend.py` | 49 | Refactor this function to reduce its Cognitive Complexity from 25 to the 15 allowed. | B: maintainability/code quality |
| `python:S1244` | MAJOR | `backend/app/governance/trend.py` | 64 | Do not perform equality checks with floating point values. | C: false positive |
| `python:S3358` | MAJOR | `backend/app/governance/trend.py` | 85 | Extract this nested conditional expression into an independent statement. | B: maintainability/code quality |
| `python:S3358` | MAJOR | `backend/app/governance/trend.py` | 87 | Extract this nested conditional expression into an independent statement. | B: maintainability/code quality |
| `python:S3776` | CRITICAL | `backend/app/governance/trend.py` | 93 | Refactor this function to reduce its Cognitive Complexity from 24 to the 15 allowed. | B: maintainability/code quality |
| `python:S7498` | MINOR | `backend/app/governance/trend.py` | 119 | Replace this constructor call with a literal. | B: maintainability/code quality |
| `python:S3358` | MAJOR | `backend/app/governance/trend.py` | 131 | Extract this nested conditional expression into an independent statement. | B: maintainability/code quality |
| `python:S3358` | MAJOR | `backend/app/governance/trend.py` | 134 | Extract this nested conditional expression into an independent statement. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 119 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 121 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 148 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 152 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 179 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S9073` | MAJOR | `tests/test_governance_phase2.py` | 211 | Split this composite assertion into separate assertions. | B: maintainability/code quality |
| `python:S9073` | MAJOR | `tests/test_governance_phase2.py` | 217 | Split this composite assertion into separate assertions. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 246 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 269 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S9073` | MAJOR | `tests/test_governance_phase2.py` | 298 | Split this composite assertion into separate assertions. | B: maintainability/code quality |
| `python:S9073` | MAJOR | `tests/test_governance_phase2.py` | 313 | Split this composite assertion into separate assertions. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 359 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 371 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S9073` | MAJOR | `tests/test_governance_phase2.py` | 385 | Split this composite assertion into separate assertions. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 388 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 447 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2.py` | 451 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S9073` | MAJOR | `tests/test_governance_phase2.py` | 532 | Split this composite assertion into separate assertions. | B: maintainability/code quality |
| `python:S9073` | MAJOR | `tests/test_governance_phase2.py` | 536 | Split this composite assertion into separate assertions. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2_adversarial.py` | 86 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2_adversarial.py` | 93 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S9073` | MAJOR | `tests/test_governance_phase2_adversarial.py` | 132 | Split this composite assertion into separate assertions. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2_adversarial.py` | 168 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |
| `python:S9073` | MAJOR | `tests/test_governance_phase2_adversarial.py` | 189 | Split this composite assertion into separate assertions. | B: maintainability/code quality |
| `python:S5778` | MAJOR | `tests/test_governance_phase2_adversarial.py` | 270 | Refactor this exception test to have only one invocation possibly throwing an exception. | B: maintainability/code quality |

Validation before push:

- Directly affected Phase 2 and adversarial tests: 151 passed.
- Full governance suite: 272 passed (the prior 268 plus four exact-threshold cases).
- Differential verification against the reviewed source: 155 serialized result cases
  matched byte for byte, including content IDs, for trend, maturity, context,
  tier classification, policy evaluation, and decision/basis records.
- `git diff --check`: passed.

The first rerun at `a288565b95416a26ca165559a04c8f773057c393` passed the gate and
closed 41 issues. It retained the following category B issue:

| Rule ID | Severity | File | Line at first rerun | Exact complaint | Category |
| --- | --- | --- | ---: | --- | --- |
| `python:S3776` | CRITICAL | `backend/app/governance/maturity.py` | 129 | Refactor this function to reduce its Cognitive Complexity from 16 to the 15 allowed. | B: maintainability/code quality |

The follow-up extracts the existing current-context validation checks into a helper;
validation order and error messages remain unchanged.

Follow-up validation: 151 directly affected tests and 272 governance tests passed;
all 155 serialized result cases still matched the reviewed source byte for byte.
The report's punctuation was corrected after the repository copy audit rejected
em dashes; all five copy-audit tests now pass. `git diff --check` passed.
