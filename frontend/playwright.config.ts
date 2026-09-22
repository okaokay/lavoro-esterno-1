import { defineConfig, devices } from "@playwright/test";

// Runs against the real Docker Compose stack (nginx reverse proxy on
// http://localhost/), NOT a locally-started `vite dev` server: this suite
// is meant to exercise the actual built frontend talking to the actual
// backend/Postgres/Redis/MinIO, the same environment verified manually
// throughout this project's development (see PROGETTO.md § 12).
//
// Prerequisite: `docker compose up -d --build` must already be running,
// with at least one Admin user bootstrapped (`app.scripts.create_admin`)
// and 2FA enabled on it (see e2e/fixtures.ts for how tests authenticate).
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // tests share one seeded Admin account; avoid racing logins/lockouts
  workers: 1, // files also share that account; serialize them to avoid triggering lockout
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // No `webServer` entry deliberately: the stack is Docker Compose, started
  // independently (see README.md), not something Playwright should try to
  // spawn/manage itself.
});
