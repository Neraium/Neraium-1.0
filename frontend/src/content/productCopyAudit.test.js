import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const repositoryRoot = path.resolve(process.cwd(), "..");
const auditedRoots = ["README.md", "docs", "backend/app", "frontend/src"];
const extensions = new Set([".js", ".jsx", ".py", ".md", ".html"]);

function collectFiles(relativePath) {
  const absolutePath = path.join(repositoryRoot, relativePath);
  const stat = fs.statSync(absolutePath);
  if (stat.isFile()) return [absolutePath];
  return fs.readdirSync(absolutePath, { withFileTypes: true }).flatMap((entry) => {
    const child = path.join(absolutePath, entry.name);
    if (entry.isDirectory()) return collectFiles(path.relative(repositoryRoot, child));
    return extensions.has(path.extname(entry.name)) && !entry.name.includes(".test.") ? [child] : [];
  });
}

const auditedText = auditedRoots.flatMap(collectFiles).map((file) => ({ file: path.relative(repositoryRoot, file), text: fs.readFileSync(file, "utf8") }));

describe("product copy guardrails", () => {
  it.each([
    ["the predictive-maintenance category", /predictive maintenance/i],
    ["the retired product name", /Neraium Operational Intelligence/i],
    ["SII used as the platform name", /SII platform/i],
    ["the retired workspace label", /Back to Gate/i],
    ["em dashes", /\u2014/],
  ])("does not contain %s", (_label, pattern) => {
    expect(auditedText.filter(({ text }) => pattern.test(text)).map(({ file }) => file)).toEqual([]);
  });
});
