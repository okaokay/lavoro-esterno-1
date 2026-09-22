/** Regressioni UI per duplicazione, riabilitazione e permessi delle fonti. */
import { test, expect, type Page } from "@playwright/test";

const admin = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "admin@example.test",
  name: "Admin",
  role: "admin",
  mfa_enabled: true,
  status: "active",
};

const enabledSource = {
  id: "10000000-0000-4000-8000-000000000001",
  code: "original",
  name: "Original source",
  country: "N/D",
  status: "healthy",
  enabled: true,
  priority: "high",
  lastRunAt: null,
  itemsLast24h: 0,
  errorRate: 0,
  consecutiveFailures: 0,
  hasScrapeConfig: true,
  proxyPoolId: null,
  proxyPoolStatus: "direct",
  automaticScrapingEnabled: false,
  scrapeIntervalMinutes: null,
  nextScrapeAt: null,
  lastScheduledAt: null,
  lastCompletedScrapeAt: null,
  lastScheduleSkipReason: null,
  scheduleRevision: 1,
  automaticScrapingState: "paused",
};

const disabledSource = {
  ...enabledSource,
  id: "20000000-0000-4000-8000-000000000002",
  code: "disabled_source",
  name: "Disabled source",
  status: "offline",
  enabled: false,
};

async function mockSourcesPage(page: Page, role = "admin", extraSources: (typeof enabledSource)[] = []) {
  await page.addInitScript(() => {
    localStorage.setItem("lavoro_esterno_access_token", "token");
    localStorage.setItem("lavoro_esterno_refresh_token", "refresh");
  });
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { ...admin, role } }));
  await page.route("**/api/v1/notifications", (route) =>
    route.fulfill({ json: { items: [], unreadCount: 0 } }),
  );
  await page.route("**/api/v1/sources/summary", (route) =>
    route.fulfill({ json: { total: 2 + extraSources.length, active: 1, degraded: 0, offline: 1 } }),
  );
  await page.route("**/api/v1/sources", (route) =>
    route.fulfill({ json: [enabledSource, disabledSource, ...extraSources] }),
  );
  await page.route("**/api/v1/admin/proxy-pools", (route) => route.fulfill({ json: [] }));
}

test("admin duplicates a source with a collision-safe suggested identity", async ({ page }) => {
  await mockSourcesPage(page, "admin", [
    {
      ...enabledSource,
      id: "40000000-0000-4000-8000-000000000004",
      code: "original_copy",
      name: "Existing copy",
    },
  ]);
  let requestBody: unknown;
  await page.route(`**/api/v1/sources/${enabledSource.id}/duplicate`, async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      json: {
        ...enabledSource,
        id: "30000000-0000-4000-8000-000000000003",
        code: "original_copy_2",
        name: "Original source (copia)",
        status: "offline",
        enabled: false,
      },
    });
  });

  await page.goto("/sources");
  const originalRow = page.getByRole("row").filter({ hasText: "Original source" });
  await originalRow.hover();
  await originalRow.getByRole("button", { name: "Duplica Original source" }).click();

  const dialog = page.getByRole("dialog", { name: "Duplica fonte" });
  await expect(dialog.getByLabel("Nome")).toHaveValue("Original source (copia)");
  await expect(dialog.getByLabel("Slug (identificatore univoco)")).toHaveValue("original_copy_2");
  await dialog.getByRole("button", { name: "Duplica", exact: true }).click();

  await expect(dialog).toBeHidden();
  expect(requestBody).toEqual({ name: "Original source (copia)", slug: "original_copy_2" });
});

