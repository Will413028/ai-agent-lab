# 多輪聊天與報告

本版仍用離線 FakeProvider；S2 驗證 persistence、context 與結構化輸出接線，不代表 Cloudflare 中文品質或 JSON schema 能力已實測。

## 資料與介面

PostgreSQL 在本機 loopback 18762；Compose 建立專案專屬 `lab` database 與 volume。只使用本機 trust development database，沒有密碼或外部 credentials；不能公開使用這份設定。pgvector image 已固定，extension／embedding store 在 S3 建立。

`agent_lab.conversations` 存 UUID、標題與時間；`turns` 一列是一組 question/answer、position、status 與完成時間；`reports` 存 validated JSON 與對話版次。成對儲存讓 terminal 與 context pair 不分離；S6 工具 message graph 另訂 run 模型，不塞進 turn 表。

保留期限：**直到使用者刪除**，不自動過期、不裁切 DB 歷史。刪除是實體 cascade，包含所有回合／報告；running 時回 409，先停止後可刪。列表、報告與 detail 不靜默截斷；大量資料造成延遲時再加 pagination，不把模型視窗當 storage retention。

| REST | 行為 |
|---|---|
| GET /conversations | 完整列表，最近更新先列 |
| POST /conversations | title 1–80 字，可省略用預設；201 |
| GET /conversations/{id} | 對話與所有回合；不存在 404 |
| DELETE /conversations/{id} | cascade，成功 204；不存在 404，running 409 |
| POST /conversations/{id}/chat | S1 相同 request／SSE v1；done 前提交 completed |
| POST /conversations/{id}/reply | 同一 typed generator/context/state，等待完成回 JSON Turn |
| POST /conversations/{id}/reports | validated title/suggestions；201；空對話／快照已變 409、格式錯 502 |
| GET /conversations/{id}/reports | 保留報告版本，source_position 標示對話版次 |

唯一來源：[OpenAPI](../contracts/openapi.json)、[REST schema](../contracts/conversation.schema.json)。Python → schema → TS，前端以同份 schema 驗回傳。S1 [SSE schema](../contracts/chat-event.schema.json) 未擴充；`/chat` 與 `/demo` 可不啟動 DB。

## Context、角色與報告

server 固定戀愛諮詢 system prompt，先釐清單身／交往／已婚、事情經過與雙方期待；browser 不送 system role。只加入同 conversation 最近最多 6 個 completed turn 的完整 user/assistant pair，加上本次問題。failed/cancelled/running 留在紀錄，不進模型歷史。

總上限 24,000 Unicode 字元，包含 system／本次問題；由最新 pair 向前累積，遇超限就停止，不切斷 pair、不截掉本次問題。這是字元 budget，**不是 token 估算**；真模型上限需 S0B 核對後更新參數。

報告也使用 bounded context，不聲稱總結完整歷史。provider 回已解碼 object；Pydantic 要求 title 1–120 字、suggestions 1–5 項且各 1–1200 字，拒絕 extra field。錯誤不保存、不 repair、不重試；live 不相容才依 D6b 決策。

## Transaction、取消與重啟

begin/finish/delete/save report 先短暫 lock parent conversation。begin 與 partial unique index 保證同一對話只有一個 running turn；模型／串流在 transaction 外。terminal update 只接受 running → terminal，完成提交後才送 done。

abort 關閉 provider generator 後，以最多 2 秒 shielded cleanup 保存已收到文字為 cancelled，不背景續跑。API crash 可能未保存尚未提交的文字；下次 startup 把遺留 running 改 cancelled/interrupted，保留問題、不重跑。每個 DB 只允許一個 persistent API，用 PostgreSQL session advisory lease 保護 recovery，第二個 process 拒絕 startup。report/reply 是一般 HTTP request，沒有 background/resume。

report 在 DB 外生成，提交前 lock parent 並重查版次／running；已出現新回合則 409。detail/reports 讀取亦 lock parent，避免與刪除拼出不一致資料。

repository dependency 只取 lifespan 持 lease 的 app state；offline 未初始化儲存能力時統一 503，不逐 route 補旗標。lease 連線失效時拒絕後續儲存請求；DB 重啟後也需重啟 API 重新取得 lease／recovery。

## Migration 與驗收

`make api` 順序啟動專屬 DB、執行 migration、啟 persistent API。SQL version/checksum ledger 全部在 transaction 內；重跑冪等，不改已套用 migration。只改 `agent_lab` schema，連線只允許 loopback 與 `lab`／受控 test database。

`make check` 不需 DB。`make check-chat` 建隨機 ephemeral container/database，驗真 DB、DB restart、全部 browser，最後只清理自己的 container，不用 dev volume。`check_chat.py --mutation` 另移除 conversation filter，隔離測試必須失敗，finally 還原後重跑。

明確傳 `POSTGRES_BIN` 可改用新建的 native test cluster；只有 loopback TCP、隨機 port，不開 Unix socket，避免長 checkout path 超出 socket 路徑上限。測試重新啟動該 cluster 的 process；保留預設 fsync，不用 in-memory DB。native 版本與 Docker image 結果分開記，不自動切換。

依據：[Psycopg async](https://www.psycopg.org/psycopg3/docs/advanced/async.html)、[transaction](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)、[pgvector image](https://github.com/pgvector/pgvector#docker)。
