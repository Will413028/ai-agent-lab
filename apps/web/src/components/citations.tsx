import type { RetrievalResult } from "../lib/rag.generated";
import { statusLabels } from "../lib/knowledge";

export function Citations({ result }: { result: RetrievalResult }) {
  return <section className="citations" aria-label="引用來源">
    <div className="eyebrow">引用快照 · {result.citations.length} 個來源</div>
    <p className="small-note">檢索查詢：{result.retrieval_query}</p>
    {result.citations.length === 0 ? <p>知識庫未找到符合條件的資料。</p> : result.citations.map((item, index) => <details key={item.chunk_id}>
      <summary>[{index + 1}] {item.name} · {statusLabels[item.relationship_status]} · 區塊 {item.ordinal + 1} · {item.score.toFixed(3)}</summary>
      <p>{item.content}</p>
    </details>)}
  </section>;
}
