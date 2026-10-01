# 重做盤點與外部介面

核對日期：2026-10-01。需求來源：Will 在本 session 確認完整重做、Next.js + FastAPI、單人學習版、repo 名稱與位置、Cloudflare 免費模型。

## 原系統基線

[原 repo 固定版本](https://github.com/liyupi/yu-ai-agent/tree/6d4608c58b442d470fffc7a5e0b2aedb0e9478c8)，已 clone 至本機參考 checkout 並核對 full SHA；未 build、不讀 credential sources。逐檔 metadata 去向見 [source-ledger](source-ledger.json)，主要介面／consumer 見 [source-interfaces](source-interfaces.md)。

重查：`python3 <附件>/discover_source.py --source <固定版本原 repo 絕對路徑> --output <附件>/source-ledger.json`；`python3 <附件>/check_plan.py --source <固定版本原 repo 絕對路徑> --self-test`。逐檔清單含 100 個 tracked paths，計數由 `git ls-files -z` 產生，內容讀取與 metadata 盤點分開。

| ID | 原能力與來源 | 去向 | 階段 |
|---|---|---|---|
| R01 | LoveApp.doChat：戀愛角色、單身／戀愛／已婚、多輪聊天 | 保留角色與業務情境，FastAPI chat service + Next.js chat UI | S2 |
| R02 | LoveApp MessageWindowChatMemory／FileBasedChatMemory | 改為持久化 conversation/message + 可配置 context window | S2 |
| R03 | LoveApp.doChatWithReport／LoveReport | Python schema 驗證 title、suggestions，前端報告呈現 | S2 |
| R04 | LoveApp.doChatByStream、AiController 的 Flux／SseEmitter | 統一成 POST + fetch SSE，保留串流能力，刪除 Java 三種重複 transport 範例 | S1–S2 |
| R05 | LoveAppDocumentLoader、MyTokenTextSplitter、MyKeywordEnricher | 文件 ingest、chunking、metadata enrichment；格式清單在 S0A 已固定：Markdown | S3 |
| R06 | LoveAppVectorStoreConfig、PgVectorVectorStoreConfig | 單一 pgvector store（D2 已批准）；本地 SimpleVectorStore 教學變體不另維護 | S3 |
| R07 | QueryRewriter、LoveAppRagCustomAdvisorFactory、ContextualQueryAugmenter | 改寫只用於檢索，保留原問題；status filter、threshold、topK、空 context 行為 | S3 |
| R08 | LoveAppRagCloudAdvisorConfig 的阿里雲知識庫 | D1 已批准以本地 RAG 取代，不接雲知識庫 | S3 |
| R09 | LoveApp.doChatWithTools；README 列搜尋／檔案／抓網頁／下載／terminal／PDF | Python typed tools；8 個工具簽章已列 source-interfaces，terminal 採受限 Docker container（D3） | S4 |
| R10 | LoveApp.doChatWithMcp、圖片搜尋 MCP server | Python MCP client + 獨立圖片搜尋 MCP server；Commons 免費 API 與 attribution（D4） | S5 |
| R11 | BaseAgent → ReActAgent → ToolCallAgent → YuManus | 明確 run state + 自管 loop；不沿用 Java 四層 inheritance | S6 |
| R12 | BaseAgent.runStream、AiController.manus/chat | Agent 步驟事件、取消、結果與產物 UI | S6 |
| R13 | MyLoggerAdvisor、ReReadingAdvisor、README 的 SDK／Ollama 教學 | 可觀察的呼叫摘要；D1 已批准省略 SDK／Ollama／獨立教程變體 | S7 |

來源：[LoveApp](https://github.com/liyupi/yu-ai-agent/blob/6d4608c58b442d470fffc7a5e0b2aedb0e9478c8/src/main/java/com/yupi/yuaiagent/app/LoveApp.java)、[Agent](https://github.com/liyupi/yu-ai-agent/tree/6d4608c58b442d470fffc7a5e0b2aedb0e9478c8/src/main/java/com/yupi/yuaiagent/agent)、[RAG](https://github.com/liyupi/yu-ai-agent/tree/6d4608c58b442d470fffc7a5e0b2aedb0e9478c8/src/main/java/com/yupi/yuaiagent/rag)、[README](https://github.com/liyupi/yu-ai-agent)。R05/R13 已核對 loader、splitter、enricher、advisor 的來源機制，細節見 source-interfaces；SDK／Ollama 教程變體依 D1 省略。

## 缺陷處置草稿

| ID | 來源／證據 | 建議處置與回歸驗收 |
|---|---|---|
| B01 | ToolCallAgent.think 沒工具回 false；ReActAgent.step 不轉 FINISHED | 無工具且有最終答案即完成；fixture 斷言只呼叫一次模型，改回繼續 loop 必須失敗 |
| B02 | BaseAgent SSE timeout 設 ERROR；loop 僅檢查 FINISHED | timeout／cancel 停止後續模型與工具呼叫；持續輸出 fixture + cancellation 測試 |
| B03 | BaseAgent currentStep >= maxSteps 將最後一步成功也標成上限 | 成功、上限、失敗、取消分開；最後一步完成仍為 succeeded |
| B04 | ReActAgent.step catch 後只回字串 | typed failure policy，基礎設施錯誤不能當成功；有副作用的檔案寫入／下載／terminal／PDF 不自動重試。唯讀搜尋／抓取只對 429 或暫時性 5xx 最多重試 1 次，遵守 Retry-After 與 run deadline；timeout 先回失敗，不猜有無副作用。取消、驗證失敗、4xx 不重試。驗收包含副作用發生後回錯，工具執行次數=1 |
| B05 | LoveApp.doChatWithRag 使用 rewrittenMessage 作為 user message | 原問題與 retrieval query 分開；fixture 斷言生成輸入仍含原問題 |
| B06 | TerminalOperationTool 直接 cmd.exe /c、waitFor 無 timeout | 依 D3 固定隔離／allowlist 邊界；禁止 host 任意 command，超時中止工具 |

B01–B06 均是靜態閱讀發現，未在舊系統跑過回歸。新系統用 scriptable provider 與工具 fixture 重現；對使用者可見的 B01–B06 行為修正已由 D1 批准。原系統無工具結果與 terminal 行為不能直接視為正確規格。

## 新系統需求與非功能需求

- UI：聊天／報告／知識庫／Agent 執行／產物；來源 R01–R12；知識庫 upload UI 為改善學習操作的提案，D1 已批准。
- API：chat、conversations、documents、runs、cancel、artifacts；契約在 D1 通過後由 S1 寫 OpenAPI + event schema。
- 資料：conversation、message、document、chunk、run、run_event、artifact；來源 R02、R05、R11；D2 已批准 PostgreSQL + pgvector。
- 成本：Cloudflare Workers Free；不購買 credits、不升級，不做付費 fallback。外部搜尋／圖片 provider 只能在免費方式經確認後接入。
- 隱私：本機單人、伺服器持有 token、logs 不記憑證；測試不使用私人對話。
- 可觀測性：run ID、狀態、工具開始／結果摘要、耗時、provider 回報用量；不儲存或展示私有 reasoning 全文。
- 保存：conversation 與 document 重啟後可讀；D5 已批准不做背景續跑或事件重連。刪除 conversation/document 的關聯資料範圍須在 S2/S3 規格固定。
- 效能：fake provider 首事件 < 1 秒，取消後 2 秒內停止安排新呼叫；真模型只量測 TTFT、總延遲與失敗率，不承諾 provider SLA。
- 可用性：額度、429、provider timeout 均明確呈現；不把未執行／檢索失敗當空結果。
- 產品風險：使用者是 Will、用途是完整重做學習（已確認），不需要市場需求驗證；是否達到學習目標以每階段能說明與修改控制流程評估。

## Cloudflare 外部介面

查詢日期：2026-10-01；執行 spike 前重開官方頁核對。

| 用途 | 建議與事實 | 未驗證部分 |
|---|---|---|
| chat／Agent | `@cf/zai-org/glm-4.7-flash`；官方列 Function calling、多語、多輪工具 | 帳號能否呼叫、stream tool delta、JSON schema 支援與中文品質 |
| embedding | `@cf/baai/bge-m3`；官方列多語 embedding | endpoint input/output、實際維度、batch limit；不可先寫死 dimension |
| 接入 | FastAPI 經 Cloudflare OpenAI-compatible `/ai/v1/chat/completions`、`/ai/v1/embeddings` | SDK 參數相容性；不支援就比較原生 REST，不能靜默換 provider |
| 免費方案 | 每日 10,000 Neurons；UTC 00:00 重置；Free 額度超出請求失敗 | 此帳號方案與實際 quota；token 不等同 Neurons，不能用 token count 假裝精確剩餘額度 |

官方來源：[Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)、[Free 可用模型](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/)、[GLM](https://developers.cloudflare.com/workers-ai/models/glm-4.7-flash/)、[BGE-M3](https://developers.cloudflare.com/workers-ai/models/bge-m3/)、[API compatibility](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)。文件支援不代表帳號實測通過。

## 非功能驗收映射

| ID | 階段 | 驗收內容 |
|---|---|---|
| N01 | S1、S6 | 首事件與取消時間邊界 |
| N02 | S6 | reasoning 不落地、usage 缺省與估算標記 |
| N03 | S1 | 429／quota／timeout 的 error code 與 UI |
| N04 | S0B、S7 | 獨立 live holdout、任務成功與失敗紀錄 |


- N01（S1/S6）：本機 fake provider、單一測試 run、warm server；從 server 接收 request 到寫出首 SSE event < 1 秒。從接收 cancel／偵測斷線到 runtime 停止安排新呼叫 ≤ 2 秒；不宣稱能撤回已送往外部 provider 的請求。使用 monotonic clock 與可控制的阻塞 fixture，CI 資源不足時不得藉重試冒稱通過。
- N02（S6/S7）：provider fixture 同時回 content、reasoning 與 usage；DB、捕獲 logs、SSE/UI 必須只有允許的 content／摘要且無 reasoning sentinel。usage 缺省顯示 unknown；估算值標 estimated，不顯示虛構 Neurons 剩餘額度。
- N03（S1/S4）：429、quota exhausted、timeout、dependency failure、成功空結果分別用 fixture 驗 SSE error code 與 browser 呈現；不能都顯示「查無資料」。不重試 quota、不觸發付費 fallback。
- N04（S0B 定義 corpus，S7 live 驗收）：每類固定一個未參與調 prompt 的必驗情境，聊天需正確保留第二輪修正條件；報告需 schema 合法且建議符合輸入；RAG 回答所列事實須能對到匯入來源且無資料時承認；工具任務需工具成功與實際非空產物（搜尋→PDF）；MCP 圖片需取得真 provider 結果；Agent 不用工具的答案需完成而非跑滿上限。所有必驗情境至少一次任務成功；逐例記錄所有失敗／重跑，不只保存成功次。單次成功只是功能 smoke，不宣稱品質或可靠率。任一必驗情境未執行或只有 fixture，完整 live 功能驗收未完成。若要更改情境或門檻需重新交 Will 批准，不因失敗事後放寬。
