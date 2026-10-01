"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { streamChat, type Scenario } from "../lib/chat";
import { conversations } from "../lib/conversations";
import type { Conversation, SavedReport, Turn } from "../lib/conversation.generated";
import { knowledge, statusLabels, type RelationshipStatus } from "../lib/knowledge";
import type { TurnRetrieval } from "../lib/rag.generated";
import { Citations } from "../components/citations";

type DisplayTurn = Pick<Turn, "id" | "question" | "answer" | "status">;
const options: { value: Scenario; label: string }[] = [
  { value: "normal", label: "正常回覆" }, { value: "slow", label: "慢速回覆（練習取消）" },
  { value: "rate_limit", label: "請求過於頻繁" }, { value: "quota", label: "免費額度已用完" },
  { value: "timeout", label: "回覆逾時" }, { value: "dependency_failure", label: "服務暫時無法使用" },
];
function describe(error: unknown) { return error instanceof Error ? error.message : "操作失敗，請稍後再試。"; }
function address(id: string | null) { window.history.replaceState(null, "", id ? `/?conversation=${encodeURIComponent(id)}` : "/"); }

export default function Page() {
  const [list, setList] = useState<Conversation[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [turns, setTurns] = useState<DisplayTurn[]>([]);
  const [reports, setReports] = useState<SavedReport[]>([]);
  const [position, setPosition] = useState(0);
  const [message, setMessage] = useState("");
  const [scenario, setScenario] = useState<Scenario>("normal");
  const [useKnowledge, setUseKnowledge] = useState(false);
  const [relationship, setRelationship] = useState<RelationshipStatus | "all">("all");
  const [retrievals, setRetrievals] = useState<TurnRetrieval[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("正在載入對話");
  const [modelMode, setModelMode] = useState<"offline" | "cloudflare">("offline");
  const controller = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const transcript = useRef<HTMLDivElement | null>(null);
  const followReply = useRef(true);

  useEffect(() => {
    if (followReply.current && transcript.current) {
      transcript.current.scrollTop = transcript.current.scrollHeight;
    }
  }, [turns]);

  const load = useCallback(async (id: string) => {
    const [detail, saved, sources] = await Promise.all([conversations.get(id), conversations.reports(id), knowledge.snapshots(id)]);
    if (!alive.current) return detail;
    setTurns(detail.turns); setReports(saved); setPosition(detail.turns.at(-1)?.position ?? 0);
    setRetrievals(sources);
    return detail;
  }, []);

  useEffect(() => {
    alive.current = true;
    async function initialize() {
      try {
        const rows = await conversations.list();
        if (!alive.current) return;
        setList(rows);
        const health = await fetch("/api/health").then(response => response.json());
        if (!alive.current) return;
        setModelMode(health.mode === "cloudflare" ? "cloudflare" : "offline");
        const requested = new URLSearchParams(window.location.search).get("conversation");
        const id = requested ?? rows[0]?.id ?? null;
        if (id) { await load(id); if (!alive.current) return; setActive(id); address(id); }
        setStatus("準備就緒");
      } catch (failure) { if (alive.current) { setError(describe(failure)); setStatus("載入失敗"); } }
      finally { if (alive.current) setLoading(false); }
    }
    void initialize();
    return () => { alive.current = false; controller.current?.abort(); };
  }, [load]);

  async function select(id: string | null) {
    if (busy || loading) return;
    followReply.current = true;
    setLoading(true); setError(""); setMessage("");
    try {
      if (id) await load(id);
      else { setTurns([]); setReports([]); setRetrievals([]); setPosition(0); }
      setActive(id); address(id); setStatus("準備就緒");
    } catch (failure) { setError(describe(failure)); }
    finally { setLoading(false); }
  }

  async function send(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = message.trim();
    if (!question || busy || loading) return;
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); setError(""); setStatus("正在回覆");
    let id = active;
    const temporary = crypto.randomUUID();
    try {
      if (!id) {
        const created = await conversations.create(question.slice(0, 36), abort.signal);
        id = created.id; setActive(id); setList(rows => [created, ...rows]); address(id);
      }
      setMessage("");
      followReply.current = true;
      setTurns(rows => [...rows, { id: temporary, question, answer: "", status: "running" }]);
      await streamChat({ message: question, scenario }, abort.signal, item => {
        if (item.type === "delta") setTurns(rows => rows.map(turn => turn.id === temporary ? { ...turn, answer: turn.answer + item.text } : turn));
        else if (item.type === "done") setStatus("回覆完成");
        else { setError(item.message); setStatus("回覆失敗"); }
      }, id, useKnowledge ? { relationship_status: relationship === "all" ? null : relationship, threshold: 0.25, top_k: 3 } : undefined);
    } catch (failure) {
      if (abort.signal.aborted) setStatus("已取消");
      else { setError(describe(failure)); setStatus("回覆失敗"); }
    } finally {
      if (alive.current && id) {
        try {
          let detail = await load(id);
          const deadline = Date.now() + 2500;
          while (detail.turns.some(turn => turn.status === "running") && Date.now() < deadline) {
            await new Promise(resolve => setTimeout(resolve, 150));
            if (!alive.current) break;
            detail = await load(id);
          }
          const rows = await conversations.list();
          if (alive.current) setList(rows);
        } catch (failure) { if (alive.current) setError(describe(failure)); }
      }
      controller.current = null;
      if (alive.current) setBusy(false);
    }
  }

  async function generateReport() {
    if (!active || busy) return;
    setBusy(true); setError(""); setStatus("正在產生報告");
    try {
      const saved = await conversations.report(active);
      setReports(rows => [saved, ...rows]); setStatus("報告已儲存");
    } catch (failure) { setError(describe(failure)); setStatus("報告失敗"); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!active || busy || !window.confirm("刪除這個對話及所有回合、報告？此操作無法復原。")) return;
    setBusy(true); setError("");
    try {
      await conversations.remove(active);
      setList(rows => rows.filter(row => row.id !== active)); setActive(null);
      setTurns([]); setReports([]); setRetrievals([]); setPosition(0); address(null); setStatus("對話已刪除");
    } catch (failure) { setError(describe(failure)); }
    finally { setBusy(false); }
  }

  const title = list.find(row => row.id === active)?.title ?? "新的戀愛諮詢";
  return <main className="shell">
    <aside className="sidebar">
      <Link className="wordmark" href="/">AI Agent <span>Lab</span></Link>
      <div className="nav-label">你的對話</div>
      <nav className="saved-conversations" aria-label="已儲存對話">
        {list.map(row => <button key={row.id} className={row.id === active ? "conversation-link selected" : "conversation-link"} disabled={busy || loading} onClick={() => void select(row.id)}>{row.title}</button>)}
        {list.length === 0 && <p className="small-note">第一句話，開啟一段對話。</p>}
      </nav>
      <div className="sidebar-note"><span className="note-mark">02</span><p>留下對話，<br />看見溝通的下一步。</p></div>
      <Link className="demo-link" href="/demo">串流示範 ↗</Link>
      <Link className="demo-link" href="/knowledge">知識庫 ↗</Link>
      <Link className="demo-link" href="/tools">工具工作台 ↗</Link>
      <Link className="demo-link" href="/images">圖片搜尋 ↗</Link>
      <Link className="demo-link" href="/agent">Agent 任務 ↗</Link>
    </aside>
    <section className="workspace">
      <header className="topbar"><span>戀愛諮詢</span><div className="header-actions"><button className="new-chat" disabled={busy || loading} onClick={() => void select(null)}>新對話 ＋</button><span className="offline"><i /> {modelMode === "cloudflare" ? "Cloudflare" : "離線示範"}</span></div></header>
      <div className="content">
        <div className="intro"><div className="eyebrow">LISTEN · REFLECT · CONNECT</div><h1>讓對話，有下一步。</h1><p>先釐清感受，再練習一個小小的溝通行動。</p></div>
        <div className="demo-note">{modelMode === "cloudflare" ? "使用 Cloudflare 回覆。" : "使用離線示範回覆。"}對話保存在本機資料庫，直到你刪除；模型只讀最近完整回合。</div>
        <div className="conversation-controls"><label htmlFor="conversation">選擇對話</label><select id="conversation" value={active ?? ""} onChange={event => void select(event.target.value || null)} disabled={busy || loading}><option value="">新增對話</option>{list.map(row => <option key={row.id} value={row.id}>{row.title}</option>)}</select><button className="text-button danger" disabled={!active || busy || loading} onClick={() => void remove()}>刪除對話</button></div>
        <h2 className="conversation-title">{title}</h2>
        <div ref={transcript} className="conversation" aria-label="對話紀錄" aria-busy={busy || loading} onScroll={event => { const node = event.currentTarget; followReply.current = node.scrollHeight - node.clientHeight - node.scrollTop < 48; }}>
          {turns.length === 0 ? <div className="empty"><div className="spark">✳</div><h2>{loading ? "正在載入…" : "想先說說你的近況嗎？"}</h2><p>你是單身、交往中，還是已婚？</p><button className="example" type="button" disabled={busy || loading} onClick={() => setMessage("我想安排一次輕鬆的約會，有什麼建議？")}>我想安排一次輕鬆的約會 ↗</button></div> : turns.map(turn => <article className="turn" key={turn.id}><div className="question"><span>你</span><p>{turn.question}</p></div><div className="answer"><span className="avatar">✳</span><div><div className="speaker">AI Agent Lab <span className="turn-state">{turn.status === "cancelled" ? "已取消" : turn.status === "failed" ? "回覆失敗" : turn.status === "running" ? "正在回覆" : ""}</span></div><p data-testid="answer">{turn.answer || (turn.status === "running" ? "正在準備回覆…" : "本次未收到文字回覆。")}</p></div></div></article>)}
        </div>
        {error && <div role="alert" className="error">{error}</div>}
        {retrievals.map(result => <Citations key={result.turn_id} result={result} />)}
        <div className="retrieval-controls"><label><input type="checkbox" checked={useKnowledge} onChange={event => setUseKnowledge(event.target.checked)} disabled={busy || loading} /> 使用知識庫</label>{useKnowledge && <label>關係狀態<select value={relationship} onChange={event => setRelationship(event.target.value as RelationshipStatus | "all")} disabled={busy || loading}><option value="all">全部</option>{Object.entries(statusLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>}<Link href="/knowledge">管理文件 ↗</Link></div>
        <form className="composer" onSubmit={send}>
          <label htmlFor="message" className="sr-only">你的訊息</label><textarea id="message" value={message} maxLength={2000} rows={3} disabled={busy || loading} onChange={event => setMessage(event.target.value)} placeholder="寫下你的想法…" />
          <div className="composer-bottom"><div><label htmlFor="scenario">測試情境</label><select id="scenario" value={scenario} onChange={event => setScenario(event.target.value as Scenario)} disabled={busy || loading || modelMode === "cloudflare"}>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>{busy && status === "正在回覆" ? <button type="button" className="send cancel" onClick={() => controller.current?.abort()}>停止回覆 ■</button> : <button type="submit" className="send" disabled={busy || loading || !message.trim()}>送出訊息 ↑</button>}</div>
        </form>
        <footer className="conversation-foot"><span role="status" aria-live="polite">{status}</span><Link href="/demo">串流示範 ↗</Link></footer>
        <section className="report-panel" aria-label="戀愛報告"><div className="report-heading"><div><div className="eyebrow">REFLECTION NOTES</div><h2>把對話，整理成行動。</h2></div><button className="new-chat" disabled={busy || loading || !active || !turns.some(turn => turn.status === "completed")} onClick={() => void generateReport()}>產生報告</button></div>{reports.length === 0 ? <p className="small-note">完成一輪對話後，可以產生結構化建議。</p> : reports.map(report => <article className="report-card" key={report.id}><div className="report-version">對話版本 {report.source_position}{report.source_position < position ? " · 較早的紀錄" : " · 最新紀錄"}</div><h3>{report.content.title}</h3><ol>{report.content.suggestions.map((suggestion,index) => <li key={index}>{suggestion}</li>)}</ol></article>)}</section>
      </div>
    </section>
  </main>;
}
