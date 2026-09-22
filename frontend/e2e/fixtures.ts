import type { Page } from "@playwright/test";
import { generateTotp } from "./totp";

// Credentials of the Admin account already bootstrapped and 2FA-enrolled
// manually in this environment during development (see PROGETTO.md § 12 /
// HANDOFF.md for how it was created: `app.scripts.create_admin` +
// `/auth/setup-2fa` + `/auth/verify-2fa`). Re-running `docker compose up`
// on a fresh Postgres volume will NOT have this account — re-create it
// with the same email/password/secret, or update these constants.
export const ADMIN_EMAIL = "admin@lavoro.internal";
export const ADMIN_PASSWORD = "TestPassword123!Strong";
export const ADMIN_TOTP_SECRET = "A2RTMM2Y2VMW2GR2B5W47QF3MO7II6ZL";

// Drives the full two-step login form (credentials, then TOTP) exactly as
// a real user would — no API shortcuts — so this also exercises the
// backend session/2FA flow end-to-end, not just the UI.
export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto("/login");
  await page.locator("#email").fill(ADMIN_EMAIL);
  await page.locator("#password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Accedi" }).click();

  await page.locator("#mfa-code").waitFor({ state: "visible" });
  await page.locator("#mfa-code").fill(generateTotp(ADMIN_TOTP_SECRET));
  await page.getByRole("button", { name: "Verifica" }).click();

  await page.waitForURL(/\/dashboard/);
}
