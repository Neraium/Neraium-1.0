# Live telemetry ingestion: Phase 1

Phase 1 accepts and stores live telemetry. It does not invoke relationship
analysis, rolling windows, persistence scoring, finding creation, baseline
creation, or evidence generation.

## API

Create signal mappings with the authenticated
`POST /api/telemetry/signal-mappings` endpoint, then submit batches to
`POST /api/telemetry/ingest`. Mapping writes require the existing admin role;
ingestion requires the existing operator role. In production, callers use the
same session cookie, `Authorization: Bearer` token, or
`X-Neraium-Access-Code` authentication as other Neraium APIs.

Clients may send a `batch_id`. Reusing a completed batch ID for the same system
and source returns the original result without changing telemetry, rejection, or
health counts. When omitted, Neraium creates and returns a batch ID. Independent
retries are also safe because normalized values have a unique key over system,
canonical signal, source timestamp, and source.

A reading is counted as accepted when at least one signal value from that
timestamp is stored. It is counted as rejected when none are stored. Signal-value
counts report partial acceptance within mixed readings.

## Validation and quarantine policy

- Timestamps must be ISO 8601 and timezone-aware. Accepted timestamps are
  normalized to UTC.
- Timestamps more than the configured future-skew allowance ahead of processing
  time are quarantined. The default allowance is 300 seconds.
- Ordering is evaluated against the newest previously accepted timestamp for the
  same system and canonical signal. A late value within the configured tolerance
  is accepted with `quality_status=out_of_order`; a value older than that
  tolerance is quarantined as `out_of_order_record`. The default tolerance is
  300 seconds.
- JSON numbers and finite numeric strings are accepted. Booleans, nulls,
  non-numeric strings, NaN, and positive or negative infinity are quarantined.
- Disabled and missing mappings are treated as `unmapped_signal`. Neraium does
  not infer canonical signal names.
- Every quarantined value is stored in `rejected_telemetry` with its batch,
  source context, reason, and safely serializable submitted value.

## Configuration

The following environment variables bound ingestion:

- `NERAIUM_TELEMETRY_MAX_REQUEST_SIZE_BYTES` (default `1048576`)
- `NERAIUM_TELEMETRY_MAX_READINGS_PER_BATCH` (default `1000`)
- `NERAIUM_TELEMETRY_MAX_SIGNALS_PER_READING` (default `100`)
- `NERAIUM_TELEMETRY_FUTURE_SKEW_SECONDS` (default `300`)
- `NERAIUM_TELEMETRY_OUT_OF_ORDER_TOLERANCE_SECONDS` (default `300`)
- `NERAIUM_TELEMETRY_DELAY_THRESHOLD_SECONDS` (default `900`)

Ingestion health is available from
`GET /api/telemetry/ingestion-health?system_id=...&source=...`. Health describes
the telemetry transport only and never creates or changes physical-system
findings.
