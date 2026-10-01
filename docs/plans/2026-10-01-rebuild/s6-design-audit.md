# S6 沿用盤點

| 機制 | 原必要條件 | 今天是否成立／從零設計 | 決定與重評條件 |
|---|---|---|---|
| Agent composition | 原 BaseAgent／ReActAgent／ToolCallAgent 繼承與可變 enum state | 保留學習 think→tool→answer；不用沿用繼承階層。D6a 已選自管 composition | AgentRuntime 組合 model／registry，run service 裝配 MCP adapter；每 run 獨立 history。需要 delegation 或 durable workflow 才評估 graph framework |
| Termination | 原無工具回 false，外層只有 FINISHED 判斷 | 原 B01/B03 不符合批准行为 | 無工具非空答案即 succeeded；最後一步成功優先；步數與工具呼叫各有硬上限；空答案／重複 call ID 為 typed failure |
| ID／transaction | 原 chatId memory；新版既有 UUID conversation/turn | 持久化、並行隔離仍必要；不需背景 queue | UUID run/workspace；begin 同一短交易 claim turn＋run；事件 ordinal 主鍵；terminal event 與 turn 完成同一交易；GET share-lock 保持 row/event snapshot。背景續跑需求成立才改 durable job ownership |
| Cancellation | 原 SSE timeout 更新 ERROR，loop 只看 FINISHED | D5 明確連線綁定，N01 停止安排新呼叫 ≤2 秒 | Event signal race 每个等待，停止新呼叫後等待 SDK／Docker 資源清理；disconnect shield 最多2秒儲存終態；DB不可用由 singleton startup recovery取消。取消不撤回已完成副作用 |
| Tool calls | 原 ToolCallback 框架 | 需要原生 assistant tool_calls／tool role ID 配對 | 保留 allowlisted assistant content／calls；按順序執行；一次檢查整批 call budget／重複 ID；doTerminate 可結束，直接回答也可結束 |
| MCP 裝配 | 舊圖片 MCP 與 YuManus tools 分開 | 不需圖片的任務不應依賴圖片 process | run service 把固定 canonical ImageSearchRequest schema 裝入 registry；runtime 不知道圖片 adapter，adapter.search 在實際呼叫時 discovery＋核對 schema。MCP 不可用時該工具與當次 run 明確失敗，其他任務不受影響。支援 third-party servers 時改成明確 discovery/trust lifecycle |
| Run／turn projection | 新 run graph 接進既有 S2 pair-table | 要在聊天 timeline 看任務結果、讓後續聊天／報告取用成功答案，並共享同一對話 busy claim；Agent 本身每次仍是獨立目標 | run 與 run_events 是任務權威；turn 是同交易同步的結果 projection：goal→question、answer/error、succeeded→completed、limit→failed，其餘同名；只有成功答案進後續 chat context，不重播 tool history。新增 run 類型／context 語意分歧時拆開 projection，不引入 queue |
| Failure／retry | 原錯誤變字串 | B04 必須分失敗與成功 | 副作用失敗立即 failed，保留已發布 artifact；無 runtime retry。readonly 參數錯誤可讓模型修正；dependency／timeout 停止 run；HTTP helper 既定有限 GET retry 保留 |
| Model SDK／usage | 新版已選 Cloudflare OpenAI-compatible SDK | native tool_calls 必要，公開／付費模型無授權 | 同一次 completion 取 allowlisted message 與可測量 usage；缺省 unknown，不猜 Neurons，估算必須 estimated；SDK max_retries=0。Live spike 不相容時依 D6b 比較免費模型 |
| Reasoning／SSE | 原 SSE 逐步字串與自訂 executor | N02 禁止 raw reasoning，UI 仍需進度 | 只持久化 typed started/state/call/result/done；新 run schema 不修改既有 chat v1；共用既有 bounded UTF-8 frame parser，run 有獨立 UUID／sequence／terminal 檢查 |
| Recovery／artifacts | 新版已有 single-process DB lease 與 workspace artifact store | D5 不續跑，R13 需下載歷史產物 | 重新啟動取消 running run/turn；刷新讀持久化結果。Artifact 存本機 ignored workspace，DB刪除不自動刪檔；需要 retention／quota 時加入明確獨立清理功能，不混入 conversation transaction |

依據：主計畫 D5/D6a、inventory B01–B04/N01/N02；[PostgreSQL locking](https://www.postgresql.org/docs/current/explicit-locking.html)、[Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html)、[Cloudflare tool calling](https://developers.cloudflare.com/workers-ai/features/function-calling/)、[MCP client lifecycle](https://py.sdk.modelcontextprotocol.io/client/)。
