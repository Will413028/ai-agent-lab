# S3 沿用盤點

| 機制 | 原必要條件 | 今天是否成立／從零設計 | 決定與重評條件 |
|---|---|---|---|
| UUID 與 conversation-scoped reads | S2 在本機保存互相隔離的對話 | RAG snapshot 屬於特定 turn；引用 chunk ID 需要穩定識別。無分散式排序需求 | 保留 UUID，FK cascade 管生命週期；需要跨系統有序 ID 時再評估 |
| pgvector 精確 cosine 檢索 | 已批准本機 PostgreSQL + pgvector；舊系統 vector store／cloud RAG 分離 | 小型單人 corpus 無 ANN 延遲需求；[pgvector exact search](https://github.com/pgvector/pgvector#querying) 支持可驗證 topK | 不建 HNSW／IVFFlat，不搬兩套 store；真 corpus 查詢超過延遲預算才比較 ANN |
| 短 DB transaction／advisory lock | S2 防並行寫入與 API process 衝突 | Embedding 網路等待不占 transaction；reindex 整批原子切換。[PostgreSQL advisory locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS) 可序列化本機 profile 修改 | 外呼在鎖外；搜尋／profile 變更的 DB 操作序列化。大量並行需求出現再比較 versioned index |
| v1 SSE encoder 與 turn cleanup | S1/S2 已固定 delta/done/error，disconnect 取消 | RAG 沒有新串流事件必要；snapshot 是獨立 REST 資料 | 保留 SSE，composition 包裝 provider，閉合內部 async generator；需要 streaming citation 時整體改契約 |
| Markdown paragraph chunking | 原專案讀 Markdown；未批准其他格式 | 字元簡單、token 靠近限制、語意較重；先需要可驗證切塊 | 600 字／80 overlap，最多 256 區塊；固定 recipe，改法須 reindex。真 holdout 缺來源時重評 |
| Metadata keywords | 原專案 LLM 補最多 5 個關鍵字 | Enrichment 可選，不必每次額外耗免費模型額度 | 用標題／英文 terms 最多 5 個；真品質測試顯示必要時比較模型 enrichment |
| Query rewrite | 舊 QueryTransformer 無條件 rewrite，再取代生成的 user message | 首輪／preview 沒有對話指代需處理，尚無品質證據支持每次額外呼叫；多輪可能有省略與指代 | 首輪與 preview 直接查原文，多輪才 rewrite；生成保留原問題。真 holdout 比較原文／改寫品質後再調觸發條件 |
| Profile metadata 與 reindex | 不同 embedding model 向量不能直接比較 | 驗 count／finite／非零／dimension；無 immutable revision 時 local epoch 明確控制 | 存 model／epoch／dimension；不匹配拒絕，UI 明確重建，不靜默 fallback |
| Embedding 去重呼叫順序 | 本機內容身份避免重複資料 | digest／status／model／epoch 可先查既有文件；短 transaction 不要求先外呼 | 先查既有文件避免重算，新內容外呼後在 final transaction 重查。併行新匯入可能各算一次，資料 unique 不重複；大量並行才評估 job claim |
| Provider SDK adapter | ADR D6a 明訂自管 runtime＋SDK | [Cloudflare compatible API](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/) 支持 SDK；SDK 可關 retry、設 timeout、async stream；自行 SSE parser 無必要 | 採 SDK-backed adapter，應用只保留 byte limit／finish／reasoning allowlist／vector 驗證與安全錯誤。鎖定 HTTPX 相容的 SDK 2.54 branch；引入需要 3.x 的能力時一起驗 transport migration |
| HTTP client lifecycle | 原 HTTP adapter 每批新建 client | Embedding 批次連續外呼可共用池；單人請求結束後清理容易 | 每個 stream／completion 一個 scoped SDK client，embedding 全部批次共用一個 client；不建 global pool，並行量增加再評估 |
