# S3 驗收證據

## 已跑

- Backend unit：47 passed，包含 provider SDK byte limits、vector shape、首輪不 rewrite、重複匯入不外呼。
- Native PostgreSQL 17.11 + pgvector 0.8.6：`make check-rag POSTGRES_BIN=/opt/homebrew/opt/postgresql@17/bin`，8 integration passed；文件、profile、vectors 在真正 DB restart 後可查。
- 兩項 mutation：移除 status filter、以 rewrite 取代原問題，對應行為測試都失敗；原檔還原後通過。
- RAG browser：2 passed，匯入／篩選／聊天來源／refresh／刪除，以及 invalid upload／mobile overflow。
- 既有聊天相容性：15 DB integration passed；當時全部 browser 12 passed、1 首輪 cold-run 30 秒 test timeout，未當成通過；最終S7在相同門檻18項browser全過，歷史失敗保留。
- Frontend lint/build、三份 canonical types、plan gate 13 mutations 通過。
- Visual QA：實際查看 `artifacts/s3-citations.png` 與 `s3-knowledge-mobile.png`，引用內容可讀、手機無橫向溢出。

## 設計審查

獨立唯讀 reviewer 檢查 profile／query rewrite／去重／SDK／transaction／lifecycle／snapshot。3 個 findings，改 3、記 0、提 0、駁回 0；回查確認全部解決。指令檔對帳改 5 處。

## 還未驗證

- Cloudflare GLM/BGE live：依Will指示延後；fixture結果不代表live品質或模型能力。
- S3當時Docker pgvector image readiness逾時，已恢復ledger中19個容器、無pending；後續S7真Docker RAG8／mutation2／browser2已通過，沒有用native結果替代。
- 遠端 CI：未 commit/push。

## 可重跑入口與 logs

`make check-rag POSTGRES_BIN=<明確 native bin>`、`make check-chat POSTGRES_BIN=<bin>`、`make check`；不自動 fallback，不用 dev volume 清除測試。

Ignored logs：`artifacts/s3-native-rag-verified.log`、`s3-chat-compatibility.log`、`s3-unit-final.log`、`s3-build-final.log`、`s3-contracts-final.log`。沿用決定見 [S3 design audit](s3-design-audit.md)。

## 最終相容性

S7再次使用固定 `pgvector/pgvector:0.8.6-pg17-trixie` 的owned disposable Docker DB，RAG8／mutation2／browser2通過；chat DB15／全套browser18通過。Logs：`artifacts/s7-check-rag-docker.log`、`s7-check-chat-docker-final.log`。
