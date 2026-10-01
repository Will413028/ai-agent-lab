"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { tools, type Artifact, type ToolDefinition, type ToolResult } from "../../lib/tools";

const labels: Record<string, string> = {
  readFile: "讀取檔案", writeFile: "建立文字檔", searchWeb: "搜尋網頁",
  scrapeWebPage: "讀取網頁", downloadResource: "下載資源",
  executeTerminalCommand: "執行 Terminal", generatePDF: "建立 PDF", doTerminate: "結束任務",
};
const fields: Record<string, string[]> = {
  readFile: ["fileName"], writeFile: ["fileName", "content"], searchWeb: ["query"],
  scrapeWebPage: ["url"], downloadResource: ["url", "fileName"],
  executeTerminalCommand: ["command"], generatePDF: ["fileName", "content"], doTerminate: [],
};
const fieldLabels: Record<string, string> = { fileName: "檔名", content: "內容", query: "搜尋詞", url: "網址", command: "Shell command" };

export default function ToolsPage() {
  const [definitions, setDefinitions] = useState<ToolDefinition[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [name, setName] = useState("generatePDF");
  const [values, setValues] = useState<Record<string, string>>({ fileName: "學習筆記.pdf", content: "# AI Agent 學習筆記\n工具結果保留 call ID，再交回模型。", query: "AI Agent", url: "https://example.com/learning", command: "python -c 'print(1 + 1)'" });
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [result, setResult] = useState<ToolResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => { let active = true;
    tools.definitions().then(data => { if (active) setDefinitions(data); }).catch(() => { if (active) setError("無法載入工具列表。"); });
    return () => { active = false; };
  }, []);

  function choose(next: string) {
    setName(next); setResult(null); setError(""); setStatus("");
    if (next === "writeFile") setValues(old => ({ ...old, fileName: "筆記.txt" }));
    if (next === "generatePDF") setValues(old => ({ ...old, fileName: "學習筆記.pdf" }));
  }

  async function invoke(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setStatus("工具執行中"); setResult(null);
    try {
      const id = workspaceId || (await tools.createWorkspace()).id;
      setWorkspaceId(id);
      const args = Object.fromEntries((fields[name] ?? []).map(field => [field, values[field] ?? ""]));
      const [outcome] = await tools.invoke(id, [{ id: crypto.randomUUID(), name, arguments: args }]);
      setResult(outcome); setArtifacts(await tools.artifacts(id));
      setStatus(outcome.status === "success" ? "工具完成" : "工具失敗");
      if (outcome.status === "error") setError(outcome.message ?? "工具執行失敗。");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "工具操作失敗。"); setStatus("工具失敗"); }
    finally { setBusy(false); }
  }

  return <main className="tools-page">
    <header className="hero"><p className="eyebrow">AI AGENT LAB · TOOLS</p><h1>工具工作台</h1><p>逐項練習工具呼叫，查看結果與下載產物。</p><nav className="page-links"><Link href="/">聊天</Link><Link href="/knowledge">知識庫</Link></nav></header>
    <section className="panel"><form onSubmit={invoke} className="knowledge-form">
      <label htmlFor="tool-name">工具</label><select id="tool-name" value={name} onChange={event => choose(event.target.value)} disabled={busy}>{definitions.map(tool => <option key={tool.name} value={tool.name}>{labels[tool.name] ?? tool.name}</option>)}</select>
      <p>{definitions.find(tool => tool.name === name)?.description}</p>
      {(fields[name] ?? []).map(field => <div key={field}><label htmlFor={`tool-${field}`}>{fieldLabels[field]}</label>{field === "content" || field === "command" ? <textarea id={`tool-${field}`} rows={field === "content" ? 6 : 3} value={values[field] ?? ""} onChange={event => setValues(old => ({ ...old, [field]: event.target.value }))} required disabled={busy} /> : <input id={`tool-${field}`} value={values[field] ?? ""} onChange={event => setValues(old => ({ ...old, [field]: event.target.value }))} required disabled={busy} />}</div>)}
      <button type="submit" disabled={busy || definitions.length === 0}>{busy ? "執行中…" : "執行工具"}</button>
      <p role="status">{status}</p>{error && <p role="alert" className="error">{error}</p>}
    </form></section>
    {result?.status === "success" && <section className="panel"><h2>呼叫結果</h2><p>call ID：{result.tool_call_id}</p><pre className="tool-output">{JSON.stringify(result.data, null, 2)}</pre></section>}
    <section className="panel"><h2>產物</h2>{artifacts.length === 0 ? <p>執行建立檔案或 PDF 工具後，產物會出現在這裡。</p> : <ul>{artifacts.map(artifact => <li key={artifact.id}><a href={tools.download(artifact)} download={artifact.name}>{artifact.name}</a> · {artifact.size.toLocaleString()} bytes</li>)}</ul>}</section>
  </main>;
}
