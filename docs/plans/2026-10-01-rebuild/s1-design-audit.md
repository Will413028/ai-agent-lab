# S1 機制重新評估

| 機制／舊做法 | 舊必要條件 | 今天是否成立 | 從零做法與決定／重新評估條件 |
|---|---|---|---|
| Vue EventSource + query message | 瀏覽器原生 GET SSE | 否；新 client 可用 fetch | 採 POST fetch SSE，訊息只在 body；見 source-interfaces R02/R13 與 streaming.md。若有 reconnect 需求先重新決定 D5。 |
| EventSource 原生 parser → 自寫 parser | 原生 parser 隨 GET EventSource 提供 | POST fetch 需另接 parser，但不強制自寫 | 自寫可學 UTF-8／frame／取消，成本是自行維護；eventsource-parser library 減少 transport 維護但多一依賴。S1 選嚴格專案 profile，以 WHATWG 為依據；需互通其他 SSE producer、reconnect 或更多 protocol 特性時改採 library。來源：[WHATWG](https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream)、[eventsource-parser](https://github.com/rexxars/eventsource-parser)。 |
| Java controller 多條文字流出口 | 教學展示多種 Spring AI API | 否；D1 已選功能等價 | S1 單一 typed chat stream，未帶 Java SDK 教學 API；S2/S6 功能新增時更新 consumers。 |
| session/memory/agent 狀態 | 多輪與 Agent 實作 | S1 無儲存需求，S2 才需要 | S1 以每 request UUID 與連續序號驗事件，不冒充 conversation/run ID；S2/S6 分別新增持久化與 run 狀態。 |
| 背景執行／串流生命周期 | 原來源 emitter/async 路徑 | D5 已批准連線綁定 | 一個 request 一個 async generator，disconnect cancel、關閉 provider，無背景續跑；新需求觸發 D5 重新決定。 |
| 非結構化文字／錯誤 | 教學文字顯示 | 否；前端需區分完成與失敗 | Pydantic schema → JSON Schema → TS + runtime Ajv；typed terminal，不傳任意內部 Exception；工具事件在 S6 整批擴充。 |
| 外部 key 與模型設定 | 真 provider | S1 不成立 | 固定 FakeProvider；不讀環境與 keys。只有 S0B 取得明確使用授權後才設定真 provider。 |
| Next.js proxy | 新技術沒有舊相容負擔 | 同源 API 與本機邊界成立 | 固定 loopback rewrite，compression off，backend host loopback；公開部署觸發重新定義 auth、proxy 與網路邊界。 |
| Fake provider 與 scenario | 新增的可重現驗收 | 免費 live 不穩定且尚未授權 | 確定性 CI，scenario 只在離線版本存在；真 provider 接入時去除使用者控制失敗注入或隔離為測試 app。 |

約束：[計畫](../2026-10-01-rebuild.md)、[已批准 ADR](decisions/learning-rebuild-architecture.md)。介面與官方依據見 [streaming.md](../../streaming.md)。原來源 pinned SHA 與 consumer 對照見 [source-interfaces](source-interfaces.md)。