test("disabled source exposes Enable and hides operational stop actions", async ({ page }) => {
  await mockSourcesPage(page);
  let enabled = false;
  await page.route(`**/api/v1/sources/${disabledSource.id}/enable`, async (route) => {
    enabled = true;
    await route.fulfill({ status: 204 });
  });

  await page.goto("/sources");
  const disabledRow = page.getByRole("row").filter({ hasText: "Disabled source" });
  await disabledRow.hover();
  await expect(disabledRow.getByRole("button", { name: "Abilita Disabled source" })).toBeVisible();
  await expect(disabledRow.getByTitle("Metti in pausa")).toHaveCount(0);
  await expect(disabledRow.getByTitle("Disabilita")).toHaveCount(0);
  await expect(disabledRow.getByTitle("Avvia scansione")).toHaveCount(0);
  await disabledRow.getByRole("button", { name: "Abilita Disabled source" }).click();
  await expect.poll(() => enabled).toBe(true);
});

test("duplicate action is hidden from operators", async ({ page }) => {
  await mockSourcesPage(page, "operator");
  await page.goto("/sources");
  await expect(page.getByRole("button", { name: /Duplica / })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Abilita Disabled source" })).toBeAttached();
});

test("slug collision keeps the duplicate dialog open and shows the API error", async ({ page }) => {
  await mockSourcesPage(page);
  await page.route(`**/api/v1/sources/${enabledSource.id}/duplicate`, (route) =>
    route.fulfill({ status: 409, json: { detail: "Una fonte con slug 'original_copy' esiste gia." } }),
  );

  await page.goto("/sources");
  await page.getByRole("row").filter({ hasText: "Original source" }).hover();
  await page.getByRole("button", { name: "Duplica Original source" }).click();
  const dialog = page.getByRole("dialog", { name: "Duplica fonte" });
  await dialog.getByRole("button", { name: "Duplica", exact: true }).click();

  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Una fonte con slug 'original_copy' esiste gia.")).toBeVisible();
});

test("enable failure is surfaced without hiding the source", async ({ page }) => {
  await mockSourcesPage(page);
  await page.route(`**/api/v1/sources/${disabledSource.id}/enable`, (route) =>
    route.fulfill({ status: 503, json: { detail: "Riabilitazione temporaneamente non disponibile." } }),
  );

  await page.goto("/sources");
  await page.getByRole("row").filter({ hasText: "Disabled source" }).hover();
  await page.getByRole("button", { name: "Abilita Disabled source" }).click();

  await expect(page.getByRole("alert")).toContainText("Si è verificato un errore sul server.");
  await expect(page.getByText("Disabled source")).toBeVisible();
});

test("configuration test sends the unsaved pagination draft and shows diagnostics", async ({ page }) => {
  await mockSourcesPage(page);
  const savedConfig = {
    startUrls: ["https://example.test/list"],
    adLinkSelector: "a.ad",
    adLinkSelectorType: "css" as const,
    nextPageSelector: "a.old-next",
    nextPageSelectorType: "css" as const,
    maxPages: 1,
    maxAdsPerRun: 50,
    rateLimitSeconds: 2,
    fetchMode: "stealth",
    renderJs: true,
    fields: {
      phone: { selector: ".phone", selectorType: "css" as const, attribute: "text", multiple: false },
      reviews: {
        extractionMode: "items",
        multiple: true,
        containerSelector: "//article[@class='review']",
        containerSelectorType: "xpath" as const,
        itemFields: {
          author: { selector: ".//span[@class='author']", selectorType: "xpath" as const, attribute: "text" },
          text: { selector: ".text", selectorType: "css" as const, attribute: "text" },
        },
        pagination: {
          nextSelector: "//button[@class='more']",
          nextSelectorType: "xpath" as const,
          maxPages: 10,
          maxItems: 1000,
        },
      },
    },
  };
  await page.route(`**/api/v1/sources/${enabledSource.id}`, (route) =>
    route.fulfill({
      json: {
        ...enabledSource,
        scrapeConfig: savedConfig,
        watermarkRemoval: { enabled: false, authorizationReference: null, regions: [] },
      },
    }),
  );
  let testBody: { scrapeConfig?: typeof savedConfig } = {};
  await page.route(`**/api/v1/sources/${enabledSource.id}/test-config`, async (route) => {
    testBody = route.request().postDataJSON();
    await route.fulfill({
      json: {
        adUrlsFound: 80,
        sampleUrl: "https://example.test/ad/1",
        extractedFields: { phone: "redacted" },
        warnings: [],
        error: null,
        pagesVisited: 5,
        configuredMaxPages: 5,
        paginationMode: "click",
        paginationStopReason: "max_pages",
        uniqueAdsFound: 80,
        fieldPagination: {
          reviews: {
            pagesVisited: 3,
            itemsCollected: 24,
            paginationMode: "click",
            stopReason: "end_of_pagination",
            complete: true,
          },
        },
      },
    });
  });

  await page.goto("/sources");
  const row = page.getByRole("row").filter({ hasText: "Original source" });
  await row.hover();
  await row.getByTitle("Modifica configurazione").click();
  const dialog = page.getByRole("dialog", { name: "Modifica fonte" });
  await expect(dialog.getByLabel("Tipo estrazione reviews")).toHaveValue("items");
  await expect(dialog.getByLabel("Tipo container reviews")).toHaveValue("xpath");
  await expect(dialog.getByLabel("Tipo sotto-campo author")).toHaveValue("xpath");
  await expect(dialog.getByLabel("Tipo paginazione reviews")).toHaveValue("xpath");
  await expect(dialog.getByLabel("Impagina reviews")).toBeChecked();
  await expect(dialog.getByLabel("Selettore paginazione reviews")).toHaveValue("//button[@class='more']");
  await dialog.getByLabel("Pagine massime", { exact: true }).fill("5");
  await dialog.getByLabel("Selettore pagina successiva (opzionale)").fill("//a[@aria-label='Next']");
  await dialog.getByLabel("Tipo selettore pagina successiva").selectOption("xpath");
  await dialog.getByRole("button", { name: "Prova configurazione" }).click();

  await expect(dialog.getByText("Pagine: 5/5")).toBeVisible();
  await expect(dialog.getByText("Annunci unici: 80")).toBeVisible();
  await expect(dialog.getByText("Modalità: click")).toBeVisible();
  await expect(dialog.getByText("24 elementi")).toBeVisible();
  await expect(dialog.getByText("completa")).toBeVisible();
  expect(testBody.scrapeConfig?.maxPages).toBe(5);
  expect(testBody.scrapeConfig?.nextPageSelector).toBe("//a[@aria-label='Next']");
  expect(testBody.scrapeConfig?.nextPageSelectorType).toBe("xpath");
  expect(testBody.scrapeConfig?.fields.reviews.pagination).toEqual({
    nextSelector: "//button[@class='more']",
    nextSelectorType: "xpath",
    maxPages: 10,
    maxItems: 1000,
  });
});

test("admin configures a fixed-delay schedule and sees the next execution", async ({ page }) => {
  await mockSourcesPage(page);
  let requestBody: unknown;
  await page.route(`**/api/v1/sources/${enabledSource.id}/schedule`, async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({
      json: {
        ...enabledSource,
        automaticScrapingEnabled: true,
        scrapeIntervalMinutes: 120,
        nextScrapeAt: "2026-09-08T13:20:00Z",
        scheduleRevision: 2,
        automaticScrapingState: "waiting",
      },
    });
  });

  await page.goto("/sources");
  const row = page.getByRole("row").filter({ hasText: "Original source" });
  await row.hover();
  await row.getByRole("button", { name: "Pianifica Original source" }).click();

  const dialog = page.getByRole("dialog", { name: "Pianificazione acquisizione automatica" });
  await dialog.getByLabel("Abilita acquisizione automatica").check();
  await dialog.getByLabel("Intervallo").fill("2");
  await dialog.getByLabel("Unità").selectOption("hours");
  await dialog.getByRole("button", { name: "Salva pianificazione" }).click();

  await expect(dialog).toBeHidden();
  expect(requestBody).toEqual({
    enabled: true,
    intervalValue: 2,
    intervalUnit: "hours",
    revision: 1,
  });
});
