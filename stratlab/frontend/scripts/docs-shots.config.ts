import { defineConfig } from "@playwright/test";

// The screenshots in docs/screenshots (the README's pictures), taken from the backend's fake world
// (tests/visual_server.py), so they hold synthetic data only. Not part of the browser tests. From stratlab/frontend:
//   npm run build && PYTHON=python npx playwright test -c scripts/docs-shots.config.ts
// E2E_API_PORT / E2E_WEB_PORT move the two servers, as for the e2e suite. The files come out as full-colour PNGs;
// squeeze them to 256 colours before committing (pngquant, or Pillow's quantize), as the ones there are.
const chromium = process.env.PW_CHROMIUM;
const apiPort = Number(process.env.E2E_API_PORT ?? 8765);
const webPort = Number(process.env.E2E_WEB_PORT ?? 5599);
process.env.E2E_API ??= `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  testDir: ".",
  testMatch: /docs-shots\.spec\.ts/,
  timeout: 120_000,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${webPort}`, launchOptions: chromium ? { executablePath: chromium } : {} },
  webServer: [
    { command: `${process.env.PYTHON ?? "python"} -m tests.visual_server`, cwd: "../../backend", port: apiPort, timeout: 120_000, reuseExistingServer: false },
    { command: `node e2e/config.mjs && npx vite preview --port ${webPort} --strictPort --host 127.0.0.1`, cwd: "..", port: webPort, timeout: 60_000,
      reuseExistingServer: false },
  ],
});
