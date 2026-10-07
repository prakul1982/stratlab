import { defineConfig, devices } from "@playwright/test";

// Browser tests: every main page on desktop and phone against the backend's fake world (tests/visual_server.py),
// checking what is actually drawn. Run: npm run build && npx playwright test
const chromium = process.env.PW_CHROMIUM;     // a preinstalled browser, when there is one
// E2E_API_PORT and E2E_WEB_PORT move both servers, so two test runs can share a machine
const apiPort = Number(process.env.E2E_API_PORT ?? 8765);
const webPort = Number(process.env.E2E_WEB_PORT ?? 5599);
process.env.E2E_API ??= `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  workers: process.env.CI ? 2 : undefined,     // GitHub's runner has 2 cores: one worker each (the default is one in all)
  reporter: process.env.GITHUB_ACTIONS ? [["list"], ["github"]] : [["list"]],     // on GitHub, failures also show as annotations
  use: { baseURL: `http://127.0.0.1:${webPort}`, launchOptions: chromium ? { executablePath: chromium } : {}, screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", testIgnore: /screens\.spec/, use: { viewport: { width: 1440, height: 1000 } } },
    { name: "phone", testIgnore: /screens\.spec/, use: { ...devices["Pixel 7"], browserName: "chromium" } },
    // every route at five screen sizes (each test makes its own browser windows at its size)
    { name: "screens", testMatch: /screens\.spec/ },
  ],
  webServer: [
    { command: `${process.env.PYTHON ?? "python"} -m tests.visual_server`, cwd: "../backend", port: apiPort, timeout: 300_000, reuseExistingServer: !process.env.CI },   // the fake world can take minutes to build on a busy machine
    { command: `node e2e/config.mjs && npx vite preview --port ${webPort} --strictPort --host 127.0.0.1`, port: webPort, timeout: 60_000, reuseExistingServer: !process.env.CI },
  ],
});
