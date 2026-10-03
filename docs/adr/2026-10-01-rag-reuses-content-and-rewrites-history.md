---
title: RAG 依內容身份與對話歷史減少冗餘模型呼叫
date: 2026-10-01
status: active
tags: [ai-agent, rag, decision, llm]
---

# RAG 依內容身份與對話歷史減少冗餘模型呼叫

## Context

單人學習版重做 RAG，原 Java 範例無條件 rewrite，重寫初版亦在文件去重前生成 embedding。獨立設計審查指出這些呼叫順序不由目前需求強制。

- `external`：Will 指定 Cloudflare 免費模型，不自動付費或換付費模型；額度需用於功能驗收與學習。
- `inherited`：原問題、retrieval query、evidence 分離；仍成立，否則 rewrite 會改掉使用者正在問的問題。
- `inherited`：已有內容 digest、status、model／local epoch／dimension；仍成立，用來辨識文件身份與不相容向量空間。
- `inherited`：模型外呼不跨 DB transaction；仍成立，避免網路等待占鎖，但不限制先做本機查詢。

## Options Considered

- **基準／選用：依歷史與內容 namespace 重用。** 無對話背景直接檢索原文，多輪才 rewrite；既有 digest＋status 且 model＋epoch 相符直接沿用文件。[官方 history-aware retriever](https://reference.langchain.com/python/langchain-classic/chains/history_aware_retriever/create_history_aware_retriever) 亦在無 history 時直接檢索；[embedding caching](https://docs.langchain.com/oss/python/integrations/embeddings#caching) 採文字 hash 與 model namespace。
- **每次 rewrite／embedding。** 流程一致，首輪改寫可能改善檢索，但額外呼叫及重複 embedding 都耗額度，現時沒有品質證據支持每次改寫。
- **獨立持久化 embedding cache＋rewrite classifier。** 可跨文件重用向量、縮小改寫範圍，但增加 cache invalidation／classifier 管理，單人 corpus 尚無此需求。

## Decision

- 首輪與 preview 直接使用原問題，多輪才額外 rewrite；generation 的最後 user message 始終保留原問題。
- 先查 digest＋status；model／epoch 相符的既有文件直接回傳，不再外呼。不相符明確要求 reindex。
- 新文件外呼後，在短 transaction 中重新核對 profile／duplicate，再原子写文件與區塊。併行首次匯入可能各算一次，但資料不重複。
- 不新增獨立 cache、背景 ingestion 或自動重試。

## Rationale

相較每次呼叫，選用方案避免確定性重複計算，保留多輪解決指代的能力。代價是無歷史首輪不做語意改寫，且併行新文件仍可能重算一次；不主張它已提升真模型檢索品質。

不選獨立 cache，因已有文件足以承擔當前重用身份，額外 store 會增加失效與生命週期成本。Provider 不公開 immutable revision，local epoch 是顯式控制；供應商模型更新仍需重新核對，不能把名稱相同當成永遠同一模型。

## Expected Outcome

- 重複匯入測試禁止 embedding 被呼叫；namespace 改變測試維持 conflict。
- 首輪／preview 測試禁止 rewriter 被呼叫；多輪測試保存兩種問題，原問題替換 mutation 必須失敗。
- 免費額度用于新內容與多輪必要接線，沒有把 fixture 的 lexical 成功冒稱真模型品質。

## Followup

- 主計畫 S7 的 live holdout 比較原文／改寫查詢品質；進度以同一主計畫為準，不建立第二份進度清單。

## Revocation Triggers

- 首輪真 holdout 顯示有穩定收益，且額度足夠 → 比較首輪 rewrite。
- 出現大量並行首次匯入或跨文件向量重用需求 → 比較 job claim／獨立 cache。
- Provider 公開模型版本或更改 embedding 行為 → 更新 epoch 與 reindex 策略。

## Related

- 本 ADR 即原始決策紀錄，無外部來源文件。
- 舊行為可取回 [LoveApp.java 固定 revision](https://github.com/liyupi/yu-ai-agent/blob/6d4608c58b442d470fffc7a5e0b2aedb0e9478c8/src/main/java/com/yupi/yuaiagent/app/LoveApp.java)。
