"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { conversations } from "../../lib/conversations";
import type { Conversation } from "../../lib/conversation.generated";
import { runs } from "../../lib/runs";
import type { Run, RunEvent } from "../../lib/runs";
import { tools } from "../../lib/tools";
import type { Artifact } from "../../lib/tools";

const names = { running: "執行中", succeeded: "已完成", failed: "失敗", cancelled: "已取消", limit: "已達上限" };
export default function AgentPage() {
  const [chats, setChats] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [history, setHistory] = useState<Run[]>([]);
  const [goal, setGoal] = useState("搜尋 Agent 學習資源，整理成中文 PDF。");
  const [maxSteps, setMaxSteps] = useState(6);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const activeId = useRef("");
  const activeConversation = useRef("");
  useEffect(() => {
    let mounted = true;
    conversations.list().then(rows => { if (mounted) { setChats(rows); setConversationId(rows[0]?.id ?? ""); } }).catch(failure => { if (mounted) setError(failure.message); });
    return () => { mounted = false; controller.current?.abort(); };
  }, []);
  useEffect(() => {
    let mounted = true;
    if (conversationId) runs.list(conversationId).then(rows => { if (mounted) setHistory(rows); }).catch(failure => { if (mounted) setError(failure.message); });
    return () => { mounted = false; };
  }, [conversationId]);
  async function show(run: Run) {
    try { const detail = await runs.get(run.conversation_id, run.id); setEvents(detail.events ?? []); setArtifacts(await tools.artifacts(detail.workspace_id)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "無法載入任務。"); }
  }
  async function start(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setEvents([]); setArtifacts([]);
    activeId.current = "";
    const abort = new AbortController(); controller.current = abort;
    let id = conversationId;
    let workspace = "";
    try {
      if (!id) { const chat = await conversations.create("Agent 任務", abort.signal); id = chat.id; setChats(rows => [chat, ...rows]); setConversationId(id); }
      activeConversation.current = id;
      await runs.stream(id, { goal, max_steps: maxSteps, max_calls: 12 }, abort.signal, event => {
        activeId.current = event.run_id;
        if (event.data.type === "started") workspace = event.data.workspace_id;
        setEvents(rows => [...rows, event]);
      });
    } catch (failure) {
      if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : "任務執行失敗。");
    } finally {
      if (id) {
        try { setHistory(await runs.list(id)); if (workspace) setArtifacts(await tools.artifacts(workspace)); }
        catch { setError("無法重新載入任務結果。"); }
      }
      setBusy(false); controller.current = null;
    }
  }
  async function cancel() {
    if (activeId.current) {
      try { await runs.cancel(activeConversation.current, activeId.current); }
      catch { setError("取消通知失敗，已中斷此連線。"); controller.current?.abort(); }
    } else controller.current?.abort();
  }
  const final = events.at(-1)?.data;
  const started = events[0]?.data;
  return <main className="tools-page"><header className="hero"><p className="eyebrow">AI AGENT LAB · AGENT</p><h1>給目標，逐步完成。</h1><p>查看工具執行、產物與任務結果。</p><nav className="page-links"><Link href="/">聊天</Link><Link href="/tools">工具</Link><Link href="/images">圖片</Link></nav></header>
    <section className="panel"><form className="knowledge-form" onSubmit={start}>
      <label htmlFor="run-conversation">對話</label><select id="run-conversation" disabled={busy} value={conversationId} onChange={e => { setConversationId(e.target.value); setEvents([]); setArtifacts([]); }}><option value="">建立新對話</option>{chats.map(chat => <option key={chat.id} value={chat.id}>{chat.title}</option>)}</select>
      <label htmlFor="run-goal">任務目標</label><textarea id="run-goal" value={goal} onChange={e => setGoal(e.target.value)} maxLength={2000} required disabled={busy} />
      <label htmlFor="run-steps">最多步數</label><input id="run-steps" type="number" min={1} max={12} value={maxSteps} onChange={e => setMaxSteps(Number(e.target.value))} disabled={busy} />
      <div className="page-links"><button disabled={busy || !goal.trim()}>開始任務</button>{busy && <button type="button" onClick={cancel}>取消任務</button>}</div>
      <p role="status">{final?.type === "done" ? names[final.status] : busy ? "執行中" : ""}</p>{error && <p role="alert" className="error">{error}</p>} {started?.type === "started" && <p>{`模型：${started.provider === "fake" ? "離線示範" : "Cloudflare"} · 網頁工具：${started.tools_mode === "live" ? "公開網站" : "離線示範"} · 圖片：${started.images_mode === "live" ? "Commons" : "離線示範"}`}</p>}
    </form></section>
    {events.length > 0 && <section className="panel"><h2>執行紀錄</h2><ol className="run-events">{events.map(event => <li key={event.sequence}><span>{event.data.type === "state" ? `第 ${event.data.step} 步：${event.data.phase === "thinking" ? "準備下一步" : "執行工具"}` : event.data.type === "tool_call" ? `呼叫 ${event.data.call.name}` : event.data.type === "tool_result" ? `${event.data.result.name}：${event.data.result.status === "success" ? "成功" : event.data.result.message}` : event.data.type === "started" ? "任務已開始" : event.data.type === "done" ? names[event.data.status] : ""}</span><small> · 經過 {event.elapsed_ms ?? 0} ms</small></li>)}</ol>
      {final?.type === "done" && <><p className="run-answer">{final.answer}</p><p>用量：{final.usage?.source === "provider" ? `provider 回報，輸入 ${final.usage.input_tokens}／輸出 ${final.usage.output_tokens} tokens` : final.usage?.source === "estimated" ? "estimated" : "unknown"}</p></>}
    </section>}
    {artifacts.length > 0 && <section className="panel"><h2>任務產物</h2>{artifacts.map(item => <p key={item.id}><a href={tools.download(item)} download>{item.name}</a> · {item.size} bytes</p>)}</section>}
    <section className="panel"><h2>歷史任務</h2>{history.length === 0 ? <p>還沒有任務。</p> : history.map(run => <button className="run-history" key={run.id} type="button" disabled={busy} onClick={() => show(run)}>{run.goal} · {names[run.status]}</button>)}</section>
  </main>;
}
