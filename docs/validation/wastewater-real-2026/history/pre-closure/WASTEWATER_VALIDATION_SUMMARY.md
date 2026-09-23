# Neraium retrospective wastewater validation

The current engine was frozen at commit `97d267d317fcce4b4424cf2141e97e87680acfc0`; production logic, thresholds and governance were unchanged.

- Analyzed 74,171 of 74,172 source rows across seven variables over a 259.6875-day record. One nonnumeric row was excluded by the existing historical wrapper; gaps and finite readings were preserved.
- A fixed first-week reference preceded 253 consecutive daily comparison windows. Twenty-one relationships produced 5,265 pair-window evaluations; 48 possible correlations were unavailable in constant-NH4 windows.
- Four pair-window observations across two relationships—NH4/NO3 and NO3/N2O—passed promotion and retained governed persistent-change flags. These are repeated evidence observations, not independently verified plant events.
- Broader graph evidence included 505 temporal-supported pair-windows across 12 relationships and 82 recurrence-supported pair-windows across six relationships. These channels can overlap and do not all qualify as promoted findings.
- All 253 windows had operating-context limitations. All 1,195 insight observations had unquantifiable measurable consequence; 46 were classified insufficient evidence. No physical loss, benefit or event-detection accuracy is established.
- All chronological input hashes and checkpoint state links verified. Three fixed fresh-process repeats matched the specified evidence outputs with source-column order preserved.

Outputs were frozen before external documentation was examined. A downloaded [Zenodo source](https://zenodo.org/records/21135508) was byte-identical; its metadata identifies full-scale Danish wastewater telemetry. No independent operating-event correspondence was established. This is retrospective real-data analysis, not deployment or prospective field validation.

[Full report](docs/validation/wastewater-real-2026/VALIDATION_REPORT.md) · [Findings](docs/validation/wastewater-real-2026/FINDINGS.md) · [Limitations](docs/validation/wastewater-real-2026/LIMITATIONS.md) · [Raw assessment](docs/validation/wastewater-real-2026/raw/assessment.json) · [Post-hoc context](docs/validation/wastewater-real-2026/POSTHOC_CONTEXT.md)
