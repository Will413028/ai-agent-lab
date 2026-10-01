import Ajv from "ajv";
import addFormats from "ajv-formats";
import schema from "../../../../contracts/rag.schema.json";
import type { Document, RetrievalResult, TurnRetrieval } from "./rag.generated";

export type RelationshipStatus = "general" | "single" | "dating" | "married";
export const statusLabels: Record<RelationshipStatus, string> = { general: "通用", single: "單身", dating: "交往中", married: "已婚" };
const ajv = new Ajv();
addFormats(ajv);
ajv.addSchema(schema, "rag");
const document = ajv.compile<Document>({ $ref: "rag#/$defs/Document" });
const retrieval = ajv.compile<RetrievalResult>({ $ref: "rag#/$defs/RetrievalResult" });
const snapshot = ajv.compile<TurnRetrieval>({ $ref: "rag#/$defs/TurnRetrieval" });

async function request(path: string, options?: RequestInit) {
  let response: Response;
  try { response = await fetch(path, options); }
  catch { throw new Error("無法連接知識庫服務。"); }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail?.message === "string" ? body.detail.message : "知識庫操作失敗。");
  }
  return response.status === 204 ? null : response.json();
}
function checked<T>(value: unknown, validator: (data: unknown) => data is T): T {
  if (!validator(value)) throw new Error("知識庫回傳格式不正確。");
  return value;
}
function list<T>(value: unknown, validator: (data: unknown) => data is T): T[] {
  if (!Array.isArray(value)) throw new Error("知識庫列表格式不正確。");
  return value.map(item => checked(item, validator));
}
export const knowledge = {
  async list() { return list(await request("/api/documents"), document); },
  async upload(file: File, status: RelationshipStatus) {
    const data = new FormData(); data.set("file", file); data.set("relationship_status", status);
    return checked(await request("/api/documents", { method: "POST", body: data }), document);
  },
  async remove(id: string) { await request(`/api/documents/${encodeURIComponent(id)}`, { method: "DELETE" }); },
  async reindex() { return list(await request("/api/documents/reindex", { method: "POST" }), document); },
  async search(query: string, status: RelationshipStatus | null, threshold: number, topK: number) {
    return checked(await request("/api/retrieval", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, relationship_status: status, threshold, top_k: topK }) }), retrieval);
  },
  async snapshots(id: string) { return list(await request(`/api/conversations/${encodeURIComponent(id)}/retrievals`), snapshot); },
};
