import { test, expect } from "@playwright/test";
import path from "node:path";
import { readFile } from "node:fs/promises";

test("creates a Chinese PDF through FastAPI and downloads the actual artifact", async ({ page }) => {
  await page.goto("/tools");
  await page.getByLabel("工具", { exact: true }).selectOption("generatePDF");
  await page.getByLabel("檔名", { exact: true }).fill("學習驗收.pdf");
  await page.getByLabel("內容", { exact: true }).fill("# 中文工具產物\n模型與工具依 call ID 關聯。");
  await page.getByRole("button", { name: "執行工具", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("工具完成");
  const pending = page.waitForEvent("download");
  await page.getByRole("link", { name: "學習驗收.pdf", exact: true }).click();
  const download = await pending;
  const target = path.resolve(import.meta.dirname, "../../../artifacts/s4-browser.pdf");
  await download.saveAs(target);
  const data = await readFile(target);
  expect(data.subarray(0, 5).toString()).toBe("%PDF-");
  expect(data.length).toBeGreaterThan(1000);
  await page.screenshot({ path: path.resolve(import.meta.dirname, "../../../artifacts/s4-tools-desktop.png"), fullPage: true });
});

test("rejects traversal and fits a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/tools");
  await page.getByLabel("工具", { exact: true }).selectOption("writeFile");
  await page.getByLabel("檔名", { exact: true }).fill("../escape.txt");
  await page.getByRole("button", { name: "執行工具", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("檔名不可包含路徑");
  await expect(page.getByRole("status")).toHaveText("工具失敗");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: path.resolve(import.meta.dirname, "../../../artifacts/s4-tools-mobile.png"), fullPage: true });
});
