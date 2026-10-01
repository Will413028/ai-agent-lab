# S1 驗收紀錄（2026-10-01）

產品範圍：Next.js → POST fetch SSE → FastAPI → FakeProvider。沒有使用憑證、live API、資料庫或外部工具；沒有 commit、push 或部署。Git 為 main 空 history。

## 已執行

| 驗收 | 結果與證據 |
|---|---|
| `make -C <repo> check` | backend Ruff lint/format、13 pytest、web ESLint/TypeScript、生成型別一致、14 Vitest、Next.js production build、plan baseline 與 13 mutations 通過 |
| `make -C <repo> check-skeleton` | 7 Playwright 通過；實際 production Next.js → FastAPI，沒有 mock HTTP route；正常中文／emoji／換行、POST body、四種 typed error、取消後下一請求、375px 手機畫面 |
| 真實 HTTP 首筆事件 | `apps/api/tests/test_chat.py::test_first_event_under_one_second` 通過；fake 的首筆 data 在 1 秒內，沒有用完整 response 時間代替 |
| 斷線 cleanup | `test_disconnect_closes_provider_without_more_chunks` 通過；disconnect 後 2 秒內 finally 執行，第二段未送出 |
| UTF-8 / SSE 完整性 | `apps/web/tests/chat.test.ts`：逐 byte UTF-8、分段 CRLF、comments、單一 error、單 chunk 多 frame、錯 header/version/序號/request、缺 terminal、重複 terminal、額外欄位、截斷／空／超限串流 |
| 新行為 mutation | 暫改 `encode_event` 的 `event: {event.type}` 為 `event: changed`；真 browser 正常案例因收到「回覆失敗」而無法達成「回覆完成」失敗；finally 還原，再重跑 browser 驗收 |
| source equality | `python3 <附件>/check_plan.py --source /private/tmp/ai-agent-lab-yu-ai-agent-reference --self-test`：固定 100 paths 與 13 種負向 mutation 通過；reference checkout 保持 clean |
| visual QA | 已檢視 `artifacts/desktop.png` 與 `artifacts/mobile.png`；沒有水平溢位，composer 可用；圖片為 ignored 本機產物 |
| 無既有 build 的 lint | 暫將自己的 `.next` 改名保留，`pnpm lint` 從乾淨目錄執行 `next typegen`、ESLint、TypeScript 通過；finally 還原 build 後，七項 browser 再次通過 |
| vault gates | `python3 <second-brain>/scripts/lint-rules.py` 與 `check-links.py` 通過；repo Markdown 相對連結另行核對 |

GitHub workflow 已建立，使用相同 `make check`／`check-skeleton`；遠端 CI 尚未執行，不把本機結果當成 GitHub 結果。backend 測試通過時有一則 Starlette TestClient/httpx deprecation warning，不影響結果；後續依上游相容版本更新測試 client。

## Code review 與設計審查

作者核對 API、事件、parser、UI、生成產物、驗收與 CI；修正 Pydantic OpenAPI discriminator annotation 與 Ajv oneOf 的相容方式、以 frame 而非 network chunk 做上限、元件卸載 abort、Next route announcer 的 browser locator 範圍，以及 lint 先執行 `next typegen`。原 8000 port 被占用，改專案 port 18761／13761，不停止其他服務。

獨立 `design-review` 覆蓋 request/turn ID、schema、SSE parser、error terminal、provider composition、取消／背景工作、cache、proxy、fake 注入、CI／tests 與後續決定。發現 1 項：自寫 parser 選擇漏列。處置：**改 0、記 1、提 0、駁回 0**；[盤點表](s1-design-audit.md) 已補學習收益、library 替代方案與切換條件。指令檔對帳更新 1 處：以實際啟動／驗收／契約指令取代 scaffold 待定規則。

## Consumers

可重跑：`rg -n '/api/|EventSource|fetch\(|event_type|readChatEvents|encode_event|ChatEvent' <repo>/apps <repo>/contracts`。

- Producer：`apps/api/agent_lab_api/main.py`、`contracts.py`、`providers.py`。
- Browser：`apps/web/src/lib/chat.ts`、`src/app/page.tsx`、`src/lib/chat-event.generated.ts`、`next.config.ts`。
- Verification/generation：`apps/api/tests/test_chat.py`、`export_contract.py`、`apps/web/tests/chat.test.ts`、`e2e/chat.spec.ts`、`check-contracts.mjs`、`contracts/*.json`。

尚未驗證：Cloudflare 429／quota／timeout 真實 mapping、stream/schema/tool 能力、embedding dimension；依 S0B 才能驗。Fake 的情境注入只保護接線與 UI。
