/** Verifica configurazione e attivazione dei provider AI dalla console Admin. */
import { test, expect } from "@playwright/test";

const providers = [
  ["ollama", "Ollama locale", "gemma4:e2b", true, false],
  ["openai", "OpenAI", "gpt-5.6-luna", false, true],
] as const;

test.describe("AI settings", () => {
  test("shows the local default and never exposes stored credentials", async ({ page }) => {
    await page.route("**/api/v1/auth/me", (route) => route.fulfill({
      json: {
        id: "00000000-0000-4000-8000-000000000001",
        email: "admin@example.test", name: "E2E Admin", role: "admin",
        mfa_enabled: true, status: "active",
      },
    }));
    await page.route("**/api/v1/notifications", (route) => route.fulfill({
      json: { items: [], unreadCount: 0 },
    }));
    await page.route("**/api/v1/admin/ai-settings", (route) => route.fulfill({
      json: {
        activeProvider: "ollama",
        promptVersion: "summary-v2-it",
        userDailyRequestLimit: 20,
        providerRequestsPerMinute: 10,
        globalDailyTokenBudget: 0,
        revision: 1,
        providers: providers.map(([provider, displayName, model, enabled, credentialConfigured]) => ({
          provider, displayName, model, enabled, active: provider === "ollama",
          baseUrl: provider === "ollama" ? "http://ollama:11434" : null,
          credentialConfigured, options: {}, revision: 1,
          lastTestedAt: null, lastTestSuccess: null,
        })),
      },
    }));
    await page.route("**/api/v1/admin/ai-settings/providers/*/models", (route) => route.fulfill({
      json: { provider: "ollama", models: ["gemma4:e2b"], cached: true },
    }));

    await page.goto("/login");
    await page.evaluate(() => {
      localStorage.setItem("lavoro_esterno_access_token", "e2e-access-token");
    });
    await page.reload();
    await page.goto("/settings/ai");
    await expect(page.getByRole("heading", { name: "Impostazioni" })).toBeVisible();
    await expect(page.locator('input[value="gemma4:e2b"]')).toBeVisible();
    await expect(page.getByText("Un budget cloud pari a 0 blocca i provider remoti, ma non Ollama locale.")).toBeVisible();
    const openAIKey = page.getByLabel(/API key .* configurata/);
    await expect(openAIKey).toHaveAttribute("type", "password");
    await expect(openAIKey).toHaveValue("");
  });
});
