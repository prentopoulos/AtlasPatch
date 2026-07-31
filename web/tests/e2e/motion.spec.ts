import { test, expect } from "@playwright/test";

/**
 * The motion-honesty guardrails (phase-10 spec: "Motion is one-shot and never implies live
 * data"). Asserted on the real computed styles of the vendored bundle: no animation loops
 * indefinitely, and a reduced-motion viewer sees every animation suppressed with the surface
 * in its final resting state. These mirror the promoted `observability-gui` requirement.
 */

test("no element animation loops indefinitely (motion is one-shot)", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Run history")).toBeVisible();

  // Walk every rendered element's computed animation-iteration-count; a snapshot tailer must
  // never present an indefinitely repeating animation (which would imply live/streaming data).
  const infinite = await page.evaluate(() => {
    const offenders: string[] = [];
    for (const el of Array.from(document.querySelectorAll("*"))) {
      const style = getComputedStyle(el);
      if (style.animationName === "none") continue;
      const counts = style.animationIterationCount.split(",").map((v) => v.trim());
      if (counts.some((c) => c === "infinite")) offenders.push(el.className || el.tagName);
    }
    return offenders;
  });
  expect(infinite, `elements with an infinite animation: ${infinite.join(", ")}`).toEqual([]);
});

test("reduced-motion suppresses animation and renders the resting state", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByText("Run history")).toBeVisible();

  // An entrance-animated node resolves to no animation and full opacity (its resting state).
  const pill = page.locator('[data-testid="agent-nodes"] > div').first();
  await expect(pill).toBeVisible();
  expect(await pill.evaluate((el) => getComputedStyle(el).animationName)).toBe("none");
  expect(await pill.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");

  // No element retains a running animation under reduced motion.
  const stillAnimating = await page.evaluate(() =>
    Array.from(document.querySelectorAll("*")).filter(
      (el) => getComputedStyle(el).animationName !== "none",
    ).length,
  );
  expect(stillAnimating).toBe(0);

  // If the current run drew flow edges, each resolves to fully drawn (dash offset 0).
  const edge = page.locator("path.ap-edge").first();
  if (await edge.count()) {
    expect(await edge.evaluate((el) => getComputedStyle(el).strokeDashoffset)).toBe("0px");
  }
});
