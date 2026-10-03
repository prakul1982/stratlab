import { defineConfig, devices } from "@playwright/test";

// Browser tests: every main page on desktop and phone against the backend's fake world (tests/visual_server.py),
// checking what is actually drawn. Run: npm run build && npx playwright test
const chromium = process.env.PW_CHROMIUM;     // a preinstalled browser, when there is one

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:5599", launchOptions: chromium ? { executablePath: chromium } : {}, screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "phone", use: { ...devices["Pixel 7"], browserName: "chromium" } },
  ],
  webServer: [
    { command: `${process.env.PYTHON ?? "python"} -m tests.visual_server`, cwd: "../backend", port: 8765, timeout: 120_000, reuseExistingServer: !process.env.CI },
    { command: "node e2e/config.mjs && npx vite preview --port 5599 --strictPort --host 127.0.0.1", port: 5599, timeout: 60_000, reuseExistingServer: !process.env.CI },
  ],
});
