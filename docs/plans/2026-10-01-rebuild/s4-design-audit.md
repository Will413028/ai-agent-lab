# S4 沿用盤點

| 機制 | 原必要條件 | 今天是否成立／從零設計 | 決定與重評條件 |
|---|---|---|---|
| 8 個工具簽章 | 原 LoveApp/ToolCallAgent 依工具描述呼叫 | 學習等價功能需要，但不用 Java annotation／全域 workspace | 保留能力與函式名稱，Pydantic registry 集中驗 schema、保留 call ID；真 provider 工具命名不相容時一起改 consumers |
| 工作區及 artifact | 舊 file/PDF/download 各自回 host path | 單人版仍需 run 隔離與可下載結果，不需任意 host 路徑 | UUID workspace、UUID artifact、basename-only；不 overwrite、REST 回 ID；同名讀取／terminal 輸入取 metadata 發布時間最新版本，UUID download 仍不變；有階層文件需求才擴張路徑契約 |
| Terminal | 原 Windows host shell | host shell 必要條件不成立；已有 Docker，需保留一般 command 能力 | 固定 PID1 保留 tmpfs，Docker exec 匯入／執行／匯出 tar，使用原生 exit code；非 root／無網路／無 host mount／資源與 deadline，不用 host fallback。引入其他語言需明確擴充固定 image |
| 免費搜尋 | 原 SearchAPI key／Baidu | 使用者未提供個人工具 key；功能仍是一般網頁搜尋 | DuckDuckGo 官方 non-JS HTML，驗證碼／格式變更回 dependency failure；免費 API 權限就緒再比較 provider，不能把 fixture 或 block 寫成 live 成功 |
| URL fetch | 原 Jsoup／任意 HTTP download | 網路工具仍必要，任意 URL 不成立 | aiohttp public DNS 全地址 guard、pin resolver、TLS/Host 保留 hostname、逐 redirect 再驗、bounded decompressed bytes；不信任 proxy env。新增內網需求須重新定義授權邊界 |
| Retry | 原工具失敗回字串 | Free provider 有短暫錯誤，但副作用不能重做 | Read-only fetch 最多一次 429/5xx retry、respect Retry-After/deadline；執行器不 retry 副作用。需要可重試寫入前先設 idempotency contract |
| 中文 PDF | 舊 iText 中文 font | 中文可讀依然必要，不需 Java font integration | ReportLab＋OFL NotoSansTC embedded TTF，文字 escape、多頁排版、抽取與 Poppler visual QA；font 缺字有實例時補涵蓋範圍，不靠系統字型 |
| SDK 與 runtime | D6a 批准 composition＋provider/MCP SDK | 不需繼承舊 BaseAgent；tool registry 不包辦模型 loop | 工具層只做 typed invocation，runtime 在 S6 接入；外部 evidence 是不可信資料，禁止當 system 指令 |

字型 source SHA256：`864727d210d54f2537bbe23b3a839436c3992af72de9322af5270897246bd44f`，來源 [Google Fonts NotoSansTC](https://github.com/google/fonts/tree/main/ofl/notosanstc)，regular 400 static subset BMP，OFL 一起保留。

主要依據：[DuckDuckGo non-JS](https://safe.duckduckgo.com/duckduckgo-help-pages/features/non-javascript)、[aiohttp resolver](https://docs.aiohttp.org/en/stable/client_advanced.html#resolving-using-custom-nameservers)、[Docker runtime constraints](https://docs.docker.com/engine/containers/resource_constraints/)、[ReportLab](https://docs.reportlab.com/)。
