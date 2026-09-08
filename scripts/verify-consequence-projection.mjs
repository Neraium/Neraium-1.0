// Read a --verify-url JSON report on stdin; exercise the shipped frontend selector.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { consequenceSummary } from "../frontend/src/viewModels/measurableConsequence.js";

const proof = JSON.parse(readFileSync(0, "utf8"));
const original = JSON.stringify(proof);
const canonical = proof.consequence;
const projected = consequenceSummary(canonical);
for (const [key, value] of Object.entries(projected)) assert.deepEqual(value, canonical[key]);
assert.equal(projected.status, "quantified");
assert.equal(projected.cumulative_amount, 3600);
assert.equal(projected.duration_seconds, 21600);
assert.equal(projected.cumulative_unit, "gal");
assert.deepEqual(projected.source_relationship_ids, ["synthetic.water.flow-to-test-load"]);
assert.deepEqual(projected.source_tag_ids, ["synthetic.water.flow-gpm", "synthetic.test.load"]);
assert.equal(projected.methodology_version, "1.0.0");
assert.equal(JSON.stringify(proof), original);
process.stdout.write(JSON.stringify({ frontend_projection_matches: true, projected }) + "\n");
