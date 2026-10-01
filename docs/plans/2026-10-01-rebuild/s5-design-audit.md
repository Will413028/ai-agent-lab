# S5 沿用盤點

| 機制 | 原必要條件 | 今天是否成立／從零設計 | 決定與重評條件 |
|---|---|---|---|
| MCP server/client | 舊 Spring server 與 ToolCallbackProvider discovery | 學習外部工具協定仍必要，不能變成內部函式 stub | 獨立 Python process＋官方 SDK 2.2；stdio 無 port/auth 設定，request-scoped async client 關閉；高並行／大量重複啟動成本才評估常駐連線 |
| SDK negotiation | SDK client 預設 auto negotiation | SDK 2.2 已支持 dual-era stdio；指定本機環境 auto probe 實测逾時，原因未確認 | 明確 mode=legacy 走實測成功的 SDK initialize handshake，不手寫協定；SDK 升級或相同 stdio lifecycle 重驗 auto 成功後恢復預設 |
| Discovery schema | 原框架自動裝載工具描述 | runtime 仍需 schema，但不需要任意 third-party servers | REST、MCP signature 與 registry 共用 SearchQuery；discovery 核對 canonical 型別／長度／required／欄位，invoke 前 validation；擴充 MCP servers 時改成直接消費 discovered schema，另定 trust／pagination 範圍 |
| Free images | 原 Pexels API key | 未配置個人 key，原品牌 provider 非必要條件；一般圖片與 attribution 仍需保留 | Commons API imageinfo + extmetadata，最多 5 個支援 MIME／作者／license；缺 attribution 的文件不顯示。需要其他影像來源時比較免費 API，不付費 fallback |
| Timeout／shutdown | 原 client lifecycle 交框架 | 斷線取消與 dependency failure 仍需明確 | SDK context 管 process tree；request deadline＋call deadline，typed errors 穿過 ExceptionGroup；關服務不是空 images；不跨請求快取／續跑 |
| Domain error | 原 provider 內部不可讀 credential source | 既定錯誤代碼需跨 process 保留，不能全降成 dependency_failure | SDK CallToolResult is_error＋canonical structured ImageToolError；client 驗證代碼並映射安全訊息，不解析 SDK 自由文字；新增代碼時同步固定 envelope |
| Server credentials | 原 MCP server key 設定 | Image provider 免 key，不需模型憑證 | SDK safe inherited env＋明確 PYTHONPATH，不轉送 Cloudflare token；不讀 original credential source |
| UI images | 原 MCP 只回 medium URLs | 重做需有產品入口与 attribution | canonical Pydantic → generated TS／Ajv，native lazy thumbnail＋escape 純文字作者、source/license links；fixture 圖片用本地 SVG，清楚標離線 |

依據：[官方 SDK clients](https://py.sdk.modelcontextprotocol.io/client/)、[protocol versions](https://py.sdk.modelcontextprotocol.io/protocol-versions/)、[MediaWiki imageinfo](https://www.mediawiki.org/wiki/API:Imageinfo)、[SDK 2.2 release](https://pypi.org/project/mcp/2.2.0/)。
