import { expect, type Page, test } from "@playwright/test";
import type { Message } from "../src/api/client";

const backend = "http://127.0.0.1:8765";

test.afterEach(async ({ request }) => {
  await request.post(`${backend}/__fixture__/mode`, { data: { hold: false } });
});

async function connect(page: Page) {
  await page.goto("/");
  await page.getByLabel("API access token", { exact: true }).fill("fixture-api-token");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Simulated SMS device", exact: true }),
  ).toBeVisible();
}

test("requires API authentication and exposes capability and identity observations", async ({
  page,
}) => {
  const balanceRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/balance")) balanceRequests.push(request.url());
  });
  await connect(page);
  await expect(page.getByText("simulated-sms-test", { exact: false })).toBeVisible();
  await expect(page.getByText("80", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("Live replies", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No stored messages" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Consult balance" })).toHaveCount(0);
  await expect(
    page.getByText("This device adapter does not offer balance consultation."),
  ).toBeVisible();
  expect(balanceRequests).toHaveLength(0);
  expect(
    await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length })),
  ).toEqual({ local: 0, session: 0 });
  expect(await page.content()).not.toContain("fixture-api-token");
  await page.getByRole("button", { name: "API connection" }).click();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.getByRole("heading", { name: "API access" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Manual submission" })).toHaveCount(0);
});

test("a status-only cellular device has no SMS or balance actions", async ({ page }) => {
  await connect(page);
  await page.getByLabel("Cellular device").selectOption("status-only");
  await expect(
    page.getByRole("heading", { name: "Simulated cellular device", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "SMS inbox not supported" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Manual submission" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Consult balance" })).toHaveCount(0);
  await page.getByRole("button", { name: "Reply jobs", exact: true }).click();
  await expect(page.getByRole("heading", { name: "SMS replies not supported" })).toBeVisible();
});

test("incoming SMS becomes a prepared plain-text reply and observable submission progress", async ({
  page,
  request,
}, testInfo) => {
  await request.get(`${backend}/__fixture__/ready`);
  await request.post(`${backend}/__fixture__/mode`, { data: { hold: true } });
  await connect(page);
  const text = "Hello from the simulated SIM. <img src=x onerror=alert('unsafe')>";
  await request.post(`${backend}/__fixture__/incoming`, { data: { text } });
  await expect(page.getByText(text, { exact: true })).toBeVisible();
  await expect(page.locator(".message img")).toHaveCount(0);
  await page.getByRole("button", { name: "Reply jobs", exact: true }).click();
  await expect(page.locator(".job .badge").first()).toHaveText("Submitting");
  await page.getByRole("button", { name: "View submission" }).first().click();
  const progress = page.getByRole("region", { name: "Selected submission", exact: true });
  await expect(
    progress.getByText("Hello! This is a simulated assistant reply.", { exact: true }),
  ).toBeVisible();
  await expect(progress.getByText("In progress", { exact: true })).toBeVisible();
  await expect(progress.getByText("Part 1", { exact: true })).toBeVisible();
  await request.post(`${backend}/__fixture__/mode`, { data: { hold: false } });
  await expect(progress.getByText("Accepted for submission", { exact: true })).toBeVisible();
  await expect(progress.getByText("Acceptance does not confirm recipient delivery.")).toBeVisible();
  expect((await (await request.get(`${backend}/__fixture__/effects`)).json()).submissions).toBe(1);
  await page.evaluate(() => window.scrollTo(0, 0));
  await testInfo.attach("operator-console", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});

test("manual submission normalizes text and existing progress can be checked without resending", async ({
  page,
  request,
}) => {
  await connect(page);
  const before = (await (await request.get(`${backend}/__fixture__/effects`)).json()).submissions;
  await page.getByLabel("Destination", { exact: true }).fill("+212600000000");
  await page.getByLabel("Message", { exact: true }).fill("**Manual** reply test");
  await page.getByRole("button", { name: "Submit SMS", exact: false }).click();
  const composer = page.locator(".composer");
  await expect(composer.getByText("Accepted for submission", { exact: true })).toBeVisible();
  await expect(composer.getByText("Manual reply test", { exact: true })).toBeVisible();
  const id = await page.getByLabel("Request ID — keep this to find progress later").inputValue();
  await composer.getByRole("button", { name: "Check progress" }).click();
  await expect(composer.getByText("Accepted for submission", { exact: true })).toBeVisible();
  await connect(page);
  await page.getByLabel("Submission request ID", { exact: true }).fill(id);
  await page.getByRole("button", { name: "Look up", exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "Selected submission", exact: true })
      .getByText("Manual reply test", { exact: true }),
  ).toBeVisible();
  expect((await (await request.get(`${backend}/__fixture__/effects`)).json()).submissions).toBe(
    before + 1,
  );
});

