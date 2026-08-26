import fs from "node:fs";
import assert from "node:assert/strict";

import { buildEngineeringReasoningModel } from "../src/viewModels/engineeringReasoning.js";
import {
  projectEvidenceRecord,
  projectFindingReview,
  projectInvestigation,
  projectResults,
} from "../src/viewModels/resultsPresentation.js";

const response = JSON.parse(fs.readFileSync(0, "utf8"));
const result = response?.product_result;
assert.ok(result && typeof result === "object" && !Array.isArray(result));
assert.equal(result.result_id, response.result_id);
assert.equal(result.payload_digest, response.payload_digest);
assert.equal(result.lineage_verified, true);

const canonical = result.canonical_result;
const identity = canonical?.identity;
assert.equal(identity?.result_id, response.result_id);
assert.equal(identity?.payload_digest, response.payload_digest);
assert.equal(identity?.analysis_window_id, response.analysis_window_id);
assert.equal(identity?.source_ingestion_run_id, response.source_run_id);
assert.equal(identity?.observation_lineage_digest, response.observation_lineage_digest);

const model = buildEngineeringReasoningModel({ result });
const results = projectResults(model, {}, { analysisResultId: response.result_id });
assert.equal(results.depth, "results");
assert.ok(["ready", "insufficient"].includes(results.variant));
assert.ok(model.findings.length > 0, "the real connector result must retain its classified finding");

const findingId = results.cards?.[0]?.findingKey ?? model.findings[0].id;
const indexedFindingIds = canonical.finding_ids?.ids ?? canonical.finding_ids?.items ?? [];
assert.ok(indexedFindingIds.includes(findingId));

const review = projectFindingReview(model, findingId);
const investigation = projectInvestigation(model, findingId);
const evidence = projectEvidenceRecord(model, findingId);
assert.equal(review.depth, "review");
assert.equal(investigation.depth, "investigation");
assert.equal(evidence.depth, "evidence");
const expectedFindingVariant = model.status === "Evidence insufficient" ? "insufficient" : "ready";
assert.equal(review.variant, expectedFindingVariant);
assert.equal(investigation.variant, expectedFindingVariant);
assert.equal(evidence.variant, expectedFindingVariant);

for (const projection of [review, investigation, evidence]) {
  assert.equal(projection.identity.findingKey, findingId);
  assert.equal(projection.identity.resultId, response.result_id);
  assert.equal(projection.identity.analysisWindowId, response.analysis_window_id);
  assert.equal(projection.identity.sourceRunId, response.source_run_id);
  assert.equal(projection.identity.payloadDigest, response.payload_digest);
}
assert.deepEqual(
  evidence.lineage.canonical.referenceMetadata,
  canonical.reference_metadata,
);
assert.equal(
  evidence.lineage.canonical.identity.observation_lineage_digest,
  response.observation_lineage_digest,
);
assert.equal(evidence.audit.canonicalResult.resultId, response.result_id);
assert.equal(evidence.audit.canonicalResult.payloadDigest, response.payload_digest);

process.stdout.write(JSON.stringify({
  result_id: response.result_id,
  finding_id: findingId,
  payload_digest: response.payload_digest,
  observation_lineage_digest: response.observation_lineage_digest,
  depths: [results.depth, review.depth, investigation.depth, evidence.depth],
}));
