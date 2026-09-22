/** Verifica creazione e ciclo di vita dell'export dalla SPA. */
import { test, expect } from "@playwright/test";
import { loginAsAdmin } from "./fixtures";

test.describe("Exports", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("an explicit record selection or filter is required", async ({ page }) => {
    await page.goto("/exports");
    await expect(page.getByTestId("export-card-text_only").getByRole("button", { name: "Crea esportazione" })).toBeDisabled();
    await expect(page.getByText("nessun ambito selezionato", { exact: true })).toBeVisible();
  });

  test("a selected record enables creation and pending-job polling", async ({ page }) => {
    const recordId = "00000000-0000-4000-8000-000000000001";
    const response = {
      id: "00000000-0000-4000-8000-000000000002",
      type: "text_only",
      status: "pending",
      progressPct: 0,
      requestedBy: "admin@lavoro.internal",
      requestedAt: new Date().toISOString(),
      startedAt: null,
      completedAt: null,
      expiresAt: new Date(Date.now() + 86_400_000).toISOString(),
      recordCount: 1,
      estimatedUncompressedBytes: 0,
      archiveSizeBytes: null,
      phoneVisibility: "clear",
      errorMessage: null,
      downloadUrl: null,
    };
    await page.route("**/api/v1/exports", async (route) => {
      if (route.request().method() === "POST") await route.fulfill({ json: response, status: 202 });
      else await route.fulfill({ json: [response] });
    });
    await page.goto(`/exports?recordIds=${recordId}`);
    await page.getByTestId("export-card-text_only").getByRole("button", { name: "Crea esportazione" }).click();
    await expect(page.getByText("In attesa", { exact: true })).toBeVisible();
  });
});
