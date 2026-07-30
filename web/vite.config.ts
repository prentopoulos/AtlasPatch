import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// The built SPA is vendored into the Python package and opened both from a wheel path and
// directly off disk, so assets must resolve relatively (base "./"), never from a server root.
// See design D-REACT-1 / D-REACT-5: outDir is the committed, wheel-shipped bundle.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "../atlas_conductor/gui/web_dist",
    emptyOutDir: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Playwright specs live under tests/e2e and run with their own runner, not Vitest.
    exclude: ["tests/e2e/**", "node_modules/**"],
    css: true,
  },
});
