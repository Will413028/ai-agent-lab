# S2 機制重新評估

| 機制／舊做法 | 舊必要條件 | 今天是否成立 | 從零做法與決定／重新評估條件 |
|---|---|---|---|
| In-memory 20 messages／Kryo 變體 | Spring AI 教學展示 | 否，D2 選 PostgreSQL | 完整保留＋6 完整回合／24k 字元 prompt，failed/cancelled 不進歷史；S0B 核對真 token 上限。 |
| caller chatId | 指定 memory key | 需要對話 identity，但不用任意 key | server UUID，所有 read/write 帶 conversation ID；S6 另加 run ID，不沿用 request ID。 |
| Java report title/suggestions | 原結構化能力 | R02 成立 | 保留欄位＋bounds/extra reject/版本/儲存，錯格式 502；不相容才提 D6b，不自動 repair。 |
| Sync/streaming | 原服務能力 | 功能成立，原 wire 不必成立 | 共用 typed generator/state/context，SSE 在外層 encode，sync 不解析自身 wire。 |
| Logging content | 教學除錯 | 否 | 不記全文與 exception payload；後續 observability 只明確 metadata。 |
| SQL / migrations | 新能力 | D2 成立 | psycopg 明確 SQL＋version/checksum；ORM/Alembic 適合大量 model，目前較易看 transaction；表／migration 分支變複雜時重評。 |
| Turn pair table | 新模型 | S2 純 user/assistant pair | terminal/pair 原子；S6 另訂 tool/run message graph，不塞進 answer。 |
| Concurrency / transaction | 新 persistence | 慢串流不能持長 transaction | parent 短 row lock＋unique running index；model 在 DB 外，report 再檢版次。 |
| Recovery / process lifecycle | 新 pending state | D5 不續跑成立 | singleton API＋PG lease；startup取消殘留；需多worker時另訂ownership，不沿用全域recover。 |
| Offline／persistent capability | S1不需DB示範 | S1成立，但不能跳過S2 ownership | repository只來自持lease的lifespan app state；未初始化統一503，lease失去連線後停止接受新儲存請求，需重啟API。來源：[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)、[PG advisory locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS)。 |
| Docker DB auth | 本機新環境 | 單人loopback成立 | 專屬container/volume，trust不碰credentials，禁止公開；分享／部署時先訂auth/network。 |
| Retention / cascade | 新能力 | 使用者控制保留 | 直到刪除，graph cascade，running先停止；大量資料時加pagination，不丟歷史。 |
| pgvector image | D2、S3需求 | S2尚無vectors | image固定，S3才建extension/schema，不猜embedding dimension。 |
| S1 parser/events | S1已驗證 | 成立 | 保留v1，REST獨立schema/TS，不偷塞tool/reasoning。 |
| Browser selected ID | 新持久化UX | reload需回到對話 | URL只存UUID，message仍POST body，不以localStorage取代DB。 |

約束：[計畫](../2026-10-01-rebuild.md)、[ADR](decisions/learning-rebuild-architecture.md)、[儲存／API契約與官方依據](../../conversations.md)。獨立審查與處置見 [S2 evidence](s2-evidence.md)。
