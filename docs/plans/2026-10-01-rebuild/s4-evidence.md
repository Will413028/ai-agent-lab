# S4 工具與產物驗收

`make check-tools` 通過：29 unit、2項 path/network guard mutation（預期失敗並還原）、2項 browser、2項真 Docker terminal。追加真取消／deadline 後，完整4項 terminal integration 全數通過（`artifacts/s4-terminal-final.log`）；早期2項與最新4項分開記錄。

- Browser 使用真 API 產生中文 PDF，下載後核對 `%PDF`；mobile traversal 被拒且無水平溢位。中文 PDF 已用 Poppler render、文字抽取與 visual QA，embedded NotoSansTC／OFL 隨產品保留。
- Terminal 真 container 驗 non-root、read-only root、network-none、artifact tar 交換、非零 exit failure、owned resource removal。固定 PID1＋Docker exec 原生 exit code，沒有 host mount／host shell fallback。
- 網路 unit 驗 public DNS、private／IPv6 translation 拒絕、redirect 再驗、decompressed byte bounds、有限 GET retry 與明確 challenge failure。Fixture 搜尋是接線 evidence，DDG live 被 challenge，未成功。
- 初輪工具 mobile test 因 label 的 accessible name 包含 options 失敗；改明確 htmlFor/id 後完整通過。保留初次失敗 log。

獨立 design-review：2項，改1／記1／提0／駁回0。改為分開 import/execute/export 的 Docker lifecycle，移除 marker／output tail 協定；D4 已採免費免 key provider，記明 challenge 與 live evidence 邊界。盤點見 [S4 audit](s4-design-audit.md)。

可重跑：`make check-tools`。歷史 logs 為 ignored `artifacts/s4-check-tools-final2.log`、`s4-terminal-cancel-final.log`、`s4-terminal-cancel-deadline.log`、`s4-terminal-final.log`；不能據此宣稱 Cloudflare native tool calling 已驗。

2026-10-18 追加：DDG live 3 個查詢（英文 2、中文 1）均回 5 筆結果，未遇 challenge；先前 challenge 判定為間歇性，程式未改。
