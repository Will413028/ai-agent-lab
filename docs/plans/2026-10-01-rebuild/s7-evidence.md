# S7 程式交付驗收

程式、文件、離線及真本機依賴驗收已完成；Will明確指示先跳過Cloudflare live，因此S0B／N04品質與本人學習練習維持未執行。

| 檢查 | 實際結果 |
|---|---|
| Backend | 最終106 unit通過；ruff lint／format，schema與OpenAPI產物一致 |
| Frontend | 16 parser unit、lint／typecheck／production build通過 |
| Docker chat | 15 DB integration、全套18 browser通過，含Agent／MCP／RAG／PDF |
| Docker RAG | 8 integration、2 mutation拒絕並還原、2 browser通過 |
| Docker terminal | 4 integration通過，包括真執行後取消與deadline清理 |
| MCP | 官方SDK真stdio 8、schema mutation1、browser1通過 |
| Agent | 13unit、loop/cancel mutation2、native DB6、browser2通過 |
| Plan／source | 固定100 tracked paths、baseline＋13負向mutation通過，reference保持clean |
| Recording | parent lint-rules與check-links通過，daily與project已更新 |

Backend在原make check為103項，人工review與durable-save regression追加後最終106項；不是把不同suite重複加總。Logs為ignored `artifacts/s7-check-final.log`、`s7-check-api-final2.log`、`s7-check-chat-docker-final.log`、`s7-check-rag-docker.log`。S4–S6詳見各stage evidence。

首輪Docker全browser16/18，timeout UI與第一輪chat click各逾時；保留 `s7-check-chat-docker.log`。Trace確認timeout request與約56ms回傳的canonical error正確，但尚未確認browser逾時根因。相同門檻、retries=0的下一次全18通過，沒有提高N01／request／取消期限。這不證明host負載穩定性。

Fresh S7 design-review檢查測試分層、配置／SDK／budget、DB與API ownership、證據retention、人工評分、CI、學習交付：2項，改2／記0／提0／駁回0。B1在清DB前保存完整attempt／events／citations／PDF與hash，cleanup獨立sidecar；C1新增人工review入口，original attempt不可覆寫，逐例理由與reviewer／時間／hash可追查。兩輪唯讀重核收口；缺引用、改PDF、改corpus、failed override、DELETE時磁碟證據存在都有行為回歸。

S3–S7累計12項design-review，改9／記3／提0／駁回0；AGENTS.md补5條現行規則、local移1條session歷史到handoff，共6處指令檔對帳。R01–R13／B01–B06映射見[implementation evidence](implementation-evidence.md)。

Cloudflare live與人工品質評分未跑；DDG live challenge、Commons MCP live dependency_failure保留原事實。本次功能與文件同批提交；遠端CI未跑，未push。沒有把真SDK transport＋fixture稱為真模型品質。

2026-10-18 live holdout（Will 指示 reasoning 開／關各跑一輪；native PG18.6＋pgvector；機器 load average 71–95，延遲偏高）：

| Attempt | thinking | H01 | H02 | H03 | H04 | H05 | H06 |
|---|---|---|---|---|---|---|---|
| `live-holdout-20261018T033445615668` | on | failed（未記原因） | failed | failed | failed：模型改用 terminal，`tool_timeout` | passed | passed |
| `live-holdout-20261018T034056220736` | on（補診斷後重跑） | failed `provider_failure` | needs_review | failed `provider_failure` | needs_review | passed | passed |
| `live-holdout-20261018T033822042093` | off | needs_review | needs_review | needs_review | needs_review | passed | passed |

reasoning 開時聊天失敗的根因已實測：H01 第一問單獨串流，reasoning 用完 `max_completion_tokens` 2048，content 0 字、`finish_reason=length`、53.3s。第一輪原本把例外吞掉，`live_holdout.py` 已補 `failure_detail`（只記例外類型、HTTP status、app sanitized code）。needs_review 待 Will 依 rubric 評分；機械通過不代表品質。

