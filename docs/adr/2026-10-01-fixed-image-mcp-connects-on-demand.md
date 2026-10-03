---
title: 固定圖片 MCP 採按需連線與共享 schema
date: 2026-10-01
status: active
tags: [ai-agent, decision, mcp]
---

# 固定圖片 MCP 採按需連線與共享 schema

## Context

圖片能力透過獨立 MCP process 提供，但多數任務不需要圖片。先為每個 run 做 discovery，會讓直接回答也依賴圖片服務；固定工具的 metadata 裝配不必帶入遠端可用性。

**約束與來源：**

- `external` 單人本機學習、保留 MCP、斷線取消：Will 本 session 已採方案。
- `external` 圖片 provider 免 key，不轉送 Cloudflare 憑證：免費／身份邊界要求。
- `inherited` 僅支援本專案固定 searchImages server；現在仍成立，沒有第三方 server 註冊需求，因此 canonical query schema 能共用。
- `inherited` composition runtime 不管理 MCP protocol；D6a 仍成立，協定交官方 SDK，runtime 只依賴 registry。

## Options Considered

- **基準 A：常駐 client／啟動時 discovery**。官方 SDK 的 context 管理連線與關閉，可在 app lifespan 內重用；減少 process 啟動，代價是需要故障恢復、schema cache 與連線 ownership。[SDK client lifecycle](https://py.sdk.modelcontextprotocol.io/client/)。
- **B：每個 run 先連線／discovery**。每次取得新 schema、不需要 cache；代價是無圖片任務也承受 MCP 不可用與啟動成本。
- **C：固定 canonical metadata，實際圖片呼叫才連線／discovery（選用）**。無圖片任務沒有 MCP dependency；代價是每次圖片呼叫啟 process，且只適合固定已知 server。

## Decision

Run service 同步裝配 canonical ImageSearchRequest；REST、MCP signature、registry 共用 SearchQuery。只有執行 searchImages 時才啟 SDK client、discovery 並核對 schema，再 invoke；client context 關閉自己 process。AgentRuntime 不知道圖片 adapter。

## Rationale

相較 B，C 讓無工具與非圖片任務獨立於圖片服務，而非把 dependency_failure 延後掩飾。相較 A，單人低並行時先省去 cache／reconnect／共享連線狀態，代價是圖片呼叫的 process 成本。固定 metadata 不能取代協定驗證，因此每次 invoke 前仍核對實際 discovery。

## Expected Outcome

MCP 不可用時，無圖片任務仍成功；真正圖片呼叫保留 typed failure。Schema 漂移被拒，正常 SDK lifecycle 結束後 subprocess 已退出。這不保證 Commons live 或 Cloudflare 模型品質。

## Followup

沒有新增立即執行項；live 能力與品質已歸唯一主計畫 S0B／S7，依 Will 指示延後。

## Revocation Triggers

- 新增第三方 MCP servers → 改為消費 discovered schema，另定 trust／pagination 契約。
- 真實圖片呼叫量或啟動延遲成為主要成本 → 比較 app-lifespan client 與失效／重連策略。

## Related

- 本 ADR 即本 session 委託範圍內的原始決策紀錄，無外部來源文件；S6 design-review 驗證後落地。
- [既有 RAG 呼叫策略](2026-10-01-rag-reuses-content-and-rewrites-history.md)。
- 原參考來源：[固定 revision](https://github.com/liyupi/yu-ai-agent/tree/6d4608c58b442d470fffc7a5e0b2aedb0e9478c8)；新產品可在本機code repo用 `git show f004a54:apps/api/agent_lab_api/agent_runtime.py` 取回。
- 未抽 tech Rule：本篇記選項取捨；具體 SDK timeout 與 schema 修正留 project Lessons，不混作跨專案規則。
