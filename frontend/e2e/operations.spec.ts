/** Regressioni trasversali per dashboard, account, Admin e operazioni. */
import { test, expect } from "@playwright/test";

const user = { id: "00000000-0000-4000-8000-000000000001", email: "admin@example.test", name: "Admin", role: "admin", mfa_enabled: true, status: "active" };

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("lavoro_esterno_access_token", "token");
    localStorage.setItem("lavoro_esterno_refresh_token", "refresh");
  });
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/notifications", (route) => route.fulfill({ json: { items: [], unreadCount: 0 } }));
});

test("records lists all sources without an explicit filter", async ({ page }) => {
  await page.route("**/api/v1/sources", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/records/search?*", (route) => route.fulfill({ json: { results: [], total: 0, page: 1, pageSize: 25 } }));
  await page.goto("/records");
  await expect(page.getByRole("heading", { name: "Record", exact: true })).toBeVisible();
  await expect(page.getByLabel("Fonte di origine")).toHaveValue("");
  await expect(page.getByText("Nessun record corrisponde ai filtri.")).toBeVisible();
});

test("missing AI summary is an empty state rather than a query error", async ({ page }) => {
  const id = "639fd3fb-27d6-4389-9893-4b03b5b95e33";
  await page.route(`**/api/v1/records/${id}`, (route) => route.fulfill({ json: { id, phone: "***", phoneVisibility: "masked", canonicalTitle: "Test", canonicalDescription: "", confidenceScore: 1, sourcesCount: 1, occurrencesCount: 1, firstSeenAt: "2026-01-01T00:00:00Z", lastSeenAt: "2026-01-01T00:00:00Z", status: "verified", tags: [] } }));
  await page.route(`**/api/v1/records/${id}/ai-summary`, (route) => route.fulfill({ status: 204 }));
  await page.route(`**/api/v1/records/${id}/ai-summary/versions`, (route) => route.fulfill({ json: [] }));
  await page.goto(`/records/${id}/ai-summary`);
  await expect(page.getByText("Nessun riepilogo AI disponibile per questo record.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Genera riepilogo/ })).toBeVisible();
});

test("account button opens the account page", async ({ page }) => {
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Account" })).toBeVisible();
  await expect(page.getByText("admin@example.test")).toBeVisible();
});

const dashboardKpis = {
  totalRecords: 12,
  totalRecordsDeltaPct: 10,
  activeSources: 2,
  activeSourcesHealthyPct: 100,
  newRecordsToday: 2,
  scrapingErrors: 0,
  scrapingErrorsDelta: 0,
  activeExports: 0,
  rangeStart: "2026-09-03T12:00:00Z",
  rangeEnd: "2026-09-04T12:00:00Z",
  newRecordsInRange: 2,
  newRecordsDeltaPct: 10,
};

async function mockDashboard(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/dashboard/kpis?*", (route) =>
    route.fulfill({
      json: dashboardKpis,
    }),
  );
  await page.route("**/api/v1/dashboard/scraping-activity?*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/dashboard/source-health", (route) =>
    route.fulfill({ json: { healthy: 0, rateLimited: 0, error: 0, total: 0 } }),
  );
  await page.route("**/api/v1/dashboard/activity?*", (route) => route.fulfill({ json: [] }));
}

test("dashboard detailed diagnostics opens and loads system status", async ({ page }) => {
  await mockDashboard(page);

  let diagnosticsRequests = 0;
  await page.route("**/api/v1/system/status", (route) => {
    diagnosticsRequests += 1;
    return route.fulfill({
      json: {
        status: "healthy",
        checkedAt: "2026-09-04T12:00:00Z",
        components: [{ name: "PostgreSQL", status: "healthy", latencyMs: 4, message: null }],
      },
    });
  });

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Visualizza diagnostica dettagliata" }).click();

  await expect(page.getByRole("dialog", { name: "Stato del sistema" })).toBeVisible();
  await expect(page.getByText("PostgreSQL")).toBeVisible();
  expect(diagnosticsRequests).toBe(1);
});

test("dashboard range selector persists the range and refresh reports completion", async ({ page }) => {
  let kpiRequests = 0;
  const requestedEnds: string[] = [];
  await mockDashboard(page);
  await page.unroute("**/api/v1/dashboard/kpis?*");
  await page.route("**/api/v1/dashboard/kpis?*", (route) => {
    kpiRequests += 1;
    requestedEnds.push(new URL(route.request().url()).searchParams.get("end") ?? "");
    return route.fulfill({ json: dashboardKpis });
  });

  await page.goto("/dashboard");
  await expect(page.getByText("Nuovi record", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Ultime 24 ore/ }).click();
  await page.getByRole("button", { name: "7 giorni" }).click();
  await expect(page).toHaveURL(/range=7d/);
  await expect(page.getByRole("button", { name: /Ultimi 7 giorni/ })).toBeVisible();

  const beforeRefresh = kpiRequests;
  const endBeforeRefresh = requestedEnds.at(-1)!;
  await page.getByRole("button", { name: "Aggiorna dati" }).click();
  await expect(page.getByText(/Aggiornato alle \d{2}:\d{2}:\d{2}/)).toBeVisible();
  expect(kpiRequests).toBeGreaterThan(beforeRefresh);
  expect(new Date(requestedEnds.at(-1)!).valueOf()).toBeGreaterThan(
    new Date(endBeforeRefresh).valueOf(),
  );

  await page.getByRole("button", { name: /Ultimi 7 giorni/ }).click();
  await page.getByRole("button", { name: "Applica intervallo" }).click();
  await expect(page).toHaveURL(/range=custom/);
  await expect(page).toHaveURL(/start=/);
  await expect(page).toHaveURL(/end=/);
});

test("create-user dialog keeps focus while typing", async ({ page }) => {
  await page.route("**/api/v1/admin/users", (route) => route.fulfill({ json: [] }));
  await page.goto("/admin");
  await page.getByRole("button", { name: "Crea utente" }).click();

  const email = page.getByLabel("Email");
  await expect(email).toBeFocused();
  await email.pressSequentially("new.user@example.test");

  await expect(email).toBeFocused();
  await expect(email).toHaveValue("new.user@example.test");
});
