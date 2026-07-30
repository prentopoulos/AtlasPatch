import { test, expect, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const GATED_FIXTURE = path.resolve(here, "../../src/fixtures/gated-snapshot.json");

/**
 * The re-homed phase-3 renderer guardrails (design D-REACT-4), asserted on the real rendered
 * DOM of the vendored bundle over both the default demo and a gated-run fixture. These mirror
 * the retired `AppTest` guards one layer down: no slide imagery, no clinical score, only
 * pseudonymized identifiers, and no control that submits/confirms/writes.
 */

// Clinical-score vocabulary that must never appear in the operational surface (spec: no scores).
const SCORE_PATTERNS = [
  /confidence/i,
  /probability/i,
  /\blogit/i,
  /softmax/i,
  /grad[\s_-]?cam/i,
  /saliency/i,
  /diagnostic score/i,
  /\bscore\b/i,
];

// Raw-identifier shapes a PHI-free surface must never render: slide filenames, MRN/accession
// labels, SSNs. Pseudonyms (`slide_<hex>`) are the only slide identifiers allowed.
const RAW_ID_PATTERNS = [
  /\b[\w-]+\.(svs|tiff?|ndpi|scn|mrxs|dcm|vms|vmu)\b/i,
  /\b(mrn|accession|patient[\s_-]?id)\b[:#]?\s*\d/i,
  /\b\d{3}-\d{2}-\d{4}\b/,
];

// Control affordances that would mutate a run/telemetry — forbidden on a read-only surface.
const WRITE_CONTROL = /\b(submit|confirm|approve|publish|delete|reject|write|save changes)\b/i;

async function assertSafetyInvariants(page: Page): Promise<void> {
  // No slide raster: no <img>, no <canvas>. Decorative chrome is inline <svg> and is allowed.
  await expect(page.locator("img")).toHaveCount(0);
  await expect(page.locator("canvas")).toHaveCount(0);

  const bodyText = await page.locator("body").innerText();

  // No clinical score anywhere in the DOM.
  for (const pattern of SCORE_PATTERNS) {
    expect(bodyText, `score token ${pattern} must be absent`).not.toMatch(pattern);
  }

  // No raw identifier; at least one pseudonym is present (identity is shown as persisted).
  for (const pattern of RAW_ID_PATTERNS) {
    expect(bodyText, `raw-identifier ${pattern} must be absent`).not.toMatch(pattern);
  }
  expect(bodyText).toMatch(/slide_[0-9a-f]{16}/);

  // No control that submits/confirms/writes: no submit inputs and no mutating button labels.
  await expect(page.locator('button[type="submit"], input[type="submit"]')).toHaveCount(0);
  for (const label of await page.locator("button").allInnerTexts()) {
    expect(label, `button "${label}" must not imply a write`).not.toMatch(WRITE_CONTROL);
  }
}

test("default demo view holds every DOM safety invariant", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Run history")).toBeVisible();
  await assertSafetyInvariants(page);
});

test("a gated-run fixture holds every DOM safety invariant", async ({ page }) => {
  await page.goto("/");
  await page.setInputFiles('input[aria-label="Load snapshot file"]', GATED_FIXTURE);
  await expect(page.getByText("job-gated").first()).toBeVisible();
  await assertSafetyInvariants(page);
});
