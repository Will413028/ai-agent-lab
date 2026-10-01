# Cloudflare provider spike：依使用者指示延後

核對日期：2026-10-01。所有 live cases 目前都是 **未執行**。Will 明確指示「先跳過，先寫程式」，因此不等待配置、不執行 live。本附件與 evidence 不包含 token；opt-in runner 已實作，日後由 server 直接消費本機個人設定。

## 接入方式

候選 chat model：`@cf/zai-org/glm-4.7-flash`；候選 embedding model：`@cf/baai/bge-m3`。

官方文件列前者支援 Function calling／多語／多輪工具，後者為多語 embedding，且 Cloudflare 提供 OpenAI-compatible Chat Completions 與 Embeddings endpoint。文件支援與帳號實際能否成功呼叫必須分開記錄。

base URL 格式為 `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1`；request schemas 使用 `/chat/completions`、`/embeddings`。Account ID／token 只從 server 環境傳給 client，驗收報告只記模型名稱、schema 形狀、成功狀態與用量摘要。

## Cases

| ID | Request schema／輸入 | 成功判準 | 狀態 |
|---|---|---|---|
| P01 | messages：繁中問候；stream=false | 正常完成、content 非空；記語言與 response shape | 未執行 |
| P02 | messages：繁中短句；stream=true | 解析完整 SSE，含跨 chunk UTF-8；正常末尾，不丟失文字 | 未執行 |
| P03 | response_format：json_schema；title string／suggestions string[] | JSON 解析與 schema validation 通過；不把支援 json_object 當 json_schema | 未執行 |
| P04 | tools：lookup_city(city:string)；stub tool 不做網路 | 模型 tool name／arguments 合法；記 call ID，回 tool message 後模型答覆 | 未執行 |
| P05 | tools：lookup_city、format_plan；多輪 stub 結果 | 兩步工具各保留 call ID；新 evidence 影響下一步；不能漏 assistant tool call message | 未執行 |
| P06 | embeddings input：兩段人工中英測資 | vectors 數量與輸入一致、值有限、維度一致；記實際 dimension，不預設 | 未執行 |

P01–P06 是能力診斷資料，不是 S7 的品質 holdout。最多 10 次模型／embedding requests；遇 quota failure 即停，不自動啟用 paid fallback。不為達成工具順序無限重試；無法觸發目標行為時記 capability failure 或 inconclusive，保留實際呼叫次數。

每列 live 證據格式：checked_at、model、request_schema、response_shape、status（passed／failed／inconclusive／not_run）、duration_ms、provider_usage（若缺省 unknown）、dimension（P06）、failure_class。不記原始 Authorization、帳號資料、私人內容或 reasoning 全文。

S1 可以依可控 fake provider 先建立 transport，不等此矩陣；S2–S6 的 live 驗收需本矩陣通過或 D6b 的明確替代決定。

## 外部工具費用盤點（D4 已決）

原搜尋使用 SearchAPI 的 baidu engine；[官方首頁](https://www.searchapi.io/) 提供 100 次 free requests、無需信用卡，尚無證據可把它當永久免費月額度。與免 key 的公開網頁搜尋相比，API 回傳較規律，但試用用完需停用或換方案。

原圖片工具使用 Pexels；[官方文件](https://www.pexels.com/api/documentation/) 表示 API 免費、需要 account/key，預設 200 requests/hour、20,000/month，且要求 attribution。已核對文件，未登入、申請 key 或發送 live request。

D4 依委託已採 DuckDuckGo non-JS HTML 搜尋與 Wikimedia Commons 圖片 API，免 key 並保留 attribution。SearchAPI／Pexels 未接入。DDG live 曾遇 challenge，Commons HTTP fetch 成功，但 MCP live 任務未通過；真 stdio＋fixture 的協定驗收另有 evidence，不能混作 live 成功。

## 可重跑入口

`make live-spike` 執行 P01–P06；`make live-holdout` 用專屬 disposable DB 與臨時 API 執行 [frozen corpus](holdout.json)。兩者不進預設 CI、不自動付費 fallback；spike 有10次 request 硬上限，quota 後停止。人工語意結果維持 needs_review，依 N04 rubric 審閱後才可判通過。

## 官方來源

- [GLM](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/)
- [BGE-M3](https://developers.cloudflare.com/workers-ai/models/bge-m3/)
- [API compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- [Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
