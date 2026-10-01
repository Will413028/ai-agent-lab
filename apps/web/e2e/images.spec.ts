import { test, expect } from "@playwright/test";
import path from "node:path";

test("searches through a real MCP subprocess and displays image attribution", async ({ page }) => {
  await page.goto("/images");
  await page.getByLabel("圖片搜尋詞").fill("coffee");
  await page.getByRole("button", { name: "搜尋圖片", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("搜尋完成", { timeout: 35_000 });
  await expect(page.getByRole("img", { name: "學習圖片範例" })).toBeVisible();
  await expect(page.getByText("AI Agent Lab（示範插圖）")).toBeVisible();
  await expect(page.getByRole("link", { name: "CC0", exact: true })).toHaveAttribute("href", "https://creativecommons.org/publicdomain/zero/1.0/");
  await page.screenshot({ path: path.resolve(import.meta.dirname, "../../../artifacts/s5-images-desktop.png"), fullPage: true });
});
