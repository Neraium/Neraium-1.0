const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const url = "http://127.0.0.1:3010";
const outRoot = "C:/Users/Owner/Documents/Neraium-1.0/audit-shots";
const outFile = path.join(outRoot, "metrics.json");

const workspaces = [
  "Cultivation Mission Control",
  "Structural Replay",
  "Evidence Lineage",
  "Propagation Map",
  "Data Connections",
  "Operator Workflow",
  "Cultivation Evidence",
  "Current Cognition State",
  "Drift Timeline",
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
  const triggers = [/workspace menu/i, /open workspace/i, /menu/i, /navigation/i];
  for (const pattern of triggers) {
    const button = page.getByRole("button", { name: pattern }).first();
    if (await button.count()) {
      await button.click({ timeout: 1500 }).catch(() => {});
      await page.waitForTimeout(250);
      return true;
    }
  }
  return false;
}

async function clickWorkspace(page, label) {
  let button = page.locator("button:visible", { hasText: label }).first();
  if (!(await button.count())) button = page.getByRole("button", { name: label, exact: true }).first();
  await button.scrollIntoViewIfNeeded({ timeout: 2500 }).catch(() => {});
  await button.click({ timeout: 4000 });
}

async function enableExpertMode(page, viewportName) {
  if (viewportName !== "desktop") {
    await openMobileDrawer(page);
  }
  const toggle = page.locator("button:visible", { hasText: "Expert Mode Off" }).first();
  if (await toggle.count()) {
    await toggle.click({ timeout: 2000 }).catch(() => {});
    await page.waitForTimeout(300);
  }
}

async function measure(page, viewportName) {
  return page.evaluate((isMobile) => {
    const root = document.documentElement;
    const horizontalOverflow = root.scrollWidth - window.innerWidth;

    const all = Array.from(document.querySelectorAll("*"));
    const visible = all.filter((el) => {
      const cs = window.getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity) === 0) return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });

    const offscreen = visible
      .map((el) => {
        const r = el.getBoundingClientRect();
        return { el, r };
      })
      .filter(({ r }) => (r.right > window.innerWidth + 2 || r.left < -2) && r.width > 140 && r.height > 24)
      .slice(0, 10)
      .map(({ el, r }) => ({
        tag: el.tagName.toLowerCase(),
        cls: (el.className || "").toString().slice(0, 120),
        text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80),
        left: Math.round(r.left),
        right: Math.round(r.right),
        width: Math.round(r.width),
      }));

    const tinyTapTargets = isMobile
      ? visible
          .filter((el) => ["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA"].includes(el.tagName))
          .map((el) => {
            const r = el.getBoundingClientRect();
            return {
              tag: el.tagName.toLowerCase(),
              cls: (el.className || "").toString().slice(0, 120),
              text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40),
              w: Math.round(r.width),
              h: Math.round(r.height),
            };
          })
          .filter((x) => x.w < 36 || x.h < 36)
          .slice(0, 12)
      : [];

    return {
      horizontalOverflow,
      offscreen,
      tinyTapTargets,
    };
  }, viewportName === "mobile");
}

(async () => {
  if (!fs.existsSync(outRoot)) fs.mkdirSync(outRoot, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const results = [];

  for (const vp of viewports) {
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    const page = await context.newPage();
    const pageErrors = [];
    page.on("pageerror", (err) => pageErrors.push(String(err?.message ?? err)));

    await page.goto(url, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForTimeout(1000);
    await enableExpertMode(page, vp.name);

    for (const label of workspaces) {
      let navOk = true;
      let navError = "";
      try {
        if (vp.name !== "desktop") await openMobileDrawer(page);
        await clickWorkspace(page, label);
        await page.waitForTimeout(700);
      } catch (err) {
        navOk = false;
        navError = String(err?.message ?? err);
      }
      const m = await measure(page, vp.name);
      results.push({
        viewport: vp.name,
        workspace: label,
        navOk,
        navError,
        pageErrors: [...pageErrors],
        ...m,
      });
      pageErrors.length = 0;
    }

    await context.close();
  }

  fs.writeFileSync(outFile, JSON.stringify(results, null, 2));
  await browser.close();
  console.log(`wrote ${outFile}`);
})();
