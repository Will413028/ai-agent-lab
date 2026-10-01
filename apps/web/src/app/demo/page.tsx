"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { streamChat, type Scenario } from "../../lib/chat";

type Turn = { id: number; question: string; answer: string };

const scenarios: { value: Scenario; label: string }[] = [
  { value: "normal", label: "正常回覆" },
  { value: "slow", label: "慢速回覆（練習取消）" },
  { value: "rate_limit", label: "請求過於頻繁" },
  { value: "quota", label: "免費額度已用完" },
  { value: "timeout", label: "回覆逾時" },
  { value: "dependency_failure", label: "服務暫時無法使用" },
];

export default function Page() {
  const [message, setMessage] = useState("");
  const [scenario, setScenario] = useState<Scenario>("normal");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("準備就緒");
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const turnId = useRef(0);
  useEffect(() => () => controller.current?.abort(), []);

  async function send(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = message.trim();
    if (!question || busy) return;
    const id = ++turnId.current;
    const current = new AbortController();
    controller.current = current;
    setTurns((previous) => [...previous, { id, question, answer: "" }]);
    setMessage("");
    setError("");
    setBusy(true);
    setStatus("正在回覆");
    try {
      await streamChat({ message: question, scenario }, current.signal, (item) => {
        if (item.type === "delta") {
          setTurns((previous) => previous.map((turn) => turn.id === id ? { ...turn, answer: turn.answer + item.text } : turn));
        } else if (item.type === "done") {
          setStatus("回覆完成");
        } else {
          setError(item.message);
          setStatus("回覆失敗");
        }
      });
    } catch (failure) {
      if (current.signal.aborted) {
        setStatus("已取消");
      } else {
        setError(failure instanceof Error ? failure.message : "無法取得回覆，請稍後再試。");
        setStatus("回覆失敗");
      }
    } finally {
      controller.current = null;
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <Link className="wordmark" href="/">AI Agent <span>Lab</span></Link>
        <div className="nav-label">你的練習空間</div>
        <div className="nav-item active"><span>◌</span> 串流聊天 <span className="dot" /></div>
        <div className="sidebar-note"><span className="note-mark">01</span><p>先讓對話流動，<br />再讓 Agent 行動。</p></div>
        <div className="sidebar-foot">NEXT.JS + FASTAPI</div>
      </aside>
      <section className="workspace">
        <header className="topbar"><span>聊天練習</span><span className="offline"><i /> 離線示範</span></header>
        <div className="content">
          <div className="intro"><div className="eyebrow">BUILD · OBSERVE · UNDERSTAND</div><h1>從一句話開始。</h1><p>觀察回覆逐步出現，試試中斷，理解每一次對話。</p></div>
          <div className="demo-note">目前使用示範回覆，不會連接真實模型。對話只保留在這個頁面。</div>
          <div className="conversation" aria-label="對話紀錄" aria-busy={busy}>
            {turns.length === 0 ? <div className="empty"><div className="spark">✳</div><h2>今天想聊些什麼？</h2><p>可以談談一個想法，或從下面的例子開始。</p><button type="button" className="example" onClick={() => setMessage("我想安排一次輕鬆的約會，有什麼建議？")}>我想安排一次輕鬆的約會 ↗</button></div> : turns.map((turn) => <article className="turn" key={turn.id}><div className="question"><span>你</span><p>{turn.question}</p></div><div className="answer"><span className="avatar">✳</span><div><div className="speaker">AI Agent Lab</div><p data-testid="answer">{turn.answer || (busy && turn.id === turns.at(-1)?.id ? "正在準備回覆…" : "本次未收到文字回覆。")}</p></div></div></article>)}
          </div>
          {error && <div role="alert" className="error">{error}</div>}
          <form className="composer" onSubmit={send}>
            <label htmlFor="message" className="sr-only">你的訊息</label>
            <textarea id="message" value={message} onChange={(event) => setMessage(event.target.value)} maxLength={2000} rows={3} placeholder="寫下你的想法…" disabled={busy} />
            <div className="composer-bottom"><div><label htmlFor="scenario">測試情境</label><select id="scenario" value={scenario} onChange={(event) => setScenario(event.target.value as Scenario)} disabled={busy}>{scenarios.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>{busy ? <button type="button" className="send cancel" onClick={() => controller.current?.abort()}>停止回覆 ■</button> : <button type="submit" className="send" disabled={!message.trim()}>送出訊息 ↑</button>}</div>
          </form>
          <footer className="conversation-foot"><span role="status" aria-live="polite">{status}</span><span>小步實作，每一步都能驗證。</span></footer>
        </div>
      </section>
    </main>
  );
}
