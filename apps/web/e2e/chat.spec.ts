import { test, expect } from "@playwright/test";
import path from "node:path";

test("streams a real FastAPI response through Next.js", async ({ page }) => {
  await page.goto("/demo");
  await expect(page.getByText("離線示範", { exact: true })).toBeVisible();
  await page.getByLabel("你的訊息").fill("想安排約會🙂\n第二行");
  const sent = page.waitForRequest((request) => request.url().endsWith("/api/chat"));
  await page.getByRole("button", { name: "送出訊息" }).click();
  const request = await sent;
  expect(request.method()).toBe("POST");
  expect(request.url()).not.toContain("message=");
  await expect(page.getByRole("status")).toHaveText("回覆完成");
  await expect(page.getByTestId("answer")).toContainText("想安排約會🙂");
  await expect(page.getByTestId("answer")).toContainText("第二行");
  await expect(page.getByTestId("answer")).toContainText("離線示範回覆");
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  await page.screenshot({ path: path.resolve(import.meta.dirname, "../../../artifacts/desktop.png"), fullPage: true });
});

for (const [scenario, message] of [
  ["rate_limit", "請求過於頻繁"],
  ["quota", "免費額度已用完"],
  ["timeout", "回覆逾時"],
  ["dependency_failure", "服務暫時無法使用"],
] as const) {
  test(`renders ${scenario} as failure, not success`, async ({ page }) => {
    await page.goto("/demo");
    await page.getByLabel("測試情境").selectOption(scenario);
    await page.getByLabel("你的訊息").fill("測試錯誤");
    await page.getByRole("button", { name: "送出訊息" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(message);
    await expect(page.getByRole("status")).toHaveText("回覆失敗");
    await expect(page.getByRole("button", { name: "送出訊息" })).toBeVisible();
  });
}

test("cancels a slow stream and allows the next request", async ({ page }) => {
  await page.goto("/demo");
  await page.getByLabel("測試情境").selectOption("slow");
  await page.getByLabel("你的訊息").fill("慢速串流");
  await page.getByRole("button", { name: "送出訊息" }).click();
  await expect(page.getByTestId("answer")).toContainText("慢速串流");
  await page.getByRole("button", { name: "停止回覆" }).click();
  await expect(page.getByRole("status")).toHaveText("已取消");
  const answer = await page.getByTestId("answer").textContent();
  await page.waitForTimeout(600);
  await expect(page.getByTestId("answer")).toHaveText(answer!);
  await page.getByLabel("測試情境").selectOption("normal");
  await page.getByLabel("你的訊息").fill("新的訊息");
  await page.getByRole("button", { name: "送出訊息" }).click();
  await expect(page.getByRole("status")).toHaveText("回覆完成");
  await expect(page.getByTestId("answer").last()).toContainText("新的訊息");
});

test("mobile composer is usable without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/demo");
  await expect(page.getByLabel("你的訊息")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: path.resolve(import.meta.dirname, "../../../artifacts/mobile.png"), fullPage: true });
});
