# Agent 任務契約

在 `/agent` 輸入目標，FastAPI 依「模型決策 → typed tool calls → 順序執行 → tool role 回填」推進。直接回答即可完成，`doTerminate` 也是合法終止方式。只有允許的 content、工具參數與结果進入事件；provider 的 reasoning 欄位不會落地。

`POST /conversations/{id}/runs/stream` 原子建立 turn 與 run，回傳獨立 run SSE schema。每個事件都有 run ID、連續 sequence 與 elapsed_ms；種類為 started、state、tool_call、tool_result、done。狀態分為 running、succeeded、failed、cancelled、limit。最後一步成功仍是 succeeded；非空無工具答案不繼續 loop。

預設最多6步、12個工具呼叫，API允許最多12步、24次呼叫，整個run deadline 120秒。每批工具在執行前檢查 budget 與重複call ID。模型呼叫與工具等待不在DB transaction內，副作用錯誤不重試；已發布的產物保留供檢查。工具參數錯誤有機會交回模型修正，依賴錯誤與timeout則終止當次run。

`POST /conversations/{id}/runs/{run_id}/cancel` 通知正在執行的run。取消signal停止安排新呼叫，等待目前擁有的SDK／Docker資源清理；不能撤回已發生副作用。離開頁面或斷線取消，不背景續跑。startup將未完成run與turn標成cancelled/interrupted。

`GET /conversations/{id}/runs` 列歷史，`GET /conversations/{id}/runs/{run_id}` 讀事件與終態。run/run_events是任務權威；turn是同交易同步的結果projection，讓聊天timeline與後續chat/report context看見成功答案。Agent每次以單一目標開始，不重播以前的tool history。limit映射成聊天turn的failed，其餘succeeded→completed、failed/cancelled同名。

圖片工具metadata由canonical ImageSearchRequest裝配，只有真正呼叫searchImages時才透過stdio連線、discovery與schema驗證。不需圖片的任務不依賴MCP服務。模型、網頁工具與圖片模式各自標示，不把fixture當live。

provider回報的token usage按步加總；任一步缺少數值，整體顯示unknown。沒有估算Neurons或剩餘免費額度。未來若加入估算，必須標estimated。

驗收：`make check-agent`（需要已有production build，使用自己的disposable DB）；明確native驗收用`POSTGRES_BIN=/absolute/path/to/postgresql/bin`。實際證據見[階段計畫](plans/2026-10-01-rebuild.md)。
