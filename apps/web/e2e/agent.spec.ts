import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test.skip(process.env.AGENT_LAB_E2E_PERSISTENCE !== "1", "需要 disposable DB");
test.setTimeout(90_000);

test("searches, produces a real PDF, persists and reloads a completed run", async ({ page }) => {
  await page.goto("/agent");
  await page.getByLabel("任務目標", { exact: true }).fill("搜尋 Agent 學習資源，整理成中文 PDF。");
  await page.getByRole("button", { name: "開始任務", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("已完成", { timeout: 65_000 });
  await expect(page.getByText("呼叫 searchWeb", { exact: true })).toBeVisible();
  await expect(page.getByText("呼叫 generatePDF", { exact: true })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "learning-report.pdf", exact: true }).click();
  const path = await (await download).path();
  expect((await readFile(path!)).subarray(0, 5).toString()).toBe("%PDF-");
  await expect(page.getByText("用量：unknown", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../artifacts/s6-agent-desktop.png", fullPage: true });
  await page.reload();
  await page.getByRole("button", { name: /搜尋 Agent 學習資源.*已完成/ }).first().click();
  await expect(page.getByRole("status")).toHaveText("已完成");
  await expect(page.getByRole("link", { name: "learning-report.pdf", exact: true })).toBeVisible();
});

test("cancels a slow run without starting tools and shows step limit distinctly", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/agent");
  await page.getByLabel("任務目標", { exact: true }).fill("fixture:slow");
  await page.getByRole("button", { name: "開始任務", exact: true }).click();
  await expect(page.getByText("任務已開始", { exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "取消任務", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("已取消", { timeout: 35_000 });
  await expect(page.getByText(/^呼叫 /)).toHaveCount(0);
  await page.getByLabel("任務目標", { exact: true }).fill("fixture:loop");
  await page.getByLabel("最多步數", { exact: true }).fill("1");
  await page.getByRole("button", { name: "開始任務", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("已達上限", { timeout: 65_000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../../artifacts/s6-agent-mobile.png", fullPage: true });
});
