import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "./fixtures";

test.describe("Search", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("mostra l'elenco completo quando non è applicato alcun filtro", async ({ page }) => {
    await page.goto("/search");
    await expect(page).toHaveURL(/\/records/);
    await expect(page.getByRole("heading", { name: "Elenco record" })).toBeVisible();
  });

  test("searching by a phone number that doesn't exist shows a real empty state", async ({ page }) => {
    await page.goto("/search");
    await page.getByPlaceholder("es. +39 345 678 9012").fill("+39 000 000 0000");

    // No record has ever been created with this number in this environment
    // (the seeded data is only the 9 sources, see app/scripts/seed_sources.py) —
    // this exercises the real backend query end-to-end, not a mock.
    await expect(page.getByText(/nessun record corrisponde ai filtri/i)).toBeVisible({ timeout: 10_000 });
  });

  test("filters are reflected in the URL and survive a reload", async ({ page }) => {
    await page.goto("/search");
    await page.getByPlaceholder("es. +39 345 678 9012").fill("+39 111 111 1111");
    await expect(page).toHaveURL(/phone=/);

    await page.reload();
    await expect(page.getByPlaceholder("es. +39 345 678 9012")).toHaveValue("+39 111 111 1111");
  });

  test("the Source Origin filter lists real seeded sources, not hardcoded placeholders", async ({
    page,
  }) => {
    await page.goto("/search");
    const sourceSelect = page.getByLabel("Fonte di origine");
    await expect(sourceSelect).toBeVisible();

    // Seeded via `app.scripts.seed_sources` (registry-backed, see
    // backend/app/scrapers/registry.py) — asserting on one confirms the
    // dropdown is populated from GET /sources, not the old hardcoded
    // web/forum/manual options.
    await expect(sourceSelect.locator("option", { hasText: "Bakeca Incontri" })).toHaveCount(1);
    await expect(sourceSelect.locator("option", { hasText: "Web Scrape" })).toHaveCount(0);
  });
});
