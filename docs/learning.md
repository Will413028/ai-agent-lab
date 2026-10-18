# 一次看懂模型到工具的循環

先啟動`make api`與`make web`，開`/agent`。預設離線模型，搜尋是fixture，PDF是實際產物。輸入目標並執行，能看到searchWeb、generatePDF、最後答案與下载連結；重新整理後仍能讀到run歷史。

一次工具往返的messages如下。call ID由模型提供，tool結果必須回到同一個ID；第二次模型決策才看得到搜尋結果。

```json
[
  {"role":"system","content":"任務規則與工具邊界"},
  {"role":"user","content":"搜尋學習資源並整理成PDF"},
  {"role":"assistant","tool_calls":[{"id":"call_0","type":"function","function":{"name":"searchWeb","arguments":"{\"query\":\"AI Agent\"}"}}]},
  {"role":"tool","tool_call_id":"call_0","content":"{\"status\":\"success\",\"data\":{\"results\":[...]}}"}
]
```

請自己畫出`user → assistant tool_calls → registry → tool result → assistant`，在每條邊標call ID。程式對照`apps/api/agent_lab_api/agent_runtime.py`的assistant_message與events、`tools.py`的invoke與tool_message。先追一個tool call，再追取消signal如何中止等待。

把畫面的「最多步數」改成2，跑以下兩個案例：

1. 目標`fixture:no-tools`：第1步直接回答，結果succeeded，沒有工具；不能為了把步數用完而繼續。
2. 目標`fixture:loop`：每步都要搜尋，2步後結果limit；與失敗、取消不同。

再跑`fixture:slow`並取消，確認結果cancelled、沒有新工具呼叫；跑`fixture:tool-error`觀察typed failure。這些是離線控制流程練習，不能拿來證明真模型能力。已提供練習與agent驗收，Will是否親自完成畫圖／修改練習需由本人確認，不能代填已完成。

RAG對照`knowledge.py → rag.py → CloudflareEmbedder`：相同內容先查digest再決定要不要embed；query rewrite只供retrieval，generation仍收到原問題；引用保存snapshot，所以刪文件後舊回答仍可查來源。

Cloudflare live已依Will指示先跳過。之後可用`make api-cloudflare`、`make live-spike`與`make live-holdout`：spike有10次request上限，holdout使用獨立[固定情境](plans/2026-10-01-rebuild/holdout.json)，人工rubric未判讀的結果是needs_review。所有失敗和重跑各存一份ignored evidence，不能只留下成功次。

## 人工驗收的結案方式

每次holdout保留`artifacts/live-holdout-<timestamp>/attempt.json`與`H04.pdf`，包含允許公開的模型content、canonical run events、搜尋結果及RAG citation snapshots；資料均來自固定人工情境，不含SDK reasoning或個人對話。Test DB清除前先保存證據；PDF另有SHA256，不靠已刪DB定位。

讀該次attempt的rubric、引用及PDF後，建立自己的`review.json`，只為needs_review案例填passed或failed及理由，例如：

```json
{
  "H01": {"status":"passed","reason":"第二輪六項條件均符合"},
  "H02": {"status":"passed","reason":"建議符合輪班及溝通條件"},
  "H03": {"status":"passed","reason":"時間可對照引用，生日未捏造"},
  "H04": {"status":"passed","reason":"已讀PDF，包含實際搜尋來源"}
}
```

這是格式示例，不能直接當實際評分。依看見的內容填寫，再執行：

```sh
make -C /absolute/path/to/ai-agent-lab review-holdout \
  ATTEMPT=/absolute/path/to/artifacts/live-holdout-<timestamp>/attempt.json \
  REVIEW=/absolute/path/to/review.json REVIEWER=Will
```

程式拒絕變更corpus、遺失／被改動PDF、缺引用或漏評；failed/not_run不能被人工覆寫成通過。另存review sidecar，包含reviewer、reviewed_at、原attempt SHA256、corpus SHA256與逐例理由。全部8例通過才會得到該attempt的passed結論；跨重跑彙整時也須同一corpus hash、每例指向一份有效review，保留全部失敗。這只代表N04功能smoke，不代表品質或可靠率。現在未跑live，沒有任何真實評分紀錄。
