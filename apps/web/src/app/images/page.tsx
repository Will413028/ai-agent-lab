"use client";
import Link from "next/link";
import { useState } from "react";
import { searchImages } from "../../lib/images";
import type { ImageSearchResult } from "../../lib/images.generated";
import { ImageResults } from "../../components/images";

export default function ImagesPage() {
  const [query, setQuery] = useState("coffee");
  const [result, setResult] = useState<ImageSearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function search(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setResult(null);
    try { setResult(await searchImages(query)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "圖片搜尋失敗。"); }
    finally { setBusy(false); }
  }
  return <main className="tools-page"><header className="hero"><p className="eyebrow">AI AGENT LAB · IMAGES</p><h1>找圖片，也保留來源。</h1><p>練習透過獨立 MCP 服務搜尋圖片。</p><nav className="page-links"><Link href="/">聊天</Link><Link href="/tools">工具工作台</Link></nav></header>
    <section className="panel"><form className="knowledge-form" onSubmit={search}><label htmlFor="image-query">圖片搜尋詞</label><input id="image-query" value={query} onChange={event => setQuery(event.target.value)} required maxLength={500} disabled={busy} /><button disabled={busy}>{busy ? "搜尋中…" : "搜尋圖片"}</button><p role="status">{busy ? "搜尋中" : result ? "搜尋完成" : error ? "搜尋失敗" : ""}</p>{error && <p role="alert" className="error">{error}</p>}</form></section>
    {result && <ImageResults result={result} />}
  </main>;
}
