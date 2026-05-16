const fs = require("fs");

const metricsPath = "C:/Users/Owner/Documents/Neraium-1.0/audit-shots/metrics.json";
const m = JSON.parse(fs.readFileSync(metricsPath, "utf8"));

console.log(`total ${m.length}`);

const by = {};
for (const r of m) {
  by[r.viewport] = by[r.viewport] || {
    total: 0,
    navFails: 0,
    overflow: 0,
    offscreen: 0,
    tinyTap: 0,
    errors: 0,
  };
  const b = by[r.viewport];
  b.total += 1;
  if (!r.navOk) b.navFails += 1;
  if (r.horizontalOverflow > 0) b.overflow += 1;
  if ((r.offscreen || []).length > 0) b.offscreen += 1;
  if ((r.tinyTapTargets || []).length > 0) b.tinyTap += 1;
  if ((r.pageErrors || []).length > 0) b.errors += 1;
}

console.log(JSON.stringify(by, null, 2));

const issues = m.filter(
  (r) =>
    !r.navOk ||
    r.horizontalOverflow > 0 ||
    (r.offscreen || []).length > 0 ||
    (r.tinyTapTargets || []).length > 0 ||
    (r.pageErrors || []).length > 0,
);

console.log(`issues ${issues.length}`);
for (const r of issues) {
  console.log(
    `${r.viewport} | ${r.workspace} | nav:${r.navOk} overflow:${r.horizontalOverflow} off:${(r.offscreen || []).length} tap:${(r.tinyTapTargets || []).length} err:${(r.pageErrors || []).length}`,
  );
}

