# 工具與 MCP

`/tools`可逐項執行8個工具：readFile、writeFile、searchWeb、scrapeWebPage、downloadResource、executeTerminalCommand、generatePDF、doTerminate。每次呼叫使用獨立call ID，回傳成功或typed error。工作區由server產生UUID，artifact另有UUID；只能按workspace／artifact ID下載。

檔案工具只接受basename，不接受host path、symlink或secret檔名。UTF-8讀取最多256KiB，單個artifact最多8MiB。相同名稱建立新artifact，readFile取最新版本；沒有覆蓋既有blob。PDF嵌入Noto Sans TC，支援繁體中文與分頁，隨附OFL授權。

Terminal在固定Python Linux Docker image中執行一般shell：non-root、唯讀root、無網路、無host mount、CPU／memory／PID／tmpfs／輸出上限。輸入與輸出以驗證過的tar交換，從不把tar path直接extract到host。固定PID1與Docker exec讓tmpfs存續；執行20秒後timeout，finally只清理該呼叫擁有的container。Docker不可用明確失敗，不切回host shell。

公開HTTP工具只允許http(s)與80/443，DNS所有位址需public，TCP連線使用驗證後的pinned resolver；每次redirect重新驗證。解壓後body也受上限控制。唯讀GET只對429／暫時5xx最多retry一次，尊重有界Retry-After與deadline。網頁內容為不可信資料。

`AGENT_LAB_TOOLS=fixture`是預設，搜尋與網頁使用固定示範；PDF／檔案與Docker Terminal仍是實際執行。`live`以DuckDuckGo non-JS HTML搜尋，驗證碼、網站格式不符或依賴失敗都回error，不能當成空結果。此來源可能被網站擋住，沒有繞過驗證碼或付費fallback。

`/images`透過獨立Python MCP process與官方SDK搜尋。`AGENT_LAB_IMAGES=fixture`預設使用本地示範SVG，`live`使用Wikimedia Commons。保留作者、來源、授權連結，只顯示支援的image MIME與完整attribution。SDK context管理stdio shutdown；client核對discovered canonical query schema。domain error用is_error＋structured ImageToolError穿過process邊界。

`make check-tools`驗guard、兩項mutation、PDF/browser與實際Docker Terminal；`make check-mcp`驗真stdio、timeout／shutdown、schema mutation及圖片browser。這兩個target不需要DB，但browser需已有build。
