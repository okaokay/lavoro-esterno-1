import { test, expect } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, loginAsAdmin } from "./fixtures";

test.describe("Login + 2FA", () => {
  test("rejects wrong password with a clear error, not a crash", async ({ page }) => {
    await page.goto("/login");
    await page.locator("#email").fill(ADMIN_EMAIL);
    await page.locator("#password").fill("definitely-not-the-password");
    await page.getByRole("button", { name: "Accedi" }).click();

    // Generic "Invalid credentials"-style message from the backend (see
    // app/api/v1/auth.py:login — deliberately identical for wrong password
    // vs. unknown email, to avoid user enumeration).
    await expect(page.getByText(/invalid|non valid/i)).toBeVisible();
    // Still on the credentials step, not silently advanced to MFA.
    await expect(page.locator("#mfa-code")).toHaveCount(0);
  });

  test("rejects a wrong TOTP code at the MFA step", async ({ page }) => {
    await page.goto("/login");
    await page.locator("#email").fill(ADMIN_EMAIL);
    await page.locator("#password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Accedi" }).click();

    await page.locator("#mfa-code").waitFor({ state: "visible" });
    await page.locator("#mfa-code").fill("000000");
    await page.getByRole("button", { name: "Verifica" }).click();

    await expect(page.getByText(/invalid|non valid/i)).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("full login flow: credentials + real TOTP code reaches the dashboard", async ({ page }) => {
    await loginAsAdmin(page);
    await expect(page.getByRole("heading", { name: "Panoramica operativa" })).toBeVisible();
  });
});
