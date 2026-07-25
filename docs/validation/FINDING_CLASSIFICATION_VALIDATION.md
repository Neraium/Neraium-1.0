# Finding classification validation

Representative deterministic scenarios are defined in `tests/fixtures/finding_classification_scenarios.json`. Run `PYTHONPATH=./backend backend/.venv/bin/python scripts/generate_finding_classification_examples.py` to regenerate `finding-classification-examples.json` from the current explanation and canonical-contract layers.

| Scenario | Classification | Confidence | Data confidence | Mode match | First check |
| --- | --- | --- | --- | --- | --- |
| One-to-two pump staging transition | Known operational change | High | High | Weak, explained by recorded staging | Confirm the recorded equipment staging event. |
| Discharge-pressure peer divergence | Possible instrumentation issue | Limited | Limited | Strong | Verify discharge pressure against an independent source. |
| Persistent like-for-like relationship shift | Unexplained systemic change | High | High | Strong | Verify source data and control-state context. |
| Sparse baseline with irregular sampling | Insufficient evidence | Low | Low | Weak | Review the stated evidence limitations. |

Validation confirms:

- Low data confidence and insufficient relationship support prevent an unexplained systemic classification.
- Weak mode matching does not produce an unexplained systemic claim; a recorded staging change is presented as known operational context.
- Signal-health evidence is presented as a possible instrumentation issue and all instrumentation/data checks precede physical inspection.
- Unexplained systemic change is limited to persistent, supported, like-for-like relationship change and does not identify a cause or exact outcome.
- Every guidance item has a supported category, editable flag, deterministic rank, and evidence-linked reason.
- Timeline milestones use recorded source times/ranges or explicit broad period labels. Missing dates are not calculated.
- Legacy findings normalize to insufficient evidence/unavailable context and retain plain guidance as structured documentation checks.
- Generated engineer wording contains no assertion that equipment is failing, no exact failure prediction, and no repair or replacement instruction.
