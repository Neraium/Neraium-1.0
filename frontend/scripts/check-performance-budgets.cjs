const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");

const distDir = path.resolve(__dirname, "..", "dist");
const manifestPath = path.join(distDir, ".vite", "manifest.json");
if (!fs.existsSync(manifestPath)) {
  throw new Error("Performance budget requires a Vite manifest. Run npm run build first.");
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const entryKey = Object.keys(manifest).find((key) => manifest[key].isEntry);
if (!entryKey) throw new Error("Vite manifest did not include an application entry.");

function routeKey(filename) {
  return Object.keys(manifest).find((key) => key.endsWith(filename));
}

function collectFiles(keys) {
  const files = new Set();
  const visited = new Set();
  function visit(key) {
    if (!key || visited.has(key)) return;
    visited.add(key);
    const chunk = manifest[key];
    if (!chunk) return;
    if (chunk.file) files.add(chunk.file);
    for (const cssFile of chunk.css || []) files.add(cssFile);
    for (const imported of chunk.imports || []) visit(imported);
  }
  keys.forEach(visit);
  return files;
}

function measure(files) {
  let rawBytes = 0;
  let gzipBytes = 0;
  for (const relative of files) {
    const bytes = fs.readFileSync(path.join(distDir, relative));
    rawBytes += bytes.length;
    gzipBytes += zlib.gzipSync(bytes, { level: 9 }).length;
  }
  return { rawBytes, gzipBytes, files: [...files].sort() };
}

const routes = {
  core: [entryKey],
  engineeringWorkspace: [entryKey, routeKey("EngineeringReasoningWorkspace.jsx")],
  issues: [entryKey, routeKey("ObservationCenterWorkspace.jsx")],
  dataSources: [entryKey, routeKey("DataConnectionsWorkspace.jsx")],
};
const budgets = {
  core: { rawBytes: 380 * 1024, gzipBytes: 100 * 1024 },
  engineeringWorkspace: { rawBytes: 575 * 1024, gzipBytes: 155 * 1024 },
  issues: { rawBytes: 415 * 1024, gzipBytes: 112 * 1024 },
  dataSources: { rawBytes: 530 * 1024, gzipBytes: 134 * 1024 },
};

const results = {};
const failures = [];
for (const [name, keys] of Object.entries(routes)) {
  if (keys.some((key) => !key)) throw new Error(`Vite manifest is missing the ${name} route chunk.`);
  const metrics = measure(collectFiles(keys));
  results[name] = metrics;
  for (const field of ["rawBytes", "gzipBytes"]) {
    if (metrics[field] > budgets[name][field]) {
      failures.push(`${name} ${field} ${metrics[field]} exceeds ${budgets[name][field]}`);
    }
  }
}

process.stdout.write(`${JSON.stringify({ budgets, results }, null, 2)}\n`);
if (failures.length) {
  throw new Error(`Performance budget exceeded: ${failures.join("; ")}`);
}
