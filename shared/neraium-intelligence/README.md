# Neraium Intelligence Core

This package contains the domain-independent contracts shared by Neraium
applications. It was extracted from the evidence-first architecture used by the
facilities product without changing that product's runtime behavior.

It owns:

- strict, serializable Evidence Package primitives;
- independent confidence/support dimensions (never an outcome probability);
- limitations and explicit unknowns;
- non-causal historical-comparison records;
- temporal eligibility and explainable weighted similarity;
- behavioral-memory repository protocols; and
- append-only JSONL Evidence Package persistence.

Domain applications own their data schemas, features, state models, feature
weights/scales, outcome observations, replay rules, and presentation.

Install for local development:

```bash
python -m pip install -e shared/neraium-intelligence
python -m pytest shared/neraium-intelligence/tests
```

