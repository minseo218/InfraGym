import { expect, test, type Page } from "@playwright/test";

const API_URL = "http://localhost:8000";
const strongDebrief = {
  rootCause:
    "Traffic surge exhausted the database connection pool and a retry storm amplified load.",
  mitigation:
    "Capped retries with backoff, scaled replicas, and monitored latency during recovery.",
  prevention:
    "Add capacity load tests, SLO alerts, and a strict retry budget with pool limits.",
};

async function collectEvidence(page: Page) {
  for (const command of [
    "kubectl top pods",
    "kubectl logs deploy/ticketing-api --tail=20",
    "kubectl get pods",
  ]) {
    await page.getByRole("button", { name: command, exact: true }).click();
  }
  await expect(page.getByTestId("incident-score")).toHaveText("42");
}

async function completeDebrief(page: Page) {
  await page.getByRole("textbox", { name: "01 · ROOT CAUSE" }).fill(strongDebrief.rootCause);
  await page
    .getByRole("textbox", { name: "02 · MITIGATION & RECOVERY" })
    .fill(strongDebrief.mitigation);
  await page.getByRole("textbox", { name: "03 · PREVENTION" }).fill(strongDebrief.prevention);
  await page.getByRole("button", { name: "Complete incident review", exact: true }).click();
}

test("completes the persistent FastAPI-backed incident learning loop", async ({
  page,
  request,
}) => {
  const browserErrors: string[] = [];
  const failedResources: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failedResources.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto("/");
  await expect(page.getByTestId("engine-status")).toHaveText("Demo engine ready");

  const createResponsePromise = page.waitForResponse(
    (response) =>
      response.url() === `${API_URL}/api/v1/sessions` &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Launch incident ↗", exact: true }).click();
  const createResponse = await createResponsePromise;
  expect(createResponse.status()).toBe(201);
  const createdSession = (await createResponse.json()) as { id: string };
  expect(createdSession.id).toBeTruthy();
  await expect(page.getByTestId("engine-status")).toHaveText("Persistent engine online");
  await expect(page.getByTestId("engine-mode")).toHaveText("FASTAPI · SQLITE");

  const terminal = page.getByRole("textbox", { name: "Virtual terminal command" });
  await terminal.fill("cat /etc/passwd");
  await page.getByRole("button", { name: "Run ↵", exact: true }).click();
  await expect(
    page.getByText("bash: cat: command not available in this lab", { exact: false }),
  ).toBeVisible();

  await collectEvidence(page);
  const mitigation = page.getByRole("button", { name: "Apply safe mitigation", exact: true });
  await expect(mitigation).toBeEnabled({ timeout: 15_000 });
  await mitigation.click();

  await expect(page.getByRole("heading", { name: "Recovery verified" })).toBeVisible();
  await expect(page.getByTestId("persistence-status")).toContainText("SAVED TO SQLITE");
  await expect(
    page.locator(".metric-card").filter({ hasText: "P95 LATENCY" }).locator(".metric-value"),
  ).toHaveText("312 ms");

  for (const label of [
    "01 · ROOT CAUSE",
    "02 · MITIGATION & RECOVERY",
    "03 · PREVENTION",
  ]) {
    await page.getByRole("textbox", { name: label }).fill("short");
  }
  await page.getByRole("button", { name: "Complete incident review", exact: true }).click();
  await expect(
    page.getByText("Write at least one clear sentence for each section.", { exact: true }),
  ).toBeVisible();

  const completeResponsePromise = page.waitForResponse(
    (response) =>
      response.url() === `${API_URL}/api/v1/sessions/${createdSession.id}/complete` &&
      response.request().method() === "POST",
  );
  await completeDebrief(page);
  const completeResponse = await completeResponsePromise;
  expect(completeResponse.status()).toBe(200);

  await expect(page.getByRole("heading", { name: "Incident report" })).toBeVisible();
  await expect(page.getByTestId("final-score")).toHaveText("90");
  await expect(
    page.getByText("Strong causal chain and operational follow-through.", { exact: true }),
  ).toBeVisible();

  const persistedResponse = await request.get(
    `${API_URL}/api/v1/sessions/${createdSession.id}`,
  );
  expect(persistedResponse.status()).toBe(200);
  const persistedSession = (await persistedResponse.json()) as {
    status: string;
    score: number;
    evidence: string[];
  };
  expect(persistedSession).toMatchObject({
    status: "completed",
    score: 90,
  });
  expect(persistedSession.evidence).toEqual(["metrics", "logs", "events"]);

  await page.getByRole("button", { name: "Reset lab", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Launch incident ↗", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("incident-score")).toHaveText("0");
  expect(browserErrors).toEqual([]);
  expect(failedResources).toEqual([]);
});

test("falls back safely when FastAPI is unavailable", async ({ page }) => {
  await page.route(`${API_URL}/**`, (route) => route.abort("connectionfailed"));
  await page.goto("/");
  await page.getByRole("button", { name: "Launch incident ↗", exact: true }).click();

  await expect(page.getByTestId("engine-status")).toHaveText("Demo engine ready");
  await expect(page.getByTestId("engine-mode")).toHaveText("SAFE FALLBACK");
  await expect(page.getByTestId("terminal-mode")).toHaveText("mock shell · scenario-aware");

  await collectEvidence(page);
  const mitigation = page.getByRole("button", { name: "Apply safe mitigation", exact: true });
  await expect(mitigation).toBeEnabled({ timeout: 15_000 });
  await mitigation.click();
  await expect(page.getByTestId("persistence-status")).toContainText("DEMO SESSION");

  await completeDebrief(page);
  await expect(page.getByRole("heading", { name: "Incident report" })).toBeVisible();
  await expect(page.getByTestId("final-score")).toHaveText("70");
  await expect(
    page.getByText(
      "Debrief saved in demo mode. Connect the local API for persistent scoring and MTTR.",
      { exact: true },
    ),
  ).toBeVisible();
});

test.describe("mobile viewport", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("launches a persistent incident and exposes the terminal", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Train like a real systems engineer." }),
    ).toBeVisible();

    const createResponsePromise = page.waitForResponse(
      (response) =>
        response.url() === `${API_URL}/api/v1/sessions` &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Launch incident ↗", exact: true }).click();
    expect((await createResponsePromise).status()).toBe(201);

    await expect(page.getByTestId("engine-status")).toHaveText("Persistent engine online");
    await expect(page.getByTestId("terminal-mode")).toHaveText(
      "persistent shell · API connected",
    );
    await expect(
      page.getByRole("textbox", { name: "Virtual terminal command" }),
    ).toBeVisible();
    const viewport = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.clientWidth);
  });
});
