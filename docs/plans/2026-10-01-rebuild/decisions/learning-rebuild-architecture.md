---
title: AI Agent Lab 採功能等價重做與自管 runtime
project: ai-agent-lab
date: 2026-10-01
review-date: 2027-04-01
last-reviewed:
status: active
tags: [ai-agent-lab, decision, architecture]
---

# AI Agent Lab 採功能等價重做與自管 runtime

## Context

Will 確認以 Next.js + FastAPI 完整重做 yu-ai-agent，供自己學習，並採用本文件的四項方案。新專案尚無應用、正式資料或部署，沒有保留 Java 架構、Vue transport 或資料格式的成本約束。

**約束與來源：**

- `external` 單人本機學習、Next.js + FastAPI、Cloudflare 免費模型：Will 本 session 的明確要求。
- `external` 保留原產品能力、雲知識庫改本地 RAG、省略 SDK／Ollama 教學變體：Will 本 session「採用」。
- 無仍需沿用的 legacy 技術限制；Java 四層 inheritance、Kryo 格式、三種 SSE 範例均重新評估。

## Options Considered

**功能範圍：**

- A. 功能等價重做：保留聊天、報告、RAG、工具、MCP、ReAct；不維護每種 SDK／provider 教學範例。
- B. 全部教程變體重做：能比較更多 library，但額外維護與 Cloudflare-only 目標衝突。

**儲存：**

- A. SQLite + 本地向量 store：單人啟動簡單；向量與關聯資料分開管理。
- B. PostgreSQL + pgvector：一套 store 處理關聯與向量資料；代價是本機資料庫服務。
- 基準來源：[pgvector](https://github.com/pgvector/pgvector) 示範向量與既有 PostgreSQL 資料一起使用。

**Agent runtime：**

- 基準 A. Framework loop：[LangGraph workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents) 展示工具循環；可減少自寫控制邏輯，但更多行為由框架管理。
- B. 完全自寫：透明度高，但 provider/MCP protocol 也需自行維護。
- C. 混合：自管 run state／ReAct loop，借用 provider 與 MCP SDK；可看清執行邊界，仍需自行處理取消與錯誤。

**任務生命週期：**

- A. 連線綁定，斷線取消：少一套背景任務協調，單人可理解。
- B. 背景執行 + 持久化事件重連：長任務體驗較好；需要背景狀態、重連與恢復契約。

## Decision

- D1：功能等價；保留產品能力、修正 B01–B06，雲知識庫改本地 RAG，省略 SDK／Ollama／獨立教程變體。
- D2：本機 PostgreSQL + pgvector，對話與向量資料共用資料庫。
- D5：斷線取消，不做背景續跑；保存結果，重啟後 running 標 interrupted，不自動重播副作用。
- D6a：自管 composition-based runtime，使用 provider/MCP SDK，不逐行翻譯 Java inheritance。

## Rationale

- 功能等價相較教程全搬，把學習集中在系統控制流程；代價是沒有各 SDK 的比較實作。
- 選 PostgreSQL 而非 SQLite + 另一套向量 store，可學到原專案的 pgvector 與持久化整合；代價是需啟動與驗證 DB。
- 混合相較 framework loop，更能修改工具往返與停止語意；代價是自己的 runtime 必須有終態、隔離、取消與錯誤回歸測試。
- 斷線取消相較背景續跑，適合第一版單人學習；代價是離開頁面不能期待任務繼續執行。本選擇不承諾撤回已送到外部服務的副作用。

## Expected Outcome

每項產品能力有可重跑的垂直驗收；能讀懂並修改一次模型→工具→結果回填循環。資料重啟可讀，但任務不自動恢復。真模型能力需另行實測。

## Followup

- [主計畫](../../2026-10-01-rebuild.md)：S0A 固定來源、S0B 驗模型；S1–S7 依批准方案執行。
- 建立本 ADR 時 D3／D4 尚未決定；後續 Will 委託完成全部功能，現行 D3 隔離 Docker、D4 DuckDuckGo／Commons 與驗證狀態見主計畫。D6b 仍依 live spike 事實處理；不以本 ADR 代替能力驗證。

## Revocation Triggers

- 需要公開分享或多使用者時，重評登入、資料隔離與網路邊界。
- 頻繁斷線使長任務無法完成時，量測中斷成本後重評 background/reconnect。
- runtime 維護成本超過學習收益時，拿相同案例比較 framework loop 再決定。

## Review Notes

## Related

- 本 ADR 即 2026-10-01 與 Will 討論「採用」的原始決策紀錄，無外部來源文件。
- [原 repo 固定版本](https://github.com/liyupi/yu-ai-agent/tree/6d4608c58b442d470fffc7a5e0b2aedb0e9478c8)
- [來源盤點](../source-interfaces.md)
- 未抽取 wiki Lessons：目前為選型，沒有已驗證的可重用失敗案例。
