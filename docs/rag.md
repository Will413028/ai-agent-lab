# 本機知識庫

`/knowledge` 匯入 UTF-8 Markdown，選擇通用、單身、交往中或已婚；回到對話勾選「使用知識庫」即可詢問並查看引用快照。通用文件會納入每種狀態；「全部」不篩選狀態。檢索預設 cosine similarity ≥ 0.25、最多 3 個來源，可在知識庫預覽調整。這是 lexical fixture 的接線預設，尚未依真 BGE 的品質校準。

文件最多 512 KiB、256 區塊。段落優先合併至 600 字；超長段落使用 80 字 overlap，不以字數冒充 token。標題與英文詞彙提供最多 5 個確定性 keyword metadata；沒有呼叫模型補關鍵字。每份文件保留原文、digest、status、chunk recipe、embedding model／local epoch／dimension。內容與狀態相同的重複匯入沿用同一份文件；embedding 失敗不會留下半份資料。

`FixtureEmbedder` 是確定性 128 維 lexical hash，只供離線接線，不代表中文語意品質。Cloudflare 模式使用 `@cf/baai/bge-m3` 的 compatible `/embeddings` API，按 index 還原順序，驗證數量、有限數、非零向量與維度，不假定模型維度。Provider 沒有公開 immutable revision，local epoch 預設 `provider-unversioned-epoch1`；調整 `AGENT_LAB_EMBEDDING_VERSION` 或切換 provider 後，在 UI 明確重建全部索引。

`POST /documents/reindex` 先在 DB transaction 外生成全部向量，再核對文件 ID／digest，原子更新 profile 與區塊。期間有匯入或刪除會拒絕本次重建，需明確重試。搜尋與匯入會拒絕混合 model／epoch／dimension；migration `002` 必須有 pgvector extension，native PostgreSQL 若未安裝 extension，不能替代此驗收。

`POST /conversations/{id}/rag` 保留既有 v1 SSE；先 claim turn，在 generator 中處理查詢、embedding、檢索並保存 snapshot，再開始生成。首輪與沒有對話背景的預覽直接檢索原問題；多輪才額外呼叫 query rewrite，補足上下文。Rewrite 只影響檢索。最後的 user message 保留原問題，來源以獨立 system message 標成未受信任資料；引用編號對應 API snapshot。空結果仍是成功檢索；embedding／DB／provider 失敗會產生 error 與 failed turn。中斷沿用 S2 的有期限 cleanup。

`GET /conversations/{id}/retrievals` 依 conversation ID 回傳快照。刪文件 cascade 刪區塊，但既有回覆仍保留當時引用的內容；刪對話連同 snapshot 刪除。文件與對話預設保留到使用者刪除。

從 repo root 跑 `make check-rag`：建立 disposable pgvector DB，驗 topK、threshold、status、dimension／epoch、reindex、原問題、snapshot 隔離、空結果與失敗、重複／刪除，以及兩項 mutation；瀏覽器完成匯入、檢索、提問、刷新、引用展開與刪除。

參考：[pgvector cosine distance](https://github.com/pgvector/pgvector#distances)、[Cloudflare compatible API](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)、[BGE-M3](https://developers.cloudflare.com/workers-ai/models/bge-m3/)。
