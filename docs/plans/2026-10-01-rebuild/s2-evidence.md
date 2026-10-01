# S2 驗收證據

本階段建立 PostgreSQL 多輪聊天、戀愛諮詢角色、bounded context、同步／SSE 回覆、validated 報告、切換／刪除／重新整理 UI。FakeProvider 保留離線示範；不把 schema 接線當成真模型品質。

## 已跑驗收

| 項目 | 證據 |
|---|---|
| Backend lint／unit | `make check-api`：Ruff check／format、23 tests 通過；包含 offline 儲存能力 503、完整 pair 視窗、字元 budget、report rejection、文字空白保留與 S1 streaming。 |
| Frontend lint／contracts／build | `make check-web`：lint/typecheck、14 tests、canonical SSE／REST schema/types、一致性檢查、Next production build 通過。 |
| Native 真 DB | `check_chat.py --mutation --postgres-bin /opt/homebrew/opt/postgresql@16/bin`：PostgreSQL 16.15，15 integration tests 通過；實體 process restart 後 turn/report 保留，migration 重跑冪等。 |
| Native browser | 同一入口對 production Next.js＋FastAPI：11 tests 通過；多輪 context、雙對話切換、reload、報告、刪除 404、取消文字持久化及下一輪、手機無橫向 overflow。 |
| 隔離負向測試 | 移除 repository `_turns` 的 conversation filter：真 DB 隔離測試出現 AssertionError，finally 還原；還原後該 case 通過。log 在 ignored `artifacts/s2-isolation-mutation.log`。 |
| 來源／計畫 gate | `check_plan.py --source <固定 reference> --self-test`：來源去向一致、baseline 與 13 negative mutations 通過；reference 保持 clean。 |
| Docker 真 DB／browser | 固定 `pgvector/pgvector:0.8.6-pg17-trixie`，暫停非本專案 workloads 後：15 integration tests（43.82 秒）、11 production browser tests、隔離 mutation 與還原後 case 通過。包含真 DB restart 與更新後 UI 捲動斷言；log 在 ignored `artifacts/s2-docker-isolated.log`。 |
| Visual QA | 檢視重跑生成的 desktop／375px mobile PNG；最新回覆完整呈現、report/controls 可用、無水平 overflow。截圖是可重跑的 ignored artifacts。 |
| 開發啟動 | 實際執行 `make api`，使用 Compose 專屬 named volume：DB healthy、migration、persistent lifespan，`/health`／`/conversations` 都回 200。正常停止 API／DB並保留 volume；startup 這輪 19 個暫停資源對帳完成，pending 0，helper exit 0。 |
| 收尾檢查 | `git ls-files --others --exclude-standard` 取得 65 個 source files，逐檔 `git diff --no-index --check` 無 whitespace 錯誤；36 個相對 Markdown file links 皆存在。second-brain `lint-rules.py`／`check-links.py` 通過。本次未修改 parent repository 的檔案。 |

## 修正與設計審查

- 獨立 design-review 找到 1 項：offline startup 沒取得 singleton lease，原 repository dependency 卻仍可存取 DB。改成只取得 lifespan 持 lease 的 app state；未啟用儲存統一 503，lease 連線失效後拒絕後續儲存。分流：改 1、記 0、提 0、駁回 0。
- Code review／真 DB 測試找到文字被共用 model strip 的問題。Turn／PromptMessage 保留 provider 空白；只在輸入標題與報告驗證使用 strip。unit regression 與真 DB partial text equality 已通過。
- Docker restart case 找到驗收工具用自動配置 host port，重啟後從 60915 變成 62269，仍連舊 port。改成選空 port 後明確綁定，啟動時核對 published port；原重啟 case 在修正前失敗，修正後真 DB restart 通過。
- Visual QA 發現長對話下新回覆位於可捲動區下方；補上跟隨最新回覆，向上閱讀時停止跟隨。新增 browser 捲動斷言；修正後 build／browser 通過並重新檢視截圖。
- 指令檔對帳更新 1 份 `AGENTS.md` 的 5 處：啟動入口、驗收入口、migration／ID transaction、singleton lifecycle、explicit native validation。未更動其他 repo 的 instructions。

審查涵蓋 UUID／conversation 隔離、turn pair、context budget、typed report、SQL／migration、transaction／concurrency、recovery／lease、retention／cascade、SSE consumer、browser selection。逐項重評見 [design audit](s2-design-audit.md)。

## 環境與驗收限制

第一次 Docker 冷啟動超過 60 秒；pgvector trixie 與既有 postgres alpine 都持續初始化，沒有 image-specific 啟動錯誤。後續 VM I/O `some avg10≈45%`、memory `some avg10≈14%`，DB statement／connection 逾時，原完整驗收結果為 7 failed、6 passed、5 errors；不能記成成功。readiness 改成可設定、預設 120 秒、上限 1200 秒；migration DDL 每 statement 限 60 秒，request 與取消期限維持原值。

Will 確認 Docker 無不能中斷工作並允許協調後，重啟 Docker Desktop，保留 containers／volumes。重啟後 13 個 integration case 通過，重啟 case 暴露 host port 換號，結果為 1 failed、13 passed、3 errors。修正 port 後，在其他 containers CPU 合計超過 VM 8 核容量時，取消 cleanup 超過 2 秒、DB restart 超過 30 秒；結果 2 failed、12 passed、3 errors，詳見 ignored `artifacts/s2-docker-under-load.log`。未拉長取消期限或加入測試 retry。

已向 Will 說明暫停非本專案的 running containers，隔離驗收後恢復；22 個暫停資源中，15 個 unpause 成功；另外 7 個因狀態變更使 wrapper 退出 1。逐 ID 只查 `State.Status`：4 個已 running、2 個 no such object、1 個 exited，沒有 paused 項；保留其現況，不重建／復活其他工作的資源。對帳後 owned ledger 清空。產品驗收 subprocess 的 tests／mutation 均通過；wrapper 初始 cleanup 非零結果另留 audit，沒有當成整個 wrapper 綠燈。

Native runner 是明確指定的診斷入口，沒有自動 fallback；新建 loopback cluster 保留 fsync，實體重啟後清理本次資源。CI 使用預設 Docker 入口，不自動管理其他 projects 的 workloads；本機忙碌環境與隔離環境結果分開記，不能用 retry 宣稱穩定通過。

Cloudflare P01–P06 live、真模型中文／報告品質、GitHub 遠端 CI 尚未跑；沒有讀 credentials、登入、commit、push 或公開部署。RAG／tools／MCP／ReAct 屬後續階段。
