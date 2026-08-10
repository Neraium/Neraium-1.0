# Atomic Terminal Job-State Publication

## Original race

Upload state is intentionally mirrored across the per-job status object, the
runtime database, local JSON, the bounded in-process cache, the upload queue,
and (when configured) S3. Two ordering gaps allowed polling to observe a
terminal state before its complete terminal payload:

- `upload_jobs.write_job` cached a terminal payload before the per-job status
  write had finished; and
- the polling read model could promote a terminal upload-queue mirror into a
  public `FAILED` response while the authoritative structured failure envelope
  was still propagating.

The second gap explains the load-sensitive symptom: the synthetic queue failure
had generic worker fields but not the classified failure stage, canonical error
code, technical message, or final progress contract.

## Authority and publication order

The authoritative polling model is the scoped per-job attempt pointer plus that
attempt's immutable `upload-terminal-state.v1` envelope. The envelope is stored
under a scope- and attempt-specific key, and its conditional create is the
terminal publication point. The mutable `upload_status_<job_id>` object remains
the current-attempt/progress pointer; it is deliberately not rewritten to a
terminal value. The runtime `upload_jobs` row, queue state, and in-process cache
are compatibility or dispatch mirrors.

Failure publication is ordered as follows:

1. Build the complete, sanitized failure payload and final failed progress.
2. Persist any derived latest summary that applies to the workflow.
3. Conditionally create the immutable terminal envelope.
4. Update the bounded cache, legacy job record, and queue mirror.

Completion publication is ordered as follows:

1. Persist and verify analysis/baseline artifacts.
2. Persist one immutable, content-digested completion bundle under an
   attempt-scoped key using the configured durable authority (or the supported
   local authority in no-bucket mode).
3. Prepare the mutable per-job result and latest result/summary from the
   canonical bundle, so existing compatibility readers are ready.
4. Conditionally create the immutable terminal envelope with the result digest
   and deterministic reference.
5. Update the bounded cache, job, and queue mirrors.

Legacy internal callers that still announce `COMPLETE` with
`result_available=true` immediately before writing the result are held at the
nonterminal `saving_result` state. Their existing result-writer call performs
the ordered completion publication, so the caller contract remains usable
without exposing its intermediate completion claim.

Consequently, a poll cannot observe `FAILED` or `COMPLETED` from the
authoritative read path until the corresponding terminal envelope is complete.
The queue read model no longer synthesizes a public failure from a terminal
queue row. It keeps the lifecycle nonterminal and exposes
`terminal_publication_pending=true` until the full status envelope is readable.

## Idempotency and attempts

Conditional creation makes terminal finalization first-writer-wins within one
attempt. Repeating the same finalization returns the committed envelope and
repairs mutable mirrors without replacing the committed result. Completion
results and their summaries share one immutable bundle before publication; the
winning bundle supplies both fields, so duplicate publishers cannot mix one
publisher's status with another publisher's result. A competing terminal state
cannot replace the winner. Nonterminal and stale-attempt writes return the
current canonical state instead of reopening or regressing the job.
Completion publication also validates job identity, attempt identity, and
dataset scope across the bundle before the terminal envelope can be created.

An explicit retry or historical-review attempt receives a new additive
`attempt_id`. Its terminal envelope has a different deterministic key, so a
valid retry can progress while late callbacks carrying the previous attempt ID
are rejected. Older records without `attempt_id` remain readable and are
treated as their original job-ID attempt.
New-attempt initialization removes terminal contract fields copied from the
prior status and explicitly restores a queued/processing `job_state`, preventing
stale failure metadata from classifying the retry itself as terminal.

## Partial failures and restart behavior

When S3 is configured, terminal conditional creation and completion-result
publication fail closed if S3 cannot durably accept the payload. A retry is safe.
If S3 accepted the terminal envelope but a secondary runtime/local copy then
failed, read-back establishes that publication succeeded and a repeat
finalization repairs the envelope copy. Completion result/latest mirror
failures during finalization are logged without regressing the worker or queue
to failed; the immutable bundle remains readable and an idempotent repeat
repairs those mirrors. Without an S3 bucket, Neraium preserves its existing
runtime-database authority with an atomic local-file fallback when the optional
database is unavailable.

Terminal envelopes are durable and are consulted before mutable status mirrors.
Completed envelopes resolve their immutable result before consulting the
mutable compatibility result, so cache resets, delayed mirror writes, and
process restarts reconstruct the same final state. Startup recovery now
publishes the structured interrupted-job failure before changing the queue
mirror to failed; an unsuccessful publication leaves the queue row eligible
for another recovery attempt.

Keeping terminal state out of the mutable attempt pointer closes the retry
handoff race: once a retry advances the pointer, a late finalizer from the prior
attempt has no terminal pointer write with which to restore the old attempt.

## Concurrency and operational impact

A fixed set of 64 re-entrant locks serializes same-process writes without a
per-job memory-growth risk. Cross-process first-terminal-wins behavior comes
from the existing conditional S3/SQLite insert; no distributed lock or sleep is
used. Existing status reads are passed through the write path so ordinary
nonterminal progress publication does not add a database or object-store read.
Terminal finalization adds one conditional envelope write and one compact
terminal status record per attempt. Finalizations carrying a result also retain
one immutable result object so terminal/result consistency does not depend on
the mutable compatibility mirror.

A three-batch local SQLite/runtime-file microbenchmark used 200 nonterminal
writes, 50 processing-plus-failure pairs, and 40 processing-plus-success pairs
per batch. Median nonterminal publication moved from 29.644 ms to 31.572 ms
(+1.928 ms, +6.5%). No extra database/object-store read was added to the normal
`upload_jobs.write_job` progress path because its existing status read is passed
through to the repository; the measured delta is local serialization, locking,
and validation overhead in the direct repository benchmark.

Processing plus failure publication moved from 57.253 ms to 61.287 ms (+4.034
ms, +7.0%). Processing plus successful completion with a small result moved
from 71.030 ms to 92.691 ms (+21.661 ms, +30.5%) because completion now persists
the immutable result bundle and terminal envelope. Terminal costs occur once
per attempt and do not change dataset-analysis computation or intelligence
semantics.

Diagnostics are limited to terminal attempts/publications, retries, rejected
regressions or conflicts, and secondary-mirror failures. No raw dataset content
is logged, and the terminal metadata is outside canonical intelligence
provenance.

## Compatibility and limitations

- Existing API fields, error payloads, progress contracts, result records, and
  worker calls remain valid. `attempt_id`, `terminal_state_contract_version`,
  `terminal_published_at`, terminal-result reference fields, and
  `terminal_publication_pending` are additive.
- Historical terminal records remain readable. The first repeated finalization
  upgrades a valid pre-v1 terminal status into the immutable envelope without
  changing its state.
- Immutable terminal envelopes add one compact durable status object per
  attempt. Successful attempts also add one immutable result representation in
  addition to the legacy mutable result mirror. Existing state-retention/reset
  policy applies; no in-memory cache is allowed to grow per attempt.
- The queue remains a dispatch authority for claiming work, not a terminal
  polling authority. If all terminal-status authorities are unavailable after
  the queue has stopped, polling intentionally remains nonterminal rather than
  fabricating an incomplete failure.
- Cross-process result publication relies on the queue's existing single-claim
  contract plus the immutable terminal compare-and-set. This change does not
  introduce a distributed transaction across S3 and SQLite.
