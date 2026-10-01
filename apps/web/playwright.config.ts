import { defineConfig } from "@playwright/test";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "../..");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:13761", trace: "retain-on-failure" },
  webServer: [
    { command: `make -C "${root}" api-offline`, url: "http://127.0.0.1:18761/health", reuseExistingServer: false, timeout: 120_000, env: { AGENT_LAB_PERSISTENCE: process.env.AGENT_LAB_E2E_PERSISTENCE ?? "0", AGENT_LAB_PROVIDER: "fake" } },
    { command: "pnpm start", url: "http://127.0.0.1:13761", reuseExistingServer: false, timeout: 120_000 },
  ],
});
