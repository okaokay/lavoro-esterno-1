import { expect, test, type Page } from "@playwright/test";

const overview = {
  id: "record-custom-fields",
  phone: "+39 *** *** 1234",
  phoneVisibility: "masked",
  canonicalTitle: "Synthetic listing",
  canonicalDescription: "Description",
  confidenceScore: 100,
  sourcesCount: 1,
  occurrencesCount: 1,
  firstSeenAt: "2026-09-07T10:00:00Z",
  lastSeenAt: "2026-09-07T11:00:00Z",
  status: "verified",
  tags: ["one", "two"],
  customFields: {
    tags: ["one", "two"],
    location: "Roma\nCentro",
    emptyField: null,
  },
  customFieldGroups: [
    {
      name: "paperino",
      values: [
        {
          value: "qua",
          sourceId: "source-1",
          sourceName: "Source one",
          sourceCode: "source_one",
          advertisementId: "occurrence-1",
          isCanonical: true,
        },
      ],
    },
    {
      name: "pippo",
      values: [
        {
          value: "pluto",
          sourceId: "source-2",
          sourceName: "Source two",
          sourceCode: "source_two",
          advertisementId: "occurrence-2",
          isCanonical: false,
        },
      ],
    },
    {
      name: "tags",
      values: [
        {
          value: ["one", "two"],
          sourceId: "source-1",
          sourceName: "Source one",
          sourceCode: "source_one",
          advertisementId: "occurrence-1",
          isCanonical: true,
        },
      ],
    },
  ],
};

async function mockAuthenticatedRecord(page: Page) {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "admin-1",
        email: "admin@example.test",
        name: "Admin",
        role: "admin",
        mfa_enabled: true,
        status: "active",
      },
    }),
  );
  await page.route("**/api/v1/notifications", (route) =>
    route.fulfill({ json: { items: [], unreadCount: 0 } }),
  );
  await page.route("**/api/v1/records/record-custom-fields/occurrences", (route) =>
    route.fulfill({
      json: [
        {
          id: "occurrence-1",
          sourceName: "Synthetic source",
          sourceCode: "synthetic",
          title: "Synthetic listing",
          url: "https://example.test/listing",
          scrapedAt: "2026-09-07T11:00:00Z",
          isCanonical: true,
          matchConfidence: 100,
          customFields: { tags: ["one", "two"], price: "100 EUR" },
          revision: 2,
          lastChangedAt: "2026-09-07T11:00:00Z",
          hasUpdates: true,
        },
      ],
    }),
  );
  await page.route(
    "**/api/v1/records/record-custom-fields/occurrences/occurrence-1/versions",
    (route) =>
      route.fulfill({
        json: [
          {
            id: "version-2",
            advertisementId: "occurrence-1",
            revision: 2,
            scrapeRunId: "run-2",
            changedFields: ["customFields"],
            snapshot: {
              title: "Synthetic listing",
              description: "Description",
              customFields: { price: "100 EUR" },
              mediaHashes: [],
            },
            createdAt: "2026-09-07T11:00:00Z",
          },
        ],
      }),
  );
  await page.route("**/api/v1/records/record-custom-fields", (route) => route.fulfill({ json: overview }));
}

test("shows fields aggregated from all sources and expandable occurrence fields", async ({ page }) => {
  await mockAuthenticatedRecord(page);

  // Establish the target origin before explicitly seeding storage. This is
  // reliable on Windows even when the first document starts at `about:blank`.
  await page.goto("/login");
  await page.evaluate(() => {
    localStorage.setItem("lavoro_esterno_access_token", "test-token");
  });
  await page.goto("/records/record-custom-fields/overview");
  await expect(page.getByRole("heading", { name: "Tutti i campi raccolti", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "paperino", exact: true })).toBeVisible();
  await expect(page.getByText("qua", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "pippo", exact: true })).toBeVisible();
  await expect(page.getByText("pluto", { exact: true })).toBeVisible();
  await expect(page.getByText("Source two", { exact: true })).toBeVisible();
  const tagsSection = page.getByRole("heading", { name: "Tag", exact: true }).locator("..");
  await expect(tagsSection.getByText("one", { exact: true })).toBeVisible();

  await page.goto("/records/record-custom-fields/occurrences");
  await page.getByRole("button", { name: /mostra campi personalizzati/i }).click();
  await expect(page.getByText("Price", { exact: true })).toBeVisible();
  await expect(page.getByText("100 EUR", { exact: true })).toBeVisible();
});
