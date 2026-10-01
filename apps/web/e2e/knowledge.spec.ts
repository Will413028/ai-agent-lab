import { test, expect } from "@playwright/test";
import path from "node:path";

test.skip(process.env.AGENT_LAB_E2E_PERSISTENCE !== "1", "Run make check-rag with a disposable pgvector database.");

test("imports Markdown, filters and cites it in a persisted conversation, then deletes", async ({ page }) => {
  await page.goto("/knowledge");
  await page.getByLabel("Markdown 文件").setInputFiles({ name: "coffee-walk.md", mimeType: "text/markdown", buffer: Buffer.from("# 咖啡散步\n\n約會建議：先約咖啡散步，選擇安靜路線，咖啡散步時確認彼此的感受。") });
  await page.getByLabel("文件適用狀態").selectOption("single");
  await page.getByRole("button", { name: "匯入文件", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("已匯入 coffee-walk.md");
  await page.getByLabel("檢索問題").fill("咖啡散步");
  await page.getByRole("button", { name: "檢索來源" }).click();
  await expect(page.getByRole("region", { name: "引用來源" })).toContainText("coffee-walk.md");
  await page.getByRole("link", { name: "返回對話" }).click();
  await expect(page.getByRole("status")).toHaveText("準備就緒");
  await page.getByRole("button", { name: "新對話" }).click();
  await page.getByLabel("使用知識庫").check();
  await page.getByLabel("關係狀態").selectOption("single");
  await page.getByLabel("你的訊息").fill("咖啡散步，該注意什麼？");
  await page.getByRole("button", { name: "送出訊息" }).click();
  await expect(page.getByRole("status")).toHaveText("回覆完成");
  await expect(page.getByTestId("answer")).toContainText("確認彼此的感受");
  await expect(page.getByRole("region", { name: "引用來源" })).toContainText("coffee-walk.md");
  await page.reload();
  await expect(page.getByRole("region", { name: "引用來源" })).toContainText("coffee-walk.md");
  await page.getByRole("region", { name: "引用來源" }).getByText("[1] coffee-walk.md", { exact: false }).click();
  await expect(page.getByRole("region", { name: "引用來源" })).toContainText("確認彼此的感受");
  await page.screenshot({ path: path.resolve(import.meta.dirname, "../../../artifacts/s3-citations.png"), fullPage: true });
  await page.getByRole("link", { name: "管理文件" }).click();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "刪除 coffee-walk.md" }).click();
  await expect(page.getByRole("status")).toHaveText("文件已刪除");
});

test("invalid file surfaces an error and mobile knowledge controls fit", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/knowledge");
  await page.getByLabel("Markdown 文件").setInputFiles({ name: "invalid.txt", mimeType: "text/plain", buffer: Buffer.from("not markdown") });
  await page.getByRole("button", { name: "匯入文件", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(".md");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: path.resolve(import.meta.dirname, "../../../artifacts/s3-knowledge-mobile.png"), fullPage: true });
});
