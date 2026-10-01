# AI Agent Lab

以 Next.js + FastAPI 重做 [yu-ai-agent](https://github.com/liyupi/yu-ai-agent) 的單人學習專案，模型使用 Cloudflare Workers AI 免費方案。

已實作 PostgreSQL 多輪聊天、結構化戀愛報告、本機 RAG、8個工具、圖片 MCP、ReAct 任務與產物下載。預設離線模型，不需憑證；Cloudflare adapter 與 opt-in 驗收程式已接入，live 驗收依使用者指示先跳過。程式驗收進度以階段計畫為準。

## 啟動

工具鏈固定 Node.js 26.10.0、pnpm 11.2.2、Python 3.14，另需已啟動的 Docker；套件版本見 lockfiles。首次下載安裝：

```sh
cd /absolute/path/to/ai-agent-lab
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements.lock
pnpm install --frozen-lockfile
```

開兩個 terminal，分別執行：

```sh
make -C /absolute/path/to/ai-agent-lab api
make -C /absolute/path/to/ai-agent-lab web
```

開啟 [http://127.0.0.1:13761](http://127.0.0.1:13761)。`make api` 自動啟動專屬 DB（18762）、跑 migration，再啟 API（18761）；前端使用同源 `/api` proxy。這三個 port 需未被占用；沒有改動其他專案 DB。資料保留在 Compose volume，直到你在畫面刪除對話。

送出第一句會建立對話；「新對話」與「選擇對話」可切換。完成一輪後按「產生報告」，重新整理仍會保留回合／報告。錯誤情境是測試注入，並非 Cloudflare 實測。只練串流時可用 `make api-offline` 與 [串流示範](http://127.0.0.1:13761/demo)，不需要 DB。

本機 DB 使用只綁 loopback 的 trust 開發設定，不適用公開部署。停止 DB 可用 `docker compose --project-directory /absolute/path/to/ai-agent-lab -f /absolute/path/to/ai-agent-lab/compose.yaml stop db`，保留 volume；不要使用 `down -v` 清空自己的學習紀錄。

DB readiness 預設最多等 120 秒；Docker 冷啟動較慢時可用 `make ... api DB_STARTUP_TIMEOUT=1200`，驗收則用 `make ... check-chat DB_STARTUP_TIMEOUT=1200`。等待以真 SQL／DB healthcheck 為準，未 ready 仍會失敗；migration DDL 另限每個 statement 60 秒。

## 驗收與學習

```sh
make -C /absolute/path/to/ai-agent-lab check
pnpm --dir /absolute/path/to/ai-agent-lab/apps/web exec playwright install chromium
make -C /absolute/path/to/ai-agent-lab check-chat
make -C /absolute/path/to/ai-agent-lab check-rag
make -C /absolute/path/to/ai-agent-lab check-tools
make -C /absolute/path/to/ai-agent-lab check-mcp
make -C /absolute/path/to/ai-agent-lab check-agent
```

`check` 執行不需 DB 的 lint/tests、schema/型別一致、production build 與計畫 mutation。`check-chat` 使用上一步 build，建立自己隨機命名的 disposable DB，驗隔離、並行、DB restart、context/report、刪除與全部 browser；測試不清空 dev volume，結束關閉自己的服務／container。GitHub workflow 使用相同入口；遠端結果分開記。

要診斷 Docker 與產品的差異，可明確執行 `make ... check-chat POSTGRES_BIN=/absolute/path/to/postgresql/bin`：建立全新的 loopback test cluster，重啟真 PostgreSQL process，最後關閉並清理自己的資料。不自動 fallback；此結果須記實際 PostgreSQL 版本，不能當作 Docker image 驗收。

先讀 [多輪聊天契約](docs/conversations.md)，跟一次 `page → POST conversation chat → begin → context → FakeProvider → finish → done`，觀察 DB 歷史與模型視窗的不同。再讀 [串流契約](docs/streaming.md)、[RAG 契約](docs/rag.md)、[工具與 MCP](docs/tools.md)、[Agent 契約](docs/agent.md) 與 [學習練習](docs/learning.md)。在 `/knowledge` 匯入文件，回到對話勾選「使用知識庫」，可查看原問題與檢索來源。修改 Python 契約後執行 `make contracts`，不手改生成型別。

Cloudflare 使用 `AGENT_LAB_PROVIDER=cloudflare`，僅 server 消費 `CLOUDFLARE_ACCOUNT_ID` 與 `CLOUDFLARE_API_TOKEN`；請在本機安全環境設定，勿貼入程式、前端或 logs。缺配置會在啟動時停止，不 fallback。SDK `max_retries=0`；使用 GLM-4.7-Flash／BGE-M3，沒有付費切換。模型切換或 `AGENT_LAB_EMBEDDING_VERSION` 變更後，須在知識庫明確重建索引。實際帳號能力仍以 live spike 為準。模型設定 `AGENT_LAB_CHAT_MODEL`／`AGENT_LAB_EMBEDDING_MODEL` 只接受目前核對的免費 GLM／BGE allowlist，未知模型 fail fast。

之後補好600權限的ignored `.env`（Account ID／API Token）可執行 `make api-cloudflare`，它只在server消費個人設定，同時啟用live工具。`make live-spike`記P01–P06能力，`make live-holdout`建立專屬disposable DB與臨時live API，執行固定人工情境；拒絕fixture，needs_review需依rubric逐例判讀。此兩項目前未實測，不進預設CI。

Holdout會在清除test DB前，把allowlisted events、引用與PDF副本存入ignored `artifacts/live-holdout-<timestamp>/`。人工評分流程見[學習文件](docs/learning.md)，`make review-holdout`會校驗corpus／PDF／原attempt並另存評分，不修改原始結果。

## 規格

- [階段計畫與唯一進度清單](docs/plans/2026-10-01-rebuild.md)
- [功能盤點、外部介面與缺陷處置](docs/plans/2026-10-01-rebuild/inventory.md)
- [固定版本的介面與 consumer](docs/plans/2026-10-01-rebuild/source-interfaces.md)
- [已採用方案](docs/plans/2026-10-01-rebuild/decisions/learning-rebuild-architecture.md)
- [Cloudflare 能力實測矩陣（尚未執行）](docs/plans/2026-10-01-rebuild/provider-spike.md)

離線文件／盤點驗收（不讀 credentials、不連外）：

```sh
python3 /absolute/path/to/ai-agent-lab/docs/plans/2026-10-01-rebuild/check_plan.py --self-test
```

如有原專案固定版本 checkout，可加 `--source /absolute/path/to/reference` 核對全部 tracked paths。這是計畫完整性檢查，不能替代應用 build、tests 或 live 模型實測。

目標包含戀愛諮詢聊天、多輪記憶、結構化報告、RAG、工具呼叫、圖片搜尋 MCP、ReAct Agent 與 SSE。採功能重做，重新設計 API 與 Python runtime，不逐行翻譯 Java。

Cloudflare 免費額度不是無限推論。預設不啟用付費模型、自動付費 fallback 或帳務變更。實際模型能力待 spike 驗證。