test("loading, offline, server errors and no-device states are explicit", async ({ page }) => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/devices", async (route) => {
    await gate;
    await route.abort();
  });
  await page.goto("/");
  await expect(page.getByRole("status").first()).toHaveText("Loading…");
  release();
  await expect(page.getByRole("heading", { name: "Server is offline" })).toBeVisible();
  await page.unroute("**/api/devices");
  await page.route("**/api/devices", (route) =>
    route.fulfill({ status: 502, json: { detail: "private provider credentials" } }),
  );
  await page.getByRole("button", { name: "Retry connection" }).click();
  await expect(page.getByRole("heading", { name: "Unable to load devices" })).toBeVisible();
  await expect(page.getByText("private provider credentials")).toHaveCount(0);
  await page.unroute("**/api/devices");
  await page.route("**/api/devices", (route) => route.fulfill({ json: [] }));
  await page.getByRole("button", { name: "Retry connection" }).click();
  await expect(page.getByRole("heading", { name: "No configured devices" })).toBeVisible();
});

test("dry-run policy is visible and a mobile viewport has no horizontal overflow", async ({
  page,
}) => {
  await page.route("**/api/devices/demo-sms/assistant", (route) =>
    route.fulfill({ json: { auto_reply: true, dry_run: true, jobs: {} } }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await connect(page);
  await expect(page.getByText("Dry run", { exact: true })).toBeVisible();
  await expect(
    page.getByText("The assistant prepares replies without submitting SMS."),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByLabel("Cellular device").selectOption("status-only");
  await expect(page.getByRole("heading", { name: "SMS inbox not supported" })).toBeVisible();
});

test("inbox pagination follows server pages without mixing records", async ({ page }) => {
  const rows: Message[] = Array.from({ length: 28 }, (_, index) => ({
    id: `fixture-${index}`,
    device_id: "demo-sms",
    storage_generation: "fixture",
    storage: "memory",
    subscription_generation: "fixture",
    subscription_uncertain: false,
    provider_id: String(index),
    sender: { value: "SIMULATED", kind: "alphanumeric" },
    body: `Paged message ${index + 1}`,
    provider_timestamp: `fixture-${index}`,
    complete: true,
    baselined: true,
    replyable: false,
    observed_at: "2026-10-16T12:00:00Z",
  }));
  await page.route("**/api/devices/demo-sms/messages?*", (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    return route.fulfill({ json: rows.slice(offset, offset + 25) });
  });
  await connect(page);
  await expect(page.getByText("Paged message 1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("Paged message 26", { exact: true })).toBeVisible();
  await expect(page.getByText("Paged message 1", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Previous", exact: true }).click();
  await expect(page.getByText("Paged message 1", { exact: true })).toBeVisible();
});

test("supported balance is consulted only on an explicit operator action", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/balance")) requests.push(request.url());
  });
  await connect(page);
  await page.getByLabel("Cellular device").selectOption("balance-demo");
  const consult = page.getByRole("button", { name: "Consult balance", exact: true });
  await expect(consult).toBeVisible();
  expect(requests).toHaveLength(0);
  await consult.click();
  await expect(page.getByText("SIMULATED carrier response:", { exact: false })).toBeVisible();
  await expect(page.getByText("Not reported", { exact: true })).toHaveCount(2);
  await page.getByRole("button", { name: "Refresh", exact: false }).click();
  await expect(page.getByText("SIMULATED carrier response:", { exact: false })).toBeVisible();
  expect(requests).toHaveLength(1);
});

test("unknown manual outcomes are observable and never automatically resent", async ({
  page,
  request,
}) => {
  await request.post(`${backend}/__fixture__/mode`, { data: { outcome: "unknown" } });
  await connect(page);
  const before = (await (await request.get(`${backend}/__fixture__/effects`)).json()).submissions;
  await page.getByLabel("Destination", { exact: true }).fill("+212600000000");
  await page.getByLabel("Message", { exact: true }).fill("One uncertain submission.");
  await page.getByRole("button", { name: "Submit SMS", exact: false }).click();
  const composer = page.locator(".composer");
  await expect(composer.getByText("Unknown outcome", { exact: true })).toBeVisible();
  await expect(composer.getByText("An outcome is uncertain.", { exact: false })).toBeVisible();
  await composer.getByRole("button", { name: "Check progress" }).click();
  await expect(composer.getByText("Unknown outcome", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Refresh", exact: false }).click();
  expect((await (await request.get(`${backend}/__fixture__/effects`)).json()).submissions).toBe(
    before + 1,
  );
});
