# LBNL validation summary

The engine was frozen at commit 97d267d317fcce4b4424cf2141e97e87680acfc0; production logic and thresholds were unchanged. The archive MD5 matched the supplied published checksum. All 22 usable LBNL simulated chiller-plant cases were tested with labels withheld until primary outputs, predefined repeats and audits were complete.

**The result is mixed, with poor separation on the predefined support-count endpoint.** All 21 fault cases and the fault-free case had some governed persistent evidence. The control had 34/120 supported periods; faults ranged from 6 to 47/120. Only six faults had more supported periods than the control, three tied and twelve had fewer (descriptive rank AUC 0.357 in the prespecified higher-count direction). This does not support a general claim that faults produce stronger or earlier evidence.

The supplementary matched-period comparison found different governed pair sets in at least one period for 19/21 fault cases. CASE_004 and CASE_013 (cooling-tower sensor biases −1°C and −2°C) had identical governed pair sets to fault-free operation in all 120 periods. They still had persistent evidence, so **no fault-specific difference on this endpoint** must be distinguished from **no persistent evidence at all**. No case supported recurrence. These are output comparisons against one simulation, not diagnostic accuracy.

Severity behavior was mixed. Stronger documented cooling-tower fouling increased supported periods (35 → 37 → 47); increasing leakage settings reduced them (36 → 18 → 15) and delayed first support. No engineering consequence was quantifiable in the governed outputs.

Reproducibility was limited: 720/720 relationship graphs matched after the predefined runtime exclusions, but only 5/720 complete governed analysis_result outputs did. Timestamp and ordering/summary discrepancies are retained. All 7,920 retained primary calls returned without module failure; the relevant production regression suite passed 117 tests. Earlier interrupted writes and first-save harness failures are disclosed in the full report.

The protocol uses exact hourly samples, fixed signal blocks, three-day comparisons and an earlier winter reference. One fault-free simulation, seasonal context, partial relationship coverage and substantial context/data-confidence limits prevent claims of broad discrimination or field performance. Controlled Neraium fixtures are a separate evidence source; no pooled accuracy is claimed. These findings establish no diagnosis, prediction, root cause, prescribed action or avoided failure.

[Full report](docs/validation/lbnl-blind-2026/VALIDATION_REPORT.md) · [Limitations](docs/validation/lbnl-blind-2026/LIMITATIONS.md) · [Evaluation](docs/validation/lbnl-blind-2026/raw/evaluation.json)
