import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright drives the *built, vendored* bundle (design D-REACT-4): it previews
 * `atlas_conductor/gui/web_dist/` — the exact artifact shipped in the wheel — and asserts the
 * re-homed phase-3 DOM safety invariants over it. Run `npm run build` first (CI checks out the
 * committed web_dist/, so preview serves it directly).
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: "http://localhost:4318",
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npx vite preview --port 4318 --strictPort",
    url: "http://localhost:4318",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
