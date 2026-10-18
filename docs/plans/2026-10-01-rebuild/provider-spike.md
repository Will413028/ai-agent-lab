# Cloudflare provider spike：P03 未通過，待 D6b

核對日期：2026-10-01；live 執行：2026-10-18（Will 授權建立 Workers AI Read＋Write token 並執行）。本附件與 evidence 不包含 token；ignored evidence `artifacts/live-spike-20261018T023944467132.json`、`artifacts/live-spike-p03-retry-20261018T*.json`。10 次 request 預算已用完（spike 9＋P03 單獨重試 1）。

## 接入方式

候選 chat model：`@cf/zai-org/glm-4.7-flash`；候選 embedding model：`@cf/baai/bge-m3`。

官方文件列前者支援 Function calling／多語／多輪工具，後者為多語 embedding，且 Cloudflare 提供 OpenAI-compatible Chat Completions 與 Embeddings endpoint。文件支援與帳號實際能否成功呼叫必須分開記錄。

base URL 格式為 `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1`；request schemas 使用 `/chat/completions`、`/embeddings`。Account ID／token 只從 server 環境傳給 client，驗收報告只記模型名稱、schema 形狀、成功狀態與用量摘要。

## Cases

| ID | Request schema／輸入 | 成功判準 | 狀態 |
|---|---|---|---|
| P01 | messages：繁中問候；stream=false | 正常完成、content 非空；記語言與 response shape | passed：31.8s，usage 19 in／905 out（短問候卻 905 out，推斷含 reasoning tokens） |
| P02 | messages：繁中短句；stream=true | 解析完整 SSE，含跨 chunk UTF-8；正常末尾，不丟失文字 | passed：9.7s，TTFT 9.5s，usage unknown |
| P03 | response_format：json_schema；title string／suggestions string[] | JSON 解析與 schema validation 通過；不把支援 json_object 當 json_schema | **failed**：`provider_timeout` 兩次（45.7s、54.9s，app HTTP timeout 45s）；官方 JSON mode 支援清單未列 GLM-4.7-flash（2026-10-18 重查） |
| P04 | tools：lookup_city(city:string)；stub tool 不做網路 | 模型 tool name／arguments 合法；記 call ID，回 tool message 後模型答覆 | passed：14.4s，1 call，usage 259／204 |
| P05 | tools：lookup_city、format_plan；多輪 stub 結果 | 兩步工具各保留 call ID；新 evidence 影響下一步；不能漏 assistant tool call message | passed：10.7s，2 calls，usage 448／176 |
| P06 | embeddings input：兩段人工中英測資 | vectors 數量與輸入一致、值有限、維度一致；記實際 dimension，不預設 | passed：0.5s，dimension 1024 |

P01–P06 是能力診斷資料，不是 S7 的品質 holdout。最多 10 次模型／embedding requests；遇 quota failure 即停，不自動啟用 paid fallback。不為達成工具順序無限重試；無法觸發目標行為時記 capability failure 或 inconclusive，保留實際呼叫次數。

每列 live 證據格式：checked_at、model、request_schema、response_shape、status（passed／failed／inconclusive／not_run）、duration_ms、provider_usage（若缺省 unknown）、dimension（P06）、failure_class。不記原始 Authorization、帳號資料、私人內容或 reasoning 全文。

S1 可以依可控 fake provider 先建立 transport，不等此矩陣；S2–S6 的 live 驗收需本矩陣通過或 D6b 的明確替代決定。

## D6b bounded probe（2026-10-18）

Will 同意後執行 3 次 request（上限 4），用 H02 長度的固定對話＋report 指令，evidence `artifacts/d6b-probe-20261018T025722.json`：

| Case | 設定 | 結果 |
|---|---|---|
| A-thinking-on | `tools=[submit_report]`、`tool_choice=required`、`parallel_tool_calls=false` | 1 call，LoveReport 驗證通過；58.6s；usage 539／497 |
| A-thinking-off | 同上＋`chat_template_kwargs.enable_thinking=false` | 1 call，驗證通過；9.0s；usage 539／273；1 項建議寫「二、四、六晚上」，違反「只有週二晚上」 |
| chat-thinking-off | P01 問候＋`enable_thinking=false` | stop；1.1s；usage 19／10（P01 開 reasoning：31.8s、905） |

`enable_thinking=false` 在 Workers AI 未見文件記載，但實測生效。每種設定只有 1 例，不能據此判品質。report 已改用 tool output；reasoning 是否關閉未決，thinking-on 的 58.6s 接近 app 60s 上限。

## 外部工具費用盤點（D4 已決）

原搜尋使用 SearchAPI 的 baidu engine；[官方首頁](https://www.searchapi.io/) 提供 100 次 free requests、無需信用卡，尚無證據可把它當永久免費月額度。與免 key 的公開網頁搜尋相比，API 回傳較規律，但試用用完需停用或換方案。

原圖片工具使用 Pexels；[官方文件](https://www.pexels.com/api/documentation/) 表示 API 免費、需要 account/key，預設 200 requests/hour、20,000/month，且要求 attribution。已核對文件，未登入、申請 key 或發送 live request。

D4 依委託已採 DuckDuckGo non-JS HTML 搜尋與 Wikimedia Commons 圖片 API，免 key 並保留 attribution。SearchAPI／Pexels 未接入。DDG live 曾遇 challenge，2026-10-18 3/3 成功；Commons MCP live 2026-10-18 修正縮圖 host 後通過；真 stdio＋fixture 的協定驗收另有 evidence，不能混作 live 成功。

## 可重跑入口

`make live-spike` 執行 P01–P06；`make live-holdout` 用專屬 disposable DB 與臨時 API 執行 [frozen corpus](holdout.json)。兩者不進預設 CI、不自動付費 fallback；spike 有10次 request 硬上限，quota 後停止。人工語意結果維持 needs_review，依 N04 rubric 審閱後才可判通過。

## 官方來源

- [GLM](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/)
- [BGE-M3](https://developers.cloudflare.com/workers-ai/models/bge-m3/)
- [API compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- [Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
