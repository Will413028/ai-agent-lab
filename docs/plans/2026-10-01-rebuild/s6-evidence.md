# S6 ReAct runtime 驗收

`make check-agent POSTGRES_BIN=<PG17 bin>` 最終通過：13 runtime unit、2項 loop/cancel mutation（錯誤行為被拒、還原後通過）、6項 PostgreSQL integration、2項 browser。Native PostgreSQL17.11＋pgvector0.8.6，不混作 Docker DB image evidence。

- 無工具立即完成；最後一步成功；max_steps/max_calls；模型／工具失敗、timeout、取消、並行 workspace/history；副作用先發生再回錯，只執行一次。
- Cancel／disconnect 停止後續模型與工具；controlled blocking fixture 驗 ≤2秒停止新呼叫。Warm fake API 首事件 <1秒；DB測試用整個 ASGI response 完成 <1秒提供更嚴的上界。
- Reasoning sentinel 不進 events／logs／DB／model context；provider usage 可量測才加總，缺省 unknown，沒有虛構 Neurons 額度。
- DB atomic begin claim、terminal只一次、scoped list/get、startup recovery、conversation cascade；成功run投影到turn並進下一次chat context。
- Browser 搜尋→實際PDF下載→完成→刷新歷史；mobile 取消與超限有不同狀態。Desktop/mobile screenshot 已 visual QA。

獨立 design-review：2項，改1／記1／提0／駁回0。MCP 改成實際圖片呼叫時才 discovery，不讓無工具任務依賴圖片 server；明確 run/events 權威與 turn 同交易 projection。見 [S6 audit](s6-design-audit.md)。

可重跑：`make check-agent` 或明確 native runner。ignored log `artifacts/s6-check-agent-final.log`。Cloudflare runtime adapter 已接入但 live 模型任務未驗。
