# 程式交付與後續驗收

## 現況

單人Next.js＋FastAPI全功能程式、本機驗收、文件與design-review／recording已完成。唯一進度是[主計畫](../2026-10-01-rebuild.md)。Cloudflare live依Will「先跳過，先寫程式」延後；本人messages／max_steps練習未操作，不代填完成。功能、計畫與evidence同批提交；以 `git log -1 --stat` 核對當前commit。已push；遠端CI `Offline checks` 於 2026-10-11 對 `b1c3b28`、`7cb2e01` 通過。

## 可重跑驗收

- `make check`：最終backend106、web16、lint/types/build、契約一致與plan13mutations。
- `make check-chat`：固定Docker pgvector DB15／全browser18，`artifacts/s7-check-chat-docker-final.log`。首輪16/18逾時保留 `s7-check-chat-docker.log`；沒有修改門檻或自動retry。timeout request/event正確，browser逾時根因未確認。
- `make check-rag`：真Docker DB8、mutation2、browser2，`s7-check-rag-docker.log`。
- `make check-tools`：工具29、guard mutation2、browser2；真Docker terminal最終4，`s4-check-tools-final2.log`＋`s4-terminal-final.log`。
- `make check-mcp`：真stdio8、schema mutation1、browser1，`s5-check-mcp-final.log`。
- `make check-agent POSTGRES_BIN=<native bin>`：runtime13、mutation2、native DB6、browser2，`s6-check-agent-final.log`；Docker全browser亦覆蓋任務下載／history。
- Fresh S3–S7 review12項：改9／記3／提0／駁回0，全收口；指令檔對帳6處。詳細見各stage evidence／audit與[功能對帳](implementation-evidence.md)。

## 本機資源

Node26.10.0、pnpm11.2.2、Python3.14.7；native PG17.11／pgvector0.8.6。API18761、Next13761、dev DB18762，啟動前確認port。測試結束已關閉自己API／Next／DB／terminal，沒有清dev volume。

Docker是共用服務，只操作當下確認owned資源。S3曾協調19個容器，finally全部恢復，ignored `s3-paused-containers.json=[]`；不要重新pause其他專案。後續Docker DB／terminal已通過，歷史失敗log保留。

原reference固定SHA `6d4608c58b442d470fffc7a5e0b2aedb0e9478c8`，保持clean；舊Java build未跑。只讀非credential allowlist。所有secrets只由server直接消費，不讀／輸出payload。

## 之後由使用者啟動的流程

`make api`＋`make web`使用fake預設，可練聊天、RAG、工具、MCP與Agent；學習路線見[learning](../../learning.md)。

使用者日後決定啟用live時，`make live-spike`驗P01–P06、`make live-holdout`用owned test DB與臨時API驗8個固定情境（H07／H08 為 blind 替代）；`make review-holdout`保存人工rubric判定。原attempt／PDF／citations先保存再清DB，review sidecar不改原結果。沒有把此流程列成等待權限的blocking work。

DDG live 2026-10-18 3/3 成功（曾被 challenge，屬間歇性）；Commons MCP live 2026-10-18 通過（修正縮圖 host）。GLM/BGE個人帳號能力未驗，D6b僅在實際不相容時重評，不靜默fallback。遠端CI只跑offline checks，不含live。
