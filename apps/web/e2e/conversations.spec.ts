import { test, expect } from "@playwright/test";
import path from "node:path";

test.skip(process.env.AGENT_LAB_E2E_PERSISTENCE !== "1", "Run make check-chat for a disposable PostgreSQL database.");

async function send(page: import("@playwright/test").Page, message: string) {
  await page.getByLabel("你的訊息").fill(message);
  await page.getByRole("button", { name: "送出訊息" }).click();
  await expect(page.getByRole("status")).toHaveText("回覆完成");
  await expect(page.getByRole("button", { name: "送出訊息" })).toBeDisabled();
}

test("persists multiple turns and reports across refresh, then cascades deletion", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("準備就緒");
  await page.getByRole("button", { name: "新對話" }).click();
  await send(page, "S2_BROWSER：我想和對方去散步🙂");
  await send(page, "我先前想做什麼？");
  await expect(page.getByTestId("answer").last()).toContainText("我記得你先前提到");
  await expect(page.getByTestId("answer").last()).toContainText("S2_BROWSER");
  await expect.poll(() => page.getByLabel("對話紀錄").evaluate(node => node.scrollHeight - node.clientHeight - node.scrollTop)).toBeLessThan(2);
  const id = await page.getByLabel("選擇對話").inputValue();
  await page.getByRole("button", { name: "產生報告" }).click();
  await expect(page.getByRole("status")).toHaveText("報告已儲存");
  await expect(page.getByRole("region", { name: "戀愛報告" })).toContainText("你的戀愛溝通練習報告");
  await page.reload();
  await expect(page.getByRole("status")).toHaveText("準備就緒");
  await expect(page.getByTestId("answer")).toHaveCount(2);
  await expect(page.getByLabel("選擇對話")).toHaveValue(id);
  await expect(page.getByRole("region", { name: "戀愛報告" }).getByRole("listitem")).toHaveCount(3);
  await page.screenshot({ path: path.resolve(import.meta.dirname, "../../../artifacts/s2-desktop.png"), fullPage: true });
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "刪除對話" }).click();
  await expect(page.getByRole("status")).toHaveText("對話已刪除");
  expect((await page.request.get(`/api/conversations/${id}`)).status()).toBe(404);
  await expect(page.getByTestId("answer")).toHaveCount(0);
});

test("switches two conversations without leaking context", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("準備就緒");
  await page.getByRole("button", { name: "新對話" }).click();
  await send(page, "S2_ONLY_A：喜歡咖啡");
  const first = await page.getByLabel("選擇對話").inputValue();
  await page.getByRole("button", { name: "新對話" }).click();
  await send(page, "S2_ONLY_B：喜歡電影");
  const second = await page.getByLabel("選擇對話").inputValue();
  await expect(page.getByTestId("answer")).not.toContainText("S2_ONLY_A");
  await page.getByLabel("選擇對話").selectOption(first);
  await expect(page.getByTestId("answer")).toContainText("S2_ONLY_A");
  await send(page, "記得我的喜好嗎？");
  await expect(page.getByTestId("answer").last()).not.toContainText("S2_ONLY_B");
  await page.getByLabel("選擇對話").selectOption(second);
  await expect(page.getByTestId("answer")).toHaveCount(1);
  await expect(page.getByTestId("answer")).toContainText("S2_ONLY_B");
});

test("cancelled partial text persists and a following request works", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("準備就緒");
  await page.getByRole("button", { name: "新對話" }).click();
  await page.getByLabel("測試情境").selectOption("slow");
  await page.getByLabel("你的訊息").fill("S2_CANCELLED");
  await page.getByRole("button", { name: "送出訊息" }).click();
  await expect(page.getByTestId("answer")).toContainText("S2_CANCELLED");
  await page.getByRole("button", { name: "停止回覆" }).click();
  await expect(page.getByRole("status")).toHaveText("已取消");
  await expect(page.getByRole("button", { name: "新對話" })).toBeEnabled();
  await page.reload();
  await expect(page.getByRole("status")).toHaveText("準備就緒");
  await expect(page.getByText("已取消", { exact: true })).toBeVisible();
  await expect(page.getByTestId("answer")).toContainText("S2_CANCELLED");
  await page.getByLabel("測試情境").selectOption("normal");
  await send(page, "S2_AFTER_CANCEL");
  await expect(page.getByTestId("answer").last()).not.toContainText("我記得你先前提到：「S2_CANCELLED");
});

test("mobile saved conversations and reports remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("準備就緒");
  await expect(page.getByLabel("選擇對話")).toBeVisible();
  await expect(page.getByRole("button", { name: "新對話" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: path.resolve(import.meta.dirname, "../../../artifacts/s2-mobile.png"), fullPage: true });
});
