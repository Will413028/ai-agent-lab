# 離線聊天串流契約

S1 的示範路徑保留在 `/demo`：Next.js → FastAPI → FakeProvider，沒有外部呼叫。此示範只顯示本頁對話，重新整理不保留；首頁的多輪儲存行為見 [多輪聊天契約](conversations.md)。

## 介面與唯一來源

- `GET /health`：回傳 `status: ok`、`mode: offline`。
- `POST /chat`：JSON body 的 `message` 為去頭尾空白後 1–2000 字；`scenario` 預設 `normal`。不接受其他欄位。前端透過同源 `/api/chat` rewrite 呼叫，只在 request body 放訊息。
- Request 與 REST schema：[OpenAPI](../contracts/openapi.json)。Python 的 [contracts.py](../apps/api/agent_lab_api/contracts.py) 定義事件，匯出 [JSON Schema](../contracts/chat-event.schema.json)，再產生前端 TypeScript。修改後執行 `make contracts`；驗收檢查產物一致。
- SSE headers：`text/event-stream`、`Cache-Control: no-store`、`X-Accel-Buffering: no`。Next.js 關閉 response compression，避免小段輸出遭緩衝。

## 事件

每筆含 `version: 1`、本次 `request_id`（UUID）、從 0 遞增的 `sequence`。SSE `event` 必須等於 JSON 的 `type`，`id` 必須是 `request_id:sequence`。

| type | payload | 意義 |
|---|---|---|
| delta | text | 追加文字 |
| done | usage: null | 完成；fake 不捏造模型用量 |
| error | code、message、retryable | 失敗；不再傳 done |

正常連線完成時恰有一個末端事件，之後不得再傳事件；使用者主動 abort 不等待末端。schema 拒絕多餘欄位；前端檢查 version、header、UUID、序號與末端事件，亦支援分段 UTF-8、CRLF 與 SSE comments。每個 frame 上限 64 Ki 字元；非主動 abort 時，缺少末端、格式錯誤或截斷顯示失敗。

## 錯誤與生命週期

`normal`、`slow` 為示範文字；`rate_limit`、`quota`、`timeout`、`dependency_failure` 注入對應 provider 錯誤。這些錯誤是在 HTTP 200 串流中送出 typed error，**不是 Cloudflare 真實 429 回應驗證**。不自動重試，不切換付費模型。request 驗證失敗則是 HTTP 422。

送出期間禁止重複送出。停止回覆使用 AbortController，保留已收到的文字；元件卸載也會 abort。FastAPI 在 disconnect 取消 coroutine，`aclosing` 關閉 provider generator；不安排背景續跑。backend 真實 HTTP 測試驗 disconnect，browser 測試驗 Next.js 路徑下的停止與再次送出。

## 來源與重新評估

- [Next.js rewrites](https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites)：同源 proxy。
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)：逐筆輸出。
- [Playwright webServer](https://playwright.dev/docs/test-webserver)：測試自行啟動與關閉本機服務。
- 加入真實 provider（S0B）才驗真實 status／usage／模型能力；S2 持久化新增獨立 conversation 契約、沿用 SSE v1。ReAct（S6）若需新事件，須一起更新事件 schema、所有 consumers 與驗收，不能在目前事件偷偷塞 tool 或 reasoning 欄位。
