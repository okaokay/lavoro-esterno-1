/** Verifica il flusso Admin di configurazione e test dei proxy. */
import { test, expect } from "@playwright/test";

test("admin creates a proxy without exposing credentials", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("lavoro_esterno_access_token", "token");
    localStorage.setItem("lavoro_esterno_refresh_token", "refresh");
  });
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: {
    id: "00000000-0000-4000-8000-000000000001", email: "admin@example.test",
    name: "Admin", role: "admin", mfa_enabled: true, status: "active",
  } }));
  await page.route("**/api/v1/notifications", (route) => route.fulfill({ json: { items: [], unreadCount: 0 } }));
  await page.route("**/api/v1/admin/proxy-pools", (route) => route.fulfill({ json: [] }));
  let endpoints: unknown[] = [];
  let submitted: Record<string, unknown> = {};
  await page.route("**/api/v1/admin/proxies", async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: endpoints });
    submitted = route.request().postDataJSON();
    endpoints = [{
      id: "10000000-0000-4000-8000-000000000001", name: "Primary",
      scheme: "http", host: "proxy.example", port: 8080, enabled: true,
      credentialConfigured: true, health: "healthy", consecutiveFailures: 0,
      cooldownUntil: null, lastUsedAt: null, lastSuccessAt: null, lastFailureAt: null,
    }];
    return route.fulfill({ status: 201, json: endpoints[0] });
  });
  await page.route("**/api/v1/sources", (route) => route.fulfill({ json: [] }));

  await page.goto("/settings/proxies");
  await page.getByPlaceholder("Nome", { exact: true }).fill("Primary");
  await page.getByPlaceholder("proxy.example.com").fill("proxy.example");
  await page.getByPlaceholder("Nome utente (opzionale)").fill("alice");
  await page.getByPlaceholder("Password").fill("secret-value");
  await page.getByRole("button", { name: "Aggiungi proxy" }).click();

  await expect(page.getByText(/credenziali configurate/)).toBeVisible();
  expect(submitted).toMatchObject({ username: "alice", password: "secret-value" });
  await expect(page.getByText("secret-value")).toHaveCount(0);
});
