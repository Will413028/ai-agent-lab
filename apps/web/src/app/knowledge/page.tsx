"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Citations } from "../../components/citations";
import { knowledge, statusLabels, type RelationshipStatus } from "../../lib/knowledge";
import type { Document, RetrievalResult } from "../../lib/rag.generated";

const describe = (error: unknown) => error instanceof Error ? error.message : "操作失敗。";
export default function KnowledgePage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [status, setStatus] = useState<RelationshipStatus>("general");
  const [filter, setFilter] = useState<RelationshipStatus | "all">("all");
  const [query, setQuery] = useState("");
  const [threshold, setThreshold] = useState(0.25);
  const [topK, setTopK] = useState(3);
  const [result, setResult] = useState<RetrievalResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { let alive = true; knowledge.list().then(rows => { if (alive) setDocuments(rows); }).catch(error => { if (alive) setError(describe(error)); }); return () => { alive = false; }; }, []);

  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget;
    const file = (form.elements.namedItem("file") as HTMLInputElement).files?.[0];
    if (!file || busy) return;
    setBusy(true); setError("");
    try { const saved = await knowledge.upload(file, status); setDocuments(await knowledge.list()); setMessage(`已匯入 ${saved.name} · ${saved.chunk_count} 個區塊`); form.reset(); }
    catch (failure) { setError(describe(failure)); }
    finally { setBusy(false); }
  }
  async function remove(id: string) {
    if (busy || !window.confirm("刪除文件及其檢索區塊？已有回覆的引用快照會保留。")) return;
    setBusy(true); setError("");
    try { await knowledge.remove(id); setDocuments(await knowledge.list()); setResult(null); setMessage("文件已刪除"); }
    catch (failure) { setError(describe(failure)); }
    finally { setBusy(false); }
  }
  async function reindex() {
    if (busy || !window.confirm("使用目前的 embedding 設定重建全部索引？這會重新呼叫 embedding 模型。")) return;
    setBusy(true); setError("");
    try { setDocuments(await knowledge.reindex()); setResult(null); setMessage("索引已重建"); }
    catch (failure) { setError(describe(failure)); }
    finally { setBusy(false); }
  }
  async function search(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy || !query.trim()) return;
    setBusy(true); setError(""); setResult(null);
    try { setResult(await knowledge.search(query.trim(), filter === "all" ? null : filter, threshold, topK)); }
    catch (failure) { setError(describe(failure)); }
    finally { setBusy(false); }
  }
  return <main className="knowledge-shell"><header className="topbar"><Link className="wordmark" href="/">AI Agent <span>Lab</span></Link><Link href="/">返回對話 ↗</Link></header><div className="content">
    <div className="intro"><div className="eyebrow">READ · RETRIEVE · CONNECT</div><h1>把知識，帶進對話。</h1><p>匯入你的 Markdown 文件，依關係狀態篩選，再查看每一次檢索的來源。</p></div>
    <form className="knowledge-card" onSubmit={upload}><h2>匯入文件</h2><p className="small-note">UTF-8 .md，最多 512 KiB／256 個區塊。重複內容與狀態會沿用同一份文件。</p><label htmlFor="file">Markdown 文件</label><input id="file" name="file" type="file" accept=".md" required disabled={busy} /><label htmlFor="document-status">文件適用狀態</label><select id="document-status" value={status} onChange={event => setStatus(event.target.value as RelationshipStatus)} disabled={busy}>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button className="send" disabled={busy}>匯入文件</button></form>
    <section className="knowledge-card" aria-label="文件列表"><div className="report-heading"><h2>你的知識庫 · {documents.length}</h2><button className="text-button" onClick={() => void reindex()} disabled={busy || !documents.length}>重建索引</button></div>{documents.length === 0 ? <p className="small-note">先匯入一份文件。</p> : documents.map(document => <article key={document.id} className="document-row"><div><h3>{document.name}</h3><p>{statusLabels[document.relationship_status]} · {document.chunk_count} 個區塊</p><p className="small-note">{document.keywords.join(" · ")}</p><details><summary>索引資訊</summary><p className="small-note">{document.embedding_model} · {document.embedding_version} · {document.embedding_dimension} 維 · {document.chunk_version}</p></details></div><button className="text-button danger" onClick={() => void remove(document.id)} disabled={busy}>刪除 {document.name}</button></article>)}</section>
    <form className="knowledge-card" onSubmit={search}><h2>試一次檢索</h2><label htmlFor="query">檢索問題</label><textarea id="query" value={query} onChange={event => setQuery(event.target.value)} maxLength={2000} required disabled={busy} /><div className="retrieval-controls"><label>適用狀態<select value={filter} onChange={event => setFilter(event.target.value as RelationshipStatus | "all")} disabled={busy}><option value="all">全部</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>最低相似度<input type="number" min="0" max="1" step="0.05" value={threshold} onChange={event => setThreshold(Number(event.target.value))} disabled={busy} /></label><label>最多來源<input type="number" min="1" max="10" value={topK} onChange={event => setTopK(Number(event.target.value))} disabled={busy} /></label></div><button className="send" disabled={busy || !query.trim()}>檢索來源</button></form>
    {error && <div className="error" role="alert">{error}</div>}<p role="status">{busy ? "處理中…" : message}</p>{result && <Citations result={result} />}
  </div></main>;
}
