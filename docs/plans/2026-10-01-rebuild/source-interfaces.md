# 固定版本的介面與消費端盤點

來源：[yu-ai-agent 固定版本](https://github.com/liyupi/yu-ai-agent/tree/6d4608c58b442d470fffc7a5e0b2aedb0e9478c8)。核對日期：2026-10-01。

`source-ledger.json` 記錄 100 個 tracked paths 的逐檔去向；由 `discover_source.py` 使用 `git ls-files -z` 產生。這是檔案涵蓋度，不等於 100 個檔案都讀過內容。設定／credential 範例只看檔案 metadata，不取回內容；被省略的教程變體不執行。

## REST 介面

以下是 controller mapping 的路徑，未讀 deployment config，故不假設全域 context-path。

| 原 GET 路徑 | 原 consumer | 新版去向 | 需求／階段 |
|---|---|---|---|
| /health | HealthController.healthCheck；外部 health consumer 未在 frontend 找到 | FastAPI health endpoint | R04／S1 |
| /ai/love_app/chat/sync | AiController → LoveApp.doChat | 聊天服務保留同步能力，UI 使用統一 SSE | R01／S2 |
| /ai/love_app/chat/sse | frontend api/index.js、LoveMaster.vue | POST + fetch SSE，message 移出 query string | R04／S1 |
| /ai/love_app/chat/server_sent_event | AiController；沒有 frontend literal caller | 合併統一 SSE event schema | R04／S1 |
| /ai/love_app/chat/sse_emitter | AiController；沒有 frontend literal caller | 合併統一 SSE event schema | R04／S1 |
| /ai/manus/chat | frontend api/index.js、SuperAgent.vue | POST run stream，新增明確終態與取消 | R12／S6 |

搜尋證據：在原 checkout 絕對路徑對 `src/main/java/com/yupi/yuaiagent/controller` 跑 `rg -n '@.*Mapping'`；對 `yu-ai-agent-frontend/src` 跑 `rg -n 'love_app/chat|manus/chat|server_sent_event|sse_emitter|/health'`。後三種路徑的「沒有 frontend literal caller」只限此搜尋範圍，不宣稱外部使用者不存在。

## 後端能力與畫面

| 後端能力 | 程式 consumer | Next.js 去向 |
|---|---|---|
| doChat / doChatByStream | AiController、LoveAppTest | 戀愛聊天、多輪狀態、SSE |
| doChatWithReport | LoveAppTest | 結構化報告入口 |
| doChatWithRag | LoveAppTest | RAG 模式、知識匯入、來源顯示 |
| doChatWithTools | LoveAppTest | 工具模式與結果 |
| doChatWithMcp | LoveAppTest | MCP 圖片搜尋模式與結果 |
| YuManus.run / runStream | YuManusTest、AiController | Agent 執行、步驟、最終結果、取消 |

能力 consumer 搜尋：`rg -n 'doChatWith|doChatByStream|new YuManus|runStream' <source>/src/main/java/com/yupi/yuaiagent/app <source>/src/main/java/com/yupi/yuaiagent/agent <source>/src/main/java/com/yupi/yuaiagent/controller <source>/src/test/java/com/yupi/yuaiagent/app <source>/src/test/java/com/yupi/yuaiagent/agent`；只列 consumer lines，不讀 credential sources。

原 frontend router 定義 `/`、`/love-master`、`/super-agent`；共用 ChatRoom 與 avatar/footer。Next.js 保留首頁、戀愛諮詢、Agent 任務三種用途；詳細 URL 由 S1 event/API 契約一起固定，不要求 Vue URL 向後相容。

## 工具簽章

從 main tools 的 `@Tool` 與 public method 盤點得到 8 個方法；MCP server 另有 1 個 `@Tool` 方法。重查：`rg -n '@Tool\(|public String' <source>/src/main/java/com/yupi/yuaiagent/tools`。MCP 工具僅記錄已知公開簽章，不用此指令讀 ImageSearchTool.java；該檔含 credential 欄位，後續維持 metadata-only。`searchMediumImages` 是內部 helper，不算 MCP tool。

| 原工具 | 參數 | 行為 | Python 去向與驗收 |
|---|---|---|---|
| readFile | fileName | UTF-8 檔案讀取 | workspace 讀取，path guard、missing vs failure |
| writeFile | fileName, content | UTF-8 寫入 | workspace 寫入，artifact ID，不回 host path |
| searchWeb | query | SearchAPI baidu engine，取前 5 結果 | D4 已採 DuckDuckGo HTML；up to 5，0–4 結果不當錯誤；challenge 為依賴失敗 |
| scrapeWebPage | url | Jsoup 擷取 HTML | 公開 URL 抓取，response size、timeout、redirect guard |
| downloadResource | url, fileName | HTTP 下載到檔案 | 受控 artifact，URL／path guard、size cap |
| executeTerminalCommand | command | Windows cmd.exe /c | D3 已採隔離 non-root Docker；無網路／host mount，不用 host fallback |
| generatePDF | fileName, content | 文字 PDF，中文 font | Python PDF，中文可讀與 artifact download |
| doTerminate | 無 | 結束任務 | runtime terminate；正常最終答案也能結束，不強迫多一次工具 |
| MCP searchImage | query | Pexels，回傳 medium URLs | D4 已採 Commons 圖片搜尋與 attribution；獨立 MCP；live 狀態見主計畫 |

main tool consumers：ToolRegistration.allTools → LoveApp.doChatWithTools → ToolCallAgent，並由 AiController 注入；每個非 terminate 工具有對應 test file。MCP tool consumer：ImageSearchToolTest、本機 MCP client 的 discovery（實際連線設定未讀），LoveApp 使用 ToolCallbackProvider，不把設定中 provider 列表當已驗證能力。

## RAG 與記憶

- corpus：tracked `src/main/resources/document/*.md` 有單身／戀愛／已婚三份 Markdown。只記 metadata，重做時自寫等價測試 corpus，不複製原作者教學 prose。
- loader：依檔名擷取 status，保留 filename/status metadata；分隔 horizontal rule，不含 code block／blockquote。新 UI 明確選 status，避免依檔名猜值。
- splitter：提供預設 splitter 與 customized 的 200/100/10/5000/true 參數。Python 切塊參數需按新 tokenizer／corpus 固定，不直接照抄不同 library 的數字。
- enricher：KeywordMetadataEnricher 產生 5 個 keyword，LoveAppVectorStoreConfig 啟用。新版保留可選 keyword enrichment，但分清 ingest 額外模型用量。
- retrieval：status filter、similarity threshold 0.5、topK 3；新 embedding 模型不同，threshold 在 S3 用固定 corpus 校準，不把 Java 數字當品質保證。
- empty context：原 custom augmenter 不允許空 context，回覆限定戀愛相關問題的文字。新版保留無 evidence 時明確回答沒有足夠知識、不虛構來源；不複製原教程客服廣告。
- memory：主 LoveApp 使用 MessageWindowChatMemory，20 messages；FileBasedChatMemory 是 Kryo persistence 變體。新版用 PostgreSQL persistence + 可配置 window，不保留 Kryo 格式相容。

consumer 搜尋：`rg -n 'loadMarkdowns|splitCustomized|enrichDocuments|doQueryRewrite|createLoveAppRagCustomAdvisor|ChatMemory' <source>/src/main/java/com/yupi/yuaiagent/{app,rag,chatmemory}`。PgVector 與 SimpleVectorStore 是原教程的兩套配置，不新增第二份新系統 store。

## 原測試基線與重做驗收

tracked main test files 由 `git ls-files 'src/test/**'` 重建；MCP test files 由 `git ls-files 'yu-image-search-mcp-server/src/test/**'` 重建。沒有執行 Java tests，也沒有下載 Java dependencies 或讀 application config；不判定原 build 能否通過。

YuManusTest.run 的 assertion 是 `assertNotNull(answer)`，不能證明 loop 正確終止。重查：`rg -n 'assert|@Test|void ' <source>/src/test/java/com/yupi/yuaiagent/agent`。新版 B01–B04 用精確呼叫次數／終態／取消驗收；不以「原測試有覆蓋」替代行為證據。

S0A 當時已核對 source 中 B01–B06 對應機制，尚未建立產品回歸。現在的功能與缺陷回歸見 [implementation evidence](implementation-evidence.md)；來源盤點本身仍不替代產品或 live 驗收。
