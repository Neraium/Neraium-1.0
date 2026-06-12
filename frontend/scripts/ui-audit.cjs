const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const url = "http://127.0.0.1:3010";
const outRoot = "C:/Users/Owner/Documents/Neraium-1.0/audit-shots";
const workspaces = [
  "Cultivation Mission Control",
  "Evidence Replay",
  "Evidence Details",
  "Propagation Map",
  "Data Connections",
  "Operator Workflow",
  "Cultivation Evidence",
  "Current Cognition State",
  "Change Timeline",
  "Multi-Site Cognition",
  "Structural Ontology",
  "Ecosystem Layer",
  "Distributed Cognition",
  "Operator Training",
  "Behavior Science",
  "Operator Curriculum",
  "Research Workspace",
];
const viewports = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 1024, height: 1366 },
  { name: "mobile", width: 390, height: 844 },
];

async function openMobileDrawer(page) {
  const triggers = [
    /workspace menu/i,
    /open workspace/i,
    /menu/i,
    /navigation/i,
  ];
  for (const pattern of triggers) {
    const button = page.getByRole("button", { name: pattern }).first();
    if (await button.count()) {
      await button.click({ timeout: 1500 }).catch(() => {});
      await page.waitForTimeout(300);
      return;
    }
  }
}

async function clickWorkspace(page, label) {
  let button = page.getByRole("button", { name: label, exact: true }).first();
  if (!(await button.count())) {
    button = page.locator("button", { hasText: label }).first();
  }
  await button.scrollIntoViewIfNeeded({ timeout: 2000 }).catch(() => {});
  await button.click({ timeout: 4000 });
}

(async () => {
  if (!fs.existsSync(outRoot)) fs.mkdirSync(outRoot, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const summary = [];

  for (const vp of viewports) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
    });
    const page = await context.newPage();
    const dir = path.join(outRoot, vp.name);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForTimeout(1200);

    for (let i = 0; i < workspaces.length; i += 1) {
      const label = workspaces[i];
      let ok = true;
      let note = "";
      try {
        if (vp.name === "mobile") {
          await openMobileDrawer(page);
        }
        await clickWorkspace(page, label);
        await page.waitForTimeout(1000);
      } catch (error) {
        ok = false;
        note = String(error?.message ?? error);
      }

      const safe = `${String(i + 1).padStart(2, "0")}-${label
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")}.png`;
      await page.screenshot({ path: path.join(dir, safe), fullPage: true });
      summary.push({ viewport: vp.name, label, ok, note });
    }

    await context.close();
  }

  fs.writeFileSync(path.join(outRoot, "summary.json"), JSON.stringify(summary, null, 2));
  await browser.close();
  console.log("ui-audit complete");
})();

