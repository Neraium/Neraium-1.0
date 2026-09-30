# Henderson blind historical PoV — data request

Please provide one anonymized CSV and a short acquisition note covering the
items below. Plain-language documentation is sufficient: Neraium will encode the
reviewed declarations and generate hashes, IDs and the analysis profile. This
adapter assesses **one preselected pair in one comparable operating context**.

## REQUIRED

* **Immutable anonymized export:** retain the exact delivered CSV bytes and a
  recoverable original. Use opaque filenames and signal names. Supply a UTF-8,
  comma-delimited CSV with a header, timestamps and **exactly two selected numeric
  signals**. Values must be finite; timestamps must be strictly increasing.
  Do not silently repair, interpolate, clip or remove rows for this handoff.
* **Timestamp semantics:** explain what each timestamp represents, clock/timezone
  and daylight-saving handling, synchronization between the two signals, and any
  consistent anonymization time shift. Prefer ISO timestamps with UTC/offset;
  if timezone is unavailable, say so and use `YYYY-MM-DD HH:MM:SS`. Preserve
  elapsed intervals; absolute UTC timing then remains unestablished.
* **Signal dictionary:** for each opaque column, provide its units, finite
  instrumentation/configuration lower and upper bounds **in those same units**,
  and the supporting specification/configuration basis. Observed sample extrema
  are not instrumentation bounds. No equipment identity is needed.
* **Acquisition/export semantics:** state whether values are raw, averaged
  (including interval and overlap), held, interpolated, deadband/exception-recorded
  or resampled. Describe collection cadence, missing-record handling, export
  selection/filtering, and any transformations already applied. Explain whether
  acquisition and export selection are independent of measured outcomes.
* **Acquisition identity:** explain how a fresh acquisition is distinguished from
  a copy or re-export, including overlapping exports. Supply stable anonymized
  acquisition keys if needed. Without keys, explicitly establish that each
  delivered row is a fresh, non-replayed acquisition in this single export.
  Equal-valued fresh measurements are allowed; do not deduplicate by value.
* **Grouping and independence:** explain which readings may be dependent and
  what acquisition/process facts justify independence **between** groups,
  conditional on the declared operating context and schedule. Supply group keys
  or a justified grouping rule supported by this version: explicit group-key
  column, or explicitly justified independent acquisitions. Sampling cadence,
  unique timestamps, row count and low autocorrelation alone are not justification.
  If the facts are unknown, say so; qualification must abstain.
  Groups may span reference epochs, but cannot cross from reference into
  comparisons or between comparison slots. Agree partitions that respect the
  real groups; do not relabel a dependent group to fit a partition.
* **Comparable context:** explain why the same declared operating population
  applies throughout the export, including relevant aggregation/configuration
  consistency. Do not identify a “healthy until” period. Mixed contexts cannot
  be silently treated as homogeneous by this adapter.
* **Coverage period:** propose a defensible operating coverage period in seconds
  and explain why it is appropriate; it is not automatically the sampling interval.

Agree the two-signal selection, broad export selection and chronological
reference/epoch/comparison partition with Neraium **without using the withheld
event and before inspecting analysis outcomes**. Neraium generates the detailed
schedule; no hand-written per-row profile is required. The current boundary is
16–12,000 rows per reference/comparison, at least two reference epochs with at
least three observations each, reference
coverage ≥2T and each epoch/comparison ≥T. A persistence assessment needs at least
six potentially supporting comparison slots within 30 days; these are structural
requirements, not a promise that the evidence will be precise enough.

## OPTIONAL

* Existing anonymized acquisition/group key columns, unless necessary to support
  the declarations above (in that case they are required). Declare these columns
  explicitly; do not add unrelated CSV columns.
* A precomputed export checksum and redacted extracts of existing acquisition or
  instrument documentation. A documented basis is required; separate attachments
  and a Henderson-generated checksum are not.

## DO NOT PROVIDE

Keep **event identity, event time, outcome, failure type and labels** with a
separate Henderson custodian until Neraium's results and checkpoint are frozen.
Exclude incident/work-order narratives, truth/label columns, event-centered
boundaries, event-named files/IDs, and “before/after fault” or “known healthy”
annotations, including hints in free text. Ordinary measurement timestamps are
required; the withheld event timestamp is not.

Do not disguise event-selected data as a noninformative export. If the selection
cannot be justified without disclosing the event, state that the required
selection declaration is unavailable and agree a blind alternative before
analysis. No credentials, cloud access or production connectivity are requested.
