import { defineConfig } from "vitest/config";

// Pure-function tests only (no DOM/React), so the lightweight node environment
// is sufficient — no jsdom/happy-dom needed.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
