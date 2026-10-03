# AI Agent Lab

單人學習專案，以 Next.js + TypeScript 前端、FastAPI + Python 後端重做 yu-ai-agent，推論使用 Cloudflare Workers AI 免費方案。

- 實作前讀取 `docs/plans/2026-10-01-rebuild.md` 與對應附件；委託執行的決定依該計畫處理，未驗證的外部能力不能當成已通過。
- 計畫內維護進度；本檔只放現行規則。
- 決策紀錄（ADR）：`docs/adr/`。
- 所有模型呼叫與工具執行由 FastAPI 負責；憑證不能進入前端、tracked files、logs 或測試 fixture。
- 單人版預設只供本機使用；不新增多使用者登入、計費或公開部署。
- 不自動升級付費方案、不自動切換付費模型。
- 文件與來源盤點變更後，從 repo root 執行 `python3 docs/plans/2026-10-01-rebuild/check_plan.py --self-test`；這是文件完整性檢查，不替代應用驗收。
- 從 repo root 使用 `make api` 順序啟動專屬 DB、migration、persistent API，`make web` 啟動前端；`make api-offline` 與 `/demo` 保留不需 DB 的串流示範。
- `make check` 不需 DB；`make check-chat` 在已有 build 上建立專屬 disposable DB，執行聊天 DB integration/restart 與全部 browser；`make check-rag` 驗 pgvector integration、兩項 mutation 與知識庫 browser；`make check-skeleton` 只驗不需 DB 的示範，persistent cases 會 skip。
- Python 事件契約是唯一來源；改完執行 `make contracts` 產生 JSON Schema、OpenAPI 與前端型別，不手改生成檔。`make check` 必須維持產物一致。
- 預設 `AGENT_LAB_PROVIDER=fake`；`cloudflare` 模式只由 server 消費個人環境設定，缺設定或未知模式 fail fast，不 fallback。SDK 禁自動 retry；reasoning 不進 logs／DB／SSE／UI。Fixture 錯誤不能當成 Cloudflare live 驗證；已跑與未跑分開記錄。
- 不修改已套用 migration；新增版本檔案。所有 conversation read/write 必須帶 ID，transaction 不跨模型／串流等待；completed 回合才進 model context。
- 每個 DB 只用一個 persistent API process，保留 singleton lease 與 startup cancellation；不用 dev volume 跑測試清除，不使用 `docker compose down -v` 清空學習紀錄。
- `check-chat`／`check-rag POSTGRES_BIN=<bin directory>` 只供明確指定的 native test cluster，需要實際 pgvector extension；記錄實際版本，不自動 fallback，也不代替 Docker image 驗收。
- 文件 profile 的 model／local epoch／dimension 與 chunk recipe 保持相容；變更需明確 reindex。Query rewrite 只供檢索，generation 保留原問題；空結果與依賴失敗不同。
- `make check-tools` 驗 typed registry、path/network mutation、browser PDF 與真 Docker terminal；`make check-mcp` 驗真 stdio discovery／invoke／typed error／shutdown、schema mutation 與圖片 browser；`make check-agent` 驗 loop／cancel mutation、run DB 與 Agent browser。
- 工具只接受 UUID workspace 與 basename；網路工具只連 public HTTP(S)，逐 redirect 驗證並固定 DNS 解析。Terminal 只在受限 Docker container 執行，不加 host shell fallback；副作用工具不自動重試。
- Run 與 run_events 是任務權威；turn 是同交易同步的聊天結果 projection。成功答案可進後續 chat context，tool history 不重播；取消與斷線停止新呼叫，資源由 owned lifecycle 清理。
- 圖片 REST、MCP signature、registry 共用 canonical query schema；MCP 只在實際圖片呼叫時啟 process、discovery 並核對 schema。SDK 關閉自己的 subprocess，不用全域 process cleanup。
- `live-spike`／`live-holdout` 是 opt-in，不放入預設 CI。Holdout 使用專屬 test DB／臨時 API，拒絕 fixture 與 dev DB；機械通過不替代人工語意 rubric。沒有 live evidence 不宣稱模型能力或品質已驗證。