評分（Will 2026-10-18 委託 AI 代評，reviewer 記為 `Claude (AI, delegated by Will 2026-10-18)`，不是本人評分）：off attempt H01 failed（第二輪捏造店名、價格、站名與公車路線，並殘留「台南」），H02／H03／H04 passed，結論 incomplete；on attempt H02 failed（建議假日共同時間，與「只有週二晚上有空」衝突），H04 passed，結論 incomplete。review sidecar 存於各 attempt 目錄，原 attempt 未改。之後 Will 決定 reasoning 預設 off。

H01 捏造店價修正（2026-10-18，Will 指示）：`context.py` SYSTEM_PROMPT 加入「只依最新更正條件」與「不寫店家、景點、場館、車站、路線的專有名稱與具體價格，只給類型、預算比例與查證關鍵字」。先用不在 corpus 的開發案例（高雄→台中、全素、500元）驗證：舊 prompt 重現捏造店名、公車號碼與價格；第一版仍捏造一間文創館；第二版未見專有店名，但仍提到一次已更正的 1000 元（各 1 樣本，`artifacts/h01-dev-*.json`）。**H01 已被這次修正參考過，不再是 blind holdout**；要宣稱 H01 類能力需新增凍結案例。重跑 `live-holdout-20261018T040654347730`（thinking off）：AI 代評 H01 passed（邊緣：冰淇淋甜點店、疑似專有名稱一處）、H02 failed（週五／週日安排與只有週二衝突，假設有子女）、H03／H04 passed、H05／H06 機械 passed，結論 incomplete。H02 三次 attempt 中兩次違反時間條件。

H02 時間條件修正（2026-10-18，Will 指示）：`cloudflare.py` report 指令加入「需同步的事只排在使用者說有空的時段，其他只建議非同步做法；不推定未提及的人或對方想法」。開發案例（遠距、只有週日 9–10 點能視訊，`artifacts/h02-dev-*.json`）修正前出現需另約同步時間的建議，修正後未見（各 1 樣本）。H02 同樣已被參考，不再是 blind。重跑 `live-holdout-20261018T042519920488`（thinking off）AI 代評：H01 failed（新竹捷運、捏造店名與票價）、H02／H03／H04 passed、H05／H06 機械 passed，結論 incomplete。同一 H01 prompt 兩次 attempt 1 過 1 不過：prompt 無法穩定阻止 GLM-4.7-flash（thinking off）捏造地點與價格。

H01 後續（Will 2026-10-18 同意建議）：(1) 接受限制，聊天頁 Cloudflare 模式與 README 註明可能捏造店家、價格、路線，請自行查證；真實地點改用 Agent searchWeb。(2) bounded probe：台中開發案例 ×2 改用 `@cf/meta/llama-3.3-70b-instruct-fp8-fast`（4 requests，`artifacts/llama-probe-20261018.json`）：兩次都依更正條件、只給類型與預算比例，未出現專有名稱或具體價格，約 5s／輪，內容較籠統，出現一個簡體字「那里」。依官方 pricing 與實測 token 推算 llama 約 71 Neurons／輪（每日免費 10,000 約 140 輪），GLM thinking off 約 13 Neurons／輪。是否把聊天改用 llama 待 Will 決定（需改 allowlist 與 D6b）；樣本僅 2，未跑 holdout。

聊天串流改用 llama-3.3-70b（Will 2026-10-18 同意）：首輪 `live-holdout-20261018T043727953457` 的 H01／H03 在約 1.3s `provider_failure`。根因實測：Workers AI llama 串流把數字 token 以 JSON number 送出（例：第 48 chunk `content: 44`），parser 只收字串。回歸測試先紅後綠，修正後同介面重跑 H01 問題完整串流。下一次 holdout 臨時 API 30s 內未就緒（load average 45→70，import 即 6.2s；stderr 未保存，推斷為負載），重跑 `live-holdout-20261018T044746339772`：AI 代評 H01–H04 passed、H05／H06 機械 passed，**review 結論 passed**。限制：AI 代評非本人；H01／H02 已被 prompt 修正參考，不是 blind；單次通過不代表可靠率。另發現缺陷：PDF 嵌入 `NotoSansTC`，generatePDF 輸入含簡體「协」「档」但 PDF 未渲染（實測），待處理。
