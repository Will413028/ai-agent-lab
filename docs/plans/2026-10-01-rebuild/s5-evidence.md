# S5 圖片 MCP 驗收

`make check-mcp` 通過：8項真 stdio／fixture integration、1項 schema mutation（預期失敗、還原後通過）、1項圖片 browser。Log 的 mutation FAILED 是必須被拒絕的錯誤 schema，不是 baseline 失敗。

- 官方 SDK 啟獨立 Python server，discovery核對 canonical query schema，實際 invoke 回 structured images／artist／license。
- Server 缺失、deadline、provider dependency failure 與 typed tool_timeout 各保留明確語意，失敗不是空 images。
- SDK context 結束後直接核對此次 subprocess returncode，確認已關閉；不 kill 其他 process。
- Browser 展示本地示範 SVG、明確離線來源、作者與 CC0，mobile 不溢位。Fixture 圖片未冒稱 Commons 實圖。
- Commons public HTTP fetch 成功；實際 MCP live 呼叫兩次仍 dependency_failure，未通過。Cloudflare live 依使用者指示延後。

獨立 design-review：3項，改2／記1／提0／駁回0。共用 SearchQuery，固定 discovery validation；用 structured ImageToolError 穿過 SDK，而非解析自由文字；SDK2.2 支援 dual-era，指定 mode=legacy 是本機 auto probe 實測逾時的明確結論，原因尚未確認，SDK 升級／auto 重驗成功時再評估。見 [S5 audit](s5-design-audit.md)。

可重跑：`make check-mcp`；ignored log `artifacts/s5-check-mcp-final.log`。真 MCP transport 通過不等於 live 圖片任務通過。
