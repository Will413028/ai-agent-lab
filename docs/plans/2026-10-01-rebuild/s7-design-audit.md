# S7 沿用盤點

| 機制 | 原必要條件 | 今天是否成立／從零設計 | 決定與重評條件 |
|---|---|---|---|
| 測試／品質分層 | 舊教程的真人 API tests 混合能力示範 | 免費額度與生成變異仍存在，預設 CI 需要可重現 | fake、HTTP fixture、真 DB、真 MCP／Docker 驗接線；opt-in spike 驗能力，獨立 frozen holdout 驗任務。公開部署前另訂可靠率，不用單次 smoke 推論品質 |
| 個人配置入口 | 原 Java API key／設定範例 | server 仍需身份；不能沿用原作者或其他身份配置 | opt-in 程式只消費同 UID、非 symlink、600 的本機設定；僅兩個必要 keys，先驗證再更新 environment，沒有 eval。支援部署 secret manager 時替換本機入口 |
| SDK 與用量 | 已選 OpenAI-compatible SDK／GLM／BGE | D6a 與免費約束仍成立；實際帳號尚未驗 | spike 共用產品 adapter，最多10 requests、quota即停；只記 allowlisted metadata，不記 raw SDK／reasoning。實測不相容時依 D6b 比較免費方案 |
| Holdout storage／API | 已有 disposable DB runner、persistent API lease | 不應污染學習紀錄，也不應讓 fixture 冒充 live | 共用 ownership-safe test DB runner，另起自己的 API process；檢查 runtime provider/tools/images 全 live、persistence_scope=test；只刪自己的測資。需要跨部署驗收時另設隔離資料契約 |
| 逐例評分 | 原教程無品質 rubric | 中文、報告、RAG 語意不能由 HTTP200 證明 | 6個人工情境在任何 live 調 prompt 前凍結；機械契約通過與 needs_review 分開記。每attempt保存canonical events、citations、PDF副本與SHA256後清DB；人工sidecar記reviewer／時間／原attempt與corpus hash／逐例理由，不覆寫原始結果。沒有全部6例的有效通過證據不宣稱N04完成；新增情境需先重訂corpus與rubric |
| CI 與教學 | 已有 monorepo check、Python schema generation | 單人學習仍需跨端一致、可重跑的缺陷回歸 | CI 跑離線全套與真 DB/MCP/Docker；live 不進預設 CI。學習文件提供 messages／max_steps 練習，Will 未操作不標成學習驗收完成 |

依據：主計畫 N01–N04、D5／D6a／D6b；[Cloudflare pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)、[Python subprocess lifecycle](https://docs.python.org/3/library/asyncio-subprocess.html)、[OpenAI SDK retries](https://github.com/openai/openai-python#retries)、[PostgreSQL CREATE DATABASE](https://www.postgresql.org/docs/current/sql-createdatabase.html)。
