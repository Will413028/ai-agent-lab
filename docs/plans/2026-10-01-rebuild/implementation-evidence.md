# 功能與缺陷對帳

所有產品能力已實作；以下分開記程式接線、真本機依賴與外部 live，沒有把 fake 模型當真模型。原 Java checkout 未 build，只作固定版本來源盤點。

| 需求 | 產品入口與實作 | 驗收／處置 |
|---|---|---|
| R01 | `/`，chat/context、戀愛狀態 | S2聊天DB／browser，live語意延後 |
| R02 | conversation／turn repository、bounded context | 雙對話隔離、restart、completed-only；S2 evidence |
| R03 | schema report／報告UI | schema rejection／DB保存／browser；live品質延後 |
| R04 | POST fetch SSE、`/demo` | canonical v1、分段UTF-8、error/done、取消、event mutation |
| R05 | `/knowledge` Markdown ingest／chunk／keywords | digest重用、profile／reindex／status、RAG DB／browser |
| R06 | KnowledgeStore、migration002 pgvector | 真pgvector exact cosine／topK／threshold／filter |
| R07 | conditional rewrite、原問題與引用快照 | 無歷史不外呼；status／原問題兩項mutation；S3 evidence |
| R08 | 本機 RAG | D1批准取代阿里雲，不另接雲store |
| R09 | `/tools`、8項typed tools、artifact API | [S4 evidence](s4-evidence.md)，真Docker與PDF；DDG live 2026-10-18 3/3 成功（曾被 challenge，屬間歇性） |
| R10 | `/images`、官方SDK stdio server/client | [S5 evidence](s5-evidence.md)，真協定＋fixture；Commons MCP live 2026-10-18 通過（修正縮圖 host） |
| R11 | AgentRuntime composition | [S6 evidence](s6-evidence.md)，13unit／loop/cancel mutations |
| R12 | `/agent`、run SSE／DB／cancel／history | 6DB、2browser、下載／刷新／mobile |
| R13 | run ID／elapsed_ms／工具摘要／usage／學習文件 | allowlist無reasoning；unknown標示；D1批准省略SDK/Ollama獨立教程 |

| 缺陷 | 新行為與回歸 |
|---|---|
| B01 | 無工具非空答案即 succeeded，一次模型；loop mutation失敗 |
| B02 | timeout/cancel/disconnect停止安排新呼叫；cancel mutation失敗 |
| B03 | 最後一步成功仍 succeeded；上限另為 limit |
| B04 | typed failure；副作用執行一次，不自動retry；readonly有限GET retry |
| B05 | generation保留原問題；rewrite只檢索，mutation失敗 |
| B06 | 受限Docker terminal；真nonroot/read-only/network-none／deadline／cancel清理 |

N01：首事件／取消期限已測；N02：reasoning排除／usage缺省已測；N03：429／quota／timeout與UI已測；N04：能力spike與6項frozen holdout runner已實作，Will指示延後live，尚未判定品質通過。

學習交付：[learning](../../learning.md)、[Agent](../../agent.md)、[tools/MCP](../../tools.md)。Will的messages圖與max_steps練習尚未操作，保留在主計畫S7。功能與本文件同批提交，實際revision用 `git log -1` 核對；已push；遠端CI `Offline checks` 於 2026-10-11 對 `b1c3b28`、`7cb2e01` 通過。
